from __future__ import annotations

import shutil

from apple_health.manifest import read_json
from apple_health.pipeline import run_parse


def test_run_parse_publishes_staging(fixture_config):
    assert run_parse(fixture_config) == 0
    stg = fixture_config.settings.warehouse_dir / "staging"
    assert (stg / "stg_record.parquet").is_file()
    manifest = read_json(stg / "_manifest.json")
    assert manifest["export_version"] == 17
    assert manifest["rows"]["stg_record"] == 33
    assert {f["path"] for f in manifest["raw_files"]} >= {"export.xml"}
    assert not (fixture_config.settings.warehouse_dir / ".tmp").exists()


def test_run_parse_refuses_unexpected_export_version(fixture_config, fixture_export, tmp_path):
    raw = tmp_path / "raw"
    shutil.copytree(fixture_export, raw)
    xml = raw / "export.xml"
    xml.write_text(xml.read_text().replace("Export Version: 17", "Export Version: 18"))
    cfg = fixture_config.with_paths(raw_dir=raw)
    assert run_parse(cfg) == 1
    assert not (cfg.settings.warehouse_dir / "staging").exists()
    assert list((cfg.settings.warehouse_dir / "_meta" / "dq").glob("*-parse.parquet"))


def test_run_parse_missing_export(fixture_config, tmp_path):
    assert run_parse(fixture_config.with_paths(raw_dir=tmp_path / "nope")) == 2


def test_run_parse_includes_routes(fixture_config):
    assert run_parse(fixture_config) == 0
    stg = fixture_config.settings.warehouse_dir / "staging"
    inv = read_json(stg / "_inventory.json")
    assert inv["gpx"]["files_found"] == 2 and inv["gpx"]["points"] == 11
    assert inv["routes"] == {
        "missing_files": [],
        "unreferenced_files": [],
        "shared_files": ["route_2023-07-28_7.20am.gpx"],
    }
    assert inv["rows"]["stg_gpx_point"] == 11
