"""Heart page: resting HR, HRV, VO2max, recovery, breathing and oxygen, heart rate through the day."""

from __future__ import annotations

from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.dashboard.references import bands

SERIES = {
    "resting_hr": "resting_hr_bpm",
    "hrv": "hrv_sdnn_sleep_ms",
    "respiratory_rate": "respiratory_rate_sleep",
    "spo2": "spo2_median",
}
RECOVERY_MATCH_MIN = 30  # a recovery reading belongs to a workout that ended at most this long before


def daily_series(wh: Warehouse) -> dict[str, list[dict[str, Any]]]:
    b = wh.read("marts", "mart_baselines")
    out = {}
    for key, metric in SERIES.items():
        out[key] = (
            b.filter(pl.col("metric") == metric)
            .select(
                pl.col("local_date").alias("d"),
                pl.col("value").round(3).alias("v"),
                pl.col("roll_long_median").round(3).alias("m"),
                pl.col("normal_p10").round(3).alias("lo"),
                pl.col("normal_p90").round(3).alias("hi"),
            )
            .sort("d")
            .to_dicts()
        )
    return out


def vo2max(wh: Warehouse) -> list[dict[str, Any]]:
    d = wh.read("marts", "mart_daily").filter(pl.col("vo2max").is_not_null())
    return (
        d.select(pl.col("local_date").alias("d"), pl.col("vo2max").round(2).alias("v")).sort("d").to_dicts()
    )


def recovery(wh: Warehouse) -> list[dict[str, Any]]:
    """1-minute recovery readings, attributed to the counted workout that ended just before."""
    rec = (
        wh.scan("curated", "fct_quantity_sample")
        .filter(pl.col("type") == "HeartRateRecoveryOneMinute")
        .select("start_utc", "local_date", pl.col("value").round(1))
        .sort("start_utc")
        .collect()
    )
    wk = (
        wh.read("marts", "mart_workout")
        .filter(pl.col("is_counted"))
        .select(pl.col("end_utc").alias("__end"), "activity_group")
        .sort("__end")
    )
    j = rec.join_asof(wk, left_on="start_utc", right_on="__end", strategy="backward").with_columns(
        pl.when((pl.col("start_utc") - pl.col("__end")) <= pl.duration(minutes=RECOVERY_MATCH_MIN))
        .then(pl.col("activity_group"))
        .otherwise(pl.lit("unmatched"))
        .alias("group")
    )
    return j.select(pl.col("local_date").alias("d"), pl.col("value").alias("v"), "group").to_dicts()


def strain(wh: Warehouse, z: float) -> dict[str, Any]:
    b = wh.read("marts", "mart_baselines").filter(
        pl.col("metric").is_in(["hrv_sdnn_sleep_ms", "resting_hr_bpm"])
    )
    wide = (
        b.filter(pl.col("metric") == "hrv_sdnn_sleep_ms")
        .select("local_date", pl.col("z").alias("z_hrv"))
        .join(
            b.filter(pl.col("metric") == "resting_hr_bpm").select("local_date", pl.col("z").alias("z_rhr")),
            on="local_date",
            how="full",
            coalesce=True,
        )
        .sort("local_date")
        .with_columns(((pl.col("z_hrv") <= -z) & (pl.col("z_rhr") >= z)).fill_null(False).alias("strained"))
    )
    monthly = (
        wide.group_by(pl.col("local_date").dt.month_start().alias("month"))
        .agg(pl.col("strained").sum().alias("strained"), pl.len().alias("days"))
        .sort("month")
    )
    return {
        "days": wide.select(
            pl.col("local_date").alias("d"), pl.col("z_hrv").round(2), pl.col("z_rhr").round(2), "strained"
        ).to_dicts(),
        "monthly": monthly.to_dicts(),
    }


def build(wh: Warehouse) -> dict[str, Any]:
    from apple_health.config import load_config

    cfg = load_config()
    return {
        "series": daily_series(wh),
        "vo2max": vo2max(wh),
        "recovery": recovery(wh),
        "strain": strain(wh, cfg.settings.analytics.strain_z),
        "strain_z": cfg.settings.analytics.strain_z,
        "references": {
            k: bands(wh, k)
            for k in ("resting_hr", "hrv_sdnn", "vo2max", "hr_recovery", "respiratory_rate", "spo2")
        },
    }
