from __future__ import annotations

import polars as pl
import pytest

from apple_health.transform.units import conversion, is_convertible, parse_value_expr


@pytest.mark.parametrize(
    ("src", "dst", "value", "expected"),
    [
        ("degF", "degC", 41.0, 5.0),
        ("degF", "degC", 212.0, 100.0),
        ("cm", "m", 1250.0, 12.5),
        ("km/hr", "m/s", 36.0, 10.0),
        ("min", "s", 2.5, 150.0),
        ("kcal", "kcal", 7.0, 7.0),
        ("K", "degC", 273.15, 0.0),
    ],
)
def test_conversion(src, dst, value, expected):
    a, b = conversion(src, dst)
    assert value * a + b == pytest.approx(expected)


def test_not_convertible():
    assert conversion("kg", "m") is None
    assert conversion("appleEffortScore", "count") is None
    assert not is_convertible(None, "kg")
    assert is_convertible("appleEffortScore", "appleEffortScore")


def test_parse_value_expr():
    raw = [
        "101.477 kPa",
        "6",
        "0:25:06",
        "1.6 kcal/hr·kg",
        "Europe/Berlin",
        "-2.5e-3 m",
        "10000 %",
        None,
        "6:B954C970-2086:665135298.70451",
    ]
    df = pl.DataFrame({"value_raw": raw}).with_columns(parse_value_expr())
    assert df["value_num"].to_list() == [101.477, 6.0, 1506.0, 1.6, None, -0.0025, 10000.0, None, None]
    assert df["value_unit"].to_list() == ["kPa", None, "s", "kcal/hr·kg", None, "m", "%", None, None]
