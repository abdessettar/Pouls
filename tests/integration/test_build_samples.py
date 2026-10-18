from __future__ import annotations

from datetime import date, datetime

import polars as pl
import pytest

from apple_health import io
from apple_health.manifest import read_json
from apple_health.schemas import warehouse_tables


@pytest.fixture(scope="module")
def cur(built_warehouse):
    return built_warehouse / "curated"


def _q(cur):
    return io.read(cur, "fct_quantity_sample")


def test_schemas_match_definitions(built_warehouse, base_config):
    for name, t in warehouse_tables(base_config).items():
        layer = built_warehouse / t.layer
        assert io.table_path(layer, name).exists(), name
        df = io.read(layer, name)
        expected = t.schema()
        if t.partition_by:
            assert set(df.columns) == set(expected)
            df = df.select(expected.names())
        assert df.schema == expected, name


def test_dedup_counts(cur):
    stats = read_json(cur / "_build.json")["stats"]["record_dedup"]
    assert stats == {"raw": 33, "exact_duplicates_dropped": 1, "rewrites_dropped": 2, "final": 30}
    hr = _q(cur).filter((pl.col("type") == "HeartRate") & (pl.col("value") == 62))
    assert hr.height == 1 and hr["dup_count"].item() == 3
    assert hr["hr_motion_context"].item() == 1  # the latest rewrite wins


def test_local_time_and_date(cur):
    q = _q(cur)
    hr = q.filter((pl.col("type") == "HeartRate") & (pl.col("value") == 62)).row(0, named=True)
    assert hr["start_local"] == datetime(2023, 1, 15, 8, 0)  # exported "09:00 +0200" in winter
    late = q.filter((pl.col("type") == "ActiveEnergyBurned") & (pl.col("value") == 50)).row(0, named=True)
    assert late["local_date"] == date(2023, 1, 15)  # exported as 2023-01-16 00:30 +0200
    abroad = q.filter((pl.col("type") == "HeartRate") & (pl.col("value") == 95)).row(0, named=True)
    assert (abroad["tz_name"], abroad["tz_source"]) == ("Africa/Lagos", "inferred")
    assert abroad["start_local"] == datetime(2023, 7, 20, 9, 0)
    old = q.filter(pl.col("start_utc").dt.year() == 2019)
    assert set(old["tz_source"]) == {"default"}


def test_flags(cur):
    q = _q(cur)
    assert q.filter(pl.col("is_outlier"))["value"].to_list() == [300.0]
    steps = q.filter((pl.col("type") == "StepCount") & (pl.col("local_date") == date(2023, 1, 15)))
    flags = dict(zip(steps["value"].to_list(), steps["is_priority_source"].to_list(), strict=True))
    assert flags == {500.0: True, 450.0: False, 300.0: True}
    spo2 = q.filter(pl.col("type") == "OxygenSaturation").row(0, named=True)
    assert (spo2["value"], spo2["unit"]) == (0.97, "%")


def test_categories(cur):
    c = io.read(cur, "fct_category_sample")
    sleep = c.filter(pl.col("type") == "SleepAnalysis").sort("start_utc")
    assert sleep["label"].to_list() == ["AsleepUnspecified", "InBed", "Core", "Deep", "REM", "Awake", "Core"]
    assert set(sleep["tz_source"]) == {"explicit"}
    stand = c.filter(pl.col("type") == "AppleStandHour")
    assert stand.height == 1 and stand["dup_count"].item() == 2


def test_dimensions(cur):
    src = io.read(cur, "dim_source")
    assert "Test User’s Apple Watch" not in src["source_name"].to_list()
    dev = io.read(cur, "dim_device")
    assert not any("Test User" in (n or "") for n in dev["name"].to_list())
    types = io.read(cur, "dim_data_type")
    new = types.filter(pl.col("type") == "NewFancyMetric").row(0, named=True)
    assert not new["is_known"] and new["kind"] == "quantity"
    periods = io.read(cur, "dim_timezone_period")
    assert periods["tz_name"].to_list() == ["Europe/Berlin", "Africa/Lagos", "Europe/Berlin"]


def test_dq_report(cur):
    dq = pl.read_parquet(cur / "_dq.parquet")
    assert dq.filter(~pl.col("passed") & (pl.col("severity") == "error")).height == 0
    failed = set(dq.filter(~pl.col("passed"))["name"])
    assert "quantity_outlier_rate" in failed  # the synthetic 300 bpm


def test_watch_with_no_break_space_is_classified(cur):
    src = io.read(cur, "dim_source").filter(pl.col("source_name") == "Apple Watch")
    assert set(src["source_kind"]) == {"watch"} and set(src["priority_rank"]) == {0}
    assert src.height == 2  # NBSP spelling (records) and plain spelling (workouts) both normalise
    dq = pl.read_parquet(cur / "_dq.parquet")
    assert dq.filter(pl.col("name") == "owner_name_stripped")["passed"].item()
