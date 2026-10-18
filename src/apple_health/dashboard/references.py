"""Reference bands for the dashboard (read from mart_reference; see config/references.toml)."""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse


def _table(wh: Warehouse) -> pl.DataFrame | None:
    path = wh.root / "marts" / "mart_reference.parquet"
    return pl.read_parquet(path) if path.is_file() else None


def bands(wh: Warehouse, metric: str) -> list[dict[str, Any]]:
    """Every band of a metric with its validity period (bands step at age-group boundaries)."""
    t = _table(wh)
    if t is None:
        return []
    return t.filter(pl.col("metric") == metric).sort("kind", "valid_from", "seq").to_dicts()


def sources(wh: Warehouse) -> list[dict[str, Any]]:
    path = wh.root / "marts" / "mart_reference_source.parquet"
    return pl.read_parquet(path).sort("source_id").to_dicts() if path.is_file() else []


def _position(rows: pl.DataFrame, value: float | None) -> dict[str, Any] | None:
    if value is None:
        return None
    for r in rows.iter_rows(named=True):
        if (r["lo"] is None or value >= r["lo"]) and (r["hi"] is None or value < r["hi"]):
            return r
    return None


def reference_at(wh: Warehouse, metric: str | None, day: date, value: float | None) -> dict[str, Any] | None:
    """The bands that apply on ``day`` and where ``value`` sits among them.

    A metric can have guideline bands (kind "range") and a population percentile table; the result
    describes both. ``current_*`` refers to the range bands, or to the percentile table when the
    metric has no range bands.
    """
    if metric is None:
        return None
    t = _table(wh)
    if t is None:
        return None
    rows = t.filter(
        (pl.col("metric") == metric) & (pl.col("valid_from") <= day) & (pl.col("valid_to") >= day)
    ).sort("seq")
    if rows.height == 0:
        return None
    ranges, pcts = rows.filter(pl.col("kind") == "range"), rows.filter(pl.col("kind") == "percentile")
    primary = ranges if ranges.height else pcts
    current = _position(primary, value)
    pct = _position(pcts, value)
    return {
        "metric": metric,
        "bands": primary.select("band", "label", "lo", "hi", "is_target", "is_warning").to_dicts(),
        "current_band": None if current is None else current["band"],
        "current_label": None if current is None else current["label"],
        "in_target": None if current is None else bool(current["is_target"]),
        "warning": None if current is None else bool(current["is_warning"]),
        "population": primary["population"][0],
        "source_id": primary["source_id"][0],
        "percentile": None
        if pct is None
        else {"band": pct["band"], "label": pct["label"], "population": pct["population"]},
    }
