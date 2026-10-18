"""Places page: routes on the map (encoded polylines), areas, trips and how days away differ."""

from __future__ import annotations

from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.dashboard.polyline import encode


def routes(wh: Warehouse) -> list[dict[str, Any]]:
    r = wh.read("marts", "mart_route").sort("start_utc")
    return r.select(
        "route_id",
        "workout_id",
        "local_date",
        "activity_type",
        "activity_group",
        pl.col("distance_km").round(2),
        pl.col("duration_min").round(0),
        pl.col("elevation_gain_m").round(0),
        "area_id",
        "area_name",
        pl.col("center_lat").round(5),
        pl.col("center_lon").round(5),
    ).to_dicts()


def tracks(wh: Warehouse) -> dict[str, str]:
    t = wh.read("marts", "mart_route_track").sort("route_id", "seq")
    return {
        rid: encode(list(zip(g["lat"], g["lon"], strict=True)))
        for (rid,), g in t.group_by("route_id", maintain_order=True)
    }


def areas(wh: Warehouse) -> list[dict[str, Any]]:
    r = wh.read("marts", "mart_route")
    return (
        r.group_by("area_id", "area_name")
        .agg(
            pl.len().alias("routes"),
            pl.col("distance_km").sum().round(0).alias("km"),
            pl.col("min_lat").min(),
            pl.col("min_lon").min(),
            pl.col("max_lat").max(),
            pl.col("max_lon").max(),
            pl.col("local_date").min().alias("first"),
            pl.col("local_date").max().alias("last"),
        )
        .sort("area_id")
        .to_dicts()
    )


def trips(wh: Warehouse, default_tz: str) -> dict[str, Any]:
    """Periods outside the home time zone. Home vs away comparisons are computed in the page, for its
    date range, from the daily rows in overview.json."""
    p = (
        wh.read("curated", "dim_timezone_period")
        .filter(pl.col("tz_name") != default_tz)
        .select(
            "tz_name",
            pl.col("valid_from_utc").dt.date().alias("start"),
            pl.col("valid_to_utc").dt.date().alias("end"),
            "n_evidence",
        )
    )
    return {"periods": p.sort("start").to_dicts()}


def build(wh: Warehouse) -> dict[str, Any]:
    from apple_health.config import load_config

    return {
        "routes": routes(wh),
        "areas": areas(wh),
        "trips": trips(wh, load_config().settings.default_timezone),
        "home_tz": load_config().settings.default_timezone,
    }
