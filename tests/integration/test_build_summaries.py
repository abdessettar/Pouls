from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl
import pytest

from apple_health import io


@pytest.fixture(scope="module")
def cur(built_warehouse):
    return built_warehouse / "curated"


def test_hrv_beats(cur):
    beats = io.read(cur, "fct_hrv_beat").sort("beat_utc")
    assert beats.height == 6
    assert beats["within_parent_interval"].all()
    winter = beats.head(4)
    assert winter["beat_utc"][2] == datetime(2023, 1, 15, 23, 0, 1, 200000, tzinfo=UTC)  # after midnight
    assert winter["beat_local"][2] == datetime(2023, 1, 16, 0, 0, 1, 200000)
    # Abroad in summer: "10:30:01" is Berlin time (export zone); the sample is local to Lagos.
    abroad = beats.tail(2)
    assert abroad["beat_utc"][0] == datetime(2023, 7, 20, 8, 30, 1, tzinfo=UTC)
    assert abroad["beat_local"][0] == datetime(2023, 7, 20, 9, 30, 1)
    assert beats["rr_interval_ms_approx"][0] == pytest.approx(1000.0)


def test_activity_summary(cur):
    a = io.read(cur, "fct_activity_summary").sort("local_date")
    assert a["local_date"].to_list() == [date(2023, 1, 15), date(2023, 1, 16)]
    assert a["active_energy_kcal"].to_list() == [150.5, 0.0]
    assert a["is_empty_day"].to_list() == [False, True]


def test_activity_reconciliation_uses_local_dates(cur):
    dq = pl.read_parquet(cur / "_dq.parquet")
    rec = dq.filter(pl.col("name") == "activity_summary_reconciliation").row(0, named=True)
    assert rec["passed"] and rec["observed"].startswith("100.0% of 1 days")
    assert dq.filter(pl.col("name") == "export_timezone_consistent")["passed"].item()


def test_profile(cur):
    p = io.read(cur, "dim_profile").row(0, named=True)
    assert p["date_of_birth"] == date(1990, 1, 1)
    assert p["biological_sex"] == "Female"
    assert p["blood_type"] is None and p["fitzpatrick_skin_type"] is None


def test_audiogram(cur):
    pts = io.read(cur, "fct_audiogram_point").sort("ordinal")
    assert pts["frequency_hz"].to_list() == [250.0, 1000.0]
    assert pts["right_masked"].to_list() == [False, True]
    assert io.read(cur, "fct_audiogram")["algorithm_version"].item() == "1"


def test_dim_date(cur):
    d = io.read(cur, "dim_date")
    assert d["local_date"].min() == date(2019, 6, 4) and d["local_date"].max() == date(2023, 7, 28)
    assert d["local_date"].is_unique().all()
    row = d.filter(pl.col("local_date") == date(2023, 1, 15)).row(0, named=True)
    assert (row["day_of_week"], row["day_name"], row["is_weekend"], row["iso_week"]) == (7, "Sunday", True, 2)
