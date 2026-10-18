"""Sleep page: barcode, duration, regularity, stages, and what goes with better nights."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.dashboard.references import bands

MIN_NIGHTS = 10
STAGE_CODE = {"Core": 0, "Deep": 1, "REM": 2, "Awake": 3, "AsleepUnspecified": 4}


def _offset_min(ts: datetime, night: date) -> int:
    """Minutes from midnight of the wake-up day (negative = the evening before)."""
    return round((ts - datetime(night.year, night.month, night.day)).total_seconds() / 60)


def barcode(wh: Warehouse) -> list[dict[str, Any]]:
    """Every night as compact segments [start_min, end_min, stage] relative to wake-day midnight."""
    nights = wh.read("marts", "mart_sleep_night").sort("night_date")
    sessions = (
        wh.read("derived", "agg_sleep_session")
        .filter(pl.col("is_primary"))
        .select("session_id", "start_utc", "end_utc")
    )
    nights = nights.join(sessions, on="session_id", how="left")
    watch = wh.read("curated", "dim_source").filter(pl.col("source_kind") == "watch").select("source_id")
    stages = (
        wh.scan("curated", "fct_category_sample")
        .filter((pl.col("type") == "SleepAnalysis") & (pl.col("label") != "InBed"))
        .join(watch.lazy(), on="source_id")
        .select("start_utc", "end_utc", "start_local", "end_local", "label")
        .sort("start_utc")
        .collect()
    )
    # Attach each stage sample to its night with an as-of join on the session start.
    sess = nights.select(
        "night_date", pl.col("start_utc").alias("__s0"), pl.col("end_utc").alias("__s1")
    ).sort("__s0")
    st = stages.join_asof(sess, left_on="start_utc", right_on="__s0", strategy="backward").filter(
        pl.col("end_utc") <= pl.col("__s1")
    )
    by_night: dict[date, list[list[int]]] = {}
    for r in st.iter_rows(named=True):
        by_night.setdefault(r["night_date"], []).append(
            [
                _offset_min(r["start_local"], r["night_date"]),
                _offset_min(r["end_local"], r["night_date"]),
                STAGE_CODE.get(r["label"], 4),
            ]
        )
    out = []
    for r in nights.iter_rows(named=True):
        out.append(
            {
                "d": r["night_date"],
                "s": _offset_min(r["start_local"], r["night_date"]),
                "e": _offset_min(r["end_local"], r["night_date"]),
                "a": None if r["asleep_min"] is None else round(r["asleep_min"]),
                "g": by_night.get(r["night_date"], []),
            }
        )
    return out


def nights(wh: Warehouse) -> list[dict[str, Any]]:
    """One row per night with what the monthly charts and the comparisons need (empty fields left out)."""
    n = wh.read("marts", "mart_sleep_night").filter(pl.col("asleep_min").is_not_null()).sort("night_date")
    rows = n.select(
        pl.col("night_date").alias("d"),
        pl.col("asleep_min").round(0).alias("asleep"),
        pl.col("efficiency").round(4).alias("eff"),
        pl.col("bedtime_h").round(3).alias("bed"),
        pl.col("waketime_h").round(3).alias("wake"),
        pl.col("midpoint_h").round(3).alias("mid"),
        pl.col("bedtime_dev_min").round(0).alias("dev"),
        pl.col("deep_share").round(4).alias("deep"),
        pl.col("rem_share").round(4).alias("rem"),
        pl.col("core_share").round(4).alias("core"),
        (pl.col("awake_min") / (pl.col("asleep_min") + pl.col("awake_min"))).round(4).alias("awake"),
        pl.col("has_stages").alias("staged"),
        pl.col("is_weekend_night").alias("weekend"),
        pl.col("is_away").alias("away"),
        pl.col("hrv_sdnn_sleep_ms").round(1).alias("hrv"),
        pl.col("prev_steps").round(0),
        pl.col("prev_daylight_min").round(0).alias("prev_daylight"),
        pl.col("prev_n_workouts").alias("prev_workouts"),
        "late_workout",
        pl.col("prev_valid_wear_day").alias("prev_valid"),
    )
    return [{k: v for k, v in r.items() if v is not None} for r in rows.to_dicts()]


def build(wh: Warehouse) -> dict[str, Any]:
    from apple_health.dashboard.meta import build as meta_build

    meta = meta_build(wh)
    return {
        "nights": nights(wh),
        "min_nights": MIN_NIGHTS,
        "stages_from": meta["firsts"]["sleep_stages"],
        "references": {
            k: bands(wh, k)
            for k in ("sleep_duration", "sleep_efficiency", "deep_sleep_share", "rem_sleep_share")
        },
    }


def barcode_data(wh: Warehouse) -> dict[str, Any]:
    """The night-by-night barcode (Sleep and Overview), in its own file so Overview stays light."""
    return {"barcode": barcode(wh), "stage_codes": {v: k for k, v in STAGE_CODE.items()}}
