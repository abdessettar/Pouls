from __future__ import annotations

from apple_health.quality.contract import header_checks, inventory_checks, read_header


def _by_name(results):
    return {r.name: r for r in results}


def test_read_header_fixture(fixture_export):
    h = read_header(fixture_export / "export.xml")
    assert h == {"root": "HealthData", "export_version": 17, "locale": "en_US"}


def test_read_header_without_doctype(tmp_path):
    p = tmp_path / "export.xml"
    p.write_text('<?xml version="1.0"?>\n<Other a="1"/>')
    assert read_header(p)["root"] == "Other"
    assert read_header(p)["export_version"] is None


def test_header_checks(base_config):
    ok = header_checks({"root": "HealthData", "export_version": 17, "locale": "x"}, base_config)
    assert all(r.passed for r in ok)
    bad = _by_name(header_checks({"root": "HealthData", "export_version": 18, "locale": "x"}, base_config))
    assert not bad["export_version"].passed and bad["export_version"].severity == "error"


def _inventory(**overrides):
    inv = {
        "top_level": {"ExportDate": 1, "Me": 1, "Record": 10},
        "children": {"Record>MetadataEntry": 3},
        "attributes": {"Record": {"type": 10, "unit": 10, "value": 10}},
        "record_types": {"HKQuantityTypeIdentifierHeartRate": {"count/min": 10}},
        "gpx": {
            "versions": {"1.1": 2},
            "tracks_segments": {"1/1": 2},
            "extensions": {"speed": 5},
            "parse_errors": [],
        },
        "routes": {"missing_files": [], "unreferenced_files": [], "shared_files": []},
    }
    inv.update(overrides)
    return inv


def test_inventory_clean(base_config):
    assert all(r.passed for r in inventory_checks(_inventory(), base_config))


def test_inventory_detects_format_changes(base_config):
    inv = _inventory(
        top_level={"ExportDate": 1, "Record": 3, "Correlation": 1, "BrandNew": 2},
        children={"Record>Surprise": 1},
        attributes={"Record": {"type": 3, "colour": 1}},
        record_types={
            "HKQuantityTypeIdentifierHeartRate": {"count/s": 1},  # convertible
            "HKQuantityTypeIdentifierBodyMass": {"stone": 1},  # not convertible
            "HKQuantityTypeIdentifierBrandNew": {"count": 1},
        },
    )
    r = _by_name(inventory_checks(inv, base_config))
    assert (
        not r["unknown_top_level_elements"].passed and "BrandNew" in r["unknown_top_level_elements"].observed
    )
    assert not r["unhandled_declared_elements"].passed
    assert not r["unknown_child_elements"].passed
    assert "Record@colour" in r["unknown_attributes"].observed
    assert not r["unknown_record_types"].passed
    assert r["record_units_convertible"].failed_error and "stone" in r["record_units_convertible"].observed
    assert "count/s->count/min" in r["record_units_converted"].observed
    errors = {x.name for x in r.values() if x.failed_error}
    assert errors == {"record_units_convertible"}
