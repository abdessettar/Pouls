"""Every day explorer: mart_daily for the browser, and a description of each column.

The page filters and charts the rows client-side; labels, units and number formats come from here so
the page does not hard-code the 70-odd columns.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.marts import metrics as m
from apple_health.schemas import BOOL, F64, I32

GROUPS = {
    "Wear": m.CONTEXT,
    "Activity": m.ACTIVITY,
    "Rings": m.RINGS,
    "Heart": m.HEART,
    "Sleep": m.SLEEP,
    "Workouts": m.WORKOUTS,
    "Sound": m.HEARING,
    "Walking": m.MOBILITY,
}

# name -> (label, unit, format). Formats: int, dec1, dec2, pct (fractions), clock (hours after
# midnight), dur (minutes shown as h:mm).
LABELS: dict[str, tuple[str, str, str]] = {
    "watch_worn_hours": ("Hours with the Watch worn", "h", "int"),
    "steps": ("Steps", "", "int"),
    "distance_walking_running_km": ("Walking and running distance", "km", "dec1"),
    "distance_cycling_km": ("Cycling distance", "km", "dec1"),
    "flights_climbed": ("Floors climbed", "", "int"),
    "active_energy_kcal": ("Active energy", "kcal", "int"),
    "basal_energy_kcal": ("Resting energy", "kcal", "int"),
    "exercise_min": ("Exercise minutes", "min", "int"),
    "stand_time_min": ("Stand minutes", "min", "int"),
    "daylight_min": ("Time in daylight", "min", "int"),
    "physical_effort_avg": ("Physical effort", "kcal/hr·kg", "dec1"),
    "move_kcal": ("Move ring", "kcal", "int"),
    "move_goal_kcal": ("Move goal", "kcal", "int"),
    "exercise_ring_min": ("Exercise ring", "min", "int"),
    "exercise_goal_min": ("Exercise goal", "min", "int"),
    "stand_hours": ("Stand ring", "h", "int"),
    "stand_goal_hours": ("Stand goal", "h", "int"),
    "resting_hr_bpm": ("Resting heart rate", "bpm", "int"),
    "walking_hr_avg_bpm": ("Walking heart rate", "bpm", "int"),
    "hr_mean_bpm": ("Mean heart rate", "bpm", "int"),
    "hr_min_bpm": ("Lowest heart rate", "bpm", "int"),
    "hr_max_bpm": ("Highest heart rate", "bpm", "int"),
    "hrv_sdnn_ms": ("HRV, all readings (SDNN)", "ms", "int"),
    "hrv_sdnn_sleep_ms": ("HRV during sleep (SDNN)", "ms", "int"),
    "hr_recovery_1min_bpm": ("Heart-rate recovery, 1 min", "bpm", "int"),
    "vo2max": ("VO2max estimate", "mL/min·kg", "dec1"),
    "vo2max_asof": ("VO2max, latest estimate", "mL/min·kg", "dec1"),
    "respiratory_rate_sleep": ("Breathing rate in sleep", "/min", "dec1"),
    "spo2_median": ("Blood oxygen, median", "", "pct"),
    "spo2_min": ("Blood oxygen, lowest", "", "pct"),
    "wrist_temp_sleep_c": ("Wrist temperature in sleep", "°C", "dec2"),
    "sleep_asleep_min": ("Time asleep", "", "dur"),
    "sleep_in_bed_min": ("Time in bed", "", "dur"),
    "sleep_core_min": ("Core sleep", "", "dur"),
    "sleep_deep_min": ("Deep sleep", "", "dur"),
    "sleep_rem_min": ("REM sleep", "", "dur"),
    "sleep_awake_min": ("Awake in the night", "min", "int"),
    "sleep_efficiency": ("Sleep efficiency", "", "pct"),
    "bedtime_h": ("Bedtime", "", "clock"),
    "waketime_h": ("Wake-up", "", "clock"),
    "sleep_midpoint_h": ("Sleep midpoint", "", "clock"),
    "nap_min": ("Naps", "min", "int"),
    "n_sleep_sessions": ("Sleep sessions", "", "int"),
    "n_workouts": ("Workouts", "", "int"),
    "workout_min": ("Workout minutes", "min", "int"),
    "workout_active_energy_kcal": ("Workout active energy", "kcal", "int"),
    "workout_distance_km": ("Workout distance", "km", "dec1"),
    "weather_temperature_c": ("Temperature outdoors", "°C", "dec1"),
    "env_audio_laeq_db": ("Environmental sound level", "dB", "int"),
    "env_audio_h": ("Environmental sound measured", "h", "dec1"),
    "headphone_audio_laeq_db": ("Headphone sound level", "dB", "int"),
    "headphone_audio_h": ("Headphone listening", "h", "dec1"),
    "audio_exposure_events": ("Sound notifications", "", "int"),
    "walking_speed_kmh": ("Walking speed", "km/h", "dec2"),
    "walking_step_length_cm": ("Step length", "cm", "int"),
    "walking_double_support": ("Double support time", "", "pct"),
    "walking_asymmetry": ("Walking asymmetry", "", "pct"),
    "walking_steadiness": ("Walking steadiness", "", "pct"),
}


def _fallback(name: str) -> tuple[str, str, str]:
    return name.replace("_", " ").capitalize(), "", "dec1"


def columns() -> list[dict[str, Any]]:
    """Numeric and flag columns of mart_daily, grouped as in the metric registry."""
    out = []
    for group, metrics in GROUPS.items():
        for metric in metrics:
            if metric.dtype == BOOL:
                kind = "flag"
            elif metric.dtype in (F64, I32):
                kind = "number"
            else:
                continue
            label, unit, fmt = LABELS.get(metric.name, _fallback(metric.name))
            out.append(
                {
                    "name": metric.name,
                    "group": group,
                    "kind": kind,
                    "label": label,
                    "unit": unit,
                    "format": fmt,
                    "doc": metric.doc,
                }
            )
    return out


def frame(wh: Warehouse) -> pl.DataFrame:
    """mart_daily with browser-friendly types: dates and times as text, lists joined."""
    d = wh.read("marts", "mart_daily")
    return d.with_columns(
        pl.col("local_date").dt.strftime("%Y-%m-%d"),
        pl.col("sleep_start_local", "sleep_end_local").dt.strftime("%Y-%m-%dT%H:%M"),
        pl.col("workout_types").list.join(", "),
        pl.col(pl.Int64).cast(pl.Int32),
    ).sort("local_date")


def build(wh: Warehouse) -> dict[str, Any]:
    from apple_health.config import load_config

    s = load_config().settings
    d = wh.read("marts", "mart_daily")
    return {
        "columns": columns(),
        "default_timezone": s.default_timezone,
        "valid_day_min_worn_hours": s.valid_day_min_worn_hours,
        "first": d["local_date"].min(),
        "last": d["local_date"].max(),
    }
