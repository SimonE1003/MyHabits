"""Stage 3 — 分块：clean Markdown -> 结构感知的 chunks。

规则：
    - 优先按 ## 标题切 section（保住段落语义完整性）
    - 单 section 超过 MAX_CHARS 再按空行段落二次切
    - 不足 MIN_CHARS 的小 section 向后合并
    - episode 的 Timestamps 列表按每块 ~20 个章节切

产出写入 kb.db 的 chunks 表（尚无 embedding / tags，由后续阶段填充），
这样 tag / embed 阶段都能断点续跑。
"""
import argparse
import json
import os
import re
import sqlite3

from .clean import CLEAN_DIR

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb.db")

# 英文 4 chars ≈ 1 token，300–500 token ≈ 1200–2000 chars
MIN_CHARS = 600
MAX_CHARS = 2200
TS_PER_CHUNK = 20   # episode 时间戳列表：每块 20 章


def init_kb():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY,
            slug TEXT UNIQUE NOT NULL,
            url TEXT, title TEXT, kind TEXT, date TEXT
        );
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            doc_id INTEGER NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
            heading TEXT,
            seq INTEGER,
            text TEXT NOT NULL,
            time_windows TEXT,      -- JSON array，tag 阶段填
            activities TEXT,        -- JSON array，tag 阶段填
            direction TEXT,         -- do | avoid | neutral，tag 阶段填
            tag_source TEXT,        -- rule | claude | null
            embedding BLOB          -- float32 bytes，embed 阶段填
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
    """)
    db.commit()
    return db


def parse_frontmatter(md):
    m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    meta = {"url": "", "kind": "", "title": "", "date": ""}
    if m:
        for line in m.group(1).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = json.loads(v) if v.strip().startswith('"') else v.strip()
        md = md[m.end():]
    return meta, md


def split_sections(md):
    """markdown -> [(heading, text)]，顶层 # 视为文档标题丢弃。"""
    sections, heading, buf = [], None, []
    for line in md.split("\n"):
        if line.startswith("## "):
            if buf:
                sections.append((heading, "\n".join(buf).strip()))
            heading, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf).strip()))
    return [(h, t) for h, t in sections if t]


def split_long(heading, text):
    """超长 section 按空行段落二次切。"""
    if len(text) <= MAX_CHARS:
        return [(heading, text)]
    paras, out, cur = text.split("\n\n"), [], ""
    for p in paras:
        if cur and len(cur) + len(p) > MAX_CHARS:
            out.append((heading, cur.strip()))
            cur = ""
        cur += p + "\n\n"
    if cur.strip():
        out.append((heading, cur.strip()))
    return out


def chunk_doc(meta, md):
    """一个文档 -> chunk 文本列表（带 heading）。"""
    sections = split_sections(md)
    # 小 section 向后合并
    merged, i = [], 0
    while i < len(sections):
        h, t = sections[i]
        while len(t) < MIN_CHARS and i + 1 < len(sections):
            i += 1
            h2, t2 = sections[i]
            t = t + "\n\n" + (f"## {h2}\n\n{t2}" if h2 else t2)
        merged.append((h, t))
        i += 1

    chunks = []
    for h, t in merged:
        if h and "timestamp" in h.lower():
            # 时间戳列表：每 TS_PER_CHUNK 章一块
            lines = t.split("\n")
            head = [ln for ln in lines if not ln.strip().startswith("- [")]
            items = [ln for ln in lines if ln.strip().startswith("- [")]
            for j in range(0, len(items), TS_PER_CHUNK):
                part = items[j:j + TS_PER_CHUNK]
                chunks.append((h, "\n".join(head + part)))
        else:
            chunks.extend(split_long(h, t))
    return [(h or "", t) for h, t in chunks if len(t) >= MIN_CHARS // 2]


def chunk(limit=None):
    db = init_kb()
    total_docs = total_chunks = 0
    for fname in sorted(os.listdir(CLEAN_DIR)):
        if not fname.endswith(".md"):
            continue
        if limit is not None and total_docs >= limit:
            break
        slug = fname[:-3]
        with open(os.path.join(CLEAN_DIR, fname), encoding="utf-8") as f:
            meta, md = parse_frontmatter(f.read())
        db.execute(
            """INSERT INTO docs (slug, url, title, kind, date)
               VALUES (?,?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET
                 url=excluded.url, title=excluded.title,
                 kind=excluded.kind, date=excluded.date""",
            (slug, meta.get("url", ""), meta.get("title", ""),
             meta.get("kind", ""), meta.get("date", "")))
        doc_id = db.execute(
            "SELECT id FROM docs WHERE slug=?", (slug,)).fetchone()[0]
        db.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
        for seq, (heading, text) in enumerate(chunk_doc(meta, md)):
            db.execute(
                """INSERT INTO chunks (doc_id, heading, seq, text)
                   VALUES (?,?,?,?)""", (doc_id, heading, seq, text))
            total_chunks += 1
        total_docs += 1
    db.commit()
    n = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    db.close()
    print(f"chunk done: {total_docs} docs, {total_chunks} chunks this run, {n} total in kb.db")
    return total_chunks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    chunk(limit=args.limit)
