"""Training page: weekly volume, load, intensity, strength, consistency."""

from __future__ import annotations

from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.dashboard.references import bands


def weekly(wh: Warehouse) -> list[dict[str, Any]]:
    return (
        wh.read("marts", "mart_training_weekly")
        .select(
            "week_start",
            "activity_group",
            "sessions",
            (pl.col("minutes") / 60).round(2).alias("hours"),
            pl.col("distance_km").round(1),
            pl.col("trimp").round(0),
            pl.col("zone_minutes_4_5").round(0).alias("vigorous_min"),
        )
        .sort("week_start")
        .to_dicts()
    )


def load(wh: Warehouse) -> list[dict[str, Any]]:
    return (
        wh.read("marts", "mart_training_load")
        .select(
            pl.col("local_date").alias("d"),
            pl.col("trimp").round(0).alias("t"),
            pl.col("acute_load").round(1).alias("a"),
            pl.col("chronic_load").round(1).alias("c"),
            pl.col("acwr").round(2).alias("r"),
        )
        .to_dicts()
    )


def intensity(w: pl.DataFrame) -> dict[str, Any]:
    zones = [f"zone{i}_min" for i in range(1, 6)]
    monthly = (
        w.filter(pl.col("has_zones"))
        .group_by(pl.col("local_date").dt.month_start().alias("month"))
        .agg(*[pl.col(z).sum().round(0).alias(z) for z in zones], pl.len().alias("sessions"))
        .sort("month")
    )
    return {"zones_monthly": monthly.to_dicts()}


def build(wh: Warehouse) -> dict[str, Any]:
    """Weekly volume, daily load and monthly zones; per-session views (strength, effort, consistency,
    recent workouts) come from workouts.json so they follow the page's date range."""
    w = wh.read("marts", "mart_workout").filter(pl.col("is_counted"))
    return {
        "weekly": weekly(wh),
        "load": load(wh),
        "zones_monthly": intensity(w)["zones_monthly"],
        "references": {
            k: bands(wh, k) for k in ("training_load_ratio", "vigorous_minutes_week", "exercise_minutes_week")
        },
    }
