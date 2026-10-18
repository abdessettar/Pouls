from __future__ import annotations

from datetime import date, datetime

import polars as pl
import pytest

from apple_health import io


@pytest.fixture(scope="module")
def der(built_warehouse):
    return built_warehouse / "derived"


def _row(df, **eq):
    for k, v in eq.items():
        df = df.filter(pl.col(k) == v)
    assert df.height == 1, eq
    return df.row(0, named=True)


def test_daily_steps_are_not_double_counted(der):
    daily = io.read(der, "agg_quantity_daily")
    steps = _row(daily, type="StepCount", local_date=date(2023, 1, 15))
    # 09:00 hour: Watch 500 and iPhone 450 overlap -> Watch; 11:00 hour: iPhone only -> 300
    assert steps["value"] == 800.0
    assert steps["value_all_sources_sum"] == 1250.0
    assert steps["sources_used"] == ["Apple Watch", "iPhone"]
    hourly = io.read(der, "agg_quantity_hourly").filter(pl.col("type") == "StepCount")
    assert _row(hourly, local_date=date(2023, 1, 15), hour=9)["sources_used"] == ["Apple Watch"]


def test_daily_energy_uses_local_dates(der):
    energy = _row(io.read(der, "agg_quantity_daily"), type="ActiveEnergyBurned")
    assert (energy["local_date"], energy["value"]) == (date(2023, 1, 15), 150.5)


def test_discrete_statistics(der):
    hr = _row(io.read(der, "agg_quantity_daily"), type="HeartRate", local_date=date(2023, 7, 28))
    assert (hr["value"], hr["value_min"], hr["value_max"], hr["n_sources"]) == (149.0, 148.0, 150.0, 2)
    assert hr["value_all_sources_sum"] is None and hr["sources_used"] is None


def test_sleep_sessions(der):
    s = io.read(der, "agg_sleep_session").sort("start_utc")
    legacy, night = s.row(0, named=True), s.row(1, named=True)
    assert night["sleep_date"] == date(2023, 1, 16)
    assert night["start_local"] == datetime(2023, 1, 15, 23, 0)
    assert night["in_bed_s"] == 8 * 3600  # iPhone InBed: the only InBed source
    assert (night["core_s"], night["deep_s"], night["rem_s"], night["awake_s"]) == (19800, 3600, 3600, 600)
    assert night["asleep_s"] == 27000 and night["sleep_efficiency"] == pytest.approx(27000 / 27600)
    assert night["stage_detail_available"] and night["is_primary"]
    assert not legacy["stage_detail_available"] and legacy["asleep_unspecified_s"] == 6 * 3600


def test_coverage(der, built_warehouse):
    cov = io.read(der, "agg_data_coverage")
    cur = built_warehouse / "curated"
    total = io.read(cur, "fct_quantity_sample").height + io.read(cur, "fct_category_sample").height
    assert cov["n_samples"].sum() == total
    steps = cov.filter((pl.col("type") == "StepCount") & (pl.col("local_date") == date(2023, 1, 15)))
    assert dict(steps.select("source_name", "n_samples").rows()) == {"Apple Watch": 1, "iPhone": 2}
