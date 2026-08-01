"""Execution & discipline metrics for MyHabits.

Computes a multi-dimensional discipline score (0-100) from habit logs:

    Completion Rate   40 pts   actual completions / expected
    Streak Consistency 25 pts   longest perfect-day streak
    Recovery Resilience 15 pts  how fast you bounce back after a miss
    Momentum Trend     20 pts   last 7 days vs prior 7 days

Also prepares calendar-heatmap data (date -> completion ratio) for the
GitHub-style visualization on /stats.

All functions are pure (read-only) — they never mutate the database.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta


def _parse_date(value):
    """Parse a date from DB (may be str or date). Returns date or None."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def compute_user_stats(db, user_id, user_tz=None):
    """Compute discipline metrics and heatmap data for a user.

    Args:
        db: sqlite3 connection with row_factory.
        user_id: the user's id.
        user_tz: a tzinfo for "today" calculation; falls back to date.today().

    Returns dict, or None if the user has no habits at all.

    Returned dict keys:
        score:               0-100 overall
        dimensions:          per-dimension breakdown (each has score + max)
        level_key:           translation key for the level label
        heatmap:             {date_str: {done, total}} for calendar viz
        rounds:              per-round summaries (habits, rates)
        longest_streak:      longest run of perfect days
        total_completions:   sum across all habits & rounds
        active_days:         days with at least one habit in scope
        full_days:           days where every in-scope habit was done
        date_range:          {start, end} of the heatmap span
        has_enough_data:     False if < 3 active days (score not meaningful)
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
    habit_ids = [h['id'] for h in habits]
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

    # ---- Per-round summaries ----
    round_summaries = []
    for rnd in sorted(rounds_map.keys()):
        rnd_habits = rounds_map[rnd]
        rnd_start = _parse_date(rnd_habits[0]["challenge_start"]) or today
        rnd_end = rnd_start + timedelta(days=20)  # 21-day challenge: days 1..21
        days_elapsed = (min(today, rnd_end) - rnd_start).days + 1
        days_elapsed = max(0, min(days_elapsed, 21))

        habit_stats = []
        total_completions = 0
        total_expected = 0
        for h in rnd_habits:
            completed = len(logs_map[h["id"]])
            expected = days_elapsed
            total_completions += completed
            total_expected += expected
            habit_stats.append({
                "name": h["name"],
                "phase": h["phase"],
                "completed": completed,
                "expected": expected,
                "rate": completed / expected if expected > 0 else 0,
            })

        rate = total_completions / total_expected if total_expected > 0 else 0
        round_summaries.append({
            "round": rnd,
            "start": rnd_start.isoformat(),
            "end": rnd_end.isoformat(),
            "days_elapsed": days_elapsed,
            "is_active": rnd_habits[0]["archived"] == 0,
            "habit_count": len(rnd_habits),
            "total_completions": total_completions,
            "completion_rate": rate,
            "habits": habit_stats,
        })

    # ---- Calendar heatmap: date -> {done, total} ----
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

    # ---- Dimension 1: Completion Rate (40 pts) ----
    # Score the current active round; fall back to the latest round.
    scoring_round = next((r for r in round_summaries if r["is_active"]), None)
    if scoring_round is None and round_summaries:
        scoring_round = round_summaries[-1]
    completion_rate = scoring_round["completion_rate"] if scoring_round else 0
    completion_score = min(40, completion_rate * 40)

    # ---- Dimension 2: Streak Consistency (25 pts) ----
    # Longest run of "perfect days" (all in-scope habits done).
    longest_streak = 0
    current_streak = 0
    full_days = 0
    for d_str in sorted_dates:
        info = daily_map[d_str]
        is_full = info["total"] > 0 and info["done"] >= info["total"]
        if is_full:
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
            full_days += 1
        else:
            current_streak = 0
    streak_score = min(25, (longest_streak / 21) * 25) if active_days > 0 else 0

    # ---- Dimension 3: Recovery Resilience (15 pts) ----
    # Measure how quickly the user returns to a perfect day after a miss.
    # A "break segment" is a maximal run of non-perfect days. Shorter
    # segments (and fewer of them) mean stronger recovery.
    break_segments = []
    in_break = False
    break_len = 0
    for d_str in sorted_dates:
        info = daily_map[d_str]
        is_full = info["total"] > 0 and info["done"] >= info["total"]
        if not is_full:
            in_break = True
            break_len += 1
        elif in_break:
            break_segments.append(break_len)
            in_break = False
            break_len = 0
    if in_break:
        break_segments.append(break_len)

    if not break_segments:
        # Never broke a streak — full marks (if there's enough data).
        recovery_score = 15.0 if active_days >= 3 else 5.0
    else:
        avg_break = sum(break_segments) / len(break_segments)
        # 1-day break => 13, 3-day => 9, 5-day => 5, 8+ => 0
        recovery_score = max(0, 15 - (avg_break - 1) * 2)

    # ---- Dimension 4: Momentum Trend (20 pts) ----
    # Compare last 7 days vs the prior 7 days.
    def avg_rate(date_strs):
        rates = []
        for ds in date_strs:
            info = daily_map.get(ds)
            if info and info["total"] > 0:
                rates.append(info["done"] / info["total"])
        return sum(rates) / len(rates) if rates else None

    recent_start = (today - timedelta(days=6)).isoformat()
    prior_start = (today - timedelta(days=13)).isoformat()
    recent_dates = [ds for ds in sorted_dates if ds >= recent_start]
    prior_dates = [ds for ds in sorted_dates if prior_start <= ds < recent_start]
    recent_rate = avg_rate(recent_dates)
    prior_rate = avg_rate(prior_dates)

    if recent_rate is None and prior_rate is None:
        momentum_score = 10.0  # neutral, no data either side
    elif prior_rate is None:
        momentum_score = 10.0 + recent_rate * 5  # bonus for recent activity
    elif recent_rate is None:
        momentum_score = max(0.0, 10.0 - prior_rate * 5)  # recent inactivity
    else:
        delta = recent_rate - prior_rate
        momentum_score = max(0, min(20, 10 + delta * 20))

    # ---- Total ----
    total_score = round(completion_score + streak_score + recovery_score + momentum_score)

    # ---- Level label ----
    if total_score >= 85:
        level_key = "stats.level_master"
    elif total_score >= 70:
        level_key = "stats.level_disciplined"
    elif total_score >= 55:
        level_key = "stats.level_consistent"
    elif total_score >= 40:
        level_key = "stats.level_building"
    else:
        level_key = "stats.level_beginning"

    has_enough_data = active_days >= 3

    return {
        "score": total_score,
        "dimensions": {
            "completion": round(completion_score),
            "completion_max": 40,
            "completion_rate_pct": round(completion_rate * 100),
            "streak": round(streak_score),
            "streak_max": 25,
            "recovery": round(recovery_score),
            "recovery_max": 15,
            "momentum": round(momentum_score),
            "momentum_max": 20,
        },
        "level_key": level_key,
        "heatmap": daily_map,
        "heatmap_cells": heatmap_cells,
        "rounds": round_summaries,
        "longest_streak": longest_streak,
        "total_completions": sum(len(v) for v in logs_map.values()),
        "active_days": active_days,
        "full_days": full_days,
        "date_range": {
            "start": first_start.isoformat(),
            "end": today.isoformat(),
        },
        "has_enough_data": has_enough_data,
    }
