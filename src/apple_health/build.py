"""Build step: staging -> curated + derived, checked, then published. Also: standalone checks."""

from __future__ import annotations

import logging
import time

from apple_health.config import Config
from apple_health.manifest import (
    CURATED,
    DERIVED,
    MARTS,
    META,
    STAGING,
    Workspace,
    code_version,
    new_run_id,
    read_json,
    write_json,
)
from apple_health.marts.baselines import build_activity_profile, build_baselines
from apple_health.marts.daily import build_daily, build_rollups, build_wear_hourly
from apple_health.marts.records import build_records
from apple_health.marts.references import build_references
from apple_health.marts.routes import build_routes
from apple_health.marts.running import build_runs
from apple_health.marts.sleep import build_sleep_nights
from apple_health.marts.training import build_workout_hr, build_workout_marts
from apple_health.quality.checks import CheckResult, has_errors, log_results, to_frame
from apple_health.quality.curated_checks import all_checks
from apple_health.quality.profile import export_profile, write_profile_and_snapshot
from apple_health.schemas import warehouse_tables
from apple_health.transform.context import BuildContext
from apple_health.transform.derived import build_coverage, build_quantity_aggregates, build_sleep_sessions
from apple_health.transform.keys import iso_utc
from apple_health.transform.samples import build_samples, build_sources_and_devices
from apple_health.transform.summaries import (
    build_activity_summaries,
    build_audiograms,
    build_dim_date,
    build_dim_profile,
    build_hrv_beats,
)
from apple_health.transform.time import parse_hk_ts
from apple_health.transform.workouts import build_workouts

log = logging.getLogger(__name__)

STEPS = (
    build_sources_and_devices,
    build_samples,
    build_workouts,
    build_hrv_beats,
    build_activity_summaries,
    build_dim_profile,
    build_audiograms,
    build_dim_date,
    build_quantity_aggregates,
    build_sleep_sessions,
    build_coverage,
    build_wear_hourly,
    build_daily,
    build_rollups,
    build_baselines,
    build_activity_profile,
    build_workout_marts,
    build_workout_hr,
    build_sleep_nights,
    build_runs,
    build_routes,
    build_records,
    build_references,
)


def _export_id(ctx: BuildContext) -> str:
    exp = ctx.stg("stg_export").select(iso_utc(parse_hk_ts("export_date")).alias("id"))
    value = exp["id"][0] if exp.height else None
    if not value:
        raise ValueError("stg_export has no parsable export date")
    return value


def _write_dq(cfg: Config, run_id: str, step: str, results: list[CheckResult]) -> None:
    path = cfg.settings.warehouse_dir / META / "dq" / f"{run_id}-{step}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    to_frame(results, run_id).write_parquet(path)


def run_build(cfg: Config) -> int:
    s = cfg.settings
    stg = s.warehouse_dir / STAGING
    if not (stg / "_manifest.json").is_file():
        log.error("no published staging layer in %s: run `apple-health parse` first", stg)
        return 2
    run_id = new_run_id()
    t0 = time.monotonic()
    ws = Workspace(s.warehouse_dir, run_id)
    try:
        ctx = BuildContext(cfg, stg, ws.layer(CURATED), ws.layer(DERIVED), ws.layer(MARTS))
        ctx.export_id = _export_id(ctx)
        log.info("building curated layer for export %s", ctx.export_id)
        for step in STEPS:
            step(ctx)

        log.info("running data-quality checks")
        results = all_checks(ctx, warehouse_tables(cfg))
        manifest = {
            "run_id": run_id,
            "step": "build",
            "code_version": code_version(),
            "export_id": ctx.export_id,
            "staging_run_id": read_json(stg / "_manifest.json")["run_id"],
            "rows": ctx.rows,
            "stats": ctx.stats,
            "duration_s": round(time.monotonic() - t0, 1),
        }
        write_json(ctx.curated / "_build.json", manifest)
        to_frame(results, run_id).write_parquet(ctx.curated / "_dq.parquet")
        _write_dq(cfg, run_id, "build", results)
        log_results(results)
        if has_errors(results):
            log.error("data-quality errors: curated/derived NOT published")
            return 1
        write_profile_and_snapshot(ctx, export_profile(ctx))
        for layer in (CURATED, DERIVED, MARTS):
            ws.publish(layer)
        write_json(s.warehouse_dir / META / "runs" / f"{run_id}-build.json", manifest)
        log.info("build finished in %.1fs", time.monotonic() - t0)
        return 0
    finally:
        ws.cleanup()


def run_check(cfg: Config) -> int:
    """Re-run all data-quality checks against the published warehouse."""
    s = cfg.settings
    cur = s.warehouse_dir / CURATED
    if not (cur / "_build.json").is_file():
        log.error("no published curated layer in %s: run `apple-health build` first", cur)
        return 2
    manifest = read_json(cur / "_build.json")
    ctx = BuildContext(
        cfg, s.warehouse_dir / STAGING, cur, s.warehouse_dir / DERIVED, s.warehouse_dir / MARTS
    )
    ctx.export_id, ctx.stats, ctx.rows = manifest["export_id"], manifest["stats"], manifest["rows"]
    run_id = new_run_id()
    results = all_checks(ctx, warehouse_tables(cfg))
    _write_dq(cfg, run_id, "check", results)
    log_results(results)
    return 1 if has_errors(results) else 0
