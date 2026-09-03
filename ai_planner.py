"""AI planner for the 'Now' page, using the HKU Claude API.

The module is deliberately layered so a future RAG stage can slot in
without touching the API client or the routes:

    build_context()  -> gather everything the planner needs (habits,
                        current time, bedtime, and an optional
                        `knowledge` payload — the RAG injection point)
    build_prompt()   -> turn a context dict into (system, user) prompts
    call_claude()    -> pure converse-API call with retries; knows
                        nothing about habits
    generate_plan()  -> thin orchestration entry point used by app.py

Adding RAG later only requires:
    1. retrieving documents and passing them via `knowledge=...`
       (a plain string, or a list of {"title": ..., "text": ...} dicts)
    2. nothing else — build_prompt already renders the knowledge section
       and the system prompt already tells the model to use it.

Used by the /api/now_plan endpoint in app.py.
"""
import os
import json
import time
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("HKU_CLAUDE_API_KEY")
ENDPOINT = os.environ.get("HKU_CLAUDE_ENDPOINT")
MODEL = os.environ.get("HKU_CLAUDE_MODEL", "claude-haiku-4.5")
URL = f"{ENDPOINT}/{MODEL}/converse" if ENDPOINT else None

SHANGHAI_TZ = timezone(timedelta(hours=8))

# Transport tuning. Total worst case stays under ~65s so the frontend's
# 75s abort cap always fires before the server gives up.
REQUEST_TIMEOUT = 30   # seconds per attempt
MAX_RETRIES = 1        # one retry after a transient failure
RETRY_DELAY = 1.5      # seconds before the retry
RETRYABLE_HTTP = {429, 500, 502, 503, 504}

SYSTEM_PROMPTS = {
    'en': (
        "You are a calm, decisive habit coach. Given the current time, the user's "
        "planned bedtime, and a list of habits not yet completed today, produce a "
        "concrete time-blocked plan for the remaining hours before sleep.\n\n"
        "Rules:\n"
        "1. The remaining time until bedtime is computed for you — trust it. If a "
        "bedtime in the late evening or small hours is given, it means the upcoming "
        "sleep, even if that crosses midnight.\n"
        "2. Consider each habit's type and a realistic duration (meditation ~15min, "
        "reading ~30min, workout ~45min, journal ~10min, etc.).\n"
        "3. Skip any habit that would harm sleep if done close to bedtime "
        "(e.g. intense workout within 90min of sleep). Say so explicitly with a reason.\n"
        "4. Order habits from most energizing to most calming, so the evening winds down.\n"
        "5. If bedtime has already passed or only minutes remain, say so and suggest "
        "doing one small habit or calling it a night.\n"
        "6. If a 'Reference knowledge' section is provided, use it to inform durations "
        "and advice; it overrides your defaults where they conflict.\n"
        "7. Consider the day of week: weekends can be looser; weekdays favor "
        "recovery-focused wind-downs.\n"
        "8. Output as clean Markdown: a short opening line, then the time blocks, "
        "then a 'Skip tonight' section if needed. NEVER use Markdown tables — "
        "columns squeeze the notes. Instead, each time block uses this format:\n"
        "**HH:MM–HH:MM | Habit name**\n"
        "- Duration: ~XX min\n"
        "- 1–3 bullet lines of practical guidance: why now (energy, light, "
        "wind-down order), what to focus on, and one concrete tip.\n"
        "Keep it actionable. No preamble, no closing remarks."
    ),
    'zh': (
        "你是一位沉稳、果断的习惯教练。根据当前时间、用户计划的就寝时间，以及今天尚未完成的习惯列表，"
        "为睡前剩余的时间制定具体的时间块计划。\n\n"
        "规则：\n"
        "1. 距就寝的剩余时间已经为你算好——直接采信。如果给出的就寝时间在深夜或凌晨，"
        "指的是即将到来的这次睡眠，即使跨越午夜也是如此。\n"
        "2. 考虑每个习惯的类型和合理时长（冥想约15分钟、阅读约30分钟、锻炼约45分钟、写日记约10分钟等）。\n"
        "3. 跳过任何在睡前做会影响睡眠的习惯（如睡前90分钟内的高强度运动），并明确说明原因。\n"
        "4. 从高能耗到低能耗排序，让晚上逐渐放松下来。\n"
        "5. 如果就寝时间已过或只剩几分钟，直接说明，并建议做一个小习惯或今晚就算了。\n"
        "6. 如果提供了「参考资料」部分，用它来校准时长和建议；与你的默认判断冲突时以资料为准。\n"
        "7. 考虑今天是星期几：周末可以更松弛，工作日更偏向恢复性的收尾。\n"
        "8. 用简洁的 Markdown 输出：一行简短开场，然后是时间块，如有需要再加一个「今晚跳过」部分。"
        "绝不使用 Markdown 表格——表格列宽会把说明文字压得太短。每个时间块用这个格式：\n"
        "**HH:MM–HH:MM｜习惯名**\n"
        "- 时长：约 XX 分钟\n"
        "- 1–3 行实用说明：为什么放在这个时段（精力、光照、放松顺序）、做什么、一条具体建议。\n"
        "内容要可执行。不要前言，不要结语。全程使用中文。"
    ),
}


