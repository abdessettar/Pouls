"""Notes page: references with their sources, coverage, sources and devices, what is not shown."""

from __future__ import annotations

from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.dashboard.references import sources as reference_sources

# Data families for the coverage grid: (label, mart_daily expression meaning "the day has it").
COVERAGE = [
    ("Steps", pl.col("steps").is_not_null()),
    ("Watch worn", pl.col("has_watch_data")),
    ("Resting heart rate", pl.col("resting_hr_bpm").is_not_null()),
    ("HRV in sleep", pl.col("hrv_sdnn_sleep_ms").is_not_null()),
    ("Breathing rate", pl.col("respiratory_rate_sleep").is_not_null()),
    ("Blood oxygen", pl.col("spo2_median").is_not_null()),
    ("VO2max", pl.col("vo2max").is_not_null()),
    ("Sleep", pl.col("sleep_asleep_min").is_not_null() | pl.col("sleep_in_bed_min").is_not_null()),
    ("Sleep stages", pl.col("sleep_has_stages")),
    ("Walking metrics", pl.col("walking_speed_kmh").is_not_null()),
    ("Daylight", pl.col("daylight_min").is_not_null()),
    ("Sound levels", pl.col("env_audio_h").is_not_null()),
]

# Records in the export that no page shows: (data types, what, why).
NOT_SHOWN = [
    (
        (
            "EnvironmentalAudioExposure",
            "HeadphoneAudioExposure",
            "EnvironmentalSoundReduction",
            "AudioExposureEvent",
            "HeadphoneAudioExposureEvent",
        ),
        "Sound and hearing",
        "Left out of the pages; daily sound levels stay in the Every day explorer.",
    ),
    (("AppleSleepingWristTemperature",), "Wrist temperature in sleep", "No page charts it yet."),
    (
        ("BodyMass", "Height"),
        "Body weight and height",
        "Weight is on the Coach page only; height is not charted.",
    ),
    (("MindfulSession",), "Mindful minutes", "No page charts them yet."),
    (("HighHeartRateEvent",), "High heart-rate notifications", "Alerts, not measurements; not charted."),
    (
        ("SixMinuteWalkTestDistance", "StairAscentSpeed", "StairDescentSpeed"),
        "Six-minute walk and stair speed estimates",
        "iPhone estimates without a page of their own.",
    ),
    (("SleepDurationGoal",), "Sleep goal", "A setting, not a measurement."),
    (
        ("SwimmingStrokeCount", "DistanceSwimming"),
        "Swimming detail",
        "Counted in workout distance only.",
    ),
    (
        ("AppleWalkingSteadiness",),
        "Walking steadiness",
        "In the explorer; Apple publishes classes but no numeric cut-offs, so no reference band.",
    ),
]


def coverage(wh: Warehouse) -> list[dict[str, Any]]:
    """Share of days per month that have each data family."""
    d = wh.scan("marts", "mart_daily").with_columns(pl.col("local_date").dt.truncate("1mo").alias("month"))
    return (
        d.group_by("month")
        .agg(
            pl.len().alias("days"),
            *[expr.fill_null(False).cast(pl.Int32).sum().alias(label) for label, expr in COVERAGE],
        )
        .unpivot(index=["month", "days"], variable_name="family", value_name="n")
        .with_columns((pl.col("n") / pl.col("days")).round(3).alias("share"))
        .select("month", "family", "share")
        .sort("family", "month")
        .collect()
        .to_dicts()
    )


def sources(wh: Warehouse) -> list[dict[str, Any]]:
    """Recording sources (apps and devices) with their priority and what they recorded."""
    cov = (
        wh.scan("derived", "agg_data_coverage")
        .group_by("source_id")
        .agg(
            pl.col("n_samples").sum().alias("records"),
            pl.col("type").n_unique().alias("types"),
            pl.col("local_date").min().alias("first"),
            pl.col("local_date").max().alias("last"),
        )
    )
    return (
        wh.scan("curated", "dim_source")
        .select("source_id", "source_name", "source_kind", "priority_rank")
        .join(cov, on="source_id", how="left")
        .sort("priority_rank", pl.col("records").fill_null(0), descending=[False, True])
        .drop("source_id")
        .collect()
        .to_dicts()
    )


def devices(wh: Warehouse) -> list[dict[str, Any]]:
    """Hardware seen in the records, by class (device names are left out: they can carry a name)."""
    return (
        wh.read("curated", "dim_device")
        .filter(pl.col("model").is_not_null() & ~pl.col("model").str.starts_with("0x"))
        .group_by("device_class", "manufacturer", "model")
        .agg(pl.col("hardware").drop_nulls().unique().sort().alias("hardware"))
        .sort("device_class", "manufacturer", "model", nulls_last=True)
        .to_dicts()
    )


def not_shown(wh: Warehouse) -> list[dict[str, Any]]:
    counts = dict(wh.read("curated", "dim_data_type").select("type", "n_raw_records").iter_rows())
    audiograms = wh.read("curated", "fct_audiogram").height
    out = []
    for types, what, why in NOT_SHOWN:
        n = sum(counts.get(t) or 0 for t in types)
        if n:
            out.append({"what": what, "records": n, "why": why})
    if audiograms:
        out.append(
            {"what": "Audiograms", "records": audiograms, "why": "Hearing tests; part of sound and hearing."}
        )
    return out


def build(wh: Warehouse) -> dict[str, Any]:
    from apple_health.config import load_config

    s = load_config().settings
    a = s.analytics
    t = (
        wh.read("marts", "mart_reference")
        if (wh.root / "marts" / "mart_reference.parquet").is_file()
        else None
    )
    return {
        "references": [] if t is None else t.sort("metric", "kind", "valid_from", "seq").to_dicts(),
        "reference_sources": reference_sources(wh),
        "coverage": coverage(wh),
        "coverage_families": [label for label, _ in COVERAGE],
        "sources": sources(wh),
        "devices": devices(wh),
        "not_shown": not_shown(wh),
        "settings": {
            "default_timezone": s.default_timezone,
            "valid_day_min_worn_hours": s.valid_day_min_worn_hours,
            "rolling_long_days": a.rolling_long_days,
            "normal_range_days": a.normal_range_days,
            "baseline_days": a.baseline_days,
            "baseline_min_days": a.baseline_min_days,
            "strain_z": a.strain_z,
            "zone_weights": list(a.zone_weights),
            "acute_days": a.acute_days,
            "chronic_days": a.chronic_days,
            "late_workout_hours": a.late_workout_hours,
            "area_cluster_km": a.area_cluster_km,
        },
    }
