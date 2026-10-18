"""Timestamps and time zones.

Facts this module is built on (see docs/source_notes.md):
* export.xml renders every instant with the device's UTC offset *at export time* (e.g. +0200 even
  for January). The instant is right; the wall-clock time is not.
* The real zone is only known where HealthKit stored ``HKTimeZone`` metadata (workouts, sleep).
  A timeline of zones is inferred from that evidence; everything else falls back to a default.
* HRV beat times are "HH:MM:SS,cc" without a date, rendered in the *export device's* zone (with
  its DST rules) — not in the zone of the measurement (verified on trips to UTC+1-only zones:
  beats are off by exactly one hour during European summer time only).
"""

from __future__ import annotations

import zoneinfo
from datetime import timedelta
from functools import cache

import polars as pl

HK_TS_FORMAT = "%Y-%m-%d %H:%M:%S %z"

EXPLICIT = "explicit"
INFERRED = "inferred"
DEFAULT = "default"

PERIOD_SCHEMA = {
    "period_nr": pl.Int32,
    "tz_name": pl.String,
    "valid_from_utc": pl.Datetime("us", "UTC"),
    "valid_to_utc": pl.Datetime("us", "UTC"),
    "first_evidence_utc": pl.Datetime("us", "UTC"),
    "last_evidence_utc": pl.Datetime("us", "UTC"),
    "n_evidence": pl.Int64,
}


@cache
def known_zones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


def parse_hk_ts(col: str | pl.Expr) -> pl.Expr:
    """'2023-01-14 20:41:55 +0200' -> Datetime(us, UTC); unparsable -> null."""
    e = pl.col(col) if isinstance(col, str) else col
    return e.str.to_datetime(HK_TS_FORMAT, time_unit="us", strict=False).dt.convert_time_zone("UTC")


def valid_zone(col: str | pl.Expr) -> pl.Expr:
    """The zone name if it is a known IANA zone, else null."""
    e = pl.col(col) if isinstance(col, str) else col
    return pl.when(e.is_in(list(known_zones()))).then(e).otherwise(None)


def build_timezone_periods(evidence: pl.DataFrame) -> pl.DataFrame:
    """Turn (instant_utc, tz_name) evidence into contiguous zone periods.

    Consecutive evidence with the same zone forms one period. Between two periods with different
    zones the switch is placed at the midpoint of the gap. The first period starts at its first
    evidence and the last one ends at its last evidence; outside, the default zone applies.
    """
    ev = (
        evidence.select("instant_utc", "tz_name")
        .drop_nulls()
        .with_columns(valid_zone("tz_name").alias("tz_name"))
        .drop_nulls()
        .sort("instant_utc")
    )
    if ev.height == 0:
        return pl.DataFrame(schema=PERIOD_SCHEMA)
    runs = (
        ev.with_columns(
            (pl.col("tz_name") != pl.col("tz_name").shift()).fill_null(True).cum_sum().alias("run")
        )
        .group_by("run", maintain_order=True)
        .agg(
            pl.col("tz_name").first(),
            pl.col("instant_utc").min().alias("first_evidence_utc"),
            pl.col("instant_utc").max().alias("last_evidence_utc"),
            pl.len().cast(pl.Int64).alias("n_evidence"),
        )
        .sort("first_evidence_utc")
    )
    prev_last = pl.col("last_evidence_utc").shift(1)
    next_first = pl.col("first_evidence_utc").shift(-1)
    return runs.select(
        (pl.int_range(pl.len()) + 1).cast(pl.Int32).alias("period_nr"),
        "tz_name",
        pl.when(prev_last.is_null())
        .then(pl.col("first_evidence_utc"))
        .otherwise(prev_last + (pl.col("first_evidence_utc") - prev_last) / 2)
        .alias("valid_from_utc"),
        pl.when(next_first.is_null())
        .then(pl.col("last_evidence_utc"))
        .otherwise(pl.col("last_evidence_utc") + (next_first - pl.col("last_evidence_utc")) / 2)
        .alias("valid_to_utc"),
        "first_evidence_utc",
        "last_evidence_utc",
        "n_evidence",
    ).cast(PERIOD_SCHEMA)  # type: ignore[arg-type]


