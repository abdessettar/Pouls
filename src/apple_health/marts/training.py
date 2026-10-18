"""mart_workout (enriched workouts), mart_training_weekly and mart_training_load."""

from __future__ import annotations

import polars as pl

from apple_health.marts.analytics_tables import (
    MART_TRAINING_LOAD,
    MART_TRAINING_WEEKLY,
    MART_WORKOUT,
    MART_WORKOUT_HR,
)
from apple_health.transform.context import BuildContext

GROUPS = {
    "Walking": "walking",
    "Hiking": "walking",
    "Running": "running",
    "TraditionalStrengthTraining": "strength",
    "FunctionalStrengthTraining": "strength",
    "CoreTraining": "strength",
    "Cycling": "cycling",
}
PACED = ["Walking", "Hiking", "Running"]
EFFORT_TYPES = [
    "HKQuantityTypeIdentifierWorkoutEffortScore",
    "HKQuantityTypeIdentifierEstimatedWorkoutEffortScore",
]


def activity_group(col: str = "activity_type") -> pl.Expr:
    return pl.col(col).replace_strict(GROUPS, default="other", return_dtype=pl.String)


def counted_flag(wk: pl.LazyFrame, ranks: pl.LazyFrame) -> pl.LazyFrame:
    """is_counted: False when the workout overlaps one from a better-ranked source (as in mart_daily)."""
    wk = wk.join(ranks, on="source_id", how="left")
    partner = wk.select(
        pl.col("workout_id").alias("overlaps_workout_id"), pl.col("priority_rank").alias("__p")
    )
    return (
        wk.join(partner, on="overlaps_workout_id", how="left")
        .with_columns(
            (pl.col("__p").is_null() | (pl.col("priority_rank") <= pl.col("__p"))).alias("is_counted")
        )
        .drop("__p")
    )


def zone_minutes(ctx: BuildContext) -> pl.LazyFrame:
    """Minutes per zone 1-5 at workout level: zones ranked by their lower bound within each group."""
    z = ctx.scan("fct_workout_zone").filter(
        pl.col("activity_id").is_null() & (pl.col("zone_type") == "HeartRate")
    )
    z = z.with_columns(
        pl.col("minimum")
        .fill_null(-1.0)
        .rank("ordinal")
        .over("workout_id", "group_ordinal")
        .cast(pl.Int32)
        .alias("zi")
    ).with_columns(pl.col("zi").clip(1, 5))
    return (
        z.group_by("workout_id")
        .agg(
            [
                (pl.col("duration_s").filter(pl.col("zi") == i).sum() / 60).alias(f"zone{i}_min")
                for i in range(1, 6)
            ]
        )
        .with_columns(pl.lit(True).alias("has_zones"))
    )


