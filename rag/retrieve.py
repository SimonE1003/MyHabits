"""Query-time retrieval for the Now-page planner.

契约（app.py /api/now_plan 调用）：
    retrieve_knowledge(habits, bedtime, lang, user_tz, top_k)
        -> [{"title": str, "text": str}, ...]  长度 0..top_k

两阶段检索（与离线流水线产出的 kb.db 对接）：
    ① 标签硬过滤：由当前时间 + 距就寝时长算出候选 time_windows，
       只保留带这些标签的 chunk（快、准）
    ② 向量精排：查询向量（习惯名 + 上下文，中英混合）与候选
       embedding 做余弦，取 top_k

降级路径（永不抛错）：
    - kb.db 不存在 / 无 embedding → 返回 []（普通计划）
    - 标签过滤后为空 → 退化为全库余弦
    - 查询 embedding 失败 → 返回 []

模块级缓存：SQLite 行与 fastembed 模型在进程内只加载一次
（Flask 开发服务器常驻，第二次请求起毫秒级返回）。
"""
import json
import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb.db")

_cache = {"loaded": False, "chunks": None, "model": None, "model_name": None}


# ---------- 时间窗计算 ----------

def _current_windows(now, bedtime):
    """当前时刻 → 候选 time_windows 标签列表（宽松匹配，宁多勿漏）。

    now: datetime（用户时区）；bedtime: "HH:MM" 或 None。
    """
    h, m = now.hour, now.minute
    windows = []
    if 5 <= h < 11:
        windows += ["post_wake", "morning"]
    elif 11 <= h < 14:
        windows += ["midday", "morning"]
    elif 14 <= h < 18:
        windows += ["afternoon"]
    elif 18 <= h < 22:
        windows += ["evening"]
    else:  # 22:00–05:00
        windows += ["night", "pre_sleep", "evening"]
    windows.append("anytime")

    # 距就寝 <2h 时加 pre_sleep（最关键的规划窗口）
    if bedtime:
        try:
            bh, bm = (int(p) for p in bedtime.split(":"))
            diff = (bh * 60 + bm) - (h * 60 + m)
            if diff < 0:
                diff += 24 * 60
            if 0 <= diff <= 120:
                if "pre_sleep" not in windows:
                    windows.append("pre_sleep")
        except ValueError:
            pass
    return windows


# ---------- kb 加载与检索 ----------

def kb_status():
    """轻量探测：(available, n_chunks)。available 需要有 embedding 才算。"""
    if not os.path.exists(KB_PATH):
        return False, None
    try:
        con = sqlite3.connect(f"file:{KB_PATH}?mode=ro", uri=True)
        n = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0]
        con.close()
        return n > 0, n
    except sqlite3.Error:
        return False, None


def _load_chunks():
    """把全部已向量化 chunk 读进内存（千级规模，一次性 <1MB）。

    kb.db 的 mtime 变化（如 rag.build 重建后）自动失效缓存，
    无需重启 Flask 进程。
    """
    try:
        mtime = os.path.getmtime(KB_PATH)
    except OSError:
        mtime = None
    if _cache["loaded"]:
        if mtime is None or mtime == _cache.get("mtime"):
            return _cache["chunks"]
        # kb.db 已更新，丢弃缓存重载
        _cache.update(loaded=False, chunks=None)
    if not os.path.exists(KB_PATH):
        _cache["loaded"] = True
        _cache["mtime"] = None
        _cache["chunks"] = []
        return []
    try:
        con = sqlite3.connect(f"file:{KB_PATH}?mode=ro", uri=True)
        rows = con.execute(
            """SELECT c.id, c.heading, c.text, c.time_windows, c.embedding,
                      d.title, d.kind
               FROM chunks c JOIN docs d ON d.id = c.doc_id
               WHERE c.embedding IS NOT NULL""").fetchall()
        con.close()
        import numpy as np
        chunks = []
        for cid, heading, text, tw_json, emb, title, kind in rows:
            vec = np.frombuffer(emb, dtype=np.float32)
            try:
                tw = set(json.loads(tw_json)) if tw_json else set()
            except (json.JSONDecodeError, TypeError):
                tw = set()
            chunks.append({
                "id": cid, "heading": heading or "", "text": text,
                "tw": tw, "vec": vec,
                "title": f"{title}" + (f" · {heading}" if heading else ""),
                "kind": kind,
            })
        _cache["loaded"] = True
        _cache["mtime"] = mtime
        _cache["chunks"] = chunks
    except sqlite3.Error as e:
        logger.warning("kb load failed: %s", e)
        _cache["loaded"] = True
        _cache["chunks"] = []
    return _cache["chunks"]


def _get_model():
    """惰性加载 fastembed 模型（进程内复用，首次约 1–2s）。"""
    if _cache["model"] is not None:
        return _cache["model"]
    try:
        from fastembed import TextEmbedding
        from .embed import MODEL, query_text  # 复用模型名与前缀逻辑
        _cache["model"] = TextEmbedding(model_name=MODEL)
        _cache["model_name"] = MODEL
        _cache["query_text"] = query_text
    except Exception as e:
        logger.warning("fastembed unavailable: %s", e)
        _cache["model"] = False
    return _cache["model"] or None


def retrieve_knowledge(habits, bedtime=None, lang="en", user_tz=None, top_k=3):
    """检索参考知识。habits: [{"name", "phase"}]。永不抛错。"""
    chunks = _load_chunks()
    if not chunks:
        return []

    model = _get_model()
    if model is None:
        return []

    now = datetime.now(user_tz) if user_tz is not None else datetime.now()
    windows = _current_windows(now, bedtime)

    # 查询文本：习惯名（中文亦可，双语模型）+ 按当前时间窗生成的语境，
    # 避免固定 "evening" 语句把早晨查询往晚间内容上带
    habit_names = " ".join(h["name"] for h in habits)
    ctx = {
        "post_wake": "morning wake-up routine after waking",
        "morning": "morning routine habits",
        "midday": "midday routine habits",
        "afternoon": "afternoon routine habits",
        "evening": "evening routine before sleep",
        "pre_sleep": "wind-down before bedtime sleep preparation",
        "night": "late night wind-down before sleep",
    }.get(windows[0], "daily routine planning")
    try:
        q = _cache["query_text"](f"{habit_names} {ctx}")
        qvec = next(iter(model.embed([q])))
    except Exception as e:
        logger.warning("query embed failed: %s", e)
        return []

    import numpy as np
    qvec = np.asarray(qvec, dtype=np.float32)
    qnorm = np.linalg.norm(qvec)
    if qnorm == 0:
        return []

    # ① 标签硬过滤 ② 余弦精排 ③ 同一文档最多 1 条（来源多样性）
    candidates = [c for c in chunks if c["tw"] & set(windows)] or chunks
    scored = []
    for c in candidates:
        denom = np.linalg.norm(c["vec"]) * qnorm
        if denom > 0:
            scored.append((float(np.dot(c["vec"], qvec) / denom), c))
    scored.sort(key=lambda x: x[0], reverse=True)

    picked, seen_docs = [], set()
    for score, c in scored:
        doc_key = c["title"].split(" · ")[0]
        if doc_key in seen_docs:
            continue
        seen_docs.add(doc_key)
        picked.append({"title": c["title"], "text": c["text"]})
        if len(picked) >= top_k:
            break
    return picked
