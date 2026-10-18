"""Table definitions of the analytics marts (dashboard-facing; see docs/decisions/0006)."""

from __future__ import annotations

from apple_health.schemas import BOOL, DATE, F64, I32, I64, LOCAL, UTC, Column, S, Table


def _t(
    name: str,
    doc: str,
    cols: list[tuple[str, object, str]],
    pk: tuple[str, ...],
    sort: tuple[str, ...] | None = None,
) -> Table:
    return Table(
        name,
        "marts",
        doc,
        tuple(Column(n, d, c) for n, d, c in cols),  # type: ignore[arg-type]
        primary_key=pk,
        sort_by=sort or pk,
    )


MART_BASELINES = _t(
    "mart_baselines",
    "Personal baselines per metric and day, over valid wear days only (analytics.baseline_metrics).",
    [
        ("local_date", DATE, "Local date."),
        ("metric", S, "mart_daily column name."),
        ("value", F64, "The day's value."),
        ("roll_short_median", F64, "Rolling median over analytics.rolling_short_days (7) days."),
        ("roll_long_median", F64, "Rolling median over analytics.rolling_long_days (28) days."),
        (
            "normal_p10",
            F64,
            "Rolling 10th percentile over analytics.normal_range_days (90): the low end of your normal.",
        ),
        ("normal_p50", F64, "Rolling median over the same window."),
        ("normal_p90", F64, "Rolling 90th percentile: the high end of your normal."),
        ("baseline_mean", F64, "Mean over the previous analytics.baseline_days (60) days, today excluded."),
        ("baseline_sd", F64, "Standard deviation over the same window."),
        ("z", F64, "(value - baseline_mean) / baseline_sd; null with fewer than baseline_min_days days."),
    ],
    ("metric", "local_date"),
)

MART_ACTIVITY_PROFILE = _t(
    "mart_activity_profile",
    "The shape of a day: activity and heart rate per local hour, by year and weekday, over valid wear days. "
    "Hours without samples count as zero steps.",
    [
        ("year", I32, "Calendar year."),
        ("day_of_week", I32, "1 = Monday ... 7 = Sunday."),
        ("hour", I32, "Local hour (0-23)."),
        ("n_days", I32, "Valid wear days contributing."),
        ("steps_mean", F64, "Mean steps in the hour."),
        ("steps_median", F64, "Median steps in the hour."),
        ("active_energy_mean", F64, "Mean active energy in the hour (kcal)."),
        ("hr_mean_bpm", F64, "Mean of the hour's mean heart rate (hours with samples only)."),
        ("hr_n_days", I32, "Days with heart-rate samples in the hour."),
    ],
    ("year", "day_of_week", "hour"),
)

MART_SLEEP_NIGHT = _t(
    "mart_sleep_night",
    "One row per night (primary sleep session), dated by the wake-up day, with stage shares, regularity and "
    "the context of the preceding day.",
    [
        ("night_date", DATE, "Local date of waking up."),
        ("session_id", S, "agg_sleep_session.session_id."),
        ("start_local", LOCAL, "Sleep start (local)."),
        ("end_local", LOCAL, "Wake-up (local)."),
        ("bedtime_h", F64, "Hours after the previous midnight (24.5 = 00:30)."),
        ("waketime_h", F64, "Hours after midnight."),
        ("midpoint_h", F64, "Hours after the previous midnight."),
        ("asleep_min", F64, "Core + deep + REM + unspecified."),
        ("in_bed_min", F64, "In bed (null without InBed data)."),
        ("core_min", F64, ""),
        ("deep_min", F64, ""),
        ("rem_min", F64, ""),
        ("awake_min", F64, ""),
        ("deep_share", F64, "Deep / asleep (null without stages)."),
        ("rem_share", F64, "REM / asleep (null without stages)."),
        ("core_share", F64, "Core / asleep (null without stages)."),
        ("efficiency", F64, "Asleep / (asleep + awake) (asleep / span without stages)."),
        ("has_stages", BOOL, ""),
        ("hrv_sdnn_sleep_ms", F64, "Mean HRV during the night."),
        ("respiratory_rate", F64, "Median respiratory rate during the night."),
        ("resting_hr_bpm", F64, "Resting HR of the wake-up day."),
        (
            "bedtime_dev_min",
            F64,
            "Bedtime minus the median bedtime of the previous 7 nights (min; >= 3 nights).",
        ),
        ("is_weekend_night", BOOL, "Wake-up day is Saturday or Sunday."),
        ("is_away", BOOL, "Wake-up day or the day before spent outside the home time zone."),
        ("prev_steps", F64, "Steps on the day before."),
        ("prev_workout_min", F64, "Counted workout minutes on the day before."),
        ("prev_n_workouts", I32, "Counted workouts on the day before."),
        ("prev_daylight_min", F64, "Daylight minutes on the day before."),
        ("late_workout", BOOL, "A counted workout ended within analytics.late_workout_hours before bedtime."),
        ("prev_valid_wear_day", BOOL, "The day before was a valid wear day."),
    ],
    ("night_date",),
)

