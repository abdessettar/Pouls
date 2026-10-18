"""Table definitions: single source of truth for written schemas, tests and the data dictionary."""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

SCHEMA_VERSION = "1"

S = pl.String
I32 = pl.Int32
I64 = pl.Int64


@dataclass(frozen=True)
class Column:
    name: str
    dtype: pl.DataType | type[pl.DataType]
    doc: str = ""


@dataclass(frozen=True)
class Table:
    name: str
    layer: str
    doc: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...] = ()
    partition_by: str | None = None
    sort_by: tuple[str, ...] = ()
    foreign_keys: tuple[tuple[str, str, str], ...] = field(default=())  # (column, table, column)

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def schema(self) -> pl.Schema:
        return pl.Schema({c.name: c.dtype for c in self.columns})


def _stg(name: str, doc: str, cols: list[tuple[str, object]] | list[str], pk: tuple[str, ...] = ()) -> Table:
    columns = []
    for c in cols:
        if isinstance(c, tuple):
            columns.append(Column(c[0], c[1]))
        else:
            columns.append(Column(c, S))
    return Table(name, "staging", doc, tuple(columns), primary_key=pk)


_SAMPLE_ATTRS = ["sourceName", "sourceVersion", "device", "creationDate", "startDate", "endDate"]
RECORD_ATTRS = ["type", "unit", "value", *_SAMPLE_ATTRS]
WORKOUT_ATTRS = [
    "workoutActivityType",
    "duration",
    "durationUnit",
    "totalDistance",
    "totalDistanceUnit",
    "totalEnergyBurned",
    "totalEnergyBurnedUnit",
    *_SAMPLE_ATTRS,
]
ACTIVITY_SUMMARY_ATTRS = [
    "dateComponents",
    "activeEnergyBurned",
    "activeEnergyBurnedGoal",
    "activeEnergyBurnedUnit",
    "appleMoveTime",
    "appleMoveTimeGoal",
    "appleExerciseTime",
    "appleExerciseTimeGoal",
    "appleStandHours",
    "appleStandHoursGoal",
]
SENSITIVITY_POINT_ATTRS = [
    "frequencyValue",
    "frequencyUnit",
    "leftEarValue",
    "leftEarUnit",
    "leftEarMasked",
    "leftEarClampingRangeLowerBound",
    "leftEarClampingRangeUpperBound",
    "rightEarValue",
    "rightEarUnit",
    "rightEarMasked",
    "rightEarClampingRangeLowerBound",
    "rightEarClampingRangeUpperBound",
]

