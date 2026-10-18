from __future__ import annotations

import math
from datetime import date

import polars as pl
import pytest

from apple_health.marts.daily import _rollup_exprs
from apple_health.marts.metrics import (
    DAILY_METRICS,
    Metric,
    mart_daily_table,
    mart_weekly_table,
    rolled_up_columns,
)


def test_registry_is_consistent():
    names = [m.name for m in DAILY_METRICS]
    assert len(names) == len(set(names))
    assert mart_daily_table().column_names == ["local_date", *names]
    weights = {m.weight for m in DAILY_METRICS if m.weight}
    assert weights <= set(names)


def test_metric_validation():
    with pytest.raises(ValueError, match="unknown rollup"):
        Metric("x", pl.Float64, "", "median")
    with pytest.raises(ValueError, match="weight"):
        Metric("x", pl.Float64, "", "energetic_mean")


def test_rollup_column_naming():
    cols = {c.name for c in rolled_up_columns()}
    assert {"steps", "steps_daily_avg", "is_valid_wear_day_days", "resting_hr_bpm", "vo2max_asof"} <= cols
    assert "tz_name" not in cols and "workout_types" not in cols  # rollup "none"
    weekly = mart_weekly_table().column_names
    assert weekly[:5] == ["iso_year", "iso_week", "week_start", "n_days", "n_valid_wear_days"]


def test_rollup_rules():
    metrics = [
        Metric("steps", pl.Float64, "", "sum"),
        Metric("rhr", pl.Float64, "", "mean"),
        Metric("lo", pl.Float64, "", "min"),
        Metric("asof", pl.Float64, "", "last"),
        Metric("flag", pl.Boolean, "", "count_true"),
        Metric("db", pl.Float64, "", "energetic_mean", weight="h"),
        Metric("h", pl.Float64, "", "sum"),
    ]
    daily = pl.DataFrame(
        {
            "local_date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
            "steps": [1000.0, None, 3000.0],
            "rhr": [60.0, 62.0, None],
            "lo": [5.0, 3.0, 4.0],
            "asof": [40.0, 41.0, None],
            "flag": [True, None, True],
            "db": [60.0, 70.0, None],
            "h": [1.0, 1.0, 2.0],
        }
    )
    out = daily.select(_rollup_exprs(metrics)).row(0, named=True)
    assert out["steps"] == 4000.0 and out["steps_daily_avg"] == 2000.0
    assert out["rhr"] == 61.0 and out["lo"] == 3.0 and out["asof"] == 41.0
    assert out["flag_days"] == 2
    # duration-weighted energy average of 60 dB and 70 dB for 1 h each (2 h without a level ignored)
    assert out["db"] == pytest.approx(10 * math.log10((10**6 + 10**7) / 2))
    empty = daily.filter(pl.lit(False)).select(_rollup_exprs(metrics)).row(0, named=True)
    assert empty["steps"] is None and empty["db"] is None
