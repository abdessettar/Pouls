"""Workouts page: every kind of workout, its sessions, and each session's heart rate per minute.

A "kind" is the Apple activity type, split into indoor and outdoor where the workout says so (the
Watch's Indoor Cycle is Cycling with the indoor flag). Only counted workouts appear: a session
recorded by two apps shows once.
"""

from __future__ import annotations

import re
from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse

LABELS = {
    "TraditionalStrengthTraining": "Strength training",
    "FunctionalStrengthTraining": "Functional strength training",
    "HighIntensityIntervalTraining": "HIIT",
    "MixedCardio": "Mixed cardio",
    "CoreTraining": "Core training",
    "StairClimbing": "Stair climbing",
    "Elliptical": "Elliptical",
    "Yoga": "Yoga",
}
# How speed reads for each kind: min/km on foot, km/h on wheels, min/100 m in water.
SPEED = {"Walking": "pace", "Running": "pace", "Hiking": "pace", "Cycling": "speed", "Swimming": "swim"}
# Kinds done outside, where Apple's weather at the start describes the session (Apple records it for
# every workout, a gym session included).
OUTDOOR = {"Walking", "Running", "Cycling", "Hiking"}
INDOOR_VARIANTS = {"Walking", "Running", "Cycling"}


def _words(name: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).capitalize()


def _indoor(activity_type: str, is_indoor: bool | None) -> bool:
    # Apple sets the indoor flag on many workouts; only these come as separate indoor and outdoor kinds.
    return bool(is_indoor) and activity_type in INDOOR_VARIANTS


def kind_key(activity_type: str, is_indoor: bool | None) -> str:
    return f"{activity_type}:indoor" if _indoor(activity_type, is_indoor) else activity_type


def kind_label(activity_type: str, is_indoor: bool | None) -> str:
    base = LABELS.get(activity_type, _words(activity_type))
    return f"Indoor {base.lower()}" if _indoor(activity_type, is_indoor) else base


def sessions(wh: Warehouse) -> pl.DataFrame:
    w = wh.read("marts", "mart_workout").filter(pl.col("is_counted"))
    zones = (
        wh.scan("curated", "fct_workout_zone")
        .filter(pl.col("activity_id").is_null() & (pl.col("zone_type") == "HeartRate"))
        .sort("workout_id", "minimum", nulls_last=False)
        .group_by("workout_id", maintain_order=True)
        .agg(pl.col("minimum").fill_null(0).round(0).alias("zone_lo"))
        .collect()
    )
    routes = (
        wh.read("marts", "mart_route")
        .sort("start_utc")
        .group_by("workout_id", maintain_order=True)
        .agg(pl.col("route_id").first())
    )
    extra = wh.read("curated", "fct_workout").select(
        "workout_id", "swimming_location_type", "lap_length_m", "step_count", "heart_rate_min_bpm"
    )
    keys = [kind_key(t, i) for t, i in w.select("activity_type", "is_indoor").iter_rows()]
    return (
        w.with_columns(pl.Series("kind", keys, dtype=pl.String))
        .join(zones, on="workout_id", how="left")
        .join(routes, on="workout_id", how="left")
        .join(extra, on="workout_id", how="left")
        .sort("start_utc")
    )


def kinds(s: pl.DataFrame) -> list[dict[str, Any]]:
    out = []
    for (key,), g in s.group_by("kind"):
        t, indoor = g["activity_type"][0], g["is_indoor"][0]
        out.append(
            {
                "key": key,
                "label": kind_label(t, indoor),
                "activity_type": t,
                "group": g["activity_group"][0],
                "speed": SPEED.get(t),
                "outdoor": t in OUTDOOR and not _indoor(t, indoor),
                "sessions": g.height,
                "minutes": g["duration_min"].sum(),
                "first": g["local_date"].min(),
                "last": g["local_date"].max(),
            }
        )
    return sorted(out, key=lambda k: (-k["sessions"], k["label"]))


def build(wh: Warehouse) -> dict[str, Any]:
    s = sessions(wh)
    rows = s.select(
        pl.col("workout_id").alias("id"),
        "kind",
        pl.col("local_date").alias("d"),
        pl.col("start_local").dt.strftime("%Y-%m-%dT%H:%M").alias("start"),
        "source_name",
        pl.col("duration_min").round(1),
        pl.col("elapsed_min").round(1),
        pl.col("distance_km").round(3),
        pl.col("active_energy_kcal").round(0),
        pl.col("avg_hr_bpm").round(0),
        pl.col("max_hr_bpm").round(0),
        pl.col("heart_rate_min_bpm").round(0).alias("min_hr_bpm"),
        *[pl.col(f"zone{i}_min").round(1) for i in range(1, 6)],
        "zone_lo",
        pl.col("trimp").round(0),
        "effort_score",
        pl.col("avg_mets").round(1),
        pl.col("pace_s_per_km").round(0),
        pl.col("speed_kmh").round(2),
        pl.col("elevation_gain_m").round(0),
        pl.col("strength_volume_kg").round(0),
        pl.col("weather_temperature_c").round(1),
        pl.col("weather_humidity_pct").round(0),
        "step_count",
        pl.col("swimming_location_type").cast(pl.Int32),
        "lap_length_m",
        "route_id",
        "tz_name",
    )
    # Most fields apply to some kinds only; leaving out the empty ones halves the file.
    compact = [{k: v for k, v in r.items() if v is not None} for r in rows.to_dicts()]
    return {"kinds": kinds(s), "sessions": compact}


def heart_rate(wh: Warehouse) -> dict[str, list[int | None]]:
    """Per-minute heart rate of each counted workout: index = minute from the start (null = no sample)."""
    h = wh.read("marts", "mart_workout_hr")
    out: dict[str, list[int | None]] = {}
    for (wid,), g in h.group_by("workout_id"):
        minutes, values = g["minute"].to_list(), g["hr_bpm"].to_list()
        series: list[int | None] = [None] * (max(minutes) + 1)
        for m, v in zip(minutes, values, strict=True):
            series[m] = round(v)
        out[str(wid)] = series
    return out
