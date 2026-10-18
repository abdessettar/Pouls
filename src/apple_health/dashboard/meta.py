"""Site-wide metadata: how far the data runs, the 28-day windows, when each series starts."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse

WINDOW_DAYS = 28
YEAR_DAYS = 364  # 52 weeks: the year-earlier window starts on the same weekday

# Series whose first day is worth naming on charts (e.g. "Watch from Jan 2022").
FIRSTS = {
    "steps": "steps",
    "watch": "has_watch_data",
    "resting_hr": "resting_hr_bpm",
    "sleep": "sleep_asleep_min",
    "sleep_stages": "sleep_has_stages",
    "vo2max": "vo2max",
    "daylight": "daylight_min",
    "workouts": "n_workouts",
}


def windows(end: date) -> dict[str, dict[str, str]]:
    def span(last: date) -> dict[str, str]:
        return {"start": (last - timedelta(days=WINDOW_DAYS - 1)).isoformat(), "end": last.isoformat()}

    return {
        "current": span(end),
        "previous": span(end - timedelta(days=WINDOW_DAYS)),
        "year_ago": span(end - timedelta(days=YEAR_DAYS)),
    }


def build(wh: Warehouse) -> dict[str, Any]:
    daily = wh.read("marts", "mart_daily")
    manifest = wh.build_manifest()
    end: date = daily["local_date"].max()  # type: ignore[assignment]
    firsts = {}
    for key, col in FIRSTS.items():
        s = daily.filter(pl.col(col).is_not_null() & (pl.col(col).cast(pl.Float64) > 0))
        firsts[key] = s["local_date"].min()
    current = windows(end)["current"]
    in_window = daily.filter(pl.col("local_date") >= date.fromisoformat(current["start"]))
    return {
        "data_through": end,
        "first_day": daily["local_date"].min(),
        "export_id": manifest["export_id"],
        "built_run": manifest["run_id"],
        "window_days": WINDOW_DAYS,
        "windows": windows(end),
        "valid_days_in_window": int(in_window["is_valid_wear_day"].sum()),
        "firsts": firsts,
        "n_days": daily.height,
    }
