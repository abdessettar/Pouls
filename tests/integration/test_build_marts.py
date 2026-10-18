from __future__ import annotations

from datetime import date, datetime

import polars as pl
import pytest

from apple_health import io


@pytest.fixture(scope="module")
def marts(built_warehouse):
    return built_warehouse / "marts"


@pytest.fixture(scope="module")
def daily(marts):
    return io.read(marts, "mart_daily")


def _day(daily, d):
    return daily.filter(pl.col("local_date") == d).row(0, named=True)


def test_grid_has_every_day(daily):
    assert daily["local_date"].min() == date(2019, 6, 4)
    assert daily["local_date"].max() == date(2023, 7, 28)
    assert daily.height == (date(2023, 7, 28) - date(2019, 6, 4)).days + 1


def test_activity_day(daily):
    d = _day(daily, date(2023, 1, 15))
    assert d["steps"] == 800.0  # Watch + iPhone overlap resolved
    assert d["active_energy_kcal"] == 150.5  # 00:30 "+0200" sample belongs to the 15th locally
    assert (d["move_kcal"], d["move_goal_met"], d["exercise_goal_met"], d["all_rings_closed"]) == (
        150.5,
        False,
        True,
        False,
    )
    assert d["resting_hr_bpm"] == 58.0  # latest estimate of the day
    assert d["vo2max"] == 45.0
    assert (d["n_workouts"], d["workout_min"], d["workout_distance_km"]) == (1, 28.0, 2.1)
    assert d["headphone_audio_laeq_db"] == pytest.approx(71.2)
    assert d["is_weekend"] and d["tz_name"] == "Europe/Berlin" and not d["is_non_default_tz"]


def test_wear(marts, daily):
    wear = io.read(marts, "mart_wear_hourly").filter(pl.col("local_date") == date(2023, 1, 15))
    assert wear.height == 24
    assert wear.filter("is_worn")["hour"].to_list() == [8, 9]  # 09:00 and 10:00 "+0200" in winter
    d = _day(daily, date(2023, 1, 15))
    assert (d["watch_worn_hours"], d["has_watch_data"], d["is_valid_wear_day"]) == (2, True, False)
    assert _day(daily, date(2019, 6, 4))["has_watch_data"] is False


def test_sleep_is_attributed_to_the_wake_up_day(daily):
    night = _day(daily, date(2023, 1, 16))
    assert night["sleep_start_local"] == datetime(2023, 1, 15, 23, 0)
    assert (night["sleep_asleep_min"], night["sleep_in_bed_min"], night["sleep_deep_min"]) == (
        450.0,
        480.0,
        60.0,
    )
    assert (night["bedtime_h"], night["waketime_h"], night["sleep_midpoint_h"]) == (23.0, 7.0, 27.0)
    assert night["hrv_sdnn_sleep_ms"] == 45.5  # reading at 23:59 local, inside the session
    assert night["n_sleep_sessions"] == 1 and night["nap_min"] == 0.0
    assert _day(daily, date(2023, 1, 15))["hrv_sdnn_ms"] == 45.5  # same reading, by its own date
    assert _day(daily, date(2023, 1, 15))["nap_min"] is None  # no session ends that day


def test_vo2max_asof_carries_forward(daily):
    assert _day(daily, date(2023, 1, 14))["vo2max_asof"] is None
    assert _day(daily, date(2023, 7, 20))["vo2max_asof"] == 45.0
    assert _day(daily, date(2023, 7, 20))["vo2max"] is None


def test_travel_and_overlapping_workouts(daily):
    abroad = _day(daily, date(2023, 7, 20))
    assert (abroad["tz_name"], abroad["is_non_default_tz"]) == ("Africa/Lagos", True)
    strength = _day(daily, date(2023, 7, 25))
    assert (strength["n_workouts"], strength["workout_min"]) == (1, 50.0)  # JEFIT duplicate not counted


def test_rollups(marts, daily):
    weekly = io.read(marts, "mart_weekly")
    w = weekly.filter((pl.col("iso_year") == 2023) & (pl.col("iso_week") == 2)).row(0, named=True)
    assert (w["week_start"], w["n_days"], w["steps"], w["n_workouts"]) == (date(2023, 1, 9), 7, 800.0, 1)
    assert w["is_weekend_days"] == 2 and w["resting_hr_bpm"] == 58.0
    monthly = io.read(marts, "mart_monthly")
    assert monthly["steps"].sum() == daily["steps"].sum() == weekly["steps"].sum()
    jan = monthly.filter((pl.col("year") == 2023) & (pl.col("month") == 1)).row(0, named=True)
    assert (jan["month_start"], jan["n_days"]) == (date(2023, 1, 1), 31)