# Staging: lossless mirrors of the source elements. Attribute columns keep the source's
# camelCase names and raw string values; lineage columns (*_nr, ordinal) are integers.
STAGING_TABLES: dict[str, Table] = {
    t.name: t
    for t in [
        _stg(
            "stg_export",
            "One row describing the export (export date, locale, format version).",
            ["export_date", "locale", ("export_version", I64)],
        ),
        _stg(
            "stg_me",
            "Profile characteristics (<Me> attributes), one row per attribute.",
            ["attribute", "value"],
        ),
        _stg(
            "stg_record",
            "Top-level <Record> elements.",
            [("record_nr", I64), *RECORD_ATTRS, "extra_attrs"],
            pk=("record_nr",),
        ),
        _stg(
            "stg_record_metadata",
            "<MetadataEntry> children of top-level records.",
            [("record_nr", I64), ("ordinal", I32), "key", "value"],
            pk=("record_nr", "ordinal"),
        ),
        _stg(
            "stg_hrv_beat",
            "<InstantaneousBeatsPerMinute> of heart-rate-variability records.",
            [("record_nr", I64), ("ordinal", I32), "bpm", "time"],
            pk=("record_nr", "ordinal"),
        ),
        _stg(
            "stg_workout",
            "<Workout> elements.",
            [("workout_nr", I64), *WORKOUT_ATTRS, "extra_attrs"],
            pk=("workout_nr",),
        ),
        _stg(
            "stg_workout_metadata",
            "<MetadataEntry> of workouts and their activities, events and routes "
            "(owner_kind = workout | activity | event | route; owner_ordinal = that child's ordinal).",
            [("workout_nr", I64), "owner_kind", ("owner_ordinal", I32), ("ordinal", I32), "key", "value"],
            pk=("workout_nr", "owner_kind", "owner_ordinal", "ordinal"),
        ),
        _stg(
            "stg_workout_activity",
            "<WorkoutActivity> children of workouts (e.g. intervals).",
            [
                ("workout_nr", I64),
                ("ordinal", I32),
                "uuid",
                "startDate",
                "endDate",
                "duration",
                "durationUnit",
                "extra_attrs",
            ],
            pk=("workout_nr", "ordinal"),
        ),
        _stg(
            "stg_workout_event",
            "<WorkoutEvent> of workouts and activities (activity_ordinal null at workout level).",
            [
                ("workout_nr", I64),
                ("ordinal", I32),
                ("activity_ordinal", I32),
                "type",
                "date",
                "duration",
                "durationUnit",
                "extra_attrs",
            ],
            pk=("workout_nr", "ordinal"),
        ),
        _stg(
            "stg_workout_statistic",
            "<WorkoutStatistics> of workouts and activities.",
            [
                ("workout_nr", I64),
                ("ordinal", I32),
                ("activity_ordinal", I32),
                "type",
                "startDate",
                "endDate",
                "sum",
                "average",
                "minimum",
                "maximum",
                "unit",
                "extra_attrs",
            ],
            pk=("workout_nr", "ordinal"),
        ),
        _stg(
            "stg_workout_zone",
            "<WorkoutZone> rows with their <WorkoutZoneGroup> attributes.",
            [
                ("workout_nr", I64),
                ("ordinal", I32),
                ("activity_ordinal", I32),
                ("group_ordinal", I32),
                "group_type",
                "group_source",
                "group_unit",
                "minimum",
                "maximum",
                "duration",
                "durationUnit",
            ],
            pk=("workout_nr", "ordinal"),
        ),
        _stg(
            "stg_workout_route",
            "<WorkoutRoute> elements with their <FileReference> path.",
            [("workout_nr", I64), ("ordinal", I32), *_SAMPLE_ATTRS, "file_path", "extra_attrs"],
            pk=("workout_nr", "ordinal"),
        ),
        _stg(
            "stg_workout_record_ref",
            "<Record> elements nested in workouts. They duplicate top-level records and are only used "
            "to link workouts to samples.",
            [("workout_nr", I64), ("ordinal", I32), *RECORD_ATTRS],
            pk=("workout_nr", "ordinal"),
        ),
        _stg(
            "stg_activity_summary",
            "<ActivitySummary> elements (one per day).",
            [("summary_nr", I64), *ACTIVITY_SUMMARY_ATTRS, "extra_attrs"],
            pk=("summary_nr",),
        ),
        _stg(
            "stg_audiogram",
            "<Audiogram> elements.",
            [("audiogram_nr", I64), "type", *_SAMPLE_ATTRS, "extra_attrs"],
            pk=("audiogram_nr",),
        ),
        _stg(
            "stg_audiogram_metadata",
            "<MetadataEntry> of audiograms.",
            [("audiogram_nr", I64), ("ordinal", I32), "key", "value"],
            pk=("audiogram_nr", "ordinal"),
        ),
        _stg(
            "stg_audiogram_point",
            "<SensitivityPoint> of audiograms.",
            [("audiogram_nr", I64), ("ordinal", I32), *SENSITIVITY_POINT_ATTRS],
            pk=("audiogram_nr", "ordinal"),
        ),
        _stg(
            "stg_other_element",
            "Any element without a dedicated table (unknown or DTD-declared-but-unhandled), kept as XML so "
            "nothing is lost. parent_nr is the *_nr of the parent element (null at top level).",
            [("element_nr", I64), "parent_tag", ("parent_nr", I64), "tag", "attributes", "xml"],
            pk=("element_nr",),
        ),
        _stg(
            "stg_gpx_file",
            "One row per GPX file in workout-routes/.",
            [
                "file_name",
                ("size_bytes", I64),
                "sha256",
                "version",
                "creator",
                "metadata_time",
                "track_name",
                ("n_tracks", I32),
                ("n_segments", I32),
                ("n_points", I64),
            ],
            pk=("file_name",),
        ),
        _stg(
            "stg_gpx_point",
            "<trkpt> elements of all GPX files, in file order (seq), with Apple extension values.",
            [
                "file_name",
                ("track_index", I32),
                ("segment_index", I32),
                ("seq", I64),
                "lat",
                "lon",
                "ele",
                "time",
                "speed",
                "course",
                "hAcc",
                "vAcc",
                "extra_ext",
            ],
            pk=("file_name", "seq"),
        ),
    ]
}


# ---------------------------------------------------------------------------------------------
# Curated layer
# ---------------------------------------------------------------------------------------------
UTC = pl.Datetime("us", "UTC")
LOCAL = pl.Datetime("us")
F64 = pl.Float64
BOOL = pl.Boolean
DATE = pl.Date
STR_LIST = pl.List(pl.String)

_LINEAGE = Column("export_id", S, "Export this row comes from (export timestamp, UTC ISO-8601).")


def _c(name: str, dtype: object, doc: str) -> Column:
    return Column(name, dtype, doc)  # type: ignore[arg-type]


