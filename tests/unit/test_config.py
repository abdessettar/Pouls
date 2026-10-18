from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from apple_health.config import ConfigError, infer_kind, load_config

ROOT = Path(__file__).resolve().parents[2]


def test_loads_project_config(base_config):
    s = base_config.settings
    assert s.default_timezone == "Europe/Berlin"
    assert s.expected_export_version == 17
    assert s.raw_dir == (ROOT / "data").resolve()
    hr = base_config.types["HKQuantityTypeIdentifierHeartRate"]
    assert (hr.kind, hr.unit, hr.aggregation) == ("quantity", "count/min", "discrete")
    sleep = base_config.types["HKCategoryTypeIdentifierSleepAnalysis"]
    assert sleep.values["HKCategoryValueSleepAnalysisAsleepCore"].label == "Core"
    assert base_config.types["HKDataTypeSleepDurationGoal"].kind == "quantity"


def test_promoted_keys(base_config):
    sample_cols = {m.promote for m in base_config.promoted_keys("sample")}
    workout_cols = {m.promote for m in base_config.promoted_keys("workout")}
    assert {"hk_time_zone", "hr_motion_context"} <= sample_cols
    assert {"hk_time_zone", "is_indoor", "weather_humidity_pct"} <= workout_cols
    assert "is_indoor" not in sample_cols


def test_with_paths_overrides(base_config, tmp_path):
    cfg = base_config.with_paths(raw_dir=tmp_path / "raw", warehouse_dir=tmp_path / "wh")
    assert cfg.settings.xml_path == tmp_path / "raw" / "export.xml"
    assert cfg.settings.warehouse_dir == tmp_path / "wh"


def test_infer_kind():
    assert infer_kind("HKCategoryTypeIdentifierSleepAnalysis") == "category"
    assert infer_kind("HKQuantityTypeIdentifierStepCount") == "quantity"
    assert infer_kind("HKDataTypeSleepDurationGoal") == "quantity"


@pytest.mark.parametrize(
    ("file", "old", "new", "match"),
    [
        (
            "settings.toml",
            'default_timezone = "Europe/Berlin"',
            'default_timezone = "Mars/Olympus"',
            "unknown time zone",
        ),
        ("types.toml", 'aggregation = "discrete"', 'aggregation = "weird"', "aggregation"),
        ("metadata_keys.toml", 'type = "bool"', 'type = "complex"', "type must be"),
    ],
)
def test_invalid_config_is_rejected(tmp_path, file, old, new, match):
    cfg_dir = tmp_path / "config"
    shutil.copytree(ROOT / "config", cfg_dir)
    p = cfg_dir / file
    p.write_text(p.read_text().replace(old, new, 1))
    with pytest.raises(ConfigError, match=match):
        load_config(cfg_dir)