MART_WORKOUT = _t(
    "mart_workout",
    "One row per workout, enriched: overlap dedup flag, minutes per heart-rate zone, Edwards-style TRIMP, "
    "pace, effort score and JEFIT volume.",
    [
        ("workout_id", S, "fct_workout.workout_id."),
        ("local_date", DATE, "Local date of the start."),
        ("start_utc", UTC, ""),
        ("end_utc", UTC, ""),
        ("start_local", LOCAL, ""),
        ("activity_type", S, "Short HealthKit activity type."),
        ("activity_group", S, "walking | running | strength | cycling | other."),
        ("source_name", S, "Normalised source name."),
        ("is_counted", BOOL, "False when the session duplicates a workout from a better-ranked source."),
        ("duration_min", F64, "Active duration."),
        ("elapsed_min", F64, "Including pauses."),
        ("distance_km", F64, "Walking/running + cycling + swimming distance (null when none)."),
        ("active_energy_kcal", F64, ""),
        ("avg_hr_bpm", F64, "Average heart rate (WorkoutStatistics)."),
        ("max_hr_bpm", F64, "Maximum heart rate (WorkoutStatistics)."),
        ("zone1_min", F64, "Minutes in heart-rate zone 1 (Apple's system zones, lowest)."),
        ("zone2_min", F64, ""),
        ("zone3_min", F64, ""),
        ("zone4_min", F64, ""),
        ("zone5_min", F64, "Minutes in zone 5 (highest)."),
        ("has_zones", BOOL, "Heart-rate zones recorded."),
        ("trimp", F64, "Training impulse: sum of zone minutes x weights 1-5 (null without zones)."),
        ("pace_s_per_km", F64, "Duration / distance for walking, running and hiking (s/km)."),
        ("speed_kmh", F64, "Distance / duration (km/h)."),
        ("effort_score", F64, "Apple workout effort score (measured, else estimated; 1-10)."),
        ("elevation_gain_m", F64, ""),
        (
            "strength_volume_kg",
            F64,
            "JEFIT total weight lifted (kg); a counted Watch session takes it from its JEFIT copy.",
        ),
        ("avg_mets", F64, "Apple's average METs for the workout (HKAverageMETs)."),
        ("weather_temperature_c", F64, "Outdoor temperature at the start (Apple weather metadata)."),
        ("weather_humidity_pct", F64, "Outdoor relative humidity at the start (%)."),
        ("is_indoor", BOOL, ""),
        ("has_route", BOOL, ""),
        ("tz_name", S, ""),
    ],
    ("workout_id",),
    ("start_utc", "workout_id"),
)

MART_WORKOUT_HR = _t(
    "mart_workout_hr",
    "Heart rate per minute of each counted workout (all heart-rate sources, from the start). A sample "
    "belongs to the latest workout that started before it, until that workout ends.",
    [
        ("workout_id", S, "mart_workout.workout_id."),
        ("minute", I32, "Whole minutes since the workout started (elapsed time, pauses included)."),
        ("hr_bpm", F64, "Mean heart rate of the samples in that minute."),
        ("n_samples", I32, "Heart-rate samples in that minute."),
    ],
    ("workout_id", "minute"),
)