def _promoted(cfg: object, target: str) -> list[Column]:
    from apple_health.transform.metadata import promoted_schema

    return [
        _c(name, dtype, f"Promoted from metadata key {spec.key!r}.")
        for spec, (name, dtype) in zip(
            cfg.promoted_keys(target),  # type: ignore[attr-defined]
            promoted_schema(target, cfg).items(),  # type: ignore[arg-type]
            strict=True,
        )
    ]


_TIME_COLS = [
    _c("start_utc", UTC, "Start instant (UTC)."),
    _c("end_utc", UTC, "End instant (UTC)."),
    _c("created_utc", UTC, "When the sample was written to HealthKit (UTC)."),
    _c("duration_s", F64, "end_utc - start_utc in seconds (0 for instantaneous samples)."),
    _c("tz_name", S, "IANA zone used for local times."),
    _c(
        "tz_source",
        S,
        "explicit (HKTimeZone on the row) | inferred (dim_timezone_period) | default (config).",
    ),
    _c("start_local", LOCAL, "Local wall-clock start in tz_name."),
    _c("end_local", LOCAL, "Local wall-clock end in tz_name."),
    _c("local_date", DATE, "Local calendar date of the start."),
]

_SAMPLE_KEYS = [
    _c("sample_id", S, "Stable id: hash(type, source, start, end, value, unit)."),
    _c("record_nr", I64, "Lineage: stg_record.record_nr of the surviving raw row."),
    _c("type", S, "Short type name, e.g. HeartRate."),
    _c("type_identifier", S, "Full HealthKit identifier."),
    _c("source_id", S, "FK dim_source."),
    _c("device_id", S, "FK dim_device (null when the record has no device)."),
    _c("source_version", S, "Version of the writing app/OS."),
    _c("device_software", S, "Software/firmware version of the device at write time."),
]

_FK_SAMPLE = (
    ("source_id", "dim_source", "source_id"),
    ("device_id", "dim_device", "device_id"),
    ("type_identifier", "dim_data_type", "type_identifier"),
)


