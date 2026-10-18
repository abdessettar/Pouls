from __future__ import annotations

import json

import polars as pl
import pytest

from apple_health.parse.healthdata import parse_export_xml
from apple_health.quality.reconcile import count_tags, parquet_rows, staging_checks


@pytest.fixture(scope="module")
def parsed(tmp_path_factory, fixture_export):
    out = tmp_path_factory.mktemp("stg")
    inv = parse_export_xml(fixture_export / "export.xml", out, chunk_rows=4, export_version=17)
    return out, inv


def _t(out, name):
    return pl.read_parquet(out / f"{name}.parquet")


def test_row_counts(parsed):
    _, inv = parsed
    rows = inv["rows"]
    assert rows["stg_record"] == 33
    assert rows["stg_workout"] == 6
    assert rows["stg_hrv_beat"] == 6
    assert rows["stg_activity_summary"] == 2
    assert rows["stg_workout_route"] == 3
    assert rows["stg_workout_record_ref"] == 1
    assert rows["stg_audiogram_point"] == 2
    assert rows["stg_me"] == 5
    assert rows["stg_other_element"] == 1


def test_values_are_lossless_strings(parsed):
    out, _ = parsed
    rec = _t(out, "stg_record")
    first = rec.row(0, named=True)
    assert first["startDate"] == "2019-06-04 10:00:00 +0200"
    assert first["device"].startswith("<<HKDevice: 0x600002222220>")
    assert rec.filter(pl.col("type") == "HKQuantityTypeIdentifierOxygenSaturation")["value"].item() == "0.97"
    assert rec["record_nr"].to_list() == list(range(33))


def test_unknown_attributes_and_elements_are_kept(parsed):
    out, inv = parsed
    rec = _t(out, "stg_record")
    assert json.loads(rec.filter(pl.col("extra_attrs").is_not_null())["extra_attrs"].item()) == {"foo": "bar"}
    other = _t(out, "stg_other_element")
    assert other["tag"].to_list() == ["Correlation"]
    assert "BloodPressureSystolic" in other["xml"].item()
    assert inv["attributes"]["Record"]["foo"] == 1
    assert inv["top_level"]["Correlation"] == 1


def test_workout_children(parsed):
    out, _ = parsed
    events = _t(out, "stg_workout_event")
    running = events.filter(pl.col("workout_nr") == 5)
    assert running["activity_ordinal"].to_list() == [0]
    stats = _t(out, "stg_workout_statistic").filter(pl.col("workout_nr") == 5)
    assert stats["activity_ordinal"].to_list() == [0, 1, None, None]
    meta = _t(out, "stg_workout_metadata")
    assert set(meta["owner_kind"]) == {"workout", "activity", "route"}
    acts = meta.filter(pl.col("owner_kind") == "activity")
    assert acts.select("owner_ordinal", "key").rows()[:2] == [
        (0, "WOIntervalStepKeyPath"),
        (0, "WOIntervalStepSuccessful"),
    ]
    routes = _t(out, "stg_workout_route")
    assert routes.filter(pl.col("workout_nr") == 5)["file_path"].n_unique() == 1
    zones = _t(out, "stg_workout_zone")
    assert zones.select("group_type", "minimum", "maximum").rows() == [
        ("HKQuantityTypeIdentifierHeartRate", None, "120"),
        ("HKQuantityTypeIdentifierHeartRate", "120", None),
    ]


def test_hrv_beats(parsed):
    out, _ = parsed
    beats = _t(out, "stg_hrv_beat")
    assert beats["time"].to_list()[:4] == ["23:59:31,50", "23:59:59,90", "00:00:01,20", "00:00:29,00"]


def test_reconciliation_passes_on_fixture(parsed, fixture_export):
    out, inv = parsed
    assert parquet_rows(out) == {k: v for k, v in inv["rows"].items()}
    counts = count_tags(fixture_export / "export.xml")
    assert counts["Record"] == 33 + 1 + 1  # top level + nested in workout + nested in correlation
    assert all(r.passed for r in staging_checks(inv, counts))


def test_reconciliation_detects_lost_rows(parsed):
    _, inv = parsed
    broken = {**inv, "rows": {**inv["rows"], "stg_record": 32}}
    failed = [r.name for r in staging_checks(broken, None) if not r.passed]
    assert failed == ["rows_stg_record"]


def test_count_tags_across_chunk_boundaries(tmp_path):
    p = tmp_path / "x.xml"
    p.write_bytes(b"<a><Record x='1'/><Record y='2'/><Workout z='3'/><Recordx/></a>")
    for size in (1, 3, 7, 64):
        assert count_tags(p, ("Record", "Workout"), chunk_size=size) == {"Record": 2, "Workout": 1}
