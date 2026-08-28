"""Stage 5 — 向量化：chunks -> 本地嵌入向量，写回 kb.db。

模型（fastembed，完全本地免费）：
    默认 jinaai/jina-embeddings-v2-base-zh —— 官方说明 supports mixed
    Chinese-English，正好匹配"中文习惯名 ↔ 英文语料"的检索需求，
    768 维。可用 RAG_EMBED_MODEL 环境变量替换（如
    intfloat/multilingual-e5-large，更强但 ~2GB）。

e5 系列模型要求前缀："query: " / "passage: "，本模块自动处理；
jina 系列不加前缀。断点续跑：只嵌入 embedding IS NULL 的 chunk。
"""
import argparse
import os
import sqlite3

from .chunk import init_kb

DEFAULT_MODEL = "jinaai/jina-embeddings-v2-base-zh"

MODEL = os.environ.get("RAG_EMBED_MODEL", DEFAULT_MODEL)
# e5 家族必须加 query:/passage: 前缀；jina / bge 系列不加
_NEEDS_PREFIX = "e5" in MODEL


def passage_text(text):
    return f"passage: {text}" if _NEEDS_PREFIX else text


def query_text(text):
    return f"query: {text}" if _NEEDS_PREFIX else text


def embed(batch_size=32):
    import numpy as np
    from fastembed import TextEmbedding

    db = init_kb()
    rows = db.execute(
        "SELECT id, text FROM chunks WHERE embedding IS NULL").fetchall()
    if not rows:
        print("embed: nothing to do")
        db.close()
        return 0
    print(f"embedding {len(rows)} chunks with {MODEL} "
          f"(first run downloads the model)...")

    model = TextEmbedding(model_name=MODEL)
    texts = [passage_text(t) for _, t in rows]
    done = 0
    for i in range(0, len(texts), batch_size):
        batch_ids = [cid for cid, _ in rows[i:i + batch_size]]
        vecs = list(model.embed(texts[i:i + batch_size]))
        for cid, vec in zip(batch_ids, vecs):
            arr = np.asarray(vec, dtype=np.float32)
            db.execute(
                "UPDATE chunks SET embedding=? WHERE id=?",
                (arr.tobytes(), cid))
        done += len(batch_ids)
        print(f"  {done}/{len(rows)}")
    db.commit()
    db.close()
    print(f"embed done: {done} chunks vectorized")
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    embed()
