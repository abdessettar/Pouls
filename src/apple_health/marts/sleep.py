"""mart_sleep_night: one row per night with stage shares, regularity and the preceding day's context."""

from __future__ import annotations

import polars as pl

from apple_health.marts.analytics_tables import MART_SLEEP_NIGHT
from apple_health.transform.context import BuildContext


def _when_slept(e: pl.Expr) -> pl.Expr:
    return pl.when(pl.col("asleep_s") > 0).then(e).otherwise(None)


def _clock(col: str) -> pl.Expr:
    t = pl.col(col)
    return t.dt.hour() + t.dt.minute() / 60 + t.dt.second() / 3600


def build_sleep_nights(ctx: BuildContext) -> None:
    a = ctx.cfg.settings.analytics
    sessions = ctx.scan("agg_sleep_session").filter(pl.col("is_primary"))
    daily = ctx.scan("mart_daily").select(
        "local_date",
        "is_weekend",
        "is_non_default_tz",
        "steps",
        "daylight_min",
        "is_valid_wear_day",
        "hrv_sdnn_sleep_ms",
        "respiratory_rate_sleep",
        "resting_hr_bpm",
    )
    workouts = ctx.scan("mart_workout").filter(pl.col("is_counted"))
    prev_workouts = workouts.group_by("local_date").agg(
        pl.col("duration_min").sum().alias("prev_workout_min"),
        pl.len().cast(pl.Int32).alias("prev_n_workouts"),
    )
    bed = _clock("start_local")
    nights = (
        sessions.select(
            pl.col("sleep_date").alias("night_date"),
            "session_id",
            "start_utc",
            "start_local",
            "end_local",
            pl.when(bed < 12).then(bed + 24).otherwise(bed).alias("bedtime_h"),
            _clock("end_local").alias("waketime_h"),
            "span_s",
            # In-bed-only nights measured no sleep: asleep and stages are unknown, not 0.
            _when_slept(pl.col("asleep_s") / 60).alias("asleep_min"),
            pl.when(pl.col("in_bed_s") > 0).then(pl.col("in_bed_s") / 60).otherwise(None).alias("in_bed_min"),
            *[
                pl.when(pl.col("stage_detail_available"))
                .then(pl.col(f"{st}_s") / 60)
                .otherwise(None)
                .alias(f"{st}_min")
                for st in ("core", "deep", "rem")
            ],
            _when_slept(pl.col("awake_s") / 60).alias("awake_min"),
            _when_slept(pl.col("sleep_efficiency")).alias("efficiency"),
            pl.col("stage_detail_available").alias("has_stages"),
        )
        .with_columns(
            (pl.col("bedtime_h") + pl.col("span_s") / 7200).alias("midpoint_h"),
            *[
                pl.when(pl.col("has_stages") & (pl.col("asleep_min") > 0))
                .then(pl.col(f"{s}_min") / pl.col("asleep_min"))
                .otherwise(None)
                .alias(f"{s}_share")
                for s in ("deep", "rem", "core")
            ],
            (pl.col("night_date") - pl.duration(days=1)).alias("__prev"),
        )
        .sort("night_date")
        .with_columns(
            (
                (pl.col("bedtime_h") - pl.col("bedtime_h").shift(1).rolling_median(7, min_samples=3)) * 60
            ).alias("bedtime_dev_min")
        )
    )
    # Context of the night itself (wake-up day) and of the day before.
    nights = (
        nights.join(
            daily.select(
                "local_date",
                "hrv_sdnn_sleep_ms",
                pl.col("respiratory_rate_sleep").alias("respiratory_rate"),
                "resting_hr_bpm",
                pl.col("is_weekend").alias("is_weekend_night"),
                pl.col("is_non_default_tz").alias("__away_today"),
            ),
            left_on="night_date",
            right_on="local_date",
            how="left",
        )
        .join(
            daily.select(
                "local_date",
                pl.col("steps").alias("prev_steps"),
                pl.col("daylight_min").alias("prev_daylight_min"),
                pl.col("is_valid_wear_day").alias("prev_valid_wear_day"),
                pl.col("is_non_default_tz").alias("__away_prev"),
            ),
            left_on="__prev",
            right_on="local_date",
            how="left",
        )
        .join(prev_workouts, left_on="__prev", right_on="local_date", how="left")
    )

    # Late workout: the last counted workout ending before bedtime ended within late_workout_hours of it.
    ends = workouts.select(pl.col("end_utc").alias("__w_end")).sort("__w_end")
    nights = (
        nights.sort("start_utc")
        .join_asof(ends, left_on="start_utc", right_on="__w_end", strategy="backward")
        .with_columns(
            ((pl.col("start_utc") - pl.col("__w_end")) <= pl.duration(minutes=int(a.late_workout_hours * 60)))
            .fill_null(False)
            .alias("late_workout"),
            (pl.col("__away_today").fill_null(False) | pl.col("__away_prev").fill_null(False)).alias(
                "is_away"
            ),
            pl.col("prev_workout_min").fill_null(0.0),
            pl.col("prev_n_workouts").fill_null(0),
        )
    )
    ctx.write(MART_SLEEP_NIGHT, nights.collect())