# ---------- Context assembly (RAG injection point) ----------


def build_context(habits_not_completed, bedtime=None, lang='en', user_tz=None,
                  knowledge=None):
    """Assemble the full planning context as a plain dict.

    Args:
        habits_not_completed: list of dicts with 'name' and 'phase' keys.
        bedtime: str like "23:30" or None.
        lang: 'en' or 'zh' — controls output language.
        user_tz: tzinfo for computing current time (defaults to Shanghai).
        knowledge: optional RAG payload — a string, or a list of
                   {"title": ..., "text": ...} dicts. Passed through to
                   build_prompt untouched.

    Returns:
        dict with keys: now, tz, bedtime, habits, lang, knowledge,
        weekday, is_weekend.
    """
    tz = user_tz if user_tz is not None else SHANGHAI_TZ
    now = datetime.now(tz)
    # 周几感知：周末计划更松弛，工作日倾向恢复
    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
                'Saturday', 'Sunday']
    weekday = weekdays[now.weekday()]
    is_weekend = now.weekday() >= 5
    return {
        "now": now,
        "tz": tz,
        "bedtime": bedtime,
        "habits": list(habits_not_completed or []),
        "lang": lang if lang in SYSTEM_PROMPTS else 'en',
        "knowledge": knowledge,
        "weekday": weekday,
        "is_weekend": is_weekend,
    }


def _minutes_until_bedtime(now, bedtime):
    """Minutes from `now` until the next occurrence of `bedtime`.

    Handles the midnight crossing: at 22:00 with bedtime 01:00 the
    answer is 180 minutes (tonight's small hours), not 23 hours.
    """
    bh, bm = (int(part) for part in bedtime.split(":"))
    target = now.replace(hour=bh, minute=bm, second=0, microsecond=0)
    diff = (target - now).total_seconds() / 60
    if diff < 0:
        diff += 24 * 60
    return int(diff)


def _format_minutes(mins):
    if mins < 60:
        return f"{mins} minutes"
    hours, rem = divmod(mins, 60)
    return f"{hours}h {rem}m" if rem else f"{hours}h"


def _bedtime_line(ctx):
    """One-line bedtime summary with the remaining-time math done server-side.

    Doing this here (instead of trusting the model) removes the AM/PM and
    midnight-crossing ambiguity that a raw 'HH:MM' string carries.
    """
    bedtime = (ctx["bedtime"] or "").strip()
    if not bedtime:
        return "Planned bedtime: not specified (assume 23:00)"
    try:
        mins = _minutes_until_bedtime(ctx["now"], bedtime)
    except ValueError:
        return "Planned bedtime: not specified (assume 23:00)"
    if mins >= 12 * 60:
        # Bedtime is >12h away — either it already passed today or the
        # user is planning far ahead. Either way it is not "soon".
        return (
            f"Planned bedtime: {bedtime} (about {_format_minutes(mins)} from now — "
            f"this time has already passed today, so treat the bedtime as vague; "
            f"plan only for the next few hours)"
        )
    return f"Planned bedtime: {bedtime} (in about {_format_minutes(mins)})"


def _knowledge_section(knowledge):
    """Render the RAG payload as a prompt section. Returns '' if empty."""
    if not knowledge:
        return ""
    if isinstance(knowledge, str):
        return f"Reference knowledge:\n{knowledge.strip()}"
    parts = []
    for i, item in enumerate(knowledge, 1):
        title = (item.get("title") or f"Source {i}").strip()
        text = (item.get("text") or "").strip()
        if text:
            parts.append(f"[{i}] {title}\n{text}")
    if not parts:
        return ""
    return "Reference knowledge:\n" + "\n\n".join(parts)


