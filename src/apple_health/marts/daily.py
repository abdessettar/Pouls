"""Daily marts: mart_wear_hourly, mart_daily and its weekly / monthly rollups."""

from __future__ import annotations

import logging

import polars as pl

from apple_health.marts.metrics import (
    DAILY_METRICS,
    Metric,
    mart_daily_table,
    mart_monthly_table,
    mart_wear_hourly_table,
    mart_weekly_table,
    mart_yearly_table,
)
from apple_health.transform.context import BuildContext

# Workouts done outside: Apple's weather at their start describes the day's conditions (it records the
# weather for every workout, gym sessions included).
OUTDOOR_WORKOUTS = ["Walking", "Running", "Cycling", "Hiking"]

log = logging.getLogger(__name__)

WATCH = "Apple Watch"

# agg_quantity_daily type -> {mart column: (agg field, expected canonical unit)}
FROM_DAILY_AGG: dict[str, dict[str, tuple[str, str]]] = {
    "StepCount": {"steps": ("value", "count")},
    "DistanceWalkingRunning": {"distance_walking_running_km": ("value", "km")},
    "DistanceCycling": {"distance_cycling_km": ("value", "km")},
    "FlightsClimbed": {"flights_climbed": ("value", "count")},
    "ActiveEnergyBurned": {"active_energy_kcal": ("value", "kcal")},
    "BasalEnergyBurned": {"basal_energy_kcal": ("value", "kcal")},
    "AppleExerciseTime": {"exercise_min": ("value", "min")},
    "AppleStandTime": {"stand_time_min": ("value", "min")},
    "TimeInDaylight": {"daylight_min": ("value", "min")},
    "PhysicalEffort": {"physical_effort_avg": ("value", "kcal/hr·kg")},
    "HeartRate": {
        "hr_mean_bpm": ("value", "count/min"),
        "hr_min_bpm": ("value_min", "count/min"),
        "hr_max_bpm": ("value_max", "count/min"),
    },
    "HeartRateVariabilitySDNN": {"hrv_sdnn_ms": ("value", "ms")},
    "HeartRateRecoveryOneMinute": {"hr_recovery_1min_bpm": ("value", "count/min")},
    "VO2Max": {"vo2max": ("value", "mL/min·kg")},
    "OxygenSaturation": {"spo2_median": ("value_median", "%"), "spo2_min": ("value_min", "%")},
    "WalkingSpeed": {"walking_speed_kmh": ("value_median", "km/hr")},
    "WalkingStepLength": {"walking_step_length_cm": ("value_median", "cm")},
    "WalkingDoubleSupportPercentage": {"walking_double_support": ("value_median", "%")},
    "WalkingAsymmetryPercentage": {"walking_asymmetry": ("value_median", "%")},
    "AppleWalkingSteadiness": {"walking_steadiness": ("value", "%")},
}
# Types with one Apple estimate per day: take the latest estimate (by end time).
LATEST_OF_DAY = {"RestingHeartRate": "resting_hr_bpm", "WalkingHeartRateAverage": "walking_hr_avg_bpm"}
SOUND = {"EnvironmentalAudioExposure": "env_audio", "HeadphoneAudioExposure": "headphone_audio"}
SOUND_EVENTS = ["AudioExposureEvent", "HeadphoneAudioExposureEvent"]


def _watch_samples(ctx: BuildContext, types: list[str]) -> pl.LazyFrame:
    watch_ids = ctx.scan("dim_source").filter(pl.col("source_name") == WATCH).select("source_id")
    return ctx.scan("fct_quantity_sample").filter(pl.col("type").is_in(types)).join(watch_ids, on="source_id")


def build_wear_hourly(ctx: BuildContext) -> None:
    dates = ctx.scan("dim_date").select("local_date")
    grid = dates.join(pl.LazyFrame({"hour": list(range(24))}, schema={"hour": pl.Int32}), how="cross")
    hr = (
        _watch_samples(ctx, ["HeartRate"])
        .group_by("local_date", pl.col("start_local").dt.hour().cast(pl.Int32).alias("hour"))
        .agg(pl.len().cast(pl.Int64).alias("watch_hr_samples"))
    )
    wear = (
        grid.join(hr, on=["local_date", "hour"], how="left")
        .with_columns(pl.col("watch_hr_samples").fill_null(0))
        .with_columns((pl.col("watch_hr_samples") > 0).alias("is_worn"))
    )
    ctx.write(mart_wear_hourly_table(), wear.collect())


