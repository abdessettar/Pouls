"""Activity page: steps over the years, calendar (with ring goals), exercise, daylight, gait.

The shape of a day comes from hourly.py; rings and streaks are counted in the page for its date range.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.dashboard.references import bands

MIN_DAYS = 10
MIN_STEPS_DAY = 100  # days below this are treated as "phone not carried", not as data


def _r(e: pl.Expr, digits: int = 2) -> pl.Expr:
    return e.round(digits)


def monthly_steps(daily: pl.DataFrame, watch_from: Any) -> list[dict[str, Any]]:
    d = daily.filter(pl.col("steps") >= MIN_STEPS_DAY)
    return (
        d.group_by(pl.col("local_date").dt.month_start().alias("month"))
        .agg(
            pl.col("steps").median().alias("median"),
            pl.col("steps").quantile(0.25).alias("p25"),
            pl.col("steps").quantile(0.75).alias("p75"),
            pl.len().alias("n"),
        )
        .filter(pl.col("n") >= MIN_DAYS)
        .with_columns(
            pl.when(pl.col("month") < watch_from)
            .then(pl.lit("iphone"))
            .otherwise(pl.lit("watch"))
            .alias("era")
        )
        .sort("month")
        .to_dicts()
    )


def calendar(daily: pl.DataFrame) -> list[dict[str, Any]]:
    return (
        daily.select(
            "local_date",
            _r(pl.col("steps"), 0).alias("steps"),
            _r(pl.col("active_energy_kcal"), 0).alias("active_energy"),
            _r(pl.col("exercise_min"), 0).alias("exercise"),
            "is_valid_wear_day",
            pl.col("move_goal_met").alias("move_met"),
            pl.col("exercise_goal_met").alias("exercise_met"),
            pl.col("stand_goal_met").alias("stand_met"),
            pl.col("all_rings_closed").alias("all_met"),
        )
        .filter(pl.col("steps").is_not_null() | pl.col("active_energy").is_not_null())
        .to_dicts()
    )


def weekly_exercise(wh: Warehouse) -> list[dict[str, Any]]:
    w = wh.read("marts", "mart_weekly").sort("week_start")
    return (
        w.filter(pl.col("n_valid_wear_days") >= 5)
        .select("week_start", _r(pl.col("exercise_min"), 0).alias("exercise_min"), "n_valid_wear_days")
        .to_dicts()
    )


def monthly_medians(daily: pl.DataFrame, cols: dict[str, str], valid_only: bool) -> list[dict[str, Any]]:
    d = daily.filter(pl.col("is_valid_wear_day")) if valid_only else daily
    aggs = [pl.col(c).median().alias(k) for k, c in cols.items()]
    counts = [pl.col(c).count().alias(f"n_{k}") for k, c in cols.items()]
    out = d.group_by(pl.col("local_date").dt.month_start().alias("month")).agg(*aggs, *counts).sort("month")
    for k in cols:
        out = out.with_columns(pl.when(pl.col(f"n_{k}") >= MIN_DAYS).then(pl.col(k)).otherwise(None).alias(k))
    return out.drop([f"n_{k}" for k in cols]).to_dicts()


def build(wh: Warehouse) -> dict[str, Any]:
    from apple_health.dashboard.meta import build as meta_build

    meta = meta_build(wh)
    daily = wh.read("marts", "mart_daily").sort("local_date")
    return {
        "monthly_steps": monthly_steps(daily, meta["firsts"]["watch"]),
        "calendar": calendar(daily),
        "weekly_exercise": weekly_exercise(wh),
        "daylight": monthly_medians(daily, {"daylight": "daylight_min"}, valid_only=True),
        "gait": monthly_medians(
            daily,
            {
                "speed": "walking_speed_kmh",
                "step_length": "walking_step_length_cm",
                "asymmetry": "walking_asymmetry",
                "double_support": "walking_double_support",
                "steadiness": "walking_steadiness",
            },
            valid_only=False,
        ),
        "references": {
            k: bands(wh, k) for k in ("steps", "exercise_minutes_week", "walking_speed", "double_support")
        },
        "watch_from": meta["firsts"]["watch"],
    }
