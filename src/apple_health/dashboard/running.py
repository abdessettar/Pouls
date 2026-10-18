"""Running page: runs, weekly distance, efficiency, form, best efforts, and per-run detail."""

from __future__ import annotations

from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.dashboard.polyline import encode

PROFILE_POINTS = 160  # elevation profile resolution per run


def runs(wh: Warehouse) -> pl.DataFrame:
    weather = wh.read("marts", "mart_workout").select(
        "workout_id", "weather_temperature_c", "weather_humidity_pct", "is_indoor"
    )
    return wh.read("marts", "mart_run").join(weather, on="workout_id", how="left").sort("start_utc")


def detail(wh: Warehouse, r: pl.DataFrame) -> dict[str, Any]:
    """Per run: splits, an elevation profile and the route geometry (encoded polyline)."""
    ids = r["workout_id"].to_list()
    splits = (
        wh.read("marts", "mart_run_split").filter(pl.col("workout_id").is_in(ids)).sort("workout_id", "split")
    )
    routes = (
        wh.read("marts", "mart_route")
        .filter(pl.col("workout_id").is_in(ids))
        .select("route_id", "workout_id")
    )
    track = (
        wh.read("marts", "mart_route_track").join(routes, on="route_id").sort("workout_id", "dist_m", "seq")
    )
    out: dict[str, Any] = {}
    for wid in ids:
        out[wid] = {"splits": [], "profile": [], "polyline": None}
    for (wid,), g in splits.group_by("workout_id", maintain_order=True):
        out[wid]["splits"] = g.select(
            "split",
            pl.col("distance_m").round(0),
            pl.col("duration_s").round(0),
            pl.col("pace_s_per_km").round(0),
            pl.col("elevation_change_m").round(1),
            pl.col("avg_hr_bpm").round(0),
        ).rows()
    for (wid,), g in track.group_by("workout_id", maintain_order=True):
        step = max(1, g.height // PROFILE_POINTS)
        prof = g.gather_every(step).select(pl.col("dist_m").round(0), pl.col("elevation_m").round(1)).rows()
        out[wid]["profile"] = prof
        out[wid]["polyline"] = encode(list(zip(g["lat"], g["lon"], strict=True)))
    return out


def build(wh: Warehouse) -> dict[str, Any]:
    r = runs(wh)
    table = r.select(
        "workout_id",
        "local_date",
        "start_local",
        pl.col("distance_km").round(2),
        pl.col("duration_min").round(1),
        pl.col("pace_s_per_km").round(0),
        pl.col("avg_hr_bpm").round(0),
        pl.col("m_per_beat").round(3),
        pl.col("power_w").round(0),
        pl.col("stride_m").round(2),
        pl.col("ground_contact_ms").round(0),
        pl.col("vertical_oscillation_cm").round(1),
        pl.col("elevation_gain_m").round(0),
        "has_route",
        pl.col("best_1k_s").round(0),
        pl.col("best_5k_s").round(0),
        pl.col("best_10k_s").round(0),
        pl.col("weather_temperature_c").round(1),
        pl.col("weather_humidity_pct").round(0),
        "is_indoor",
    )
    weekly = (
        r.group_by(
            (pl.col("local_date") - pl.duration(days=pl.col("local_date").dt.weekday() - 1)).alias("week")
        )
        .agg(pl.col("distance_km").sum().round(1).alias("km"), pl.len().alias("runs"))
        .sort("week")
    )
    best = (
        r.group_by(pl.col("local_date").dt.month_start().alias("month"))
        .agg(*[pl.col(c).min().alias(c) for c in ("best_1k_s", "best_5k_s", "best_10k_s")])
        .sort("month")
    )
    records = wh.read("marts", "mart_records").filter(pl.col("category") == "running")
    return {
        "runs": table.to_dicts(),
        "weekly": weekly.to_dicts(),
        "best_monthly": best.to_dicts(),
        "records": records.to_dicts(),
        "detail": detail(wh, r),
    }
