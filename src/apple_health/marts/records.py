"""mart_records: personal records, streaks and lifetime totals."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import polars as pl

from apple_health.marts.analytics_tables import MART_RECORDS
from apple_health.transform.context import BuildContext


def longest_streak(dates: list[date], flags: list[bool | None]) -> tuple[int, date | None, date | None]:
    """Longest run of consecutive days where the flag is true (dates must be consecutive and sorted)."""
    best = (0, None, None)
    run, start, prev = 0, None, None
    for d, f in zip(dates, flags, strict=True):
        if f and prev is not None and run and d == prev + timedelta(days=1):
            run += 1
        elif f:
            run, start = 1, d
        else:
            run = 0
        if f and run > best[0]:
            best = (run, start, d)
        prev = d
    return best


def _extreme(df: pl.DataFrame, col: str, how: str) -> tuple[float | None, date | None, str | None]:
    s = df.filter(pl.col(col).is_not_null())
    if s.height == 0:
        return None, None, None
    row = s.sort(col, descending=(how == "max")).row(0, named=True)
    return row[col], row.get("local_date"), row.get("workout_id")


def build_records(ctx: BuildContext) -> None:
    daily = ctx.scan("mart_daily").sort("local_date").collect()
    valid = daily.filter(pl.col("is_valid_wear_day"))
    workouts = ctx.scan("mart_workout").filter(pl.col("is_counted")).collect()
    runs = ctx.scan("mart_run").collect()
    rows: list[dict[str, Any]] = []

    def add(
        rid: str,
        category: str,
        label: str,
        kind: str,
        value: float | None,
        unit: str,
        start: date | None = None,
        end: date | None = None,
        detail: str | None = None,
    ) -> None:
        rows.append(
            {
                "record_id": rid,
                "category": category,
                "label": label,
                "kind": kind,
                "value": float(value) if value is not None else None,
                "unit": unit,
                "start_date": start,
                "end_date": end,
                "detail_id": detail,
            }
        )

    for rid, cat, label, frame, col, how, unit in [
        ("most_steps_day", "activity", "Most steps in a day", daily, "steps", "max", "steps"),
        (
            "most_active_energy_day",
            "activity",
            "Most active energy in a day",
            daily,
            "active_energy_kcal",
            "max",
            "kcal",
        ),
        (
            "most_exercise_day",
            "activity",
            "Most exercise minutes in a day",
            daily,
            "exercise_min",
            "max",
            "min",
        ),
        ("lowest_resting_hr", "heart", "Lowest resting heart rate", valid, "resting_hr_bpm", "min", "bpm"),
        ("highest_vo2max", "heart", "Highest VO2max", daily, "vo2max", "max", "mL/min·kg"),
        ("highest_sleep_hrv", "heart", "Highest night HRV", valid, "hrv_sdnn_sleep_ms", "max", "ms"),
        ("longest_sleep", "sleep", "Longest night asleep", daily, "sleep_asleep_min", "max", "min"),
    ]:
        v, d, _ = _extreme(frame, col, how)
        add(rid, cat, label, how, v, unit, d)

    for rid, cat, label, frame, col, how, unit, where in [
        ("longest_workout", "training", "Longest workout", workouts, "duration_min", "max", "min", None),
        ("longest_walk", "training", "Longest walk", workouts, "distance_km", "max", "km", "walking"),
        ("longest_run", "running", "Longest run", runs, "distance_km", "max", "km", None),
        ("fastest_1k", "running", "Fastest 1 km", runs, "best_1k_s", "min", "s", None),
        ("fastest_5k", "running", "Fastest 5 km", runs, "best_5k_s", "min", "s", None),
        ("fastest_10k", "running", "Fastest 10 km", runs, "best_10k_s", "min", "s", None),
        ("highest_trimp", "training", "Hardest workout (TRIMP)", workouts, "trimp", "max", "TRIMP", None),
    ]:
        f = frame.filter(pl.col("activity_group") == where) if where else frame
        v, d, wid = _extreme(f, col, how)
        add(rid, cat, label, how, v, unit, d, detail=wid)

    dates = daily["local_date"].to_list()
    workout_days = set(workouts["local_date"].to_list())
    for rid, cat, label, flags in [
        (
            "streak_all_rings",
            "activity",
            "Longest streak closing all rings",
            daily["all_rings_closed"].to_list(),
        ),
        (
            "streak_move_ring",
            "activity",
            "Longest streak closing the move ring",
            daily["move_goal_met"].to_list(),
        ),
        (
            "streak_exercise_ring",
            "activity",
            "Longest streak closing the exercise ring",
            daily["exercise_goal_met"].to_list(),
        ),
        (
            "streak_7h_sleep",
            "sleep",
            "Longest streak of nights with 7 h or more",
            [(v or 0) >= 420 for v in daily["sleep_asleep_min"].to_list()],
        ),
        (
            "streak_workout_days",
            "training",
            "Longest streak of days with a workout",
            [d in workout_days for d in dates],
        ),
    ]:
        n, s, e = longest_streak(dates, flags)
        add(rid, cat, label, "streak", n, "days", s, e)

    total = lambda c: daily[c].sum() if daily[c].count() else None  # noqa: E731
    first = daily["local_date"].min()
    add("total_steps", "totals", "Steps", "total", total("steps"), "steps", first)
    add(
        "total_distance_km",
        "totals",
        "Distance walked and run",
        "total",
        total("distance_walking_running_km"),
        "km",
        first,
    )
    add("total_flights", "totals", "Floors climbed", "total", total("flights_climbed"), "floors", first)
    add(
        "total_workouts",
        "totals",
        "Workouts",
        "total",
        float(workouts.height),
        "workouts",
        workouts["local_date"].min() if workouts.height else None,
    )
    add(
        "total_workout_hours",
        "totals",
        "Hours of training",
        "total",
        (workouts["duration_min"].sum() / 60) if workouts.height else None,
        "h",
        workouts["local_date"].min() if workouts.height else None,
    )
    add(
        "total_sleep_hours",
        "totals",
        "Hours asleep",
        "total",
        (daily["sleep_asleep_min"].sum() / 60) if daily["sleep_asleep_min"].count() else None,
        "h",
        first,
    )
    add(
        "total_running_km",
        "totals",
        "Kilometres run",
        "total",
        runs["distance_km"].sum() if runs.height else None,
        "km",
        runs["local_date"].min() if runs.height else None,
    )
    ctx.write(MART_RECORDS, pl.DataFrame(rows, schema=MART_RECORDS.schema()))