def _minutes(col: str) -> pl.Expr:
    return pl.col(col) / 60


def _when_slept(e: pl.Expr) -> pl.Expr:
    """Null for sessions without any asleep time (in bed only)."""
    return pl.when(pl.col("asleep_s") > 0).then(e).otherwise(None)


def _when_staged(e: pl.Expr) -> pl.Expr:
    """Null for sessions without Core/Deep/REM stages."""
    return pl.when(pl.col("stage_detail_available")).then(e).otherwise(None)


def _clock_hours(col: str) -> pl.Expr:
    t = pl.col(col)
    return t.dt.hour() + t.dt.minute() / 60 + t.dt.second() / 3600


def _within_primary_sleep(samples: pl.LazyFrame, sessions: pl.DataFrame) -> pl.LazyFrame:
    """Attach the sleep_date of the primary session containing each sample's start (inner)."""
    s = (
        sessions.lazy()
        .select(pl.col("start_utc").alias("__s0"), pl.col("end_utc").alias("__s1"), pl.col("sleep_date"))
        .sort("__s0")
    )
    return (
        samples.sort("start_utc")
        .join_asof(s, left_on="start_utc", right_on="__s0", strategy="backward")
        .filter(pl.col("start_utc") <= pl.col("__s1"))
    )


def build_daily(ctx: BuildContext) -> None:
    cfg = ctx.cfg.settings
    table = mart_daily_table()
    parts: list[pl.LazyFrame] = []

    # -- calendar and context ------------------------------------------------------------------
    base = ctx.scan("dim_date").select(
        "local_date", "year", "month", "iso_year", "iso_week", "day_of_week", "is_weekend"
    )
    tz = (
        pl.concat(
            [
                ctx.scan("fct_quantity_sample").select("local_date", "tz_name"),
                ctx.scan("fct_category_sample").select("local_date", "tz_name"),
            ]
        )
        .group_by("local_date", "tz_name")
        .len()
        .sort(["local_date", "len", "tz_name"], descending=[False, True, False])
        .group_by("local_date", maintain_order=True)
        .agg(pl.col("tz_name").first())
    )
    wear = (
        ctx.scan("mart_wear_hourly")
        .group_by("local_date")
        .agg(pl.col("is_worn").sum().cast(pl.Int32).alias("watch_worn_hours"))
    )
    parts += [tz, wear]

    # -- metrics from agg_quantity_daily ----------------------------------------------------------
    agg = ctx.scan("agg_quantity_daily").collect()
    mismatches = {}
    for typ, cols in FROM_DAILY_AGG.items():
        sel = agg.filter(pl.col("type") == typ)
        for col, (_field, unit) in cols.items():
            units = set(sel["unit"].drop_nulls())
            if units - {unit}:
                mismatches[col] = sorted(units)
        parts.append(sel.lazy().select("local_date", *[pl.col(f).alias(c) for c, (f, _) in cols.items()]))
    ctx.stats["mart_unit_mismatches"] = mismatches

    q = ctx.scan("fct_quantity_sample")
    for typ, col in LATEST_OF_DAY.items():
        parts.append(
            q.filter(pl.col("type") == typ)
            .sort("end_utc")
            .group_by("local_date")
            .agg(pl.col("value").last().alias(col))
        )
    parts.append(
        q.filter(pl.col("type") == "AppleSleepingWristTemperature")
        .with_columns(pl.col("end_local").dt.date().alias("__d"))
        .sort("end_utc")
        .group_by("__d")
        .agg(pl.col("value").last().alias("wrist_temp_sleep_c"))
        .rename({"__d": "local_date"})
    )

    # -- sleep (night ending on the date) ---------------------------------------------------------
    sessions = ctx.scan("agg_sleep_session").collect()
    primary = sessions.filter(pl.col("is_primary"))
    bed = _clock_hours("start_local")
    bed = pl.when(bed < 12).then(bed + 24).otherwise(bed)
    parts.append(
        primary.lazy().select(
            pl.col("sleep_date").alias("local_date"),
            pl.col("start_local").alias("sleep_start_local"),
            pl.col("end_local").alias("sleep_end_local"),
            # In-bed-only nights (iPhone before the Watch) measured no sleep: asleep is unknown, not 0.
            _when_slept(_minutes("asleep_s")).alias("sleep_asleep_min"),
            pl.when(pl.col("in_bed_s") > 0)
            .then(_minutes("in_bed_s"))
            .otherwise(None)
            .alias("sleep_in_bed_min"),
            *[_when_staged(_minutes(f"{st}_s")).alias(f"sleep_{st}_min") for st in ("core", "deep", "rem")],
            _when_slept(_minutes("awake_s")).alias("sleep_awake_min"),
            _when_slept(pl.col("sleep_efficiency")).alias("sleep_efficiency"),
            pl.col("stage_detail_available").alias("sleep_has_stages"),
            bed.alias("bedtime_h"),
            _clock_hours("end_local").alias("waketime_h"),
            (bed + pl.col("span_s") / 7200).alias("sleep_midpoint_h"),
        )
    )
    parts.append(
        sessions.lazy()
        .group_by(pl.col("sleep_date").alias("local_date"))
        .agg(
            pl.col("asleep_s").filter(~pl.col("is_primary")).sum().truediv(60).alias("nap_min"),
            pl.len().cast(pl.Int32).alias("n_sleep_sessions"),
        )
    )
    hrv = _within_primary_sleep(
        q.filter(pl.col("type") == "HeartRateVariabilitySDNN").select("start_utc", "value"), primary
    )
    parts.append(
        hrv.group_by(pl.col("sleep_date").alias("local_date")).agg(
            pl.col("value").mean().alias("hrv_sdnn_sleep_ms")
        )
    )
    rr = _within_primary_sleep(
        q.filter(pl.col("type") == "RespiratoryRate").select("start_utc", "value"), primary
    )
    parts.append(
        rr.group_by(pl.col("sleep_date").alias("local_date")).agg(
            pl.col("value").median().alias("respiratory_rate_sleep")
        )
    )

    # -- workouts ------------------------------------------------------------------------------------
    # A session recorded by several apps is counted once: a workout overlapping a workout from a
    # better-ranked source (e.g. JEFIT under an Apple Watch workout) is left out of the totals.
    ranks = ctx.scan("dim_source").select("source_id", "priority_rank")
    wk = ctx.scan("fct_workout").join(ranks, on="source_id", how="left")
    partner = wk.select(
        pl.col("workout_id").alias("overlaps_workout_id"), pl.col("priority_rank").alias("__p")
    )
    wk = wk.join(partner, on="overlaps_workout_id", how="left").filter(
        pl.col("__p").is_null() | (pl.col("priority_rank") <= pl.col("__p"))
    )
    dist = (
        pl.col("distance_walking_running_km").fill_null(0)
        + pl.col("distance_cycling_km").fill_null(0)
        + pl.col("distance_swimming_m").fill_null(0) / 1000
    )
    parts.append(
        wk.group_by("local_date").agg(
            pl.len().cast(pl.Int32).alias("n_workouts"),
            (pl.col("duration_s").sum() / 60).alias("workout_min"),
            pl.col("active_energy_kcal").sum().alias("workout_active_energy_kcal"),
            dist.sum().alias("workout_distance_km"),
            pl.col("activity_type").unique().sort().alias("workout_types"),
            pl.col("weather_temperature_c")
            .filter(pl.col("activity_type").is_in(OUTDOOR_WORKOUTS) & ~pl.col("is_indoor").fill_null(False))
            .mean()
            .alias("weather_temperature_c"),
        )
    )

    # -- hearing ---------------------------------------------------------------------------------
    for typ, prefix in SOUND.items():
        d = pl.col("duration_s")
        parts.append(
            q.filter((pl.col("type") == typ) & (d > 0))
            .group_by("local_date")
            .agg(
                (10 * ((d * 10 ** (pl.col("value") / 10)).sum() / d.sum()).log10()).alias(
                    f"{prefix}_laeq_db"
                ),
                (d.sum() / 3600).alias(f"{prefix}_h"),
            )
        )
    parts.append(
        ctx.scan("fct_category_sample")
        .filter(pl.col("type").is_in(SOUND_EVENTS))
        .group_by("local_date")
        .agg(pl.len().cast(pl.Int32).alias("audio_exposure_events"))
    )

    # -- activity rings --------------------------------------------------------------------------
    def met(value: str, goal: str) -> pl.Expr:
        return pl.when(pl.col(goal) > 0).then(pl.col(value) >= pl.col(goal)).otherwise(None)

    rings = (
        ctx.scan("fct_activity_summary")
        .select(
            "local_date",
            pl.col("active_energy_kcal").alias("move_kcal"),
            pl.col("active_energy_goal_kcal").alias("move_goal_kcal"),
            pl.col("exercise_min").alias("exercise_ring_min"),
            pl.col("exercise_goal_min"),
            pl.col("stand_hours"),
            pl.col("stand_goal_hours"),
        )
        .with_columns(
            met("move_kcal", "move_goal_kcal").alias("move_goal_met"),
            met("exercise_ring_min", "exercise_goal_min").alias("exercise_goal_met"),
            met("stand_hours", "stand_goal_hours").alias("stand_goal_met"),
        )
        .with_columns(
            (pl.col("move_goal_met") & pl.col("exercise_goal_met") & pl.col("stand_goal_met")).alias(
                "all_rings_closed"
            )
        )
    )
    parts.append(rings)

    # -- assemble ------------------------------------------------------------------------------
    daily = base
    for p in parts:
        daily = daily.join(p, on="local_date", how="left")
    daily = (
        daily.sort("local_date")
        .with_columns(
            pl.col("tz_name").fill_null(cfg.default_timezone),
            pl.col("watch_worn_hours").fill_null(0),
            pl.col("n_workouts", "n_sleep_sessions", "audio_exposure_events").fill_null(0),
            pl.col("workout_min", "workout_active_energy_kcal", "workout_distance_km").fill_null(0.0),
            pl.col("vo2max").forward_fill().alias("vo2max_asof"),
        )
        .with_columns(
            (pl.col("tz_name") != cfg.default_timezone).alias("is_non_default_tz"),
            (pl.col("watch_worn_hours") > 0).alias("has_watch_data"),
            (pl.col("watch_worn_hours") >= cfg.valid_day_min_worn_hours).alias("is_valid_wear_day"),
            pl.when(pl.col("n_sleep_sessions") > 0).then(pl.col("nap_min")).otherwise(None).alias("nap_min"),
        )
    )
    ctx.write(table, daily.collect())


