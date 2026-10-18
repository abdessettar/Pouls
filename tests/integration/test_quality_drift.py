from __future__ import annotations

import shutil

import polars as pl

from apple_health.build import run_build, run_check
from apple_health.manifest import read_json
from apple_health.pipeline import run_parse
from apple_health.quality.profile import diff_profiles, has_changes, list_profiles, run_diff


def _build(cfg):
    assert run_parse(cfg) == 0
    assert run_build(cfg) == 0


def test_profile_against_itself_is_empty(fixture_config):
    _build(fixture_config)
    (profile,) = list_profiles(fixture_config.settings.warehouse_dir)
    p = read_json(profile)
    d = diff_profiles(p, p)
    assert not has_changes(d)
    assert d["row_changes"] == {}
    assert p["types"]["HeartRate"]["count"] == 6
    assert "HKTimeZone" in p["record_metadata_keys"]


def test_rebuilding_same_export_keeps_one_profile(fixture_config):
    _build(fixture_config)
    _build(fixture_config)
    assert len(list_profiles(fixture_config.settings.warehouse_dir)) == 1
    assert run_diff(fixture_config.settings.warehouse_dir) == 0


def test_drift_between_exports(fixture_config, fixture_export, tmp_path, capsys):
    _build(fixture_config)
    raw = tmp_path / "raw2"
    shutil.copytree(fixture_export, raw)
    xml = raw / "export.xml"
    s = xml.read_text()
    s = s.replace(
        '<ExportDate value="2025-05-05 18:29:01 +0200"/>', '<ExportDate value="2025-11-05 18:29:01 +0100"/>'
    )
    # one sample vanishes from history, one new type and one new attribute appear
    s = s.replace('value="70.5" foo="bar"/>', 'value="70.5" foo="bar" colour="red"/>')
    s = s.replace(
        ' <Record type="HKQuantityTypeIdentifierOxygenSaturation"',
        ' <Record type="HKQuantityTypeIdentifierBrandNewThing" sourceName="iPhone" unit="count" '
        'creationDate="2023-02-01 08:00:00 +0200" startDate="2023-02-01 08:00:00 +0200" '
        'endDate="2023-02-01 08:00:00 +0200" value="3"/>\n'
        ' <Record type="HKQuantityTypeIdentifierOxygenSaturation"',
        1,
    )
    start = s.index(' <Record type="HKQuantityTypeIdentifierHeadphoneAudioExposure"')
    end = s.index("\n", start) + 1
    s = s[:start] + s[end:]
    xml.write_text(s)
    _build(fixture_config.with_paths(raw_dir=raw))

    assert len(list_profiles(fixture_config.settings.warehouse_dir)) == 2
    assert run_diff(fixture_config.settings.warehouse_dir) == 0
    report = capsys.readouterr().out
    assert "types added: BrandNewThing" in report
    assert "HeadphoneAudioExposure" in report and "samples missing from history" in report
    assert "colour" in report
    (diff_file,) = (fixture_config.settings.warehouse_dir / "_meta" / "diffs").glob("*.json")
    d = read_json(diff_file)
    assert d["history"]["vanished_samples_by_type"] == {"HeadphoneAudioExposure": 1}
    assert d["types"]["added"] == ["BrandNewThing"]
    assert d["types"]["removed"] == ["HeadphoneAudioExposure"]  # its only sample vanished


def test_check_detects_corruption(fixture_config):
    _build(fixture_config)
    assert run_check(fixture_config) == 0
    path = fixture_config.settings.warehouse_dir / "curated" / "dim_source.parquet"
    df = pl.read_parquet(path)
    pl.concat([df, df.head(1)]).write_parquet(path)  # inject a duplicate primary key
    assert run_check(fixture_config) == 1
    dq = sorted((fixture_config.settings.warehouse_dir / "_meta" / "dq").glob("*-check.parquet"))[-1]
    failed = pl.read_parquet(dq).filter(~pl.col("passed") & (pl.col("severity") == "error"))["name"].to_list()
    assert failed == ["pk_unique_dim_source"]


def test_failed_checks_do_not_publish(fixture_config, monkeypatch):
    _build(fixture_config)
    before = read_json(fixture_config.settings.warehouse_dir / "curated" / "_build.json")["run_id"]
    monkeypatch.setattr("apple_health.build.has_errors", lambda results: True)
    assert run_build(fixture_config) == 1
    after = read_json(fixture_config.settings.warehouse_dir / "curated" / "_build.json")["run_id"]
    assert before == after  # previous good build still in place
