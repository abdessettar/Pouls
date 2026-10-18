"""Daily metric registry: the single definition of every mart_daily column and how it rolls up.

mart_daily, mart_weekly and mart_monthly schemas (and their data-dictionary entries) are generated
from ``DAILY_METRICS``; the daily builder must produce exactly these columns (tested).

Rollup rules (weekly / monthly):
  sum             -> ``<name>`` = total over the period, ``<name>_daily_avg`` = mean over days with a value
  mean            -> ``<name>`` = mean of the daily values
  min / max       -> ``<name>`` = min / max of the daily values
  last            -> ``<name>`` = value of the last day with a value
  count_true      -> ``<name>_days`` = number of days where the flag is true
  energetic_mean  -> ``<name>`` = 10*log10(sum(w * 10^(L/10)) / sum(w)) weighted by ``weight`` (sound levels)
  none            -> not rolled up
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from apple_health.schemas import BOOL, DATE, F64, I32, LOCAL, STR_LIST, Column, S, Table

ROLLUPS = {"sum", "mean", "min", "max", "last", "count_true", "energetic_mean", "none"}


@dataclass(frozen=True)
class Metric:
    name: str
    dtype: object
    doc: str
    rollup: str
    weight: str | None = None  # energetic_mean only

    def __post_init__(self) -> None:
        if self.rollup not in ROLLUPS:
            raise ValueError(f"{self.name}: unknown rollup {self.rollup!r}")
        if (self.rollup == "energetic_mean") != (self.weight is not None):
            raise ValueError(f"{self.name}: energetic_mean needs a weight (and only it)")


M = Metric

CALENDAR = [
    M("year", I32, "Calendar year.", "none"),
    M("month", I32, "Calendar month.", "none"),
    M("iso_year", I32, "ISO year.", "none"),
    M("iso_week", I32, "ISO week.", "none"),
    M("day_of_week", I32, "1 = Monday ... 7 = Sunday.", "none"),
    M("is_weekend", BOOL, "Saturday or Sunday.", "count_true"),
]

CONTEXT = [
    M("tz_name", S, "Most frequent time zone among the day's samples (default zone when none).", "none"),
    M(
        "is_non_default_tz",
        BOOL,
        "tz_name differs from time.default_timezone (e.g. travel abroad).",
        "count_true",
    ),
    M("has_watch_data", BOOL, "At least one Apple Watch heart-rate sample.", "count_true"),
    M("watch_worn_hours", I32, "Local hours with >= 1 Apple Watch heart-rate sample (0-24).", "mean"),
    M("is_valid_wear_day", BOOL, "watch_worn_hours >= marts.valid_day_min_worn_hours.", "count_true"),
]

ACTIVITY = [
    M("steps", F64, "Steps (source priority per hour; agg_quantity_daily).", "sum"),
    M("distance_walking_running_km", F64, "Walking + running distance (km).", "sum"),
    M("distance_cycling_km", F64, "Cycling distance (km).", "sum"),
    M("flights_climbed", F64, "Floors climbed.", "sum"),
    M("active_energy_kcal", F64, "Active energy (kcal).", "sum"),
    M("basal_energy_kcal", F64, "Basal (resting) energy (kcal).", "sum"),
    M("exercise_min", F64, "Apple exercise minutes (from samples).", "sum"),
    M("stand_time_min", F64, "Apple stand minutes.", "sum"),
    M("daylight_min", F64, "Time in daylight (min).", "sum"),
    M("physical_effort_avg", F64, "Mean PhysicalEffort sample (kcal/hr·kg, MET-like).", "mean"),
]

RINGS = [
    M("move_kcal", F64, "Move ring value (ActivitySummary, kcal).", "sum"),
    M("move_goal_kcal", F64, "Move goal (kcal).", "mean"),
    M("exercise_ring_min", F64, "Exercise ring value (min).", "sum"),
    M("exercise_goal_min", F64, "Exercise goal (min).", "mean"),
    M("stand_hours", F64, "Stand ring value (hours).", "sum"),
    M("stand_goal_hours", F64, "Stand goal (hours).", "mean"),
    M("move_goal_met", BOOL, "move_kcal >= move_goal_kcal (goal > 0).", "count_true"),
    M("exercise_goal_met", BOOL, "exercise_ring_min >= exercise_goal_min (goal > 0).", "count_true"),
    M("stand_goal_met", BOOL, "stand_hours >= stand_goal_hours (goal > 0).", "count_true"),
    M("all_rings_closed", BOOL, "All three goals met.", "count_true"),
]

HEART = [
    M("resting_hr_bpm", F64, "Apple resting heart rate (latest estimate of the day).", "mean"),
    M("walking_hr_avg_bpm", F64, "Apple walking heart-rate average (latest estimate of the day).", "mean"),
    M("hr_mean_bpm", F64, "Mean of all heart-rate samples (biased towards measured activity).", "mean"),
    M("hr_min_bpm", F64, "Lowest heart-rate sample.", "min"),
    M("hr_max_bpm", F64, "Highest heart-rate sample (outliers included; see agg_quantity_daily).", "max"),
    M(
        "hrv_sdnn_ms",
        F64,
        "Mean HRV (SDNN) of the day's readings (taken at varying activity levels).",
        "mean",
    ),
    M(
        "hrv_sdnn_sleep_ms",
        F64,
        "Mean HRV (SDNN) of readings during the primary sleep session ending this day (more comparable).",
        "mean",
    ),
    M("hr_recovery_1min_bpm", F64, "Mean 1-minute heart-rate recovery after workouts that day.", "mean"),
    M("vo2max", F64, "Mean VO2max estimate of the day (mL/min·kg); null when none.", "mean"),
    M("vo2max_asof", F64, "Latest VO2max estimate on or before this day.", "last"),
    M(
        "respiratory_rate_sleep",
        F64,
        "Median respiratory rate during the primary sleep session ending this day (count/min).",
        "mean",
    ),
    M("spo2_median", F64, "Median blood-oxygen saturation (fraction, 0.97 = 97 %).", "mean"),
    M("spo2_min", F64, "Lowest blood-oxygen saturation (fraction).", "min"),
    M("wrist_temp_sleep_c", F64, "Sleeping wrist temperature for the night ending this day (degC).", "mean"),
]

SLEEP = [
    M("sleep_start_local", LOCAL, "Start of the primary sleep session ending this day (local).", "none"),
    M("sleep_end_local", LOCAL, "End (wake-up) of the primary sleep session (local).", "none"),
    M(
        "sleep_asleep_min",
        F64,
        "Asleep time (Core + Deep + REM + unspecified) of the night ending this day.",
        "mean",
    ),
    M("sleep_in_bed_min", F64, "In-bed time of the night (null without InBed data).", "mean"),
    M("sleep_core_min", F64, "Core sleep (min); null without stage data.", "mean"),
    M("sleep_deep_min", F64, "Deep sleep (min); null without stage data.", "mean"),
    M("sleep_rem_min", F64, "REM sleep (min); null without stage data.", "mean"),
    M("sleep_awake_min", F64, "Awake time within the session (min).", "mean"),
    M(
        "sleep_efficiency",
        F64,
        "asleep / (asleep + awake) within the session (asleep / span without stages).",
        "mean",
    ),
    M("sleep_has_stages", BOOL, "Core/Deep/REM available (from Sept 2022).", "count_true"),
    M(
        "bedtime_h",
        F64,
        "Sleep start as hours after the previous midnight (23.5 = 23:30, 24.5 = 00:30).",
        "mean",
    ),
    M("waketime_h", F64, "Wake-up time as hours after midnight (6.75 = 06:45).", "mean"),
    M("sleep_midpoint_h", F64, "Midpoint of the session, hours after the previous midnight.", "mean"),
    M("nap_min", F64, "Asleep time of other (non-primary) sessions ending this day.", "sum"),
    M("n_sleep_sessions", I32, "Sleep sessions ending this day.", "sum"),
]

WORKOUTS = [
    M(
        "n_workouts",
        I32,
        "Workouts starting this day; a session recorded by several apps counts once (best-ranked source).",
        "sum",
    ),
    M("workout_min", F64, "Active workout duration (min).", "sum"),
    M("workout_active_energy_kcal", F64, "Workout active energy (kcal).", "sum"),
    M("workout_distance_km", F64, "Workout distance: walking/running + cycling + swimming (km).", "sum"),
    M("workout_types", STR_LIST, "Distinct activity types of the day's workouts.", "none"),
    M(
        "weather_temperature_c",
        F64,
        "Mean outdoor temperature at the start of the day's outdoor walks, runs, rides and hikes "
        "(Apple weather metadata, degC); null without one.",
        "mean",
    ),
]

HEARING = [
    M(
        "env_audio_laeq_db",
        F64,
        "Environmental sound level, energy average weighted by duration (dBA).",
        "energetic_mean",
        weight="env_audio_h",
    ),
    M("env_audio_h", F64, "Hours of environmental sound measurement.", "sum"),
    M(
        "headphone_audio_laeq_db",
        F64,
        "Headphone sound level, energy average weighted by duration (dBA).",
        "energetic_mean",
        weight="headphone_audio_h",
    ),
    M("headphone_audio_h", F64, "Hours of headphone listening measured.", "sum"),
    M("audio_exposure_events", I32, "Loud-environment and headphone-limit notifications.", "sum"),
]

MOBILITY = [
    M("walking_speed_kmh", F64, "Median walking speed (iPhone, km/h).", "mean"),
    M("walking_step_length_cm", F64, "Median walking step length (cm).", "mean"),
    M("walking_double_support", F64, "Median double-support share of the gait cycle (fraction).", "mean"),
    M("walking_asymmetry", F64, "Median walking asymmetry (fraction).", "mean"),
    M("walking_steadiness", F64, "Apple walking steadiness score (fraction; weekly estimate).", "mean"),
]

DAILY_METRICS: list[Metric] = [
    *CALENDAR,
    *CONTEXT,
    *ACTIVITY,
    *RINGS,
    *HEART,
    *SLEEP,
    *WORKOUTS,
    *HEARING,
    *MOBILITY,
]

_DAILY_DOC = (
    "One row per local calendar day from the first to the last day with data (no gaps; days without "
    "data have nulls). Sleep columns describe the night that ENDS on this day. Activity totals resolve "
    "overlapping sources per hour. Use is_valid_wear_day to exclude days the Watch was barely worn."
)


def mart_daily_table() -> Table:
    cols = [
        Column("local_date", DATE, "PK: local calendar date."),
        *[Column(m.name, m.dtype, m.doc) for m in DAILY_METRICS],
    ]  # type: ignore[arg-type]
    return Table(
        "mart_daily", "marts", _DAILY_DOC, tuple(cols), primary_key=("local_date",), sort_by=("local_date",)
    )


def rolled_up_columns() -> list[Column]:
    """Columns produced by rolling DAILY_METRICS up to a period (week or month)."""
    out: list[Column] = []
    for m in DAILY_METRICS:
        if m.rollup == "none":
            continue
        if m.rollup == "sum":
            dtype = F64 if m.dtype == F64 else pl.Int64
            out.append(Column(m.name, dtype, f"Total over the period. Daily: {m.doc}"))
            out.append(Column(f"{m.name}_daily_avg", F64, "Mean over days with a value."))
        elif m.rollup == "count_true":
            out.append(Column(f"{m.name}_days", pl.Int32, f"Days where true. Daily: {m.doc}"))
        elif m.rollup in ("min", "max", "last"):
            out.append(
                Column(m.name, m.dtype, f"{m.rollup.capitalize()} of the daily values. Daily: {m.doc}")
            )  # type: ignore[arg-type]
        else:  # mean, energetic_mean
            how = "Energy average" if m.rollup == "energetic_mean" else "Mean"
            out.append(Column(m.name, F64, f"{how} of the daily values. Daily: {m.doc}"))
    return out


def _period_table(name: str, doc: str, keys: list[Column], pk: tuple[str, ...]) -> Table:
    base = [
        *keys,
        Column("n_days", pl.Int32, "Days of the period present in mart_daily (edges can be partial)."),
        Column("n_valid_wear_days", pl.Int32, "Days with is_valid_wear_day."),
    ]
    return Table(name, "marts", doc, tuple(base + rolled_up_columns()), primary_key=pk, sort_by=pk)


def mart_weekly_table() -> Table:
    return _period_table(
        "mart_weekly",
        "mart_daily rolled up to ISO weeks (rules in src/apple_health/marts/metrics.py). Aggregates use "
        "every day with a value; filter on n_valid_wear_days for Watch-based comparisons.",
        [
            Column("iso_year", pl.Int32, "ISO year."),
            Column("iso_week", pl.Int32, "ISO week."),
            Column("week_start", DATE, "Monday of the week."),
        ],
        ("iso_year", "iso_week"),
    )


def mart_monthly_table() -> Table:
    return _period_table(
        "mart_monthly",
        "mart_daily rolled up to calendar months (rules in src/apple_health/marts/metrics.py).",
        [
            Column("year", pl.Int32, "Year."),
            Column("month", pl.Int32, "Month."),
            Column("month_start", DATE, "First day of the month."),
        ],
        ("year", "month"),
    )


def mart_wear_hourly_table() -> Table:
    return Table(
        "mart_wear_hourly",
        "marts",
        "Apple Watch wear per local hour (full grid of dates x 24 hours): basis of watch_worn_hours.",
        (
            Column("local_date", DATE, "Local date."),
            Column("hour", pl.Int32, "Local hour (0-23)."),
            Column("watch_hr_samples", pl.Int64, "Apple Watch heart-rate samples starting in this hour."),
            Column("is_worn", BOOL, "watch_hr_samples > 0."),
        ),
        primary_key=("local_date", "hour"),
        sort_by=("local_date", "hour"),
    )


def mart_yearly_table() -> Table:
    return _period_table(
        "mart_yearly",
        "mart_daily rolled up to calendar years (rules in src/apple_health/marts/metrics.py).",
        [Column("year", pl.Int32, "Year."), Column("year_start", DATE, "1 January.")],
        ("year",),
    )


def mart_tables() -> list[Table]:
    from apple_health.marts.analytics_tables import ANALYTICS_TABLES

    return [
        mart_wear_hourly_table(),
        mart_daily_table(),
        mart_weekly_table(),
        mart_monthly_table(),
        mart_yearly_table(),
        *ANALYTICS_TABLES,
    ]
