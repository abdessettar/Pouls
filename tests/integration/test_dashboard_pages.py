from __future__ import annotations

import json
from datetime import date

import polars as pl
import pytest

from apple_health.dashboard import Warehouse, alltime, dumps, overview


@pytest.fixture(scope="module")
def wh(built_warehouse):
    return Warehouse(built_warehouse)


def test_overview(wh):
    ov = overview.build(wh)
    keys = [k["key"] for k in ov["kpis"]]
    assert keys == [
        "steps",
        "active_energy",
        "exercise",
        "rings",
        "resting_hr",
        "hrv",
        "vo2max",
        "respiratory_rate",
        "asleep",
        "bedtime",
        "training",
        "running",
    ]
    assert {k["stat"] for k in ov["kpis"]} == {"median", "rate_week", "share", "last"}
    # One row per day of the history; empty fields are left out.
    assert ov["days"][0]["d"] == date(2019, 6, 4) and len(ov["days"]) == wh.read("marts", "mart_daily").height
    run_day = next(d for d in ov["days"] if d["d"] == date(2023, 7, 28))
    assert run_day["run_km"] == 3.9
    assert all(v is not None for d in ov["days"] for v in d.values())
    assert next(d for d in ov["days"] if d["d"] == date(2023, 1, 15))["vo2max"] == 45.0
    assert [w["d"] for w in ov["workouts"]][-1] == date(2023, 7, 28) and len(ov["workouts"]) == 5
    assert set(ov["references"]) >= {"steps", "resting_hr", "vo2max", "sleep_duration"}
    json.loads(dumps(ov))


def test_alltime(wh):
    at = alltime.build(wh)
    assert at["series"]["steps"][0]["month_start"] == date(2019, 6, 1)
    assert at["series"]["running"][-1]["value"] == 3.9
    assert [y["year"] for y in at["years"]] == [2019, 2020, 2021, 2022, 2023]
    rec = {r["record_id"]: r for r in at["records"]}
    assert rec["longest_run"]["value"] == 3.9
    assert any(t["tz_name"] == "Africa/Lagos" for t in at["trips"])
    assert {e["label"] for e in at["events"]} == {"Apple Watch", "Sleep stages", "Daylight"}
    json.loads(dumps(at))


def test_activity_heart_sleep_builders(wh):
    from apple_health.dashboard import activity, heart, sleep

    act = activity.build(wh)
    assert act["monthly_steps"] == []  # fewer than 10 days per month in the fixture
    assert {r["local_date"] for r in act["calendar"]} >= {date(2023, 1, 15)}
    h = heart.build(wh)
    assert h["vo2max"] == [{"d": date(2023, 1, 15), "v": 45.0}]
    assert set(h["series"]) == {"resting_hr", "hrv", "respiratory_rate", "spo2"}
    bc = sleep.barcode_data(wh)
    night = next(n for n in bc["barcode"] if n["d"] == date(2023, 1, 16))
    assert (night["s"], night["e"]) == (-60, 420)  # 23:00 to 07:00 around the wake-up day's midnight
    assert [bc["stage_codes"][g[2]] for g in night["g"]] == ["Core", "Deep", "REM", "Awake", "Core"]
    assert night["g"][0][:2] == [-50, 60]
    s = sleep.build(wh)
    n16 = next(n for n in s["nights"] if n["d"] == date(2023, 1, 16))
    assert n16["deep"] == pytest.approx(60 / 450, abs=1e-4) and n16["prev_steps"] == 800.0
    assert all(v is not None for n in s["nights"] for v in n.values())
    for build in (act, h, s, bc):
        json.loads(dumps(build))


def test_training_running_places_builders(wh):
    from apple_health.dashboard import places, running, training
    from apple_health.dashboard.polyline import decode

    t = training.build(wh)
    assert t["load"][0] == {"d": date(2023, 1, 15), "t": 46.0, "a": None, "c": None, "r": None}
    assert t["zones_monthly"][0]["zone2_min"] == 18.0
    assert {w["activity_group"] for w in t["weekly"]} >= {"walking", "running", "strength"}

    r = running.build(wh)
    run = r["runs"][0]
    assert (run["distance_km"], run["best_1k_s"]) == (3.9, 596.0)
    detail = r["detail"][run["workout_id"]]
    assert [s[0] for s in detail["splits"]] == [1, 2, 3]
    assert decode(detail["polyline"]) == [(46.0, 6.0), (46.01, 6.0), (46.02, 6.0)]

    tracks = places.tracks(wh)
    p = places.build(wh)
    assert [a["area_name"] for a in p["areas"]] == ["Berlin", "Berlin 2"]
    assert {x["route_id"] for x in p["routes"]} == set(tracks)
    assert p["trips"]["periods"][0]["tz_name"] == "Africa/Lagos" and p["home_tz"] == "Europe/Berlin"
    for build in (t, r, p):
        json.loads(dumps(build))


def test_explorer_and_notes_builders(wh):
    import io

    import polars as pl

    from apple_health.dashboard import explorer, notes

    cols = {c["name"]: c for c in explorer.columns()}
    assert cols["resting_hr_bpm"]["group"] == "Heart" and cols["resting_hr_bpm"]["unit"] == "bpm"
    assert cols["is_valid_wear_day"]["kind"] == "flag" and "local_date" not in cols
    f = explorer.frame(wh)
    buf = io.BytesIO()
    f.write_parquet(buf)
    buf.seek(0)
    back = pl.read_parquet(buf)
    assert back["local_date"].dtype == pl.String and back["local_date"][0] == "2019-06-04"
    assert pl.Int64 not in back.dtypes  # Int64 would arrive as BigInt in the browser

    n = notes.build(wh)
    assert {s["source_id"] for s in n["reference_sources"]} >= {b["source_id"] for b in n["references"]}
    assert {c["family"] for c in n["coverage"]} == set(n["coverage_families"])
    assert all(0 <= c["share"] <= 1 for c in n["coverage"])
    assert all("name" not in d for d in n["devices"])  # device names can carry a person's name
    json.loads(dumps(n))


def test_workouts_builder(wh):
    from apple_health.dashboard import workouts

    b = workouts.build(wh)
    kinds = {k["key"]: k for k in b["kinds"]}
    assert set(kinds) == {"Walking", "Cycling", "TraditionalStrengthTraining", "Running"}
    assert kinds["Walking"]["sessions"] == 2 and kinds["Walking"]["speed"] == "pace"
    assert kinds["TraditionalStrengthTraining"]["sessions"] == 1  # the JEFIT copy is not counted
    assert not kinds["TraditionalStrengthTraining"]["outdoor"] and kinds["Running"]["outdoor"]
    walk = next(s for s in b["sessions"] if s["d"] == date(2023, 1, 15))
    assert walk["zone_lo"] == [0.0, 120.0] and walk["route_id"]
    assert all(v is not None for s in b["sessions"] for v in s.values())  # empty fields are left out
    run = next(s for s in b["sessions"] if s["kind"] == "Running")
    assert workouts.heart_rate(wh)[run["id"]] == [None, None, None, None, None, 149]
    json.loads(dumps(b))


def test_hourly_builder(wh):
    from apple_health.dashboard import hourly

    rows = hourly.build(wh)
    valid = wh.read("marts", "mart_daily").filter(pl.col("is_valid_wear_day")).height
    assert len(rows) == valid
    assert all(len(r["steps"]) == 24 and len(r["hr"]) == 24 for r in rows)
    json.loads(dumps(rows))
