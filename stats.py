"""Execution & discipline metrics for MyHabits.

Per-round 2-dimension discipline score (0-100):

    Completion Rate    70 pts   completion_rate * 50  +  full_day_ratio * 20
                                 (base completion)       (bonus for perfect days)
    Streak Consistency 30 pts   longest perfect-day streak / 21 * 30

Each 21-day challenge round is scored independently — the score resets
at the start of every new round, like a sleep score per night. The main
score shown on /stats is the active round's; archived rounds display
their final scores in the history section so the user can see their
trajectory across rounds.

Also prepares calendar-heatmap data (date -> completion ratio) for the
GitHub-style visualization on /stats.

All functions are pure (read-only) — they never mutate the database.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

# Level thresholds — single source of truth, shared with the template.
# (min_score, translation_key, label_for_range)
LEVEL_THRESHOLDS = [
    (85, "stats.level_master",      "85 - 100"),
    (70, "stats.level_disciplined", "70 - 84"),
    (55, "stats.level_consistent",  "55 - 69"),
    (40, "stats.level_building",    "40 - 54"),
    (0,  "stats.level_beginning",   "0 - 39"),
]


def level_for_score(score):
    """Return the translation key for the level label at this score."""
    for threshold, key, _ in LEVEL_THRESHOLDS:
        if score >= threshold:
            return key
    return "stats.level_beginning"


def _parse_date(value):
    """Parse a date from DB (may be str or date). Returns date or None."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _score_round(rnd_habits, logs_map, today):
    """Score a single challenge round (0-100).

    Returns dict with score, dimensions, and per-habit stats, or None
    if the round has no habits.
    """
    if not rnd_habits:
        return None

    is_active = rnd_habits[0]["archived"] == 0
    start = _parse_date(rnd_habits[0]["challenge_start"]) or today
    end = start + timedelta(days=20)  # 21-day window: days 1..21

    if is_active:
        days_elapsed = max(0, min(21, (min(today, end) - start).days + 1))
    else:
        days_elapsed = 21
    # Guard against div-by-zero on the very first day.
    if days_elapsed <= 0:
        days_elapsed = 1

    # ---- Per-habit completion within this round's window ----
    habit_stats = []
    total_completions = 0
    total_expected = 0
    for h in rnd_habits:
        h_done = 0
        for i in range(days_elapsed):
            d = (start + timedelta(days=i)).isoformat()
            if d in logs_map[h["id"]]:
                h_done += 1
        h_expected = days_elapsed
        total_completions += h_done
        total_expected += h_expected
        habit_stats.append({
            "name": h["name"],
            "phase": h["phase"],
            "completed": h_done,
            "expected": h_expected,
            "rate": h_done / h_expected if h_expected > 0 else 0,
        })

    # ---- Full days & longest streak within this round ----
    # A "full day" = every habit in scope was done that day.
    full_days = 0
    longest_streak = 0
    current_streak = 0
    for i in range(days_elapsed):
        d = (start + timedelta(days=i)).isoformat()
        done = sum(1 for h in rnd_habits if d in logs_map[h["id"]])
        if done >= len(rnd_habits):
            full_days += 1
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 0

    completion_rate = total_completions / total_expected if total_expected > 0 else 0
    full_day_ratio = full_days / days_elapsed if days_elapsed > 0 else 0

    # ---- Score ----
    # Completion dimension (0-70): base rate (0-50) + full-day bonus (0-20).
    completion_base = completion_rate * 50
    full_day_bonus = full_day_ratio * 20
    completion_score = completion_base + full_day_bonus

    # Streak dimension (0-30): longest perfect-day run / 21.
    streak_score = min(30, (longest_streak / 21) * 30)

    total_score = round(completion_score + streak_score)
    level_key = level_for_score(total_score)

    return {
        "round": rnd_habits[0]["challenge_round"],
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days_elapsed": days_elapsed,
        "is_active": is_active,
        "habit_count": len(rnd_habits),
        "total_completions": total_completions,
        "total_expected": total_expected,
        "completion_rate": completion_rate,
        "full_days": full_days,
        "longest_streak": longest_streak,
        "score": total_score,
        "level_key": level_key,
        "dimensions": {
            "completion": round(completion_score),
            "completion_max": 70,
            "completion_rate_pct": round(completion_rate * 100),
            "full_days": full_days,
            "days_elapsed": days_elapsed,
            "full_day_ratio_pct": round(full_day_ratio * 100),
            "streak": round(streak_score),
            "streak_max": 30,
            "longest_streak": longest_streak,
        },
        "habits": habit_stats,
    }


