from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from apple_health.marts.baselines import build_baselines
from apple_health.marts.metrics import mart_daily_table
from apple_health.marts.records import longest_streak
from apple_health.marts.routes import cluster, elevation_gain, haversine_m, thin
from apple_health.marts.running import best_effort, clean_cumulative, splits
from apple_health.transform.context import BuildContext


def test_longest_streak():
    d0 = date(2024, 1, 1)
    dates = [d0 + timedelta(days=i) for i in range(8)]
    flags = [True, True, False, True, True, True, None, True]
    assert longest_streak(dates, flags) == (3, dates[3], dates[5])
    assert longest_streak(dates, [False] * 8) == (0, None, None)


def test_clean_cumulative_drops_gps_jumps():
    t = [0, 1, 1, 2, 3]
    seg = [None, 3.0, 50.0, 3.0, 3.0]  # 50 m in the same second: a jump
    assert clean_cumulative(t, seg) == [0.0, 3.0, 3.0, 6.0, 9.0]


def test_best_effort_and_splits():
    # 2.5 km at 5 min/km, except the second km at 4 min/km
    cum = [0.0, 500.0, 1000.0, 1500.0, 2000.0, 2500.0]
    t = [0.0, 150.0, 300.0, 420.0, 540.0, 690.0]
    assert best_effort(cum, t, 1000) == 240.0
    assert best_effort(cum, t, 5000) is None
    s = splits(cum, t, [10.0, None, 12.0, 12.0, 15.0, 20.0], 1000)
    assert [round(x["distance_m"]) for x in s] == [1000, 1000, 500]
    assert [round(x["pace_s_per_km"]) for x in s] == [300, 240, 300]
    assert s[0]["elevation_change_m"] == pytest.approx(2.0)


def test_route_helpers():
    assert haversine_m(45.0, 5.0, 45.0, 5.001) == pytest.approx(78.63, abs=0.01)
    assert elevation_gain([100, 101, 102, None, 103, 104, 101, 106]) == pytest.approx(9.0)
    assert elevation_gain([None]) is None
    assert thin([None, 5.0, 5.0, 5.0, 5.0, 5.0], 12) == [0, 3, 5]
    assert cluster([(52.52, 13.40), (52.53, 13.41), (53.55, 9.99), (52.51, 13.39)], 25) == [0, 0, 1, 0]


def test_baselines_on_synthetic_daily(base_config, tmp_path):
    t = mart_daily_table()
    n = 120
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    df = pl.DataFrame({c.name: [None] * n for c in t.columns}, schema=t.schema()).with_columns(
        pl.Series("local_date", days),
        pl.Series("is_valid_wear_day", [i % 10 != 9 for i in range(n)]),  # every 10th day not worn
        pl.Series("resting_hr_bpm", [60.0 + (i % 5) for i in range(n)]),
    )
    marts = tmp_path / "marts"
    marts.mkdir()
    df.write_parquet(marts / "mart_daily.parquet")
    ctx = BuildContext(base_config, tmp_path / "staging", tmp_path / "curated", tmp_path / "derived", marts)
    build_baselines(ctx)
    b = pl.read_parquet(marts / "mart_baselines.parquet")
    assert set(b["metric"]) == {"resting_hr_bpm"}
    assert b.height == sum(i % 10 != 9 for i in range(n))  # valid wear days only
    last = b.sort("local_date").row(-1, named=True)
    assert last["normal_p10"] <= last["normal_p50"] <= last["normal_p90"]
    assert 60 <= last["baseline_mean"] <= 64 and last["baseline_sd"] > 0
    assert last["z"] == pytest.approx((last["value"] - last["baseline_mean"]) / last["baseline_sd"])
    early = b.sort("local_date").row(5, named=True)
    assert early["z"] is None  # fewer than baseline_min_days of history


def test_place_name_weighs_size_against_distance():
    from apple_health.marts.routes import place_name

    places = [
        ("Big city", 45.0, 5.0, 1_000_000),
        ("Suburb", 45.18, 5.0, 20_000),
        ("Far town", 47.0, 5.0, 50_000),
    ]
    assert place_name(45.2, 5.0, places, 50) == "Big city"  # 22 km away, but much bigger than the suburb
    assert place_name(45.18, 5.0, places, 50) == "Big city"
    assert place_name(46.0, 5.0, places, 50) == "Suburb"  # nothing within 50 km: the nearest within 100 km
    assert place_name(46.95, 5.0, places, 50) == "Far town"
    assert place_name(10.0, 10.0, places, 50) is None
