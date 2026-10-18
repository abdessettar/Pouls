from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from apple_health import io


@pytest.fixture(scope="module")
def cur(built_warehouse):
    return built_warehouse / "curated"


@pytest.fixture(scope="module")
def workouts(cur):
    return io.read(cur, "fct_workout")


def _one(df, **eq):
    out = df
    for k, v in eq.items():
        out = out.filter(pl.col(k) == v)
    assert out.height == 1, eq
    return out.row(0, named=True)


def test_workout_attributes(workouts):
    walk = _one(workouts, activity_type="Walking", tz_name="Europe/Berlin")
    assert walk["start_local"] == datetime(2023, 1, 15, 9, 0)
    assert (walk["duration_s"], walk["elapsed_s"]) == (1680.0, 1800.0)  # pause excluded from duration
    assert walk["weather_temperature_c"] == pytest.approx(5.0)
    assert walk["weather_humidity_pct"] == 80.0
    assert walk["elevation_ascended_m"] == 12.5
    assert walk["is_indoor"] is False
    assert (walk["active_energy_kcal"], walk["distance_walking_running_km"]) == (100.5, 2.1)
    assert (walk["heart_rate_min_bpm"], walk["heart_rate_avg_bpm"], walk["heart_rate_max_bpm"]) == (
        90,
        110,
        130,
    )
    assert (walk["n_events"], walk["n_pauses"], walk["n_routes"], walk["has_route"]) == (3, 1, 1, True)
    abroad = _one(workouts, tz_name="Africa/Lagos")
    assert abroad["start_local"] == datetime(2023, 7, 20, 9, 0)


def test_overlapping_workouts_are_linked(workouts):
    strength = workouts.filter(pl.col("activity_type") == "TraditionalStrengthTraining")
    ids = set(strength["workout_id"])
    assert set(strength["overlaps_workout_id"]) == ids
    assert workouts.filter(pl.col("overlaps_workout_id").is_not_null()).height == 2


def test_children(cur, workouts):
    run_id = _one(workouts, activity_type="Running")["workout_id"]
    acts = io.read(cur, "fct_workout_activity").filter(pl.col("workout_id") == run_id).sort("ordinal")
    assert acts["interval_step_successful"].to_list() == [True, False]
    stats = io.read(cur, "fct_workout_statistic").filter(pl.col("workout_id") == run_id)
    assert stats.filter(pl.col("activity_id").is_not_null())["sum"].sort().to_list() == [1.9, 2.0]
    zones = io.read(cur, "fct_workout_zone")
    assert zones["duration_s"].to_list() == [600.0, 1080.0]
    jefit = _one(workouts, activity_type="TraditionalStrengthTraining", tz_source="inferred")
    meta = io.read(cur, "fct_workout_metadata").filter(pl.col("workout_id") == jefit["workout_id"])
    assert dict(meta.select("key", "value_canonical").rows())["Total Rest Time"] == 90.0


def test_routes_and_points(cur):
    routes = io.read(cur, "fct_workout_route").sort("start_utc")
    shared = routes.filter(pl.col("file_shared"))
    assert shared.height == 2
    owner = shared.filter(pl.col("owns_file_points")).row(0, named=True)
    assert owner["start_utc"] == datetime(2023, 7, 28, 5, 0, 4, tzinfo=UTC)  # best match to the GPX times
    assert owner["n_points"] == 4
    pts = io.read(cur, "fct_route_point")
    assert pts.height == 10  # 11 GPX points, 1 exact duplicate dropped
    walk = pts.filter(pl.col("file_name") == "route_2023-01-15_9.30am.gpx").sort("seq")
    assert walk["invalid_course"].sum() == 1 and walk["course_deg"].null_count() == 1
    assert walk["invalid_altitude"].sum() == 1 and walk["elevation_m"].null_count() == 1
    assert walk["speed_outlier"].sum() == 1 and walk["low_accuracy"].sum() == 1
    assert walk["segment_dist_m"][1] == pytest.approx(78.63, abs=0.01)  # 0.001° of longitude at 45°N
    assert walk["ts_local"][0] == datetime(2023, 1, 15, 9, 0)
    assert set(pts["year"]) == {2023}


def test_bridge(cur):
    bridge = io.read(cur, "bridge_workout_sample")
    q = io.read(cur, "fct_quantity_sample")
    linked = q.join(bridge, on="sample_id")
    assert linked["type"].to_list() == ["WorkoutEffortScore"]