def _rollup_exprs(metrics: list[Metric]) -> list[pl.Expr]:
    exprs: list[pl.Expr] = []
    for m in metrics:
        c = pl.col(m.name)
        if m.rollup == "sum":
            exprs.append(pl.when(c.count() > 0).then(c.sum()).otherwise(None).alias(m.name))
            exprs.append(c.mean().cast(pl.Float64).alias(f"{m.name}_daily_avg"))
        elif m.rollup == "mean":
            exprs.append(c.mean().alias(m.name))
        elif m.rollup == "min":
            exprs.append(c.min().alias(m.name))
        elif m.rollup == "max":
            exprs.append(c.max().alias(m.name))
        elif m.rollup == "last":
            exprs.append(c.drop_nulls().last().alias(m.name))
        elif m.rollup == "count_true":
            exprs.append(c.sum().cast(pl.Int32).alias(f"{m.name}_days"))
        elif m.rollup == "energetic_mean":
            w = pl.col(m.weight).filter(c.is_not_null())  # type: ignore[arg-type]
            energy = (pl.col(m.weight) * 10 ** (c / 10)).filter(c.is_not_null())  # type: ignore[arg-type]
            exprs.append(
                pl.when(w.sum() > 0).then(10 * (energy.sum() / w.sum()).log10()).otherwise(None).alias(m.name)
            )
    return exprs


def build_rollups(ctx: BuildContext) -> None:
    daily = ctx.scan("mart_daily").sort("local_date")
    common = [
        pl.len().cast(pl.Int32).alias("n_days"),
        pl.col("is_valid_wear_day").sum().cast(pl.Int32).alias("n_valid_wear_days"),
        *_rollup_exprs(DAILY_METRICS),
    ]
    weekly = daily.group_by("iso_year", "iso_week").agg(
        (pl.col("local_date") - pl.duration(days=pl.col("day_of_week") - 1)).min().alias("week_start"),
        *common,
    )
    monthly = daily.group_by("year", "month").agg(
        pl.col("local_date").min().dt.month_start().alias("month_start"), *common
    )
    yearly = daily.group_by("year").agg(pl.date(pl.col("year").first(), 1, 1).alias("year_start"), *common)
    ctx.write(mart_weekly_table(), weekly.collect())
    ctx.write(mart_monthly_table(), monthly.collect())
    ctx.write(mart_yearly_table(), yearly.collect())
