"""AI planner using HKU Claude API.

Generates a personalized evening plan based on:
- Habits not yet completed today
- Current time (auto-injected, Asia/Shanghai)
- User's planned bedtime (optional, from form input)

Used by the /api/now_plan endpoint in app.py.
"""
import os
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("HKU_CLAUDE_API_KEY")
ENDPOINT = os.environ.get("HKU_CLAUDE_ENDPOINT")
MODEL = os.environ.get("HKU_CLAUDE_MODEL", "claude-haiku-4.5")
URL = f"{ENDPOINT}/{MODEL}/converse" if ENDPOINT else None

SHANGHAI_TZ = timezone(timedelta(hours=8))

SYSTEM_PROMPTS = {
    'en': (
        "You are a calm, decisive habit coach. Given the current time, the user's "
        "planned bedtime, and a list of habits not yet completed today, produce a "
        "concrete time-blocked plan for the remaining hours before sleep.\n\n"
        "Rules:\n"
        "1. Consider each habit's type and a realistic duration (meditation ~15min, "
        "reading ~30min, workout ~45min, journal ~10min, etc.).\n"
        "2. Skip any habit that would harm sleep if done close to bedtime "
        "(e.g. intense workout within 90min of sleep). Say so explicitly with a reason.\n"
        "3. Order habits from most energizing to most calming, so the evening winds down.\n"
        "4. If bedtime has already passed or only minutes remain, say so and suggest "
        "doing one small habit or calling it a night.\n"
        "5. Output as clean Markdown: a short opening line, then a time-blocked schedule, "
        "then a 'Skip tonight' section if needed. Keep it concise and actionable. "
        "No preamble, no closing remarks."
    ),
    'zh': (
        "你是一位沉稳、果断的习惯教练。根据当前时间、用户计划的就寝时间，以及今天尚未完成的习惯列表，"
        "为睡前剩余的时间制定具体的时间块计划。\n\n"
        "规则：\n"
        "1. 考虑每个习惯的类型和合理时长（冥想约15分钟、阅读约30分钟、锻炼约45分钟、写日记约10分钟等）。\n"
        "2. 跳过任何在睡前做会影响睡眠的习惯（如睡前90分钟内的高强度运动），并明确说明原因。\n"
        "3. 从高能耗到低能耗排序，让晚上逐渐放松下来。\n"
        "4. 如果就寝时间已过或只剩几分钟，直接说明，并建议做一个小习惯或今晚就算了。\n"
        "5. 用简洁的 Markdown 输出：一行简短开场，然后是时间块计划，如有需要再加一个「今晚跳过」部分。"
        "不要前言，不要结语。全程使用中文。"
    ),
}


def generate_plan(habits_not_completed, bedtime=None, lang='en', user_tz=None):
    """Generate an evening plan using HKU Claude API.

    Args:
        habits_not_completed: list of dicts with 'name' and 'phase' keys.
        bedtime: str like "23:30" or None.
        lang: 'en' or 'zh' — controls output language.
        user_tz: a tzinfo (ZoneInfo or timezone) for computing current time.
                 Defaults to Shanghai time if not provided.

    Returns:
        dict with keys: plan (str|None), latency_ms (int|None),
        usage (dict), error (str|None).
    """
    if not API_KEY or not ENDPOINT:
        return {
            "plan": None,
            "error": "AI service is not configured. Set HKU_CLAUDE_API_KEY and HKU_CLAUDE_ENDPOINT in .env.",
            "latency_ms": None,
            "usage": {},
        }

    if not habits_not_completed:
        return {
            "plan": None,
            "error": "No habits left to plan — today is complete.",
            "latency_ms": None,
            "usage": {},
        }

    # Use the caller's timezone (per-user), falling back to Shanghai.
    tz = user_tz if user_tz is not None else SHANGHAI_TZ
    now_sh = datetime.now(tz)
    current_time = now_sh.strftime("%H:%M")

    habit_list = "\n".join(
        f"{i + 1}. {h['name']} ({h['phase']})"
        for i, h in enumerate(habits_not_completed)
    )

    bedtime_text = bedtime.strip() if bedtime and bedtime.strip() else "not specified (assume 23:00)"

    user_prompt = (
        f"Current time: {current_time} (Asia/Shanghai)\n"
        f"Planned bedtime: {bedtime_text}\n\n"
        f"Habits not completed today:\n{habit_list}\n\n"
        f"Plan the remaining time before sleep."
    )

    body = {
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "max_tokens": 800,
        "temperature": 0.6,
        "system": [{"text": SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS['en'])}],
    }

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
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latency_ms = int((time.time() - start) * 1000)
            text = data["output"]["message"]["content"][0]["text"]
            usage = data.get("usage", {})
            return {"plan": text, "latency_ms": latency_ms, "usage": usage, "error": None}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return {
            "plan": None,
            "error": f"AI service error (HTTP {e.code}): {err_body[:200]}",
            "latency_ms": None,
            "usage": {},
        }
    except Exception as e:
        return {
            "plan": None,
            "error": f"{type(e).__name__}: {e}",
            "latency_ms": None,
            "usage": {},
        }
