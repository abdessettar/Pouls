from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from apple_health import io


@pytest.fixture(scope="module")
def marts(built_warehouse):
    return built_warehouse / "marts"


def _row(df, **eq):
    for k, v in eq.items():
        df = df.filter(pl.col(k) == v)
    assert df.height == 1, eq
    return df.row(0, named=True)


def test_mart_workout(marts):
    w = io.read(marts, "mart_workout")
    walk = _row(w, local_date=date(2023, 1, 15))
    assert (walk["zone1_min"], walk["zone2_min"], walk["has_zones"]) == (10.0, 18.0, True)
    assert walk["trimp"] == 10 * 1 + 18 * 2
    assert walk["effort_score"] == 4.0
    assert walk["pace_s_per_km"] == pytest.approx(28 * 60 / 2.1)
    assert walk["activity_group"] == "walking"
    jefit = _row(w, source_name="JEFIT")
    assert (jefit["is_counted"], jefit["strength_volume_kg"], jefit["trimp"]) == (False, 1250.5, None)
    assert w["is_counted"].sum() == 5
    watch_strength = _row(w, local_date=date(2023, 7, 25), source_name="Apple Watch")
    assert (
        watch_strength["is_counted"] and watch_strength["strength_volume_kg"] == 1250.5
    )  # from the JEFIT copy


def test_training_weekly_and_load(marts):
    weekly = io.read(marts, "mart_training_weekly")
    strength = _row(weekly, week_start=date(2023, 7, 24), activity_group="strength")
    assert (strength["sessions"], strength["minutes"]) == (1, 50.0)  # the JEFIT duplicate is not counted
    assert _row(weekly, week_start=date(2023, 7, 24), activity_group="running")["distance_km"] == 3.9
    load = io.read(marts, "mart_training_load")
    assert load["local_date"].min() == date(2023, 1, 15) and load["local_date"].max() == date(2023, 7, 28)
    assert _row(load, local_date=date(2023, 1, 15))["trimp"] == 46.0
    assert load.filter(pl.col("local_date") < date(2023, 2, 11))["acwr"].null_count() > 0  # < 28 days history


def test_mart_sleep_night(marts):
    n = _row(io.read(marts, "mart_sleep_night"), night_date=date(2023, 1, 16))
    assert n["deep_share"] == pytest.approx(60 / 450)
    assert (n["prev_steps"], n["prev_workout_min"], n["prev_n_workouts"], n["late_workout"]) == (
        800.0,
        28.0,
        1,
        False,
    )
    assert n["hrv_sdnn_sleep_ms"] == 45.5 and n["bedtime_h"] == 23.0


def test_runs_and_splits(marts):
    run = _row(io.read(marts, "mart_run"), local_date=date(2023, 7, 28))
    assert run["distance_km"] == 3.9 and run["pace_s_per_km"] == pytest.approx(20 * 60 / 3.9)
    assert run["best_1k_s"] == 596.0 and run["best_5k_s"] is None and run["has_route"]
    splits = io.read(marts, "mart_run_split").sort("split")
    assert splits["split"].to_list() == [1, 2, 3]
    assert splits["distance_m"][:2].to_list() == [1000.0, 1000.0]
    assert splits["avg_hr_bpm"][0] == 149.0  # Watch 148 and chest strap 150 in the first km


def test_routes_and_tracks(marts):
    r = io.read(marts, "mart_route").sort("start_utc")
    assert r.height == 2
    walk = r.row(0, named=True)
    assert walk["distance_km"] == pytest.approx(0.393, abs=0.001)
    assert walk["elevation_gain_m"] == 4.0
    assert (walk["area_id"], walk["area_name"]) == (1, "Berlin")
    assert r.row(1, named=True)["area_name"] == "Berlin 2"  # 136 km away: its own area
    assert io.read(marts, "mart_route_track").height == 9


def test_records(marts):
    rec = {r["record_id"]: r for r in io.read(marts, "mart_records").iter_rows(named=True)}
    assert (rec["most_steps_day"]["value"], rec["most_steps_day"]["start_date"]) == (800.0, date(2023, 1, 15))
    assert rec["longest_run"]["value"] == 3.9 and rec["fastest_1k"]["value"] == 596.0
    assert rec["total_workouts"]["value"] == 5.0
    assert rec["streak_workout_days"]["value"] == 1.0


def test_yearly(marts):
    y = io.read(marts, "mart_yearly")
    assert y["year"].to_list() == [2019, 2020, 2021, 2022, 2023]
    assert _row(y, year=2023)["steps"] == 800.0


def test_reference_bands_follow_age_and_sex(marts):
    ref = io.read(marts, "mart_reference")
    vo2 = ref.filter((pl.col("metric") == "vo2max") & (pl.col("band") == "p25_p50")).sort("valid_from")
    # The fixture profile: born 1 January 1990, female; FRIEND women 20-29, then 30-39 from 2020.
    assert vo2["valid_to"][0] == date(2019, 12, 31) and vo2["valid_from"][1] == date(2020, 1, 1)
    assert vo2["lo"].to_list() == [30.5, 25.3]
    assert vo2["population"][1] == "Women aged 30–39, FRIEND registry, US treadmill tests"
    assert ref.filter(pl.col("population").str.starts_with("Men")).height == 0
    assert set(ref["source_id"]) <= set(io.read(marts, "mart_reference_source")["source_id"])


def test_workout_heart_rate_per_minute(marts):
    run = _row(io.read(marts, "mart_workout"), local_date=date(2023, 7, 28))
    hr = io.read(marts, "mart_workout_hr").filter(pl.col("workout_id") == run["workout_id"])
    # Watch 148 and chest strap 150, five minutes in: both sources count, as in the splits.
    assert hr.select("minute", "hr_bpm", "n_samples").rows() == [(5, 149.0, 2)]
    jefit = _row(io.read(marts, "mart_workout"), source_name="JEFIT")
    assert io.read(marts, "mart_workout_hr").filter(pl.col("workout_id") == jefit["workout_id"]).height == 0
