"""Shared state of one build run."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from apple_health import io
from apple_health.config import Config
from apple_health.schemas import Table

log = logging.getLogger(__name__)


@dataclass
class BuildContext:
    cfg: Config
    staging: Path
    curated: Path
    derived: Path
    marts: Path | None = None
    export_id: str = ""
    stats: dict[str, Any] = field(default_factory=dict)
    rows: dict[str, int] = field(default_factory=dict)
    # small lookups shared between steps
    dim_source: pl.DataFrame | None = None
    device_map: pl.DataFrame | None = None
    tz_periods: pl.DataFrame | None = None
    dim_data_type: pl.DataFrame | None = None
    unit_conversions: pl.DataFrame | None = None

    def stg(self, name: str) -> pl.DataFrame:
        return pl.read_parquet(self.staging / f"{name}.parquet")

    def layer_dir(self, layer: str) -> Path:
        dirs = {"curated": self.curated, "derived": self.derived, "marts": self.marts}
        d = dirs.get(layer)
        if d is None:
            raise ValueError(f"no output directory for layer {layer!r}")
        return d

    def write(self, table: Table, df: pl.DataFrame | pl.LazyFrame) -> int:
        n = io.write_table(df, self.layer_dir(table.layer), table)
        self.rows[table.name] = n
        log.info("  %-28s %10d rows", table.name, n)
        return n

    def scan(self, table: Table | str) -> pl.LazyFrame:
        """Scan a table written by this build (curated, derived or marts)."""
        name = table if isinstance(table, str) else table.name
        for d in (self.curated, self.derived, self.marts):
            if d is not None and ((d / name).exists() or (d / f"{name}.parquet").exists()):
                return io.scan(d, name)
        raise FileNotFoundError(f"table {name!r} not found in this build")
