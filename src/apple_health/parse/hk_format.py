"""What the pipeline knows about the HealthKit export format (export version 17 DTD).

Anything outside these sets is still captured (``extra_attrs`` columns, ``stg_other_element``)
and reported by the source contract, so format changes never silently lose data.
"""

from __future__ import annotations

# Top-level children of <HealthData> that the parser maps to dedicated staging tables.
HANDLED_TOP_LEVEL = frozenset({"ExportDate", "Me", "Record", "Workout", "ActivitySummary", "Audiogram"})

# Declared in the DTD but absent from the profiled export: captured generically.
DECLARED_UNHANDLED_TOP_LEVEL = frozenset({"Correlation", "ClinicalRecord", "VisionPrescription"})

KNOWN_CHILDREN: dict[str, frozenset[str]] = {
    "Record": frozenset({"MetadataEntry", "HeartRateVariabilityMetadataList"}),
    "HeartRateVariabilityMetadataList": frozenset({"InstantaneousBeatsPerMinute"}),
    "Workout": frozenset(
        {
            "MetadataEntry",
            "WorkoutEvent",
            "WorkoutRoute",
            "WorkoutStatistics",
            "WorkoutActivity",
            "WorkoutZoneGroup",
            "Record",
        }
    ),
    "WorkoutActivity": frozenset({"MetadataEntry", "WorkoutEvent", "WorkoutStatistics", "WorkoutZoneGroup"}),
    "WorkoutEvent": frozenset({"MetadataEntry"}),
    "WorkoutRoute": frozenset({"MetadataEntry", "FileReference"}),
    "WorkoutZoneGroup": frozenset({"WorkoutZone"}),
    "Audiogram": frozenset({"MetadataEntry", "SensitivityPoint"}),
}

_SAMPLE = ("sourceName", "sourceVersion", "device", "creationDate", "startDate", "endDate")

KNOWN_ATTRS: dict[str, tuple[str, ...]] = {
    "HealthData": ("locale",),
    "ExportDate": ("value",),
    "Me": (
        "HKCharacteristicTypeIdentifierDateOfBirth",
        "HKCharacteristicTypeIdentifierBiologicalSex",
        "HKCharacteristicTypeIdentifierBloodType",
        "HKCharacteristicTypeIdentifierFitzpatrickSkinType",
        "HKCharacteristicTypeIdentifierCardioFitnessMedicationsUse",
    ),
    "Record": ("type", "unit", "value", *_SAMPLE),
    "Workout": (
        "workoutActivityType",
        "duration",
        "durationUnit",
        "totalDistance",
        "totalDistanceUnit",
        "totalEnergyBurned",
        "totalEnergyBurnedUnit",
        *_SAMPLE,
    ),
    "WorkoutActivity": ("uuid", "startDate", "endDate", "duration", "durationUnit"),
    "WorkoutEvent": ("type", "date", "duration", "durationUnit"),
    "WorkoutStatistics": ("type", "startDate", "endDate", "average", "minimum", "maximum", "sum", "unit"),
    "WorkoutRoute": _SAMPLE,
    "WorkoutZoneGroup": ("type", "source", "unit"),
    "WorkoutZone": ("minimum", "maximum", "duration", "durationUnit"),
    "FileReference": ("path",),
    "ActivitySummary": (
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
    ),
    "MetadataEntry": ("key", "value"),
    "HeartRateVariabilityMetadataList": (),
    "InstantaneousBeatsPerMinute": ("bpm", "time"),
    "Audiogram": ("type", *_SAMPLE),
    "SensitivityPoint": (
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
    ),
}

GPX_NS = "http://www.topografix.com/GPX/1/1"
GPX_VERSION = "1.1"
KNOWN_GPX_EXTENSIONS = ("speed", "course", "hAcc", "vAcc")