def compute_user_stats(db, user_id, user_tz=None):
    """Compute discipline metrics and heatmap data for a user.

    Args:
        db: sqlite3 connection with row_factory.
        user_id: the user's id.
        user_tz: a tzinfo for "today" calculation; falls back to date.today().

    Returns dict, or None if the user has no habits at all.

    The main score is the ACTIVE round's score (resets each round).
    Archived rounds carry their own final scores in `rounds`.
    """
    if user_tz is not None:
        today = datetime.now(user_tz).date()
    else:
        today = date.today()

    # ---- Load all habits (active + archived) ----
    habits = db.execute(
        """SELECT id, name, phase, completed_days, challenge_start,
                  last_completed, challenge_round, archived
           FROM habits WHERE user_id = ?
           ORDER BY challenge_round, id""",
        (user_id,)
    ).fetchall()

    if not habits:
        return None

    # ---- Load all habit logs ----
    habit_ids = [h["id"] for h in habits]
    logs_map = defaultdict(set)  # habit_id -> {date_str, ...}
    if habit_ids:
        placeholders = ",".join("?" * len(habit_ids))
        logs = db.execute(
            f"SELECT habit_id, completed_date FROM habit_logs "
            f"WHERE habit_id IN ({placeholders})",
            habit_ids
        ).fetchall()
        for log in logs:
            logs_map[log["habit_id"]].add(log["completed_date"])

    # ---- Group habits by round ----
    rounds_map = defaultdict(list)
    for h in habits:
        rounds_map[h["challenge_round"]].append(h)

    # ---- Score each round independently ----
    round_summaries = []
    for rnd in sorted(rounds_map.keys()):
        scored = _score_round(rounds_map[rnd], logs_map, today)
        if scored:
            round_summaries.append(scored)

    # ---- Main score = active round, else latest round ----
    active_round = next((r for r in round_summaries if r["is_active"]), None)
    main_round = active_round if active_round else (
        round_summaries[-1] if round_summaries else None
    )

    if main_round is None:
        return None

    # ---- Calendar heatmap: date -> {done, total} across ALL rounds ----
    # A habit is "in scope" on day D if D falls within its 21-day window.
    first_start = min(
        (_parse_date(h["challenge_start"]) for h in habits if h["challenge_start"]),
        default=today,
    )

    daily_map = {}
    d = first_start
    while d <= today:
        d_str = d.isoformat()
        done = 0
        total = 0
        for h in habits:
            h_start = _parse_date(h["challenge_start"])
            if h_start and h_start <= d <= h_start + timedelta(days=20):
                total += 1
                if d_str in logs_map[h["id"]]:
                    done += 1
        if total > 0:
            daily_map[d_str] = {"done": done, "total": total}
        d += timedelta(days=1)

    active_days = len(daily_map)
    sorted_dates = sorted(daily_map.keys())

    # ---- Build ordered cell list with week-alignment (start on Monday) ----
    # Leading empty cells pad the first week so days land in the right row.
    first_monday = first_start - timedelta(days=first_start.weekday())
    heatmap_cells = []
    d = first_monday
    while d <= today:
        d_str = d.isoformat()
        info = daily_map.get(d_str)
        if info:
            ratio = info["done"] / info["total"] if info["total"] > 0 else 0
            heatmap_cells.append({
                "date": d_str,
                "done": info["done"],
                "total": info["total"],
                "ratio": ratio,
                "is_placeholder": False,
            })
        else:
            heatmap_cells.append({
                "date": d_str,
                "done": 0,
                "total": 0,
                "ratio": 0,
                "is_placeholder": True,
            })
        d += timedelta(days=1)

    # ---- Aggregate stats for display ----
    total_completions_all = sum(len(v) for v in logs_map.values())

    # Longest streak across all rounds (for the headline number).
    longest_streak_all = 0
    current_streak = 0
    for d_str in sorted_dates:
        info = daily_map[d_str]
        is_full = info["total"] > 0 and info["done"] >= info["total"]
        if is_full:
            current_streak += 1
            longest_streak_all = max(longest_streak_all, current_streak)
        else:
            current_streak = 0

    has_enough_data = main_round["days_elapsed"] >= 3

    return {
        "score": main_round["score"],
        "dimensions": main_round["dimensions"],
        "level_key": main_round["level_key"],
        "level_thresholds": LEVEL_THRESHOLDS,
        "round_is_active": main_round["is_active"],
        "round_number": main_round["round"],
        "heatmap": daily_map,
        "heatmap_cells": heatmap_cells,
        "rounds": round_summaries,
        "longest_streak": longest_streak_all,
        "total_completions": total_completions_all,
        "active_days": active_days,
        "date_range": {
            "start": first_start.isoformat(),
            "end": today.isoformat(),
        },
        "has_enough_data": has_enough_data,
    }
