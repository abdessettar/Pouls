"""Overview page: tile definitions and the daily history they are computed from.

The page computes each tile for the chosen date range in the browser and compares it with your
typical period of the same length (the median over every such period in your history), so this
module only shapes the data: one row per day for the whole history, the counted workouts, the
reference bands, and what each tile measures.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.dashboard.references import bands


@dataclass(frozen=True)
class Kpi:
    key: str
    label: str
    domain: str
    unit: str
    column: str  # field of the day rows below
    # median: median day; rate_week: total per 7 days; share: share of days where true; last: latest value
    stat: str
    better: str | None  # higher | lower | None
    delta: str  # rel (percent) | abs (in the tile's unit)
    valid_only: bool = True  # Watch-based: valid wear days only
    scale: float = 1.0  # column unit -> tile unit (minutes -> hours)
    reference: str | None = None  # reference metric key (config/references.toml)


KPIS = [
    Kpi("steps", "Steps per day", "activity", "", "steps", "median", "higher", "rel", reference="steps"),
    Kpi(
        "active_energy", "Active energy per day", "activity", "kcal", "active_kcal", "median", "higher", "rel"
    ),
    Kpi(
        "exercise",
        "Exercise per week",
        "activity",
        "min",
        "exercise_min",
        "rate_week",
        "higher",
        "rel",
        valid_only=False,
        reference="exercise_minutes_week",
    ),
    Kpi(
        "rings",
        "Days with all rings closed",
        "activity",
        "",
        "rings",
        "share",
        "higher",
        "abs",
        valid_only=False,
    ),
    Kpi(
        "resting_hr",
        "Resting heart rate",
        "heart",
        "bpm",
        "rhr",
        "median",
        "lower",
        "abs",
        reference="resting_hr",
    ),
    Kpi("hrv", "HRV during sleep", "heart", "ms", "hrv", "median", "higher", "abs", reference="hrv_sdnn"),
    Kpi(
        "vo2max",
        "VO2max",
        "heart",
        "mL/min·kg",
        "vo2max_asof",
        "last",
        "higher",
        "abs",
        valid_only=False,
        reference="vo2max",
    ),
    Kpi(
        "respiratory_rate",
        "Breathing rate in sleep",
        "heart",
        "/min",
        "resp",
        "median",
        None,
        "abs",
        reference="respiratory_rate",
    ),
    Kpi(
        "asleep", "Time asleep", "sleep", "", "asleep", "median", "higher", "abs", reference="sleep_duration"
    ),
    Kpi("bedtime", "Bedtime", "sleep", "", "bedtime", "median", None, "abs"),
    Kpi(
        "training",
        "Training per week",
        "training",
        "h",
        "workout_min",
        "rate_week",
        "higher",
        "rel",
        valid_only=False,
        scale=1 / 60,
    ),
    Kpi(
        "running",
        "Running per week",
        "running",
        "km",
        "run_km",
        "rate_week",
        "higher",
        "rel",
        valid_only=False,
    ),
]


def days(wh: Warehouse) -> list[dict[str, Any]]:
    """Every day of the history with the fields the pages use (empty fields left out)."""
    d = wh.read("marts", "mart_daily").sort("local_date")
    base = wh.read("marts", "mart_baselines").filter(
        pl.col("metric").is_in(["resting_hr_bpm", "hrv_sdnn_sleep_ms"])
    )
    for metric, prefix in (("resting_hr_bpm", "rhr"), ("hrv_sdnn_sleep_ms", "hrv")):
        d = d.join(
            base.filter(pl.col("metric") == metric).select(
                "local_date",
                pl.col("normal_p10").round(1).alias(f"{prefix}_lo"),
                pl.col("normal_p90").round(1).alias(f"{prefix}_hi"),
                pl.col("z").round(2).alias(f"z_{prefix}"),
            ),
            on="local_date",
            how="left",
        )
    runs = (
        wh.read("marts", "mart_run")
        .group_by("local_date")
        .agg(pl.col("distance_km").sum().round(2).alias("run_km"))
    )
    d = d.join(runs, on="local_date", how="left")
    rows = d.select(
        pl.col("local_date").alias("d"),
        pl.col("is_valid_wear_day").alias("valid"),
        pl.col("steps").round(0),
        pl.col("active_energy_kcal").round(0).alias("active_kcal"),
        pl.col("exercise_min").round(0),
        pl.col("all_rings_closed").alias("rings"),
        pl.col("resting_hr_bpm").round(1).alias("rhr"),
        pl.col("hrv_sdnn_sleep_ms").round(1).alias("hrv"),
        pl.col("vo2max").round(2),
        pl.col("vo2max_asof").round(2),
        pl.col("respiratory_rate_sleep").round(2).alias("resp"),
        pl.col("sleep_asleep_min").round(0).alias("asleep"),
        pl.col("bedtime_h").round(3).alias("bedtime"),
        pl.col("workout_min").round(1),
        pl.col("n_workouts").alias("workouts"),
        "run_km",
        "tz_name",
        pl.col("is_non_default_tz").alias("away"),
        "rhr_lo",
        "rhr_hi",
        "z_rhr",
        "hrv_lo",
        "hrv_hi",
        "z_hrv",
    )
    return [{k: v for k, v in r.items() if v is not None} for r in rows.to_dicts()]


def workouts(wh: Warehouse) -> list[dict[str, Any]]:
    """Counted workouts: date, kind and minutes."""
    from apple_health.dashboard.workouts import kind_label

    w = wh.read("marts", "mart_workout").filter(pl.col("is_counted")).sort("start_utc")
    return [
        {
            "d": r["local_date"],
            "label": kind_label(r["activity_type"], r["is_indoor"]),
            "min": round(r["duration_min"]),
        }
        for r in w.select("local_date", "activity_type", "is_indoor", "duration_min").iter_rows(named=True)
    ]


def build(wh: Warehouse) -> dict[str, Any]:
    from apple_health.config import load_config

    return {
        "kpis": [asdict(k) for k in KPIS],
        "days": days(wh),
        "workouts": workouts(wh),
        "references": {k.reference: bands(wh, k.reference) for k in KPIS if k.reference},
        "strain_z": load_config().settings.analytics.strain_z,
    }
