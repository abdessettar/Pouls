"""Unit conversions and parsing of HealthKit values that embed their unit ("101.477 kPa")."""

from __future__ import annotations

import polars as pl

# unit -> (dimension, factor, offset) with base = value * factor + offset
_UNITS: dict[str, tuple[str, float, float]] = {
    # length (base m)
    "mm": ("length", 0.001, 0.0),
    "cm": ("length", 0.01, 0.0),
    "m": ("length", 1.0, 0.0),
    "km": ("length", 1000.0, 0.0),
    "in": ("length", 0.0254, 0.0),
    "ft": ("length", 0.3048, 0.0),
    "yd": ("length", 0.9144, 0.0),
    "mi": ("length", 1609.344, 0.0),
    # mass (base kg)
    "g": ("mass", 0.001, 0.0),
    "kg": ("mass", 1.0, 0.0),
    "lb": ("mass", 0.45359237, 0.0),
    "oz": ("mass", 0.028349523125, 0.0),
    # time (base s)
    "ms": ("time", 0.001, 0.0),
    "s": ("time", 1.0, 0.0),
    "min": ("time", 60.0, 0.0),
    "hr": ("time", 3600.0, 0.0),
    "d": ("time", 86400.0, 0.0),
    # energy (base kcal); HealthKit "Cal" is the food calorie = kcal
    "kcal": ("energy", 1.0, 0.0),
    "Cal": ("energy", 1.0, 0.0),
    "cal": ("energy", 0.001, 0.0),
    "kJ": ("energy", 0.239005736137667, 0.0),
    "J": ("energy", 0.000239005736137667, 0.0),
    # temperature (base degC)
    "degC": ("temperature", 1.0, 0.0),
    "degF": ("temperature", 5.0 / 9.0, -32.0 * 5.0 / 9.0),
    "K": ("temperature", 1.0, -273.15),
    # speed (base m/s)
    "m/s": ("speed", 1.0, 0.0),
    "km/hr": ("speed", 1.0 / 3.6, 0.0),
    "mi/hr": ("speed", 0.44704, 0.0),
    # frequency (base count/min)
    "count/min": ("frequency", 1.0, 0.0),
    "count/s": ("frequency", 60.0, 0.0),
    # pressure (base kPa)
    "Pa": ("pressure", 0.001, 0.0),
    "kPa": ("pressure", 1.0, 0.0),
    "mmHg": ("pressure", 0.133322387415, 0.0),
    "cmAq": ("pressure", 0.0980665, 0.0),
}


def conversion(from_unit: str | None, to_unit: str | None) -> tuple[float, float] | None:
    """Linear conversion ``to = from * a + b``; ``None`` if the units are not convertible."""
    if from_unit == to_unit:
        return (1.0, 0.0)
    if from_unit is None or to_unit is None:
        return None
    src, dst = _UNITS.get(from_unit), _UNITS.get(to_unit)
    if src is None or dst is None or src[0] != dst[0]:
        return None
    _, f1, o1 = src
    _, f2, o2 = dst
    # base = x*f1 + o1 ; y = (base - o2) / f2
    return (f1 / f2, (o1 - o2) / f2)


def is_convertible(from_unit: str | None, to_unit: str | None) -> bool:
    return conversion(from_unit, to_unit) is not None


DURATION_TO_SECONDS = {u: f for u, (dim, f, _) in _UNITS.items() if dim == "time"}

NUMBER_WITH_UNIT = r"^\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?:\s+(\S.*?))?\s*$"
HMS = r"^(\d+):([0-5]\d):([0-5]\d(?:\.\d+)?)$"


def parse_value_expr(col: str = "value_raw") -> list[pl.Expr]:
    """Expressions adding ``value_num`` and ``value_unit`` parsed from a raw metadata string.

    "101.477 kPa" -> 101.477, "kPa";  "6" -> 6.0, null;  "0:25:06" -> 1506.0, "s";
    anything else (identifiers, time-zone names, ...) -> null, null.
    """
    groups = pl.col(col).str.extract_groups(NUMBER_WITH_UNIT)
    hms = pl.col(col).str.extract_groups(HMS)
    hms_seconds = (
        hms.struct.field("1").cast(pl.Float64, strict=False) * 3600
        + hms.struct.field("2").cast(pl.Float64, strict=False) * 60
        + hms.struct.field("3").cast(pl.Float64, strict=False)
    )
    num = groups.struct.field("1").cast(pl.Float64, strict=False)
    return [
        pl.coalesce(num, hms_seconds).alias("value_num"),
        pl.when(num.is_not_null())
        .then(groups.struct.field("2"))
        .when(hms_seconds.is_not_null())
        .then(pl.lit("s"))
        .otherwise(None)
        .alias("value_unit"),
    ]