def resolve_timezone(
    df: pl.DataFrame,
    instant_col: str,
    explicit_col: str | None,
    periods: pl.DataFrame,
    default_tz: str,
) -> pl.DataFrame:
    """Add ``tz_name`` and ``tz_source`` (explicit | inferred | default) to ``df``. Row order is kept.

    Resolution runs on a narrow (row, instant, explicit zone) frame, so wide inputs are not copied.
    """
    idx = "__row"
    explicit = valid_zone(explicit_col) if explicit_col else pl.lit(None, dtype=pl.String)
    narrow = df.select(
        pl.int_range(pl.len(), dtype=pl.UInt32).alias(idx),
        pl.col(instant_col).alias("__instant"),
        explicit.alias("__explicit"),
    ).sort("__instant", nulls_last=True)
    right = periods.select(
        pl.col("valid_from_utc").alias("__from"),
        pl.col("valid_to_utc").alias("__to"),
        pl.col("tz_name").alias("__tz_inferred"),
    ).sort("__from")
    joined = narrow.join_asof(right, left_on="__instant", right_on="__from", strategy="backward")
    inferred = pl.when(pl.col("__instant") <= pl.col("__to")).then(pl.col("__tz_inferred")).otherwise(None)
    resolved = (
        joined.select(
            idx,
            pl.coalesce(pl.col("__explicit"), inferred, pl.lit(default_tz)).alias("tz_name"),
            pl.when(pl.col("__explicit").is_not_null())
            .then(pl.lit(EXPLICIT))
            .when(inferred.is_not_null())
            .then(pl.lit(INFERRED))
            .otherwise(pl.lit(DEFAULT))
            .alias("tz_source"),
        )
        .sort(idx)
        .drop(idx)
    )
    return df.hstack(resolved)


def to_local(utc_col: str, tz_col: str, zones: list[str]) -> pl.Expr:
    """Naive local wall-clock datetime of a UTC column, per-row zone from ``tz_col``."""
    if not zones:
        return pl.lit(None, dtype=pl.Datetime("us"))
    expr = None
    for z in sorted(zones):
        local = pl.col(utc_col).dt.convert_time_zone(z).dt.replace_time_zone(None)
        expr = (pl.when(pl.col(tz_col) == z) if expr is None else expr.when(pl.col(tz_col) == z)).then(local)
    return expr.otherwise(None)  # type: ignore[union-attr]


def from_local(local_col: str, tz_col: str, zones: list[str], ambiguous: str) -> pl.Expr:
    """UTC instant of a naive local datetime in the row's zone (``ambiguous``: earliest | latest)."""
    if not zones:
        return pl.lit(None, dtype=pl.Datetime("us", "UTC"))
    expr = None
    for z in sorted(zones):
        utc = (
            pl.col(local_col)
            .dt.replace_time_zone(z, ambiguous=ambiguous, non_existent="null")
            .dt.convert_time_zone("UTC")
        )
        expr = (pl.when(pl.col(tz_col) == z) if expr is None else expr.when(pl.col(tz_col) == z)).then(utc)
    return expr.otherwise(None)  # type: ignore[union-attr]


def hrv_beat_times(
    beats: pl.DataFrame, zones: list[str], start_utc: str = "start_utc", tz_col: str = "tz_name"
) -> pl.DataFrame:
    """Resolve 'HH:MM:SS,cc' beat times to instants.

    The time of day is wall-clock in the zone given by ``tz_col`` (the export zone). It is combined
    with the local date of the parent's start in that zone and shifted by one day when that is
    closer to the parent's start (midnight rollover). DST ambiguity is resolved the same way: the
    candidate nearest the start.
    """
    half_day = timedelta(hours=12)
    df = beats.with_columns(
        pl.col("time")
        .str.replace(",", ".", literal=True)
        .str.to_time("%H:%M:%S%.f", strict=False)
        .alias("__t"),
        to_local(start_utc, tz_col, zones).alias("__start_local"),
    ).with_columns(pl.col("__start_local").dt.date().dt.combine(pl.col("__t")).alias("__local"))
    df = df.with_columns(
        pl.when(pl.col("__local") < pl.col("__start_local") - half_day)
        .then(pl.col("__local") + timedelta(days=1))
        .when(pl.col("__local") > pl.col("__start_local") + half_day)
        .then(pl.col("__local") - timedelta(days=1))
        .otherwise(pl.col("__local"))
        .alias("beat_local")
    )
    df = df.with_columns(
        from_local("beat_local", tz_col, zones, "earliest").alias("__early"),
        from_local("beat_local", tz_col, zones, "latest").alias("__late"),
    )
    dist_early = (pl.col("__early") - pl.col(start_utc)).abs()
    dist_late = (pl.col("__late") - pl.col(start_utc)).abs()
    return df.with_columns(
        pl.when(pl.col("__late").is_not_null() & (dist_late < dist_early))
        .then(pl.col("__late"))
        .otherwise(pl.col("__early"))
        .alias("beat_utc")
    ).drop("__t", "__start_local", "__local", "__early", "__late")
