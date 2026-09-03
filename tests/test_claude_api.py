"""
独立测试 HKU Claude API 的脚本。
测试三件事：
1. 连通性 + 响应速度
2. 模拟真实的"睡前习惯规划"prompt，看输出质量
3. 测试错误情况（空消息、超长输入等）

运行方式：
    cd "/Users/simon/Desktop/Habit Tracker"
    source venv/bin/activate
    python test_claude_api.py
"""

import os
import time
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("HKU_CLAUDE_API_KEY")
ENDPOINT = os.environ.get("HKU_CLAUDE_ENDPOINT")
MODEL = os.environ.get("HKU_CLAUDE_MODEL", "claude-haiku-4.5")

if not API_KEY or not ENDPOINT:
    raise SystemExit("Missing API key or endpoint in .env")

URL = f"{ENDPOINT}/{MODEL}/converse"


def call_claude(user_text, system_text=None, max_tokens=1024, temperature=0.7):
    """Call HKU Claude Converse API. Returns (text, latency_ms, usage)."""
    messages = [{"role": "user", "content": [{"text": user_text}]}]

    body = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system_text:
        # AWS Bedrock Converse: system must be a list of content blocks
        body["system"] = [{"text": system_text}]

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
            latency = int((time.time() - start) * 1000)
            text = data["output"]["message"]["content"][0]["text"]
            usage = data.get("usage", {})
            return text, latency, usage
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[HTTP {e.code}] {body}", None, {}
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}", None, {}


# ============================================================
# Test 1: Basic connectivity + latency
# ============================================================
print("=" * 60)
print("TEST 1: Basic connectivity")
print("=" * 60)
text, latency, usage = call_claude("Say 'OK' in one word.", max_tokens=10)
print(f"Response: {text}")
print(f"Latency: {latency} ms")
print(f"Tokens: {usage}")
print()

# ============================================================
# Test 2: Real-world prompt (simulating the actual /now use case)
# ============================================================
print("=" * 60)
print("TEST 2: Realistic habit planning prompt")
print("=" * 60)

system_prompt = (
    "You are a habit coach. Given the current time, the user's planned bedtime, "
    "and a list of habits not yet completed today, produce a concrete time-blocked plan "
    "for the remaining hours before sleep. Consider: (1) habit type and typical duration, "
    "(2) whether the habit is appropriate close to bedtime (e.g. intense workout disrupts sleep), "
    "(3) total available time. If a habit should be skipped tonight, say so explicitly with a reason. "
    "Output as a clean schedule with time blocks. Keep it concise and actionable."
)

user_prompt = """Current time: 21:45 (Asia/Shanghai)
Planned bedtime: 23:30

Habits not completed today:
1. Meditate (morning)
2. Workout (afternoon)
3. Read 30 Min (evening)
4. Journal (evening)

Please plan the next 1h45m before sleep."""

print(f"\nPrompt:\n{user_prompt}\n")
print("Waiting for response...\n")

text, latency, usage = call_claude(user_prompt, system_text=system_prompt, max_tokens=800, temperature=0.6)
print(f"--- AI Plan ---\n{text}\n")
print(f"--- Stats ---")
print(f"Latency: {latency} ms ({(latency/1000):.2f}s)" if latency else "Latency: N/A")
print(f"Input tokens: {usage.get('inputTokens', '?')}")
print(f"Output tokens: {usage.get('outputTokens', '?')}")
print(f"Total tokens: {usage.get('totalTokens', '?')}")
print()

# ============================================================
# Test 3: Empty/minimal input
# ============================================================
print("=" * 60)
print("TEST 3: Edge case - very short input")
print("=" * 60)
text, latency, usage = call_claude("What time is it?", max_tokens=50)
print(f"Response: {text}")
print(f"Latency: {latency} ms")
print()

# ============================================================
# Test 4: Chinese output (test multilingual)
# ============================================================
print("=" * 60)
print("TEST 4: Chinese output test")
print("=" * 60)
text, latency, usage = call_claude(
    "用中文说一句关于坚持习惯的话，10 个字以内。",
    max_tokens=50,
    temperature=0.8,
)
print(f"Response: {text}")
print(f"Latency: {latency} ms")
print()

print("=" * 60)
print("All tests complete.")
print("=" * 60)
