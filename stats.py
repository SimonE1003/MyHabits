"""Execution & discipline metrics for MyHabits.

Per-round 3-dimension discipline score (0-100):

    Completion Rate    40 pts   completion_rate * 40
    Successful Days    40 pts   successful_days / days_elapsed * 40
                                 (a "successful day" = >=60% habits done)
    Success Streak     20 pts   longest successful-day streak / 21 * 20

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

    # ---- Successful days & longest success streak within this round ----
    # A "successful day" = >=60% of in-scope habits done that day.
    success_threshold = max(1, int(len(rnd_habits) * 0.6))  # ceil-ish for small N
    successful_days = 0
    longest_streak = 0
    current_streak = 0
    for i in range(days_elapsed):
        d = (start + timedelta(days=i)).isoformat()
        done = sum(1 for h in rnd_habits if d in logs_map[h["id"]])
        if done >= success_threshold:
            successful_days += 1
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 0

    completion_rate = total_completions / total_expected if total_expected > 0 else 0
    success_day_ratio = successful_days / days_elapsed if days_elapsed > 0 else 0

    # ---- Score (3 dimensions, 40/40/20) ----
    # Completion Rate (0-40): overall completion rate.
    completion_score = completion_rate * 40

    # Successful Days (0-40): ratio of successful days to elapsed days.
    success_days_score = success_day_ratio * 40

    # Success Streak (0-20): longest successful-day run / 21.
    streak_score = min(20, (longest_streak / 21) * 20)

    total_score = round(completion_score + success_days_score + streak_score)
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
        "successful_days": successful_days,
        "longest_streak": longest_streak,
        "score": total_score,
        "level_key": level_key,
        "dimensions": {
            "completion": round(completion_score),
            "completion_max": 40,
            "completion_rate_pct": round(completion_rate * 100),
            "success_days": round(success_days_score),
            "success_days_max": 40,
            "successful_days": successful_days,
            "days_elapsed": days_elapsed,
            "success_day_ratio_pct": round(success_day_ratio * 100),
            "streak": round(streak_score),
            "streak_max": 20,
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

    # Normalize round numbers so they start from 1 (defensive: handles
    # legacy data where round 0 may exist due to an older bug).
    if round_summaries and round_summaries[0]["round"] != 1:
        offset = 1 - round_summaries[0]["round"]
        for r in round_summaries:
            r["round"] += offset

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

    # Longest success-day streak across all rounds (for the headline number).
    # A "success day" = >=60% of in-scope habits done that day.
    longest_streak_all = 0
    current_streak = 0
    for d_str in sorted_dates:
        info = daily_map[d_str]
        is_success = info["total"] > 0 and info["done"] >= max(1, int(info["total"] * 0.6))
        if is_success:
            current_streak += 1
            longest_streak_all = max(longest_streak_all, current_streak)
        else:
            current_streak = 0

    has_enough_data = main_round["days_elapsed"] >= 3

    # ---- Year-scoped heatmap for the GitHub-style calendar ----
    # The user can browse by year; default to the current year.
    earliest_year = first_start.year
    current_year = today.year
    available_years = list(range(earliest_year, current_year + 1))

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
        "calendar": _build_year_calendar(
            daily_map, available_years, current_year, today
        ),
    }


def _build_year_calendar(daily_map, available_years, selected_year, today):
    """Build GitHub-style calendar data for one year.

    Returns:
        {
            "available_years": [2024, 2025, ...],
            "selected_year": 2026,
            "months": [{label, offset_weeks}, ...],  # top labels
            "weeks": [[cell, ...], ...],              # 7 rows × N week columns
        }
    """
    from datetime import date as _date

    year = selected_year
    jan1 = _date(year, 1, 1)
    dec31 = _date(year, 12, 31)
    # Start from the Monday on or before Jan 1.
    start = jan1 - timedelta(days=jan1.weekday())
    end = dec31

    # Cap future dates at today (don't render cells for days that
    # haven't happened yet).
    render_end = min(end, today) if year == today.year else end

    # Build week columns (each column = Mon..Sun).
    weeks = []
    d = start
    while d <= render_end:
        col = []
        for _ in range(7):
            if d > render_end:
                col.append({"date": d.isoformat(), "is_future": True})
            else:
                d_str = d.isoformat()
                info = daily_map.get(d_str)
                if info and info["total"] > 0:
                    ratio = info["done"] / info["total"]
                    col.append({
                        "date": d_str,
                        "done": info["done"],
                        "total": info["total"],
                        "ratio": ratio,
                        "is_placeholder": False,
                    })
                else:
                    col.append({
                        "date": d_str,
                        "done": 0,
                        "total": 0,
                        "ratio": 0,
                        "is_placeholder": True,
                    })
            d += timedelta(days=1)
        weeks.append(col)

    # Month labels positioned by week-column offset.
    # Only consider days within the selected year, so that a late-December
    # tail from the previous year doesn't push January's label to the right.
    # January's label lands on the week containing Jan 1, even if that week
    # starts on a Monday in late December.
    months = []
    if weeks:
        last_month = -1
        for i, week in enumerate(weeks):
            for cell in week:
                if cell.get("is_future"):
                    continue
                d = _date.fromisoformat(cell["date"])
                if d.year != year:
                    continue
                m = d.month
                if m != last_month:
                    months.append({"label": m, "offset": i})
                    last_month = m
                break

    return {
        "available_years": available_years,
        "selected_year": selected_year,
        "months": months,
        "weeks": weeks,
    }
