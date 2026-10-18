"""Builds the whole dashboard against the synthetic fixture warehouse (``pytest -m dashboard``).

The dashboard project is copied to a temporary directory (node_modules symlinked) so the fixture's
loader output never lands in the real loader cache.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboard"

pytestmark = pytest.mark.dashboard


@pytest.fixture
def dashboard_copy(tmp_path):
    if shutil.which("npm") is None or not (DASH / "node_modules").is_dir():
        pytest.skip("npm or dashboard/node_modules not available (run `npm install` in dashboard/)")
    dest = tmp_path / "dashboard"
    shutil.copytree(DASH, dest, ignore=shutil.ignore_patterns("node_modules", "dist", ".observablehq"))
    (dest / "node_modules").symlink_to(DASH / "node_modules")
    # the loaders use ../.venv/bin/python relative to the project
    (tmp_path / ".venv").symlink_to(ROOT / ".venv")
    return dest


def test_dashboard_builds_on_fixture(built_warehouse, dashboard_copy, tmp_path):
    env = {
        **os.environ,
        "APPLE_HEALTH_WAREHOUSE": str(built_warehouse),
        "APPLE_HEALTH_COACH_JOURNAL": str(tmp_path / "journal.sqlite"),  # never the real journal
        "POULS_OUTPUT": "dist",
    }
    proc = subprocess.run(
        ["npm", "run", "build"], cwd=dashboard_copy, env=env, capture_output=True, text=True, timeout=600
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert "check-dist:" in proc.stdout
    assert (dashboard_copy / "dist" / "index.html").is_file()