def build_prompt(ctx):
    """Turn a context dict into (system_prompt, user_prompt).

    Kept section-based so new context fields (e.g. more RAG data)
    become one more appended section — never a rewrite.
    """
    now = ctx["now"]
    habit_list = "\n".join(
        f"{i + 1}. {h['name']} ({h['phase']})"
        for i, h in enumerate(ctx["habits"])
    )
    sections = [
        f"Current time: {now.strftime('%H:%M')} ({ctx['tz']})",
        _bedtime_line(ctx),
    ]
    # 周几/周末感知：影响计划基调
    if ctx.get("weekday"):
        weekend_note = ("weekend" if ctx.get("is_weekend") else "a weekday")
        sections.append(f"Day: {ctx['weekday']} ({weekend_note})")
    sections += [
        "",
        f"Habits not completed today:\n{habit_list}",
    ]
    knowledge_block = _knowledge_section(ctx.get("knowledge"))
    if knowledge_block:
        sections += ["", knowledge_block]
    sections += ["", "Plan the remaining time before sleep."]

    system = SYSTEM_PROMPTS.get(ctx["lang"], SYSTEM_PROMPTS['en'])
    return system, "\n".join(sections)


# ---------- API client (pure transport) ----------

def _err(message, error_type):
    return {
        "text": None,
        "latency_ms": None,
        "usage": {},
        "error": message,
        "error_type": error_type,
    }


def _extract_text(data):
    """Pull text out of a converse-style response.

    Tolerates mixed content blocks (text + tool_use + ...) instead of
    assuming content[0] is always a text block.
    """
    try:
        blocks = data["output"]["message"]["content"]
        parts = [b["text"] for b in blocks if isinstance(b, dict) and b.get("text")]
        return "\n".join(parts).strip() or None
    except (KeyError, TypeError, IndexError, AttributeError):
        return None


def call_claude(system_prompt, user_prompt, max_tokens=800, temperature=0.6):
    """Call the Claude converse API. Pure transport — no habit logic.

    Retries once on transient failures (429/5xx, network errors).

    Returns:
        dict: text (str|None), latency_ms (int|None), usage (dict),
        error (str|None), error_type ('config'|'api'|None).
    """
    if not API_KEY or not ENDPOINT:
        return _err(
            "AI service is not configured. Set HKU_CLAUDE_API_KEY and "
            "HKU_CLAUDE_ENDPOINT in .env.",
            "config",
        )

    body = {
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": [{"text": system_prompt}],
    }

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(
            URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "api-key": API_KEY,
            },
            method="POST",
        )
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latency_ms = int((time.time() - start) * 1000)
            text = _extract_text(data)
            if not text:
                return _err("AI service returned an empty response.", "api")
            logger.info(
                "claude call ok: %dms usage=%s", latency_ms, data.get("usage", {})
            )
            return {
                "text": text,
                "latency_ms": latency_ms,
                "usage": data.get("usage", {}),
                "error": None,
                "error_type": None,
            }
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                err_body = ""
            last_error = f"HTTP {e.code}: {err_body}"
            retryable = e.code in RETRYABLE_HTTP
        except Exception as e:
            # URLError, socket.timeout, ConnectionError, JSON decode ...
            last_error = f"{type(e).__name__}: {e}"
            retryable = True

        if retryable and attempt < MAX_RETRIES:
            logger.warning("claude call failed (%s), retrying", last_error)
            time.sleep(RETRY_DELAY)
            continue
        break

    logger.error("claude call failed permanently: %s", last_error)
    return _err(f"AI request failed ({last_error})", "api")


# ---------- Entry point ----------

def generate_plan(habits_not_completed, bedtime=None, lang='en', user_tz=None,
                  knowledge=None):
    """Generate an evening plan. Backward-compatible orchestration entry.

    Args:
        habits_not_completed: list of dicts with 'name' and 'phase' keys.
        bedtime: str like "23:30" or None.
        lang: 'en' or 'zh' — controls output language.
        user_tz: tzinfo for computing current time (defaults to Shanghai).
        knowledge: optional RAG payload — a string, or a list of
                   {"title": ..., "text": ...} dicts.

    Returns:
        dict: plan (str|None), latency_ms (int|None), usage (dict),
        error (str|None), error_type ('config'|'api'|'input'|None).
    """
    if not habits_not_completed:
        return _err("No habits left to plan — today is complete.", "input")

    ctx = build_context(
        habits_not_completed, bedtime=bedtime, lang=lang,
        user_tz=user_tz, knowledge=knowledge,
    )
    system_prompt, user_prompt = build_prompt(ctx)
    result = call_claude(system_prompt, user_prompt)
    return {
        "plan": result["text"],
        "latency_ms": result["latency_ms"],
        "usage": result["usage"],
        "error": result["error"],
        "error_type": result["error_type"],
    }
