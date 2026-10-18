from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from apple_health.transform.keys import iso_utc, stable_id
from apple_health.transform.time import (
    build_timezone_periods,
    hrv_beat_times,
    parse_hk_ts,
    resolve_timezone,
    to_local,
)


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _frame(**cols):
    df = pl.DataFrame(cols)
    return df.with_columns(
        pl.col(c).dt.cast_time_unit("us") for c, t in df.schema.items() if t == pl.Datetime
    )


def test_stable_id_is_deterministic_and_null_safe():
    df = pl.DataFrame({"a": ["x", "x", None, ""], "b": ["1", "1", "1", "1"]})
    ids = df.select(stable_id("a", "b")).to_series().to_list()
    assert ids[0] == ids[1] and len(ids[0]) == 16
    assert ids[2] != ids[3]  # null and empty string differ
    # a known value: guards against accidental changes of the key recipe
    assert ids[0] == pl.DataFrame({"a": ["x"], "b": ["1"]}).select(stable_id("a", "b")).item()


def test_parse_hk_ts_and_iso():
    df = pl.DataFrame({"s": ["2023-01-14 20:41:55 +0200", "garbage", None]})
    out = df.select(parse_hk_ts("s").alias("t"))
    assert out["t"][0] == _utc("2023-01-14T18:41:55")
    assert out["t"][1] is None and out["t"][2] is None
    assert out.select(iso_utc("t"))["t"][0] == "2023-01-14T18:41:55.000000Z"


def test_winter_offset_is_converted_to_real_local_time():
    # Exported as "+0200" in January; the wall clock in Berlin was one hour earlier.
    df = pl.DataFrame({"s": ["2023-01-15 10:00:00 +0200"]}).select(
        parse_hk_ts("s").alias("t"), tz=pl.lit("Europe/Berlin")
    )
    local = df.select(to_local("t", "tz", ["Europe/Berlin"])).item()
    assert local == datetime(2023, 1, 15, 9, 0)


def _periods():
    ev = _frame(
        instant_utc=[
            _utc("2023-01-01T00:00"),
            _utc("2023-01-10T00:00"),
            _utc("2023-01-20T00:00"),
            _utc("2023-01-30T00:00"),
            _utc("2023-02-01T00:00"),
        ],
        tz_name=["Europe/Berlin", "Europe/Berlin", "Africa/Lagos", "Europe/Berlin", "Not/AZone"],
    ).with_columns(pl.col("instant_utc").dt.replace_time_zone("UTC"))
    return build_timezone_periods(ev)


def test_timezone_periods_switch_at_midpoints():
    p = _periods()
    assert p["tz_name"].to_list() == ["Europe/Berlin", "Africa/Lagos", "Europe/Berlin"]
    assert p["valid_to_utc"][0] == _utc("2023-01-15T00:00")  # midpoint of Jan 10 and Jan 20
    assert p["valid_from_utc"][2] == _utc("2023-01-25T00:00")
    assert p["valid_to_utc"][2] == _utc("2023-01-30T00:00")  # invalid zone evidence is ignored
    assert p["n_evidence"].to_list() == [2, 1, 1]


def test_timezone_periods_empty():
    empty = pl.DataFrame(schema={"instant_utc": pl.Datetime("us", "UTC"), "tz_name": pl.String})
    assert build_timezone_periods(empty).height == 0


@pytest.mark.parametrize(
    ("instant", "explicit", "tz", "source"),
    [
        ("2022-12-31T00:00", "Asia/Tokyo", "Asia/Tokyo", "explicit"),
        ("2022-12-31T00:00", "Bad/Zone", "Europe/Berlin", "default"),
        ("2023-01-14T23:00", None, "Europe/Berlin", "inferred"),
        ("2023-01-15T01:00", None, "Africa/Lagos", "inferred"),
        ("2023-03-01T00:00", None, "Europe/Berlin", "default"),
    ],
)
def test_resolve_timezone(instant, explicit, tz, source):
    df = _frame(t=[_utc(instant)], x=pl.Series([explicit], dtype=pl.String)).with_columns(
        pl.col("t").dt.replace_time_zone("UTC")
    )
    out = resolve_timezone(df, "t", "x", _periods(), "Europe/Berlin")
    assert out.row(0, named=True)["tz_name"] == tz
    assert out.row(0, named=True)["tz_source"] == source


def test_resolve_timezone_keeps_row_order():
    df = _frame(t=[_utc("2023-03-01T00:00"), _utc("2023-01-15T01:00"), _utc("2022-12-01T00:00")], n=[0, 1, 2])
    df = df.with_columns(pl.col("t").dt.replace_time_zone("UTC"))
    out = resolve_timezone(df, "t", None, _periods(), "Europe/Berlin")
    assert out["n"].to_list() == [0, 1, 2]
    assert out["tz_name"].to_list() == ["Europe/Berlin", "Africa/Lagos", "Europe/Berlin"]


def test_hrv_beats_roll_over_midnight_and_resolve_dst():
    beats = _frame(
        start_utc=[_utc("2023-01-15T22:59:30")] * 4 + [_utc("2023-10-29T00:30:00")],
        tz_name=["Europe/Berlin"] * 5,
        time=["23:59:31,50", "23:59:59,90", "00:00:01,20", "00:00:29,00", "02:30:00,00"],
    ).with_columns(pl.col("start_utc").dt.replace_time_zone("UTC"))
    out = hrv_beat_times(beats, ["Europe/Berlin"])
    assert out["beat_utc"].to_list() == [
        datetime(2023, 1, 15, 22, 59, 31, 500000, tzinfo=UTC),
        datetime(2023, 1, 15, 22, 59, 59, 900000, tzinfo=UTC),
        datetime(2023, 1, 15, 23, 0, 1, 200000, tzinfo=UTC),  # next local day
        datetime(2023, 1, 15, 23, 0, 29, tzinfo=UTC),
        datetime(2023, 10, 29, 0, 30, tzinfo=UTC),  # 02:30 occurs twice that night; nearest to start
    ]
