from __future__ import annotations

from datetime import date

import pytest

from apple_health.coach import context
from apple_health.coach.redact import safe
from apple_health.dashboard import Warehouse, dumps


@pytest.fixture(scope="module")
def wh(built_warehouse):
    return Warehouse(built_warehouse)


def test_every_summary_is_safe_to_send(wh):
    run_id = context.workouts(wh, date(2023, 7, 1), date(2023, 7, 31), kind="Running")["workouts"][0]["id"]
    for result in (
        context.status(wh),
        context.history(wh),
        context.recovery(wh),
        context.workouts(wh, date(2023, 1, 1), date(2023, 12, 31)),
        context.workout(wh, run_id),
        context.weight(wh),
        context.references(wh),
    ):
        assert safe(result) == result  # nothing to remove, nothing refused
        assert "Europe/" not in dumps(result) and "Africa/" not in dumps(result)


def test_status_and_profile(wh):
    s = context.status(wh)
    last_day = wh.read("marts", "mart_daily")["local_date"].max()
    assert s["data_through"] == s["as_of"] == last_day.isoformat()
    assert s["last_28_days"]["to"] == last_day.isoformat()
    assert s["profile"] == {"age": 33, "sex": "Female", "height_cm": None}
    keys = [m["key"] for m in s["last_28_days"]["metrics"]]
    assert {"steps", "training", "strength", "running", "resting_hr", "vo2max"} <= set(keys)
    assert s["last_workout"]["kind"] == "Running"
    assert "date_of_birth" not in dumps(s)


def test_workouts_and_detail(wh):
    w = context.workouts(wh, date(2023, 1, 1), date(2023, 12, 31))
    assert w["total"] == 5  # the JEFIT copy is not counted
    run = next(x for x in w["workouts"] if x["kind"] == "Running")
    assert run["recorded_by"] == "watch" and run["distance_km"] == 3.9
    detail = context.workout(wh, run["id"])
    assert detail["hr_per_minute"] == [None, None, None, None, None, 149.0]
    assert [s["km"] for s in detail["splits"]] == [1, 2, 3]
    assert "route_id" not in detail and "polyline" not in dumps(detail)


def test_history_and_recovery(wh):
    h = context.history(wh)
    assert h["months"][0]["month"] == "2019-06-01"
    assert h["best_12_weeks"]["training_h_per_week"] > 0
    r = context.recovery(wh, date(2023, 7, 28), days=7)
    assert [d["date"] for d in r["days"]][-1] == "2023-07-28"
    assert all("tz_name" not in d for d in r["days"])
