from __future__ import annotations

import polars as pl
import pytest

from apple_health.io import TableWriter, conform, read, scan, write_table
from apple_health.schemas import Column, Table

T = Table("t", "test", "", (Column("id", pl.Int64), Column("name", pl.String)), sort_by=("id",))
P = Table("p", "test", "", (Column("k", pl.String), Column("v", pl.Int64)), partition_by="k")


def test_table_writer_flushes_parts_and_combines(tmp_path):
    w = TableWriter(T, tmp_path, chunk_rows=3)
    for i in range(8):
        w.add(i, f"n{i}")
    assert w.close() == 8
    df = pl.read_parquet(tmp_path / "t.parquet")
    assert df["id"].to_list() == list(range(8))  # order preserved across parts
    assert df.schema == T.schema()
    assert not (tmp_path / ".parts").exists()


def test_table_writer_empty(tmp_path):
    w = TableWriter(T, tmp_path, chunk_rows=3)
    assert w.close() == 0
    assert pl.read_parquet(tmp_path / "t.parquet").schema == T.schema()


def test_table_writer_rejects_wrong_arity(tmp_path):
    w = TableWriter(T, tmp_path, chunk_rows=3)
    with pytest.raises(ValueError):
        w.add(1)


def test_conform_orders_casts_and_sorts():
    df = pl.DataFrame({"name": ["b", "a"], "id": [2, 1], "extra": [0, 0]}).with_columns(
        pl.col("id").cast(pl.Int32)
    )
    out = conform(df, T)
    assert out.columns == ["id", "name"] and out.schema == T.schema()
    assert out["id"].to_list() == [1, 2]
    with pytest.raises(ValueError, match="missing columns"):
        conform(df.drop("name"), T)


def test_partitioned_roundtrip(tmp_path):
    write_table(pl.DataFrame({"k": ["a", "a", "b"], "v": [1, 2, 3]}), tmp_path, P)
    assert (tmp_path / "p" / "k=a").is_dir()
    df = read(tmp_path, "p").sort("v")
    assert df["k"].to_list() == ["a", "a", "b"]
    write_table(pl.DataFrame({"k": [], "v": []}, schema=P.schema()), tmp_path, P)
    assert scan(tmp_path, "p").collect().height == 0