def warehouse_tables(cfg: object) -> dict[str, Table]:
    tables = [
        Table(
            "dim_data_type",
            "curated",
            "Every HealthKit sample type in the config registry or in the data.",
            (
                _c("type_identifier", S, "Full HealthKit identifier (PK)."),
                _c("type", S, "Short name (prefix stripped)."),
                _c("kind", S, "quantity | category."),
                _c("canonical_unit", S, "Unit of fct_quantity_sample.value for this type."),
                _c(
                    "aggregation",
                    S,
                    "cumulative (sum) | discrete (mean/min/max) | category | null (unknown).",
                ),
                _c("min_plausible", F64, "Lower plausible bound (config); outside -> is_outlier."),
                _c("max_plausible", F64, "Upper plausible bound (config)."),
                _c("is_known", BOOL, "Listed in config/types.toml."),
                _c("raw_units", STR_LIST, "Units seen in the export."),
                _c("n_raw_records", I64, "Raw records of this type in the export (before dedup)."),
            ),
            primary_key=("type_identifier",),
            sort_by=("type_identifier",),
        ),
        Table(
            "dim_source",
            "curated",
            "Apps and devices that wrote data. source_name has the owner's name stripped.",
            (
                _c("source_id", S, "PK: hash of the raw source name."),
                _c("source_name", S, "Normalised name, e.g. 'Apple Watch'."),
                _c("source_kind", S, "watch | phone | external_sensor | apple_app | third_party_app."),
                _c("priority_rank", I32, "Lower wins when sources overlap (config sources.priority)."),
                _c("source_name_raw", S, "Name as exported (may contain the owner's name; sensitive)."),
            ),
            primary_key=("source_id",),
            sort_by=("priority_rank", "source_name"),
        ),
        Table(
            "dim_device",
            "curated",
            "Device models parsed from HKDevice strings (pointer and local identifiers/MACs dropped).",
            (
                _c("device_id", S, "PK: hash(name, manufacturer, model, hardware)."),
                _c("name", S, "Device name (owner's name stripped)."),
                _c("manufacturer", S, ""),
                _c("model", S, ""),
                _c("hardware", S, "Hardware identifier, e.g. WatchN,M."),
                _c("device_class", S, "watch | phone | audio | sensor | other (heuristic)."),
            ),
            primary_key=("device_id",),
            sort_by=("device_id",),
        ),
        Table(
            "dim_category_value",
            "curated",
            "Category enum values with short labels and HealthKit ordinals.",
            (
                _c("type_identifier", S, "Category type."),
                _c("type", S, "Short type name."),
                _c("category_value", S, "Raw enum value, e.g. HKCategoryValueSleepAnalysisAsleepCore."),
                _c("label", S, "Short label, e.g. Core."),
                _c("ordinal", I32, "HealthKit raw value where configured."),
                _c("is_known", BOOL, "Configured in config/types.toml."),
                _c("n_raw_records", I64, "Raw records with this value (before deduplication)."),
            ),
            primary_key=("type_identifier", "category_value"),
            sort_by=("type_identifier", "ordinal", "category_value"),
        ),
        Table(
            "dim_timezone_period",
            "curated",
            "Inferred time-zone timeline from HKTimeZone evidence (workouts, sleep).",
            (
                _c("period_nr", I32, "PK, chronological."),
                _c("tz_name", S, "IANA zone."),
                _c("valid_from_utc", UTC, "Period start (midpoint to the previous period's evidence)."),
                _c("valid_to_utc", UTC, "Period end (midpoint to the next period's evidence)."),
                _c("first_evidence_utc", UTC, ""),
                _c("last_evidence_utc", UTC, ""),
                _c("n_evidence", I64, "Number of tagged samples/workouts in the period."),
            ),
            primary_key=("period_nr",),
            sort_by=("period_nr",),
        ),
        Table(
            "fct_quantity_sample",
            "curated",
            "One row per quantity record after deduplication. Values in the type's canonical unit "
            "(HealthKit '%' values are fractions 0-1). Partitioned by type.",
            (
                *_SAMPLE_KEYS,
                _c("value", F64, "Value in canonical_unit."),
                _c("unit", S, "Canonical unit."),
                _c("raw_unit", S, "Unit as exported."),
                *_TIME_COLS,
                _c("dup_count", I32, "Raw rows collapsed into this one by deduplication (1 = unique)."),
                _c("is_outlier", BOOL, "Value outside the plausible range of the type (kept, flagged)."),
                _c(
                    "is_priority_source",
                    BOOL,
                    "Source has the best priority among sources with this type in the same local hour.",
                ),
                *_promoted(cfg, "sample"),
                _LINEAGE,
            ),
            primary_key=("sample_id",),
            partition_by="type",
            sort_by=("type", "start_utc", "sample_id"),
            foreign_keys=_FK_SAMPLE,
        ),
        Table(
            "fct_category_sample",
            "curated",
            "One row per category record (sleep stages, stand hours, events) after deduplication.",
            (
                *_SAMPLE_KEYS,
                _c("category_value", S, "Raw enum value."),
                _c("label", S, "Short label from dim_category_value."),
                *_TIME_COLS,
                _c("dup_count", I32, "Raw rows collapsed into this one by deduplication."),
                *_promoted(cfg, "sample"),
                _LINEAGE,
            ),
            primary_key=("sample_id",),
            sort_by=("type", "start_utc", "sample_id"),
            foreign_keys=_FK_SAMPLE,
        ),
        Table(
            "fct_sample_metadata",
            "curated",
            "Every metadata entry of every surviving sample (long format).",
            (
                _c("sample_id", S, "FK fct_quantity_sample / fct_category_sample."),
                _c("ordinal", I32, "Position within the record."),
                _c("key", S, "Metadata key."),
                _c("value_raw", S, "Value as exported."),
                _c(
                    "value_num", F64, "Number parsed from value_raw ('101.477 kPa' -> 101.477; H:MM:SS -> s)."
                ),
                _c("value_unit", S, "Unit parsed from value_raw."),
                _c("value_canonical", F64, "value_num converted/scaled per config/metadata_keys.toml."),
                _c("canonical_unit", S, "Unit of value_canonical."),
            ),
            primary_key=("sample_id", "ordinal"),
            sort_by=("sample_id", "ordinal"),
        ),
    ]
    tables += _workout_tables(cfg)
    tables += _other_tables()
    tables += _derived_tables()
    from apple_health.marts.metrics import mart_tables  # registry lives with the marts

    tables += mart_tables()
    return {t.name: t for t in tables}


def _workout_stat_columns(cfg: object) -> list[Column]:
    cols = []
    for ident, stats in cfg.workout_statistics.items():  # type: ignore[attr-defined]
        unit = cfg.types[ident].unit  # type: ignore[attr-defined]
        for stat, col in stats.items():
            cols.append(_c(col, F64, f"WorkoutStatistics {stat} of {ident} ({unit})."))
    return cols


_W_FK = (("workout_id", "fct_workout", "workout_id"),)