MART_TRAINING_WEEKLY = _t(
    "mart_training_weekly",
    "Counted workouts per ISO week and activity group.",
    [
        ("week_start", DATE, "Monday of the ISO week."),
        ("iso_year", I32, ""),
        ("iso_week", I32, ""),
        ("activity_group", S, "walking | running | strength | cycling | other."),
        ("sessions", I32, ""),
        ("minutes", F64, "Active minutes."),
        ("distance_km", F64, ""),
        ("active_energy_kcal", F64, ""),
        ("trimp", F64, "Sum of TRIMP (sessions with zones)."),
        ("zone_minutes_4_5", F64, "Minutes in zones 4-5 (vigorous)."),
    ],
    ("week_start", "activity_group"),
)

MART_TRAINING_LOAD = _t(
    "mart_training_load",
    "Daily training load: acute (analytics.acute_days) and chronic (analytics.chronic_days) TRIMP and their "
    "ratio (acute daily average / chronic daily average).",
    [
        ("local_date", DATE, "Every day from the first workout to the last day of data."),
        ("trimp", F64, "TRIMP of the day's counted workouts (0 on rest days)."),
        ("acute_load", F64, "Mean daily TRIMP over the last 7 days."),
        ("chronic_load", F64, "Mean daily TRIMP over the last 28 days."),
        ("acwr", F64, "acute_load / chronic_load (null while chronic is 0 or history < chronic_days)."),
        ("workout_min", F64, "Counted workout minutes that day."),
    ],
    ("local_date",),
)

MART_RUN = _t(
    "mart_run",
    "Counted running workouts with a distance: pace, efficiency, form and best efforts from GPS.",
    [
        ("workout_id", S, ""),
        ("local_date", DATE, ""),
        ("start_utc", UTC, ""),
        ("start_local", LOCAL, ""),
        ("distance_km", F64, ""),
        ("duration_min", F64, ""),
        ("pace_s_per_km", F64, ""),
        ("avg_hr_bpm", F64, ""),
        ("m_per_beat", F64, "Metres per heartbeat: speed (m/min) / average heart rate (beats/min)."),
        ("power_w", F64, "Average running power."),
        ("stride_m", F64, "Average stride length."),
        ("ground_contact_ms", F64, ""),
        ("vertical_oscillation_cm", F64, ""),
        ("elevation_gain_m", F64, ""),
        ("has_route", BOOL, "GPS points available."),
        ("best_1k_s", F64, "Fastest 1 km within the run (GPS sliding window; null if shorter)."),
        ("best_5k_s", F64, "Fastest 5 km within the run."),
        ("best_10k_s", F64, "Fastest 10 km within the run."),
        ("tz_name", S, ""),
    ],
    ("workout_id",),
    ("start_utc", "workout_id"),
)

MART_RUN_SPLIT = _t(
    "mart_run_split",
    "Per-kilometre splits of runs with GPS (last split may be partial).",
    [
        ("workout_id", S, "FK mart_run."),
        ("split", I32, "1-based kilometre."),
        ("distance_m", F64, "Distance of the split (1000 except possibly the last)."),
        ("duration_s", F64, ""),
        ("pace_s_per_km", F64, ""),
        ("elevation_change_m", F64, "End minus start elevation (valid altitudes only)."),
        ("avg_hr_bpm", F64, "Mean heart-rate sample within the split."),
        ("start_offset_s", F64, "Seconds since the start of the run."),
    ],
    ("workout_id", "split"),
)

