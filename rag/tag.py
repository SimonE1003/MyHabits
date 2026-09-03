"""Stage 4 — 打标：给每个 chunk 标 time_windows / activities / direction。

两级策略（省 quota）：
    1. 规则打标（免费）：关键词正则匹配。Huberman 文本时间词密度极高，
       大部分 chunk 能被打中至少一个标签。
    2. Claude 兜底（花 quota）：规则完全打不中的 chunk 才批量送
       claude-haiku，一次调用塞 BATCH_SIZE 条，严格 JSON 输出。

quota 防护（HKU 学生 API：3 次/分钟、300 次/天）：
    - 每次调用间隔 CALL_INTERVAL 秒（默认 21s，稳定低于 3/min）
    - 当日调用数记在 rag/tag_state.json，超过 DAILY_LIMIT 自动停止，
      留余量给 Now 页面日常使用
    - 断点续跑：已有 tag_source 的 chunk 不再处理

用法：
    python -m rag.tag [--only-rule] [--dry-run]
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time

from .chunk import init_kb
from ai_planner import call_claude  # 复用已带重试的 API client（项目根在 sys.path）

# ---------------- 标签词表 ----------------

TIME_WINDOWS = [
    "post_wake",   # 醒后 0–90 min（光照/咖啡因窗口）
    "morning",     # 上午
    "midday",      # 正午
    "afternoon",   # 下午
    "evening",     # 晚间
    "pre_sleep",   # 睡前 0–2h
    "night",       # 深夜 / 应当入睡
    "anytime",
]

ACTIVITIES = [
    "meditation", "breathing", "exercise", "resistance_training", "cardio",
    "reading", "journaling", "sleep_hygiene", "light_exposure", "caffeine",
    "nutrition", "fasting", "cold_exposure", "heat_exposure", "nsdr",
    "focus_work", "social", "screens", "hydration", "supplements",
    "walking", "goal_setting", "gratitude", "learning", "stress",
    "motivation", "habit_formation", "planning",
]

DIRECTIONS = ["do", "avoid", "neutral"]

# ---------------- 规则词表（小写，词干匹配） ----------------

TIME_RULES = [
    ("post_wake", r"upon wak\w+|first thing in the morn\w+|waking up|after (you )?wak\w+|"
                  r"shortly after wak\w+|zero to 90|0-90 minutes|first 90 minutes|醒来后|起床后|刚醒"),
    ("morning",   r"\bmorning\b|\bmornings\b|early part of the day|before noon|early day|"
                  r"早上|早晨|清晨|上午|早间"),
    ("midday",    r"\bmidday\b|noon\b|middle of the day|正午|中午|午间"),
    ("afternoon", r"\bafternoon\b|after lunch|下午|午后"),
    ("evening",   r"\bevening\b|\bevenings\b|end of the day|dinnertime|傍晚|晚上|晚间|黄昏"),
    ("pre_sleep", r"before (bed|sleep|bedtime)|prior to (bed|sleep)|leading up to (bed|sleep)|"
                  r"close to bedtime|in preparation for sleep|wind(ing)? down|睡前|就寝前|入睡前|"
                  r"上床前"),
    ("night",     r"\bnight\b|late night|middle of the night|2 a\.?m\.|3 a\.?m\.|4 a\.?m\.|"
                  r"深夜|夜间|凌晨|半夜"),
]

# 无时序信息的 chunk 兜底标签：检索查询的窗口列表恒含 "anytime"，
# 打上 anytime 后该 chunk 在任何时段都可被余弦排序召回（否则永远不可见）
ANYTIME = ["anytime"]

ACTIVITY_RULES = [
    ("meditation",       r"meditat\w+|mindful\w*"),
    ("breathing",        r"breath\w+|physiological sigh\w*|inhale\w*|exhale\w*"),
    ("exercise",         r"\bexercis\w+|\bworkout\w*|physical (activity|training)"),
    ("resistance_training", r"resistance training|weight (training|lifting)|strength train\w+|hypertrophy"),
    ("cardio",           r"\bcardio\b|aerobic\w*|high[- ]intensity|sprint\w*|zone 2"),
    ("reading",          r"\bread(ing|er)?\b|book\w*"),
    ("journaling",       r"journal\w+|writing (about|down|protocol)|expressive writing"),
    ("sleep_hygiene",    r"sleep (quality|hygiene|schedule|environment|routine|depriv\w+)|deepens? sleep|rem sleep|non-?sleep deep rest is not|sleeping"),
    ("light_exposure",   r"light (viewing|exposure|exposure|box)|bright light|sunlight|sunshine|morning light|dim the lights"),
    ("caffeine",         r"caffeine|coffee|espresso|tea\b"),
    ("nutrition",        r"\bmeals?\b|\beat(ing)?\b|food\b|protein\b|carbohydrate\w*|fat intake"),
    ("fasting",          r"fast\w*|feeding window"),
    ("cold_exposure",    r"cold (exposure|shower|plunge|water)|deliberate cold|ice bath"),
    ("heat_exposure",    r"sauna\b|heat exposure|hot (bath|tub)|hyperthermic"),
    ("nsdr",             r"nsdr\b|non-?sleep deep rest|yoga nidra"),
    ("focus_work",       r"focus\b|focused (work|state)|deep work|concentration|attention\b|90-?minute (blocks?|cycles?|ultradian)"),
    ("social",           r"social (bond\w*|connection\w*|interact\w+)|friendship\w*|loneliness"),
    ("screens",          r"screen\w*|phone\b|device\b|television\b|\btv\b"),
    ("hydration",        r"hydrat\w*|water intake|electrolyte\w*|\bfluids\b"),
    ("supplements",      r"supplement\w*|creatine|magnesium|theanine|omega-?3|vitamin [a-d]\b|Ashwagandha|apigenin"),
    ("walking",          r"\bwalk\w*"),
    ("goal_setting",     r"goal\w*|objectives?\b"),
    ("gratitude",        r"gratitude\w*|thankful\w*"),
    ("learning",         r"learn\w+|neuroplasticity|stud(y|ying)|memory\b"),
    ("stress",           r"stress\w*|anxiety|cortisol\b|relax\w*"),
    ("motivation",       r"motivation\w*|dopamine\b|discipline\b"),
    ("habit_formation",  r"habit\w*"),
    ("planning",         r"plan\w*|schedule\w*|time-?block\w*|to-?do list"),
]

# 避免 "eat" 之类过宽词的误报白名单——命中行里同时出现这些才算
CTX_REQUIRED = {
    "reading": r"read|book",   # 防止 "already read the room" 之类（保守，可忽略）
}


def rule_tag(text):
    """规则打标。返回 (time_windows, activities) 或 (None, None) 表示打不中。"""
    low = text.lower()
    tw = [tag for tag, pat in TIME_RULES if re.search(pat, low)]
    acts = [tag for tag, pat in ACTIVITY_RULES if re.search(pat, low)]
    return tw, acts


# ---------------- Claude 兜底 ----------------

BATCH_SIZE = 10          # 每次调用的 chunk 数
CALL_INTERVAL = 21.0     # 秒；≈2.8 次/分钟，低于 3/min 限速
DAILY_LIMIT = 250        # 每日熔断线（总 quota 300，留 50 给 Now 页面）

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag_state.json")

TAG_SYSTEM = (
    "You are a precise text annotation engine. For each numbered text chunk "
    "from Huberman Lab content, assign labels about WHEN an activity should "
    "happen and WHAT it involves. Output ONLY a JSON array, one object per "
    "chunk, no markdown, no commentary.\n\n"
    "Allowed time_windows values: " + ", ".join(TIME_WINDOWS) + "\n"
    "Allowed activities values: " + ", ".join(ACTIVITIES) + "\n"
    "Allowed direction values: do (recommended at this time), avoid (harmful "
    "at this time), neutral (informational only).\n\n"
    "Rules:\n"
    "- time_windows: when in the day this advice applies. Empty list only if "
    "the chunk has no timing information at all.\n"
    "- activities: what the chunk is actually about, not every word mentioned.\n"
    "- direction: 'do' if the chunk recommends the activity in that window, "
    "'avoid' if it warns against it, 'neutral' otherwise.\n"
    "- Be conservative: prefer fewer, correct labels over many loose ones."
)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"date": "", "claude_calls": 0}


def save_state(s):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)


def _today():
    return time.strftime("%Y-%m-%d")


def claude_tag_batch(batch):
    """batch: [(id, text)] -> {id: (time_windows, activities, direction)}。"""
    today = _today()
    state = load_state()
    if state.get("date") != today:
        state = {"date": today, "claude_calls": 0}
    if state["claude_calls"] >= DAILY_LIMIT:
        print(f"daily limit reached ({DAILY_LIMIT} calls); stopping for today")
        return {}

    lines = []
    for cid, text in batch:
        snippet = " ".join(text.split())[:1500]
        lines.append(f"### chunk {cid}\n{snippet}")
    user_prompt = (
        "Label each chunk. Respond with a JSON array like:\n"
        '[{"id": 123, "time_windows": ["evening"], '
        '"activities": ["journaling"], "direction": "do"}]\n\n'
        + "\n\n".join(lines)
    )

    result = call_claude(TAG_SYSTEM, user_prompt, max_tokens=2000, temperature=0.0)
    state["claude_calls"] += 1
    save_state(state)

    if result["error"]:
        print(f"  claude call failed: {result['error']}", file=sys.stderr)
        return {}

    # 剥掉可能裹挟的 markdown 代码栅栏再解析
    raw = re.sub(r"^```(json)?|```$", "", result["text"].strip(), flags=re.M).strip()
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        print(f"  claude returned non-JSON: {raw[:120]!r}", file=sys.stderr)
        return {}
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        print(f"  claude JSON parse error: {e}", file=sys.stderr)
        return {}

    out = {}
    for it in items:
        try:
            cid = int(it["id"])
            tw = [w for w in it.get("time_windows", []) if w in TIME_WINDOWS]
            acts = [a for a in it.get("activities", []) if a in ACTIVITIES]
            d = it.get("direction", "neutral")
            d = d if d in DIRECTIONS else "neutral"
            out[cid] = (tw, acts, d)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def tag(only_rule=False, dry_run=False):
    db = init_kb()
    rows = db.execute(
        "SELECT id, text FROM chunks WHERE tag_source IS NULL").fetchall()
    print(f"{len(rows)} untagged chunks")

    # ---- Pass 1: 规则 ----
    claude_pending = []
    rule_done = 0
    for cid, text in rows:
        tw, acts = rule_tag(text)
        if tw or acts:
            if not dry_run:
                db.execute(
                    "UPDATE chunks SET time_windows=?, activities=?, "
                    "tag_source='rule' WHERE id=?",
                    (json.dumps(tw or ANYTIME), json.dumps(acts), cid))
            rule_done += 1
        else:
            claude_pending.append((cid, text))
    db.commit()
    print(f"rule pass: {rule_done} tagged, {len(claude_pending)} need claude")

    if dry_run or not claude_pending:
        db.close()
        return

    if only_rule:
        db.close()
        return

    # ---- Pass 2: Claude 兜底（限速 + 配额 + 断点） ----
    claude_done = 0
    for i in range(0, len(claude_pending), BATCH_SIZE):
        batch = claude_pending[i:i + BATCH_SIZE]
        print(f"claude batch {i // BATCH_SIZE + 1}/"
              f"{(len(claude_pending) + BATCH_SIZE - 1) // BATCH_SIZE} "
              f"(ids {batch[0][0]}..{batch[-1][0]})")
        tagged = claude_tag_batch(batch)
        for cid, _ in batch:
            if cid in tagged:
                tw, acts, d = tagged[cid]
                db.execute(
                    "UPDATE chunks SET time_windows=?, activities=?, "
                    "direction=?, tag_source='claude' WHERE id=?",
                    (json.dumps(tw or ANYTIME), json.dumps(acts), d, cid))
                claude_done += 1
        db.commit()
        if i + BATCH_SIZE < len(claude_pending):
            time.sleep(CALL_INTERVAL)
    db.close()
    print(f"claude pass: {claude_done} tagged, "
          f"{len(claude_pending) - claude_done} left for next run")
    state = load_state()
    print(f"claude calls today: {state['claude_calls']}/{DAILY_LIMIT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-rule", action="store_true",
                    help="只跑规则打标，不调 Claude")
    ap.add_argument("--dry-run", action="store_true",
                    help="不写库，只统计")
    args = ap.parse_args()
    tag(only_rule=args.only_rule, dry_run=args.dry_run)