def _workout_tables(cfg: object) -> list[Table]:
    metadata_value_cols = (
        _c("key", S, "Metadata key."),
        _c("value_raw", S, "Value as exported."),
        _c("value_num", F64, "Number parsed from value_raw."),
        _c("value_unit", S, "Unit parsed from value_raw."),
        _c("value_canonical", F64, "value_num converted/scaled per config/metadata_keys.toml."),
        _c("canonical_unit", S, "Unit of value_canonical."),
    )
    return [
        Table(
            "fct_workout",
            "curated",
            "One row per workout. Totals come from WorkoutStatistics (export v17 has no total* attributes).",
            (
                _c("workout_id", S, "Stable id: hash(activity type, source, start, end)."),
                _c("workout_nr", I64, "Lineage: stg_workout.workout_nr."),
                _c("activity_type", S, "Short activity type, e.g. Walking."),
                _c("activity_type_identifier", S, "Full HKWorkoutActivityType identifier."),
                _c("source_id", S, "FK dim_source."),
                _c("device_id", S, "FK dim_device."),
                _c("source_version", S, ""),
                _c("device_software", S, ""),
                _c("start_utc", UTC, ""),
                _c("end_utc", UTC, ""),
                _c("created_utc", UTC, ""),
                _c("duration_s", F64, "Active duration reported by HealthKit (excludes pauses)."),
                _c("elapsed_s", F64, "end_utc - start_utc in seconds (includes pauses)."),
                _c("tz_name", S, "IANA zone used for local times."),
                _c("tz_source", S, "explicit | inferred | default."),
                _c("start_local", LOCAL, ""),
                _c("end_local", LOCAL, ""),
                _c("local_date", DATE, "Local date of the start."),
                *_promoted(cfg, "workout"),
                *_workout_stat_columns(cfg),
                _c("total_distance", F64, "Legacy Workout@totalDistance (absent in export v17)."),
                _c("total_distance_unit", S, ""),
                _c("total_energy_burned", F64, "Legacy Workout@totalEnergyBurned (absent in export v17)."),
                _c("total_energy_burned_unit", S, ""),
                _c("n_activities", I32, "WorkoutActivity children (e.g. intervals)."),
                _c("n_events", I32, "WorkoutEvent rows (all levels)."),
                _c("n_pauses", I32, "Pause events."),
                _c("n_routes", I32, "WorkoutRoute children."),
                _c("has_route", BOOL, "At least one route with GPS points."),
                _c(
                    "overlaps_workout_id", S, "Another workout overlapping in time (largest overlap), if any."
                ),
                _LINEAGE,
            ),
            primary_key=("workout_id",),
            sort_by=("start_utc", "workout_id"),
            foreign_keys=(("source_id", "dim_source", "source_id"), ("device_id", "dim_device", "device_id")),
        ),
        Table(
            "fct_workout_activity",
            "curated",
            "WorkoutActivity children (e.g. intervals of a custom workout).",
            (
                _c("activity_id", S, "PK: the activity's HealthKit UUID."),
                _c("workout_id", S, "FK fct_workout."),
                _c("ordinal", I32, "Position within the workout."),
                _c("start_utc", UTC, ""),
                _c("end_utc", UTC, ""),
                _c("duration_s", F64, ""),
                _c("interval_step_key_path", S, "Metadata WOIntervalStepKeyPath."),
                _c("interval_step_successful", BOOL, "Metadata WOIntervalStepSuccessful."),
                _LINEAGE,
            ),
            primary_key=("activity_id",),
            sort_by=("workout_id", "ordinal"),
            foreign_keys=_W_FK,
        ),
        Table(
            "fct_workout_event",
            "curated",
            "Workout events: pause/resume, laps, segments, markers (workout or activity level).",
            (
                _c("workout_id", S, "FK fct_workout."),
                _c("ordinal", I32, "Position within the workout (all levels)."),
                _c("activity_id", S, "FK fct_workout_activity (null at workout level)."),
                _c("event_type", S, "Short event type, e.g. Pause."),
                _c("event_utc", UTC, ""),
                _c("duration_s", F64, "Event duration (segments, laps); null for instantaneous events."),
                _LINEAGE,
            ),
            primary_key=("workout_id", "ordinal"),
            sort_by=("workout_id", "ordinal"),
            foreign_keys=(*_W_FK, ("activity_id", "fct_workout_activity", "activity_id")),
        ),
        Table(
            "fct_workout_statistic",
            "curated",
            "All WorkoutStatistics in long form, values in the type's canonical unit.",
            (
                _c("workout_id", S, "FK fct_workout."),
                _c("ordinal", I32, "Position within the workout (all levels)."),
                _c("activity_id", S, "FK fct_workout_activity (null at workout level)."),
                _c("type", S, "Short quantity type."),
                _c("type_identifier", S, ""),
                _c("start_utc", UTC, ""),
                _c("end_utc", UTC, ""),
                _c("sum", F64, ""),
                _c("average", F64, ""),
                _c("minimum", F64, ""),
                _c("maximum", F64, ""),
                _c("unit", S, "Canonical unit."),
                _c("raw_unit", S, "Unit as exported."),
                _LINEAGE,
            ),
            primary_key=("workout_id", "ordinal"),
            sort_by=("workout_id", "ordinal"),
            foreign_keys=(*_W_FK, ("activity_id", "fct_workout_activity", "activity_id")),
        ),
        Table(
            "fct_workout_zone",
            "curated",
            "Workout zones (heart-rate zones computed by the system): time spent per zone.",
            (
                _c("workout_id", S, "FK fct_workout."),
                _c("ordinal", I32, "Position within the workout."),
                _c("activity_id", S, "FK fct_workout_activity (null at workout level)."),
                _c("group_ordinal", I32, "Zone group within the workout."),
                _c("zone_type", S, "Short quantity type of the zones, e.g. HeartRate."),
                _c("zone_source", S, "Zone definition source, e.g. system."),
                _c("unit", S, "Unit of minimum/maximum."),
                _c("minimum", F64, "Lower bound (null = open)."),
                _c("maximum", F64, "Upper bound (null = open)."),
                _c("duration_s", F64, "Time spent in the zone."),
                _LINEAGE,
            ),
            primary_key=("workout_id", "ordinal"),
            sort_by=("workout_id", "ordinal"),
            foreign_keys=_W_FK,
        ),
        Table(
            "fct_workout_metadata",
            "curated",
            "Every metadata entry of workouts and their activities, events and routes (long format), "
            "including app-specific keys (e.g. JEFIT 'Total Weight Lifted').",
            (
                _c("workout_id", S, "FK fct_workout."),
                _c("owner_kind", S, "workout | activity | event | route."),
                _c("owner_ordinal", I32, "Ordinal of the owning child; 0 for the workout itself."),
                _c("ordinal", I32, "Position within the owner."),
                *metadata_value_cols,
                _LINEAGE,
            ),
            primary_key=("workout_id", "owner_kind", "owner_ordinal", "ordinal"),
            sort_by=("workout_id", "owner_kind", "owner_ordinal", "ordinal"),
            foreign_keys=_W_FK,
        ),
        Table(
            "fct_workout_route",
            "curated",
            "WorkoutRoute elements and their GPX file.",
            (
                _c("route_id", S, "Stable id: hash(workout_id, start, end)."),
                _c("workout_id", S, "FK fct_workout."),
                _c("ordinal", I32, "Position within the workout."),
                _c("source_id", S, "FK dim_source."),
                _c("device_id", S, "FK dim_device."),
                _c("start_utc", UTC, ""),
                _c("end_utc", UTC, ""),
                _c("created_utc", UTC, ""),
                _c("file_name", S, "GPX file in workout-routes/."),
                _c("file_exists", BOOL, "The referenced GPX file is present."),
                _c(
                    "file_shared",
                    BOOL,
                    "Another route references the same file (minute-resolution file names).",
                ),
                _c("owns_file_points", BOOL, "This route was assigned the file's points (best time match)."),
                _c("n_points", I64, "Route points assigned to this route."),
                _c("sync_identifier", S, "Metadata HKMetadataKeySyncIdentifier."),
                _LINEAGE,
            ),
            primary_key=("route_id",),
            sort_by=("start_utc", "route_id"),
            foreign_keys=(*_W_FK, ("source_id", "dim_source", "source_id")),
        ),
        Table(
            "fct_route_point",
            "curated",
            "GPS points of workout routes. Sentinel values (-1) are nulled and flagged; nothing is dropped "
            "except exact duplicate points. Partitioned by year.",
            (
                _c("route_id", S, "FK fct_workout_route."),
                _c("seq", I64, "Position within the GPX file."),
                _c("file_name", S, "Lineage: GPX file."),
                _c("ts_utc", UTC, "Point timestamp (UTC, from GPX)."),
                _c("ts_local", LOCAL, "Local time in the workout's zone."),
                _c("lat", F64, "Latitude (WGS84)."),
                _c("lon", F64, "Longitude (WGS84)."),
                _c("elevation_m", F64, "Elevation; null when vAcc < 0 (invalid altitude)."),
                _c("speed_mps", F64, "Speed in m/s; null when < 0."),
                _c("course_deg", F64, "Course in degrees; null when < 0 (invalid)."),
                _c("h_acc_m", F64, "Horizontal accuracy (m)."),
                _c("v_acc_m", F64, "Vertical accuracy (m); null when < 0."),
                _c("segment_dist_m", F64, "Haversine distance to the previous point of the route (m)."),
                _c("invalid_course", BOOL, ""),
                _c("invalid_altitude", BOOL, ""),
                _c("speed_outlier", BOOL, "speed_mps above routes.max_speed_mps."),
                _c("low_accuracy", BOOL, "h_acc_m above routes.max_horizontal_accuracy_m."),
                _c("year", I64, "Partition: UTC year of ts_utc."),
            ),
            primary_key=("route_id", "seq"),
            partition_by="year",
            sort_by=("year", "route_id", "seq"),
            foreign_keys=(("route_id", "fct_workout_route", "route_id"),),
        ),
        Table(
            "bridge_workout_sample",
            "curated",
            "Samples linked to a workout by HealthKit (records nested in the workout, e.g. effort scores).",
            (
                _c("workout_id", S, "FK fct_workout."),
                _c("sample_id", S, "FK fct_quantity_sample / fct_category_sample."),
                _c("link_type", S, "nested_record."),
            ),
            primary_key=("workout_id", "sample_id"),
            sort_by=("workout_id", "sample_id"),
            foreign_keys=_W_FK,
        ),
    ]


