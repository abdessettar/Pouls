from __future__ import annotations

from pathlib import Path

import pytest

from apple_health.config import Config, load_config

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_EXPORT = ROOT / "tests" / "fixtures" / "mini_export"
REAL_EXPORT = ROOT / "data"


@pytest.fixture(scope="session")
def base_config() -> Config:
    from dataclasses import replace

    cfg = load_config(ROOT / "config")
    # Tests name map areas from time zones, whether or not the GeoNames file is on this machine.
    s = cfg.settings
    return replace(cfg, settings=replace(s, analytics=replace(s.analytics, place_names_file=None)))


@pytest.fixture
def fixture_config(base_config: Config, tmp_path: Path) -> Config:
    """Config pointing at the synthetic mini export and a throw-away warehouse."""
    return base_config.with_paths(raw_dir=FIXTURE_EXPORT, warehouse_dir=tmp_path / "warehouse")


@pytest.fixture(scope="session")
def fixture_export() -> Path:
    return FIXTURE_EXPORT


@pytest.fixture(scope="session")
def built_warehouse(base_config: Config, tmp_path_factory) -> Path:
    """Parse + build the synthetic export once per test session; returns the warehouse dir."""
    from apple_health.build import run_build
    from apple_health.pipeline import run_parse

    wh = tmp_path_factory.mktemp("warehouse")
    cfg = base_config.with_paths(raw_dir=FIXTURE_EXPORT, warehouse_dir=wh)
    assert run_parse(cfg) == 0
    assert run_build(cfg) == 0
    return wh


@pytest.fixture(scope="session")
def real_export() -> Path:
    if not (REAL_EXPORT / "export.xml").is_file():
        pytest.skip("no real export in data/")
    return REAL_EXPORT