MART_ROUTE = _t(
    "mart_route",
    "Routes with GPS points: distance, elevation, centre and an area cluster for the map.",
    [
        ("route_id", S, ""),
        ("workout_id", S, ""),
        ("local_date", DATE, ""),
        ("start_utc", UTC, ""),
        ("activity_type", S, ""),
        ("activity_group", S, ""),
        ("distance_km", F64, "Sum of GPS segment distances."),
        ("duration_min", F64, "First to last GPS point."),
        ("elevation_gain_m", F64, "Positive elevation change (2 m hysteresis, valid altitudes only)."),
        ("center_lat", F64, ""),
        ("center_lon", F64, ""),
        ("min_lat", F64, ""),
        ("min_lon", F64, ""),
        ("max_lat", F64, ""),
        ("max_lon", F64, ""),
        ("area_id", I32, "Cluster of route centres (analytics.area_cluster_km)."),
        ("area_name", S, "Area label from the routes' time zone (e.g. Berlin), numbered when repeated."),
        ("n_points", I64, "GPS points of the route."),
    ],
    ("route_id",),
    ("start_utc", "route_id"),
)

MART_ROUTE_TRACK = _t(
    "mart_route_track",
    "Map tracks: route points thinned to one every analytics.track_resolution_m metres.",
    [
        ("route_id", S, ""),
        ("seq", I32, "Order along the route."),
        ("lat", F64, ""),
        ("lon", F64, ""),
        ("elevation_m", F64, "Elevation (null where the altitude was invalid)."),
        ("dist_m", F64, "Distance from the start of the route along the GPS track."),
    ],
    ("route_id", "seq"),
)

MART_RECORDS = _t(
    "mart_records",
    "Personal records, streaks and lifetime totals.",
    [
        ("record_id", S, "Stable key, e.g. most_steps_day."),
        ("category", S, "activity | heart | sleep | training | running | totals."),
        ("label", S, "Human-readable name."),
        ("kind", S, "max | min | streak | total."),
        ("value", F64, ""),
        ("unit", S, ""),
        ("start_date", DATE, "Date of the record (or streak start)."),
        ("end_date", DATE, "Streak end (null otherwise)."),
        ("detail_id", S, "workout_id for workout-based records."),
    ],
    ("record_id",),
)

MART_REFERENCE = _t(
    "mart_reference",
    "Population and guideline reference bands for the profile's age and sex (config/references.toml). "
    "Bands step at age-group boundaries: valid_from/valid_to say when each applies.",
    [
        ("metric", S, "Reference metric key (e.g. resting_hr, sleep_duration)."),
        ("kind", S, "range (guideline or clinical bands) or percentile (population percentile table)."),
        ("band", S, "Band id within its set (e.g. normal, p25_p50)."),
        ("label", S, "Short label for display (e.g. 60–100 bpm, 25th–50th percentile)."),
        ("lo", F64, "Lower bound, inclusive, in warehouse units; null = open."),
        ("hi", F64, "Upper bound, exclusive; null = open."),
        ("is_target", BOOL, "The recommended or typical band."),
        ("is_warning", BOOL, "A band the source calls abnormal or not recommended."),
        ("valid_from", DATE, "First local date the band applies (age group start, within the export)."),
        ("valid_to", DATE, "Last local date the band applies."),
        ("population", S, "Who the numbers describe (e.g. Women aged 30–39, FRIEND registry)."),
        ("source_id", S, "mart_reference_source.source_id."),
        ("seq", I32, "Band order within its set, from low to high values."),
    ],
    ("metric", "kind", "valid_from", "band"),
    ("metric", "kind", "valid_from", "seq"),
)

MART_REFERENCE_SOURCE = _t(
    "mart_reference_source",
    "Citations behind mart_reference.",
    [
        ("source_id", S, "Source key in config/references.toml."),
        ("short", S, "Short name shown next to a band (e.g. WHO 2020)."),
        ("citation", S, "Full citation."),
        ("url", S, "DOI or web address."),
        ("note", S, "How the source was measured and how it compares with Apple's measurement."),
    ],
    ("source_id",),
)

ANALYTICS_TABLES = [
    MART_BASELINES,
    MART_ACTIVITY_PROFILE,
    MART_SLEEP_NIGHT,
    MART_WORKOUT,
    MART_WORKOUT_HR,
    MART_TRAINING_WEEKLY,
    MART_TRAINING_LOAD,
    MART_RUN,
    MART_RUN_SPLIT,
    MART_ROUTE,
    MART_ROUTE_TRACK,
    MART_RECORDS,
    MART_REFERENCE,
    MART_REFERENCE_SOURCE,
]
