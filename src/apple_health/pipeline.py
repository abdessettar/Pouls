"""Pipeline steps wired together: parse (raw -> staging) and build (staging -> curated/derived)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from apple_health.config import Config
from apple_health.manifest import (
    META,
    STAGING,
    Workspace,
    code_version,
    new_run_id,
    raw_inventory,
    write_json,
)
from apple_health.parse.gpx import parse_gpx_dir, route_inventory
from apple_health.parse.healthdata import parse_export_xml
from apple_health.quality.checks import CheckResult, has_errors, log_results, to_frame
from apple_health.quality.contract import header_checks, inventory_checks, read_header
from apple_health.quality.reconcile import count_tags, parquet_rows, staging_checks

log = logging.getLogger(__name__)


def _write_dq(cfg: Config, run_id: str, step: str, results: list[CheckResult]) -> Path:
    path = cfg.settings.warehouse_dir / META / "dq" / f"{run_id}-{step}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    to_frame(results, run_id).write_parquet(path)
    return path


def run_parse(cfg: Config) -> int:
    """raw -> staging. Returns a process exit code (0 = published)."""
    s = cfg.settings
    run_id = new_run_id()
    t0 = time.monotonic()
    if not s.xml_path.is_file():
        log.error("export not found: %s", s.xml_path)
        return 2

    header = read_header(s.xml_path)
    results = header_checks(header, cfg)
    if has_errors(results):
        log_results(results)
        _write_dq(cfg, run_id, "parse", results)
        return 1

    ws = Workspace(s.warehouse_dir, run_id)
    try:
        stg = ws.layer(STAGING)
        log.info("parsing %s", s.xml_path)
        inv: dict[str, Any] = parse_export_xml(s.xml_path, stg, s.chunk_rows, header["export_version"])
        inv["header"] = header

        log.info("parsing GPX files in %s", s.routes_path)
        gpx = parse_gpx_dir(s.routes_path, stg, s.chunk_rows, s.gpx_workers)
        inv["gpx"] = gpx
        inv["routes"] = route_inventory(stg)
        inv["rows"] = parquet_rows(stg)

        log.info("independent element count (byte scan)")
        byte_counts = count_tags(s.xml_path)

        results += inventory_checks(inv, cfg)
        results += staging_checks(inv, byte_counts)

        manifest = {
            "run_id": run_id,
            "step": "parse",
            "code_version": code_version(),
            "export_date": inv["export_date"],
            "export_version": header["export_version"],
            "raw_dir": str(s.raw_dir),
            "raw_files": raw_inventory(s.raw_dir, s.hash_files),
            "rows": inv["rows"],
            "duration_s": round(time.monotonic() - t0, 1),
        }
        write_json(stg / "_inventory.json", inv)
        write_json(stg / "_manifest.json", manifest)
        to_frame(results, run_id).write_parquet(stg / "_source_checks.parquet")
        _write_dq(cfg, run_id, "parse", results)
        log_results(results)
        if has_errors(results):
            log.error("source contract / reconciliation failed: staging NOT published")
            return 1
        ws.publish(STAGING)
        write_json(s.warehouse_dir / META / "runs" / f"{run_id}-parse.json", manifest)
        log.info("parse finished in %.1fs", time.monotonic() - t0)
        return 0
    finally:
        ws.cleanup()