def _other_tables() -> list[Table]:
    return [
        Table(
            "fct_hrv_beat",
            "curated",
            "Instantaneous heart rate of HRV (SDNN) measurements, with resolved timestamps.",
            (
                _c("sample_id", S, "FK fct_quantity_sample (type HeartRateVariabilitySDNN)."),
                _c("ordinal", I32, "Beat position within the measurement."),
                _c(
                    "beat_utc",
                    UTC,
                    "Beat instant (local time of day + parent date, midnight rollover handled).",
                ),
                _c("beat_local", LOCAL, "Local wall-clock beat time."),
                _c("bpm", F64, "Instantaneous beats per minute."),
                _c("rr_interval_ms_approx", F64, "60000 / bpm. Approximation: bpm is rounded in the export."),
                _c("within_parent_interval", BOOL, "beat_utc within the parent's start/end (± tolerance)."),
                _LINEAGE,
            ),
            primary_key=("sample_id", "ordinal"),
            sort_by=("beat_utc", "sample_id", "ordinal"),
            foreign_keys=(("sample_id", "fct_quantity_sample", "sample_id"),),
        ),
        Table(
            "fct_activity_summary",
            "curated",
            "Apple Activity rings, one row per local calendar day.",
            (
                _c("local_date", DATE, "PK: local calendar date (as exported, no time zone)."),
                _c("active_energy_kcal", F64, "Move ring value."),
                _c("active_energy_goal_kcal", F64, ""),
                _c("move_time_min", F64, "Move ring in minutes (only for time-based move goals; else 0)."),
                _c("move_time_goal_min", F64, ""),
                _c("exercise_min", F64, "Exercise ring."),
                _c("exercise_goal_min", F64, ""),
                _c("stand_hours", F64, "Stand ring."),
                _c("stand_goal_hours", F64, ""),
                _c("is_empty_day", BOOL, "All ring values are zero (device not worn / no data)."),
                _LINEAGE,
            ),
            primary_key=("local_date",),
            sort_by=("local_date",),
        ),
        Table(
            "dim_profile",
            "curated",
            "Profile characteristics (sensitive). One row.",
            (
                _c("date_of_birth", DATE, ""),
                _c("biological_sex", S, "e.g. Male, Female; null when not set."),
                _c("blood_type", S, "null when not set."),
                _c("fitzpatrick_skin_type", S, "null when not set."),
                _c("cardio_fitness_medications_use", S, ""),
                _LINEAGE,
            ),
        ),
        Table(
            "fct_audiogram",
            "curated",
            "Hearing tests (audiograms).",
            (
                _c("audiogram_id", S, "PK: hash(type, source, start, end)."),
                _c("source_id", S, "FK dim_source."),
                _c("device_id", S, "FK dim_device."),
                _c("start_utc", UTC, ""),
                _c("end_utc", UTC, ""),
                _c("created_utc", UTC, ""),
                _c("algorithm_version", S, "Metadata HKAlgorithmVersion."),
                _LINEAGE,
            ),
            primary_key=("audiogram_id",),
            sort_by=("start_utc",),
            foreign_keys=(("source_id", "dim_source", "source_id"), ("device_id", "dim_device", "device_id")),
        ),
        Table(
            "fct_audiogram_point",
            "curated",
            "Hearing sensitivity per frequency and ear (dB HL).",
            (
                _c("audiogram_id", S, "FK fct_audiogram."),
                _c("ordinal", I32, ""),
                _c("frequency_hz", F64, ""),
                _c("left_db_hl", F64, ""),
                _c("right_db_hl", F64, ""),
                _c("left_masked", BOOL, ""),
                _c("right_masked", BOOL, ""),
                _c("left_clamp_lower_db_hl", F64, ""),
                _c("left_clamp_upper_db_hl", F64, ""),
                _c("right_clamp_lower_db_hl", F64, ""),
                _c("right_clamp_upper_db_hl", F64, ""),
                _c("frequency_unit", S, "As exported (expected Hz)."),
                _c("level_unit", S, "As exported (expected dBHL)."),
            ),
            primary_key=("audiogram_id", "ordinal"),
            sort_by=("audiogram_id", "ordinal"),
            foreign_keys=(("audiogram_id", "fct_audiogram", "audiogram_id"),),
        ),
        Table(
            "dim_date",
            "curated",
            "Calendar of every local date covered by samples, workouts or activity summaries.",
            (
                _c("local_date", DATE, "PK."),
                _c("year", I32, ""),
                _c("quarter", I32, ""),
                _c("month", I32, ""),
                _c("month_name", S, ""),
                _c("day", I32, "Day of month."),
                _c("day_of_week", I32, "1 = Monday ... 7 = Sunday (ISO)."),
                _c("day_name", S, ""),
                _c("day_of_year", I32, ""),
                _c("iso_year", I32, ""),
                _c("iso_week", I32, ""),
                _c("is_weekend", BOOL, ""),
            ),
            primary_key=("local_date",),
            sort_by=("local_date",),
        ),
    ]


