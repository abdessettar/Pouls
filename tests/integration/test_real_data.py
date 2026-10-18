"""Smoke test on the real export in data/ (``uv run pytest -m real_data``; skipped without data)."""

from __future__ import annotations

import polars as pl
import pytest

from apple_health import io
from apple_health.build import run_build
from apple_health.pipeline import run_parse
from apple_health.schemas import warehouse_tables

pytestmark = pytest.mark.real_data


def test_real_export_end_to_end(base_config, real_export, tmp_path):
    cfg = base_config.with_paths(raw_dir=real_export, warehouse_dir=tmp_path / "warehouse")
    assert run_parse(cfg) == 0
    assert run_build(cfg) == 0
    wh = cfg.settings.warehouse_dir
    dq = pl.read_parquet(wh / "curated" / "_dq.parquet")
    assert dq.filter(~pl.col("passed") & (pl.col("severity") == "error")).height == 0
    for name, t in warehouse_tables(cfg).items():
        n = io.scan(wh / t.layer, name).select(pl.len()).collect().item()
        assert n > 0, name
