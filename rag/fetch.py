"""Stage 1 — 采集：从 hubermanlab.com sitemap 拉取语料原始 HTML，
并支持把本地知识库文档（knowledge_base/）纳入语料。

语料范围（免费内容）：
    /newsletter/<slug>   Neural Network newsletter（核心语料，protocol 密度最高）
    /episode/<slug>      播客页（免费部分：标题 + 简介 + 章节时间戳；
                         完整 transcript 是 Premium 付费内容，抓不到）
    白名单专题页         /nsdr /daily-blueprint 等 protocol 页
    本地文档             knowledge_base/ 下的中文总结等
                         （fetch --local 转成 clean/ 下的 .md，跳过抓取）

特性：
    - sitemap 驱动，无需爬列表页
    - 断点续抓：已存在且非空的文件直接跳过
    - 限速：每请求间隔 FETCH_DELAY 秒，对站点友好
    - manifest.json 记录每次抓取（url/kind/slug/时间/字节数）

用法（通常由 build.py 调用）：
    python -m rag.fetch [--limit N] [--refresh] [--local]
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.request

BASE = "https://www.hubermanlab.com"
SITEMAP = f"{BASE}/sitemap.xml"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
MANIFEST = os.path.join(RAW_DIR, "manifest.json")
FETCH_DELAY = 2.0   # 秒，两个请求之间
TIMEOUT = 30

# 本地知识库目录（项目根下）；其中的 .md 直接并入语料
LOCAL_KB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_base")

# 免费专题页白名单（不含列表页/导航页）
EXTRA_PAGES = {
    "/nsdr": ("nsdr", "NSDR Protocols"),
    "/daily-blueprint": ("protocol", "Daily Blueprint"),
}


def _http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_sitemap(xml_text):
    """sitemap.xml -> [(url, kind, slug)]，只保留目标语料。"""
    out = []
    for loc in re.findall(r"<loc>(.*?)</loc>", xml_text):
        path = loc.replace(BASE, "").rstrip("/")
        if path.startswith("/newsletter/") and len(path) > len("/newsletter/"):
            out.append((loc, "newsletter", path.split("/")[-1]))
        elif path.startswith("/episode/") and len(path) > len("/episode/"):
            out.append((loc, "episode", path.split("/")[-1]))
        elif path in EXTRA_PAGES:
            out.append((loc, *EXTRA_PAGES[path]))
    return out


def load_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(m):
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1, sort_keys=True)


def raw_path(kind, slug):
    return os.path.join(RAW_DIR, f"{kind}--{slug}.html")


def ingest_local():
    """把 knowledge_base/ 的 .md 复制到 clean/（补 frontmatter），直接进入 chunk 阶段。

    本地文档已是 Markdown，无需抓取/清洗；写入 frontmatter（title/kind=local）
    让 chunk 阶段能登记标题，检索结果的 source 列表才可读。返回复制数。
    """
    from .clean import CLEAN_DIR
    if not os.path.isdir(LOCAL_KB_DIR):
        print(f"no local knowledge base at {LOCAL_KB_DIR}")
        return 0
    os.makedirs(CLEAN_DIR, exist_ok=True)
    count = 0
    for root, _, files in os.walk(LOCAL_KB_DIR):
        if "README" in root:
            continue
        for fname in files:
            if not fname.endswith(".md") or fname.upper().startswith("README"):
                continue
            src = os.path.join(root, fname)
            sub = os.path.relpath(root, LOCAL_KB_DIR)
            slug = (f"local--{sub}--{fname[:-3]}" if sub != "."
                    else f"local--{fname[:-3]}")
            dst = os.path.join(CLEAN_DIR, f"{slug}.md")
            if not os.path.exists(dst):
                with open(src, encoding="utf-8") as f:
                    body = f.read()
                title = fname[:-3]  # 文件名即标题
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(f'---\nkind: "local"\ntitle: "{title}"\n---\n\n{body}')
                count += 1
                print(f"  local doc: {slug}")
    print(f"ingest_local: {count} docs copied to clean/")
    return count


def fetch(limit=None, refresh=False, local=False):
    """抓取全部目标语料。返回 (新抓数, 跳过数, 失败数)。"""
    if local:
        ingest_local()
        return 0, 0, 0
    targets = parse_sitemap(_http_get(SITEMAP))
    print(f"sitemap: {len(targets)} target pages "
          f"({sum(1 for t in targets if t[1]=='newsletter')} newsletters, "
          f"{sum(1 for t in targets if t[1]=='episode')} episodes, "
          f"{sum(1 for t in targets if t[1] in ('nsdr','protocol'))} protocol pages)")

    manifest = load_manifest()
    fetched = skipped = failed = 0

    for url, kind, slug in targets:
        path = raw_path(kind, slug)
        if not refresh and os.path.exists(path) and os.path.getsize(path) > 5000:
            skipped += 1
            continue
        if limit is not None and fetched >= limit:
            break
        try:
            html = _http_get(url)
            os.makedirs(RAW_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            manifest[f"{kind}/{slug}"] = {
                "url": url, "bytes": len(html),
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            fetched += 1
            print(f"  [{fetched}] {kind}/{slug} ({len(html)//1024} KB)")
        except Exception as e:
            failed += 1
            print(f"  FAIL {kind}/{slug}: {e}", file=sys.stderr)
        time.sleep(FETCH_DELAY)

    save_manifest(manifest)
    print(f"fetch done: {fetched} new, {skipped} skipped, {failed} failed")
    return fetched, skipped, failed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="只抓前 N 个（测试用）")
    ap.add_argument("--refresh", action="store_true", help="已抓过的也重新抓")
    ap.add_argument("--local", action="store_true",
                    help="只导入本地 knowledge_base/ 文档，不抓网络")
    args = ap.parse_args()
    fetch(limit=args.limit, refresh=args.refresh, local=args.local)
