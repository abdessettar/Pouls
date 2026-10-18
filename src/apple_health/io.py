"""Parquet reading and writing with the project's conventions."""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import quote

import polars as pl

from apple_health.schemas import SCHEMA_VERSION, Table

ROW_GROUP_SIZE = 262_144


def table_path(layer_dir: Path, table: Table | str) -> Path:
    """``<layer>/<name>.parquet`` for plain tables, ``<layer>/<name>/`` for partitioned ones."""
    name = table if isinstance(table, str) else table.name
    d = layer_dir / name
    return d if d.is_dir() else layer_dir / f"{name}.parquet"


def conform(df: pl.DataFrame | pl.LazyFrame, table: Table) -> pl.DataFrame:
    """Select the table's columns in order and cast to the declared dtypes (fails on missing columns)."""
    frame = df.lazy() if isinstance(df, pl.DataFrame) else df
    names = frame.collect_schema().names()
    missing = [c for c in table.column_names if c not in names]
    if missing:
        raise ValueError(f"{table.name}: missing columns {missing}")
    out = frame.select([pl.col(c.name).cast(c.dtype, strict=True) for c in table.columns])
    if table.sort_by:
        out = out.sort(list(table.sort_by), nulls_last=True, maintain_order=True)
    return out.collect()


def _meta(table: Table) -> dict[str, str]:
    return {"apple_health.table": table.name, "apple_health.schema_version": SCHEMA_VERSION}


def write_table(df: pl.DataFrame | pl.LazyFrame, layer_dir: Path, table: Table) -> int:
    """Conform ``df`` to ``table`` and write it; returns the number of rows.

    Partitioned tables are written one hive partition at a time (``<name>/<col>=<value>/part-0.parquet``)
    to keep peak memory at one partition rather than a sorted copy of the whole table.
    """
    if not table.partition_by:
        out = conform(df, table)
        layer_dir.mkdir(parents=True, exist_ok=True)
        out.write_parquet(
            layer_dir / f"{table.name}.parquet",
            compression="zstd",
            statistics=True,
            row_group_size=ROW_GROUP_SIZE,
            metadata=_meta(table),
        )
        return out.height

    key = table.partition_by
    dest = layer_dir / table.name
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    frame = df.lazy() if isinstance(df, pl.DataFrame) else df
    values = frame.select(pl.col(key).unique()).collect().to_series().sort().to_list()
    file_cols = [c for c in table.columns if c.name != key]
    file_table = Table(
        table.name,
        table.layer,
        table.doc,
        tuple(file_cols),
        sort_by=tuple(c for c in table.sort_by if c != key),
    )
    total = 0
    for v in values:
        if v is None:
            raise ValueError(f"{table.name}: null partition value in {key!r}")
        part = conform(frame.filter(pl.col(key) == v), file_table)
        pdir = dest / f"{key}={quote(str(v), safe='')}"
        pdir.mkdir()
        part.write_parquet(
            pdir / "part-0.parquet",
            compression="zstd",
            statistics=True,
            row_group_size=ROW_GROUP_SIZE,
            metadata=_meta(table),
        )
        total += part.height
    if not values:
        # An empty partitioned table is a single empty file with the full schema, so it stays readable.
        conform(frame, table).write_parquet(dest / "empty.parquet", compression="zstd", metadata=_meta(table))
    return total


def scan(layer_dir: Path, table: Table | str) -> pl.LazyFrame:
    path = table_path(layer_dir, table)
    if path.is_dir():
        return pl.scan_parquet(path, hive_partitioning=True)
    return pl.scan_parquet(path)


def read(layer_dir: Path, table: Table | str) -> pl.DataFrame:
    return scan(layer_dir, table).collect()


class TableWriter:
    """Buffers rows for one table and flushes them to Parquet part files every ``chunk_rows`` rows.

    Bounds memory while streaming a large source; ``close()`` combines the parts into
    ``<out_dir>/<table>.parquet``.
    """

    def __init__(self, table: Table, out_dir: Path, chunk_rows: int) -> None:
        self.table = table
        self.out_dir = out_dir
        self.chunk_rows = chunk_rows
        self._names = table.column_names
        self._schema = table.schema()
        self._buf: list[list[object]] = [[] for _ in self._names]
        self._n = 0
        self.rows = 0
        self._parts: list[Path] = []
        self._parts_dir = out_dir / ".parts" / table.name

    def add(self, *values: object) -> None:
        for buf, v in zip(self._buf, values, strict=True):
            buf.append(v)
        self._n += 1
        if self._n >= self.chunk_rows:
            self.flush()

    def _frame(self) -> pl.DataFrame:
        return pl.DataFrame(dict(zip(self._names, self._buf, strict=True)), schema=self._schema)

    def flush(self) -> None:
        if not self._n:
            return
        self._parts_dir.mkdir(parents=True, exist_ok=True)
        part = self._parts_dir / f"part-{len(self._parts):05d}.parquet"
        self._frame().write_parquet(part, compression="lz4")
        self._parts.append(part)
        self.rows += self._n
        self._buf = [[] for _ in self._names]
        self._n = 0

    def close(self) -> int:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        dest = self.out_dir / f"{self.table.name}.parquet"
        meta = _meta(self.table)
        if not self._parts:
            self.rows += self._n
            self._frame().write_parquet(dest, compression="zstd", statistics=True, metadata=meta)
        else:
            self.flush()
            pl.scan_parquet(self._parts).sink_parquet(
                dest, compression="zstd", statistics=True, row_group_size=ROW_GROUP_SIZE, metadata=meta
            )
            shutil.rmtree(self._parts_dir)
            parts_root = self.out_dir / ".parts"
            if parts_root.is_dir() and not any(parts_root.iterdir()):
                parts_root.rmdir()
        self._buf = [[] for _ in self._names]
        self._n = 0
        return self.rows
