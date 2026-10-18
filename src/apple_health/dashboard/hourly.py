"""Hour-by-hour activity for every valid wear day: steps and mean heart rate per local hour.

Activity's "shape of a day" and Heart's "heart rate through the day" average these over whatever
date range the page shows, so they ship per day rather than pre-aggregated by year.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse


def build(wh: Warehouse) -> list[dict[str, Any]]:
    days = (
        wh.read("marts", "mart_daily").filter(pl.col("is_valid_wear_day")).select("local_date", "day_of_week")
    )
    hourly = (
        wh.scan("derived", "agg_quantity_hourly")
        .filter(pl.col("type").is_in(["StepCount", "HeartRate"]))
        .select("type", "local_date", "hour", "value")
        .join(days.lazy().select("local_date"), on="local_date")
        .collect()
    )
    by_day: dict[Any, dict[str, list[float | None]]] = {}
    for typ, d, h, v in hourly.iter_rows():
        slot = by_day.setdefault(d, {"StepCount": [0.0] * 24, "HeartRate": [None] * 24})
        slot[typ][h] = v
    out = []
    for d, dow in days.sort("local_date").iter_rows():
        slot = by_day.get(d, {"StepCount": [0.0] * 24, "HeartRate": [None] * 24})
        out.append(
            {
                "d": d,
                "dow": dow,
                "steps": [round(v) for v in slot["StepCount"]],  # hours without samples count as zero
                "hr": [None if v is None else round(v, 1) for v in slot["HeartRate"]],
            }
        )
    return out
