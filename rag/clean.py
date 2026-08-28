"""Stage 2 — 清洗：raw HTML -> 干净 Markdown 文档（rag/clean/*.md）。

两类页面两种策略：
    newsletter  trafilatura 提取正文（页面干净，效果可靠），
                标题从 <title> / og:title 取
    episode     trafilatura 对这种 tab 结构页面会丢内容，改为手动解析：
                ① <h1> 标题  ② og:description 简介
                ③ 章节时间戳（所有 ?timestamp= 链接 "HH:MM:SS 章节名"）
                时间戳本身就是"第几分钟讲什么"的语义骨架，检索价值高。

输出文件带 YAML 风格 frontmatter（title/url/kind/date），供 chunk 阶段引用。
"""
import argparse
import html as htmllib
import json
import os
import re
import sys

import trafilatura

from .fetch import RAW_DIR, load_manifest

CLEAN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean")

# 站点模板/无信息量的样板文字，命中即丢弃该段
BOILERPLATE = [
    "transcript is currently under human review",
    "Become a Huberman Lab Premium member",
    "Zero-Cost Support",
    "Apple Reviews",
    "Neural Network Newsletter</li>",
]

TS_LINK = re.compile(
    r'<a[^>]*href="[^"]*\?timestamp=\d+"[^>]*>\s*(?:&#8203;|\u200b|\s)*'
    r'(\d{2}:\d{2}:\d{2})\s*(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")


def _meta(html, prop):
    m = re.search(
        rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"',
        html)
    if not m:
        m = re.search(
            rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{re.escape(prop)}"',
            html)
    return htmllib.unescape(m.group(1)).strip() if m else ""


def _h1(html):
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    return htmllib.unescape(TAG.sub("", m.group(1))).strip() if m else ""


def _article_date(html):
    m = re.search(r'<time[^>]*datetime="([\d-]{10})', html)
    if m:
        return m.group(1)
    m = re.search(
        r'(January|February|March|April|May|June|July|August|September|'
        r'October|November|December)\s+\d{1,2},\s+\d{4}', html)
    return m.group(0) if m else ""


def _drop_boilerplate(text):
    """丢弃命中样板文字的段落。"""
    kept = []
    for para in text.split("\n\n"):
        if not any(b.lower() in para.lower() for b in BOILERPLATE):
            kept.append(para)
    return "\n\n".join(kept)


def clean_newsletter(html, url):
    title = _meta(html, "og:title") or _h1(html) or "Untitled newsletter"
    text = trafilatura.extract(
        html, output_format="markdown", include_comments=False,
        include_tables=True, favor_recall=True) or ""
    date = _article_date(html)
    return title, date, _drop_boilerplate(text).strip()


def clean_episode(html, url):
    title = _meta(html, "og:title") or _h1(html) or "Untitled episode"
    date = _article_date(html)
    desc = _meta(html, "og:description")

    # 章节时间戳：[("00:03:06", "Sponsors: LMNT, ..."), ...]
    chapters = [(t, TAG.sub("", d).strip())
                for t, d in TS_LINK.findall(html)]
    chapters = [(t, d) for t, d in chapters if d][:60]

    parts = []
    if desc:
        parts.append(desc)
    if chapters:
        parts.append("## Timestamps\n" +
                     "\n".join(f"- [{t}] {d}" for t, d in chapters))
    # trafilatura 兜底：偶尔能抓到 show notes 正文，去重后并入
    body = trafilatura.extract(html, output_format="markdown",
                               include_comments=False) or ""
    for para in _drop_boilerplate(body).split("\n"):
        p = para.strip()
        if p and p not in "".join(parts) and len(p) > 80:
            parts.append(p)
    return title, date, "\n\n".join(parts).strip()


def clean(limit=None):
    os.makedirs(CLEAN_DIR, exist_ok=True)
    manifest = load_manifest()
    docs = []
    for key, info in sorted(manifest.items()):
        kind, slug = key.split("/", 1)
        raw = os.path.join(RAW_DIR, f"{kind}--{slug}.html")
        if not os.path.exists(raw):
            continue
        if limit is not None and len(docs) >= limit:
            break
        with open(raw, encoding="utf-8", errors="replace") as f:
            html = f.read()
        try:
            if kind == "newsletter":
                title, date, text = clean_newsletter(html, info["url"])
            else:
                title, date, text = clean_episode(html, info["url"])
        except Exception as e:
            print(f"  FAIL {key}: {e}", file=sys.stderr)
            continue
        if len(text) < 200:
            print(f"  skip {key}: extracted text too short ({len(text)} chars)")
            continue
        out = os.path.join(CLEAN_DIR, f"{kind}--{slug}.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write("---\n")
            f.write(f"url: {info['url']}\nkind: {kind}\ntitle: {json.dumps(title, ensure_ascii=False)}\n")
            if date:
                f.write(f"date: {date}\n")
            f.write("---\n\n")
            f.write(f"# {title}\n\n")
            f.write(text)
            f.write("\n")
        docs.append(key)
    print(f"clean done: {len(docs)} docs -> {CLEAN_DIR}")
    return docs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    clean(limit=args.limit)
