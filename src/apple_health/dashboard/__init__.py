"""Page data builders for the Pouls dashboard (``dashboard/``).

Each page module exposes ``build(wh: Warehouse) -> dict`` returning JSON-ready data; the Observable
Framework loaders in ``dashboard/src/data/`` are one-line wrappers around them. Builders only filter and
shape warehouse tables; reusable analysis belongs in the marts.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

ENV_WAREHOUSE = "APPLE_HEALTH_WAREHOUSE"


@dataclass(frozen=True)
class Warehouse:
    root: Path

    @classmethod
    def locate(cls) -> Warehouse:
        """``$APPLE_HEALTH_WAREHOUSE`` if set, else ``paths.warehouse_dir`` from config/settings.toml."""
        env = os.environ.get(ENV_WAREHOUSE)
        if env:
            return cls(Path(env).resolve())
        from apple_health.config import load_config

        return cls(load_config().settings.warehouse_dir)

    def scan(self, layer: str, table: str) -> pl.LazyFrame:
        from apple_health import io

        return io.scan(self.root / layer, table)

    def read(self, layer: str, table: str) -> pl.DataFrame:
        return self.scan(layer, table).collect()

    def build_manifest(self) -> dict[str, Any]:
        return json.loads((self.root / "curated" / "_build.json").read_text())


def jsonable(obj: Any) -> Any:
    """Recursively convert to JSON-safe values: NaN/inf -> None, dates -> ISO, frames -> records."""
    if isinstance(obj, pl.DataFrame):
        return [jsonable(r) for r in obj.iter_rows(named=True)]
    if isinstance(obj, pl.Series):
        return [jsonable(v) for v in obj.to_list()]
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else round(obj, 6)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def dumps(obj: Any) -> str:
    return json.dumps(jsonable(obj), allow_nan=False, ensure_ascii=False, separators=(",", ":"))


def emit(obj: Any) -> None:
    """Write a loader's JSON output to stdout."""
    sys.stdout.write(dumps(obj))


def emit_parquet(df: pl.DataFrame) -> None:
    """Write a loader's Parquet output to stdout (via memory: stdout is not seekable)."""
    import io

    buf = io.BytesIO()
    df.write_parquet(buf, compression="zstd", statistics=False)
    sys.stdout.buffer.write(buf.getvalue())