def build_workout_marts(ctx: BuildContext) -> None:
    a = ctx.cfg.settings.analytics
    ranks = ctx.scan("dim_source").select("source_id", "source_name", "priority_rank")
    wk = counted_flag(ctx.scan("fct_workout"), ranks)
    effort = (
        ctx.scan("bridge_workout_sample")
        .join(ctx.scan("fct_quantity_sample").select("sample_id", "type_identifier", "value"), on="sample_id")
        .filter(pl.col("type_identifier").is_in(EFFORT_TYPES))
        .with_columns((pl.col("type_identifier") == EFFORT_TYPES[0]).alias("__measured"))
        .sort("__measured", descending=True)
        .group_by("workout_id")
        .agg(pl.col("value").first().alias("effort_score"))
    )
    volume = (
        ctx.scan("fct_workout_metadata")
        .filter((pl.col("owner_kind") == "workout") & (pl.col("key") == "Total Weight Lifted"))
        .group_by("workout_id")
        .agg(pl.col("value_canonical").first().alias("strength_volume_kg"))
    )
    dist = (
        pl.col("distance_walking_running_km").fill_null(0)
        + pl.col("distance_cycling_km").fill_null(0)
        + pl.col("distance_swimming_m").fill_null(0) / 1000
    )
    weights = a.zone_weights
    trimp = sum((pl.col(f"zone{i + 1}_min") * w for i, w in enumerate(weights)), pl.lit(0.0))
    out = (
        wk.join(zone_minutes(ctx), on="workout_id", how="left")
        .join(effort, on="workout_id", how="left")
        .join(volume, on="workout_id", how="left")
        .with_columns(
            activity_group().alias("activity_group"),
            (pl.col("duration_s") / 60).alias("duration_min"),
            (pl.col("elapsed_s") / 60).alias("elapsed_min"),
            pl.when(dist > 0).then(dist).otherwise(None).alias("distance_km"),
            pl.col("heart_rate_avg_bpm").alias("avg_hr_bpm"),
            pl.col("heart_rate_max_bpm").alias("max_hr_bpm"),
            pl.col("has_zones").fill_null(False),
            pl.col("elevation_ascended_m").alias("elevation_gain_m"),
        )
        .with_columns(
            pl.when(pl.col("has_zones")).then(trimp).otherwise(None).alias("trimp"),
            pl.when(pl.col("activity_type").is_in(PACED) & (pl.col("distance_km") > 0))
            .then(pl.col("duration_s") / pl.col("distance_km"))
            .otherwise(None)
            .alias("pace_s_per_km"),
            pl.when(pl.col("distance_km") > 0)
            .then(pl.col("distance_km") / (pl.col("duration_s") / 3600))
            .otherwise(None)
            .alias("speed_kmh"),
        )
    )
    # A session logged by JEFIT and recorded by the Watch counts as the Watch's; the weight lifted only
    # exists on the JEFIT copy, so carry it over to the counted one.
    lifted = (
        out.filter(
            ~pl.col("is_counted")
            & pl.col("strength_volume_kg").is_not_null()
            & pl.col("overlaps_workout_id").is_not_null()
        )
        .group_by(pl.col("overlaps_workout_id").alias("workout_id"))
        .agg(pl.col("strength_volume_kg").sum().alias("__lifted"))
    )
    out = (
        out.join(lifted, on="workout_id", how="left")
        .with_columns(
            pl.when(pl.col("is_counted"))
            .then(pl.coalesce("strength_volume_kg", "__lifted"))
            .otherwise(pl.col("strength_volume_kg"))
            .alias("strength_volume_kg")
        )
        .drop("__lifted")
    )
    ctx.write(MART_WORKOUT, out.collect())

    counted = ctx.scan("mart_workout").filter(pl.col("is_counted"))
    weekly = (
        counted.with_columns(
            (pl.col("local_date") - pl.duration(days=pl.col("local_date").dt.weekday() - 1)).alias(
                "week_start"
            )
        )
        .group_by("week_start", "activity_group")
        .agg(
            pl.len().cast(pl.Int32).alias("sessions"),
            pl.col("duration_min").sum().alias("minutes"),
            pl.col("distance_km").sum().alias("distance_km"),
            pl.col("active_energy_kcal").sum().alias("active_energy_kcal"),
            pl.when(pl.col("trimp").count() > 0).then(pl.col("trimp").sum()).otherwise(None).alias("trimp"),
            (pl.col("zone4_min").fill_null(0) + pl.col("zone5_min").fill_null(0))
            .sum()
            .alias("zone_minutes_4_5"),
        )
        .with_columns(
            pl.col("week_start").dt.iso_year().cast(pl.Int32).alias("iso_year"),
            pl.col("week_start").dt.week().cast(pl.Int32).alias("iso_week"),
        )
    )
    ctx.write(MART_TRAINING_WEEKLY, weekly.collect())

    per_day = (
        counted.group_by("local_date")
        .agg(pl.col("trimp").sum().alias("trimp"), pl.col("duration_min").sum().alias("workout_min"))
        .collect()
    )
    if per_day.height == 0:
        ctx.write(MART_TRAINING_LOAD, pl.DataFrame(schema=MART_TRAINING_LOAD.schema()))
        return
    last = ctx.scan("mart_daily").select(pl.col("local_date").max()).collect().item()
    first = per_day["local_date"].min()
    grid = pl.DataFrame(
        {"local_date": pl.date_range(first, max(last, per_day["local_date"].max()), "1d", eager=True)}
    )
    load = (
        grid.join(per_day, on="local_date", how="left")
        .with_columns(pl.col("trimp", "workout_min").fill_null(0.0))
        .sort("local_date")
        .with_columns(
            pl.col("trimp").rolling_mean(a.acute_days, min_samples=a.acute_days).alias("acute_load"),
            pl.col("trimp").rolling_mean(a.chronic_days, min_samples=a.chronic_days).alias("chronic_load"),
        )
        .with_columns(
            pl.when(pl.col("chronic_load") > 0)
            .then(pl.col("acute_load") / pl.col("chronic_load"))
            .otherwise(None)
            .alias("acwr")
        )
    )
    ctx.write(MART_TRAINING_LOAD, load)


def build_workout_hr(ctx: BuildContext) -> None:
    """mart_workout_hr: per-minute heart rate of counted workouts, for session curves."""
    wk = (
        ctx.scan("mart_workout")
        .filter(pl.col("is_counted"))
        .select("workout_id", "start_utc", "end_utc")
        .sort("start_utc")
        .collect()
    )
    if wk.height == 0:
        ctx.write(MART_WORKOUT_HR, pl.DataFrame(schema=MART_WORKOUT_HR.schema()))
        return
    hr = (
        ctx.scan("fct_quantity_sample")
        .filter(
            (pl.col("type") == "HeartRate")
            & ~pl.col("is_outlier").fill_null(False)
            & (pl.col("start_utc") >= wk["start_utc"].min())
        )
        .select(pl.col("start_utc").alias("t"), pl.col("value").alias("hr"))
        .sort("t")
        .collect()
    )
    per_minute = (
        hr.join_asof(wk, left_on="t", right_on="start_utc", strategy="backward")
        .filter(pl.col("workout_id").is_not_null() & (pl.col("t") <= pl.col("end_utc")))
        .with_columns(
            ((pl.col("t") - pl.col("start_utc")).dt.total_seconds() // 60).cast(pl.Int32).alias("minute")
        )
        .group_by("workout_id", "minute")
        .agg(pl.col("hr").mean().alias("hr_bpm"), pl.len().cast(pl.Int32).alias("n_samples"))
        .sort("workout_id", "minute")
    )
    ctx.write(MART_WORKOUT_HR, per_minute)