def _derived_tables() -> list[Table]:
    agg_cols = (
        _c(
            "aggregation",
            S,
            "cumulative | discrete (from dim_data_type; unknown types are treated as discrete).",
        ),
        _c("unit", S, "Canonical unit."),
        _c(
            "value",
            F64,
            "cumulative: sum over the priority source(s) of each local hour; discrete: mean of all samples.",
        ),
        _c("value_min", F64, "Smallest sample value (all sources)."),
        _c("value_max", F64, "Largest sample value (all sources)."),
        _c("n_samples", I64, "Samples contributing (all sources)."),
        _c("n_sources", I32, "Distinct sources with samples."),
        _c("n_outliers", I64, "Samples flagged is_outlier (included in the values)."),
        _c(
            "value_all_sources_sum",
            F64,
            "cumulative only: naive sum over all sources (double-counts overlapping sources).",
        ),
    )
    return [
        Table(
            "agg_quantity_hourly",
            "derived",
            "Quantity samples per type and local hour (start time). Overlapping sources of cumulative types "
            "are resolved by source priority per hour.",
            (
                _c("type", S, "Short type name."),
                _c("local_date", DATE, ""),
                _c("hour", I32, "Local hour of the sample start (0-23)."),
                *agg_cols,
                _c("sources_used", STR_LIST, "cumulative: source(s) whose values make up `value`."),
            ),
            primary_key=("type", "local_date", "hour"),
            sort_by=("type", "local_date", "hour"),
        ),
        Table(
            "agg_quantity_daily",
            "derived",
            "Quantity samples per type and local date. Cumulative: sum of the priority-resolved hourly "
            "values. Discrete: statistics over all samples.",
            (
                _c("type", S, "Short type name."),
                _c("local_date", DATE, ""),
                *agg_cols,
                _c("value_median", F64, "discrete only: median of all samples."),
                _c("sources_used", STR_LIST, "cumulative: sources used in at least one hour."),
            ),
            primary_key=("type", "local_date"),
            sort_by=("type", "local_date"),
        ),
        Table(
            "agg_sleep_session",
            "derived",
            "Sleep sessions built from SleepAnalysis samples (gap > sleep.session_gap_minutes starts a new "
            "session). For each stage the highest-priority source with that stage in the session is used.",
            (
                _c("session_id", S, "PK: hash of the session start."),
                _c("sleep_date", DATE, "Local date of the session end (wake-up date)."),
                _c("is_primary", BOOL, "Longest-asleep session of its sleep_date (main sleep vs. naps)."),
                _c("start_utc", UTC, ""),
                _c("end_utc", UTC, ""),
                _c("tz_name", S, "Zone of the session's last sample."),
                _c("start_local", LOCAL, ""),
                _c("end_local", LOCAL, ""),
                _c("span_s", F64, "end - start (s)."),
                _c("in_bed_s", F64, "InBed time (s)."),
                _c("asleep_s", F64, "Core + Deep + REM + AsleepUnspecified (s)."),
                _c("core_s", F64, ""),
                _c("deep_s", F64, ""),
                _c("rem_s", F64, ""),
                _c(
                    "asleep_unspecified_s", F64, "Stage-less sleep (before watchOS 9 or third-party sources)."
                ),
                _c("awake_s", F64, ""),
                _c(
                    "sleep_efficiency",
                    F64,
                    "asleep / (asleep + awake) for staged nights; asleep / span otherwise.",
                ),
                _c("stage_detail_available", BOOL, "Core/Deep/REM present."),
                _c("n_samples", I64, "Samples used."),
                _c("sources_used", STR_LIST, ""),
            ),
            primary_key=("session_id",),
            sort_by=("start_utc",),
        ),
        Table(
            "agg_data_coverage",
            "derived",
            "Samples per type, source and local date: tells 'zero' from 'not measured'.",
            (
                _c("type", S, "Short type name."),
                _c("kind", S, "quantity | category."),
                _c("source_id", S, "FK dim_source."),
                _c("source_name", S, ""),
                _c("local_date", DATE, ""),
                _c("n_samples", I64, ""),
                _c("first_start_utc", UTC, ""),
                _c("last_end_utc", UTC, ""),
            ),
            primary_key=("type", "source_id", "local_date"),
            sort_by=("type", "source_id", "local_date"),
        ),
    ]
