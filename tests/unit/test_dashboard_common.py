from __future__ import annotations

import json
import math
from datetime import date, datetime

import polars as pl
import pytest

from apple_health.dashboard import ENV_WAREHOUSE, Warehouse, dumps, jsonable
from apple_health.dashboard.meta import build, windows


def test_jsonable_handles_nan_dates_and_frames():
    df = pl.DataFrame({"d": [date(2024, 1, 2)], "x": [float("nan")], "y": [1.23456789]})
    out = jsonable({"df": df, "inf": math.inf, "when": datetime(2024, 1, 2, 3, 4), "t": (1, None)})
    assert out == {
        "df": [{"d": "2024-01-02", "x": None, "y": 1.234568}],
        "inf": None,
        "when": "2024-01-02T03:04:00",
        "t": [1, None],
    }
    assert json.loads(dumps({"v": float("nan")})) == {"v": None}


def test_warehouse_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_WAREHOUSE, str(tmp_path))
    assert Warehouse.locate().root == tmp_path.resolve()


def test_windows_keep_weekdays_aligned():
    w = windows(date(2025, 5, 5))
    assert w["current"] == {"start": "2025-04-08", "end": "2025-05-05"}
    assert w["previous"] == {"start": "2025-03-11", "end": "2025-04-07"}
    cur, ago = date.fromisoformat(w["current"]["start"]), date.fromisoformat(w["year_ago"]["start"])
    assert cur.weekday() == ago.weekday()


def test_meta_on_fixture(built_warehouse):
    m = build(Warehouse(built_warehouse))
    assert m["data_through"] == date(2023, 7, 28)
    assert m["first_day"] == date(2019, 6, 4)
    assert m["firsts"]["watch"] == date(2023, 1, 15)
    assert m["firsts"]["sleep_stages"] == date(2023, 1, 16)
    assert m["n_days"] == (date(2023, 7, 28) - date(2019, 6, 4)).days + 1
    json.loads(dumps(m))


def test_meta_loader_script_runs(built_warehouse, monkeypatch, capsys):
    import runpy
    from pathlib import Path

    monkeypatch.setenv(ENV_WAREHOUSE, str(built_warehouse))
    loader = Path(__file__).resolve().parents[2] / "dashboard" / "src" / "data" / "meta.json.py"
    runpy.run_path(str(loader))
    assert json.loads(capsys.readouterr().out)["data_through"] == "2023-07-28"


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_dumps_never_emits_nan(bad):
    assert "NaN" not in dumps([bad]) and "Infinity" not in dumps([bad])


def test_polyline_matches_the_reference_example():
    from apple_health.dashboard.polyline import decode, encode

    # The worked example from Google's encoded polyline algorithm documentation.
    points = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    assert encode(points) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    assert decode("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == points
    assert decode(encode([(52.520008, 13.404954)])) == [(52.52001, 13.40495)]  # rounded to 5 decimals


def test_workout_kinds_split_indoor_only_where_apple_does():
    from apple_health.dashboard.workouts import kind_key, kind_label

    assert (kind_key("Cycling", True), kind_label("Cycling", True)) == ("Cycling:indoor", "Indoor cycling")
    assert (kind_key("Cycling", False), kind_label("Cycling", None)) == ("Cycling", "Cycling")
    # Strength sessions carry the indoor flag too, but there is no outdoor variant to tell apart.
    assert kind_key("TraditionalStrengthTraining", True) == "TraditionalStrengthTraining"
    assert kind_label("TraditionalStrengthTraining", True) == "Strength training"
    assert kind_label("MindAndBody", None) == "Mind and body"
