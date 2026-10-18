from __future__ import annotations

from pathlib import Path

from apple_health.docs import data_dictionary, write_data_dictionary
from apple_health.schemas import STAGING_TABLES, warehouse_tables

ROOT = Path(__file__).resolve().parents[2]


def test_dictionary_lists_every_table_and_column(base_config):
    text = data_dictionary(base_config)
    for t in warehouse_tables(base_config).values():
        assert f"### `{t.name}`" in text
        for c in t.columns:
            assert f"| `{c.name}` |" in text
    for name in STAGING_TABLES:
        assert f"| `{name}` |" in text
    assert "timestamp (UTC)" in text and "list[string]" in text


def test_committed_dictionary_is_current(base_config):
    committed = (ROOT / "docs" / "data_dictionary.md").read_text()
    assert committed == data_dictionary(base_config), "run `uv run apple-health dictionary`"


def test_write_dictionary(base_config, tmp_path):
    p = write_data_dictionary(base_config, tmp_path / "d" / "dict.md")
    assert p.read_text().startswith("# Data dictionary")
