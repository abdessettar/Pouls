"""Minimal data-quality check framework: every check yields a ``CheckResult``."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import polars as pl

log = logging.getLogger(__name__)

ERROR = "error"  # pipeline bug or unusable input: nothing is published
WARN = "warn"  # suspicious source data: published, reported
INFO = "info"  # facts worth knowing


@dataclass(frozen=True)
class CheckResult:
    name: str
    layer: str
    severity: str
    passed: bool
    observed: str
    expected: str = ""
    message: str = ""

    @property
    def failed_error(self) -> bool:
        return not self.passed and self.severity == ERROR


def result(
    name: str,
    layer: str,
    severity: str,
    passed: bool,
    observed: object,
    expected: object = "",
    message: str = "",
) -> CheckResult:
    return CheckResult(name, layer, severity, bool(passed), str(observed), str(expected), message)


def has_errors(results: list[CheckResult]) -> bool:
    return any(r.failed_error for r in results)


def to_frame(results: list[CheckResult], run_id: str) -> pl.DataFrame:
    schema = {
        "run_id": pl.String,
        "name": pl.String,
        "layer": pl.String,
        "severity": pl.String,
        "passed": pl.Boolean,
        "observed": pl.String,
        "expected": pl.String,
        "message": pl.String,
    }
    rows = [{"run_id": run_id, **asdict(r)} for r in results]
    return pl.DataFrame(rows, schema=schema)


def log_results(results: list[CheckResult]) -> None:
    failed = [r for r in results if not r.passed]
    for r in failed:
        level = {ERROR: logging.ERROR, WARN: logging.WARNING}.get(r.severity, logging.INFO)
        msg = f" — {r.message}" if r.message else ""
        log.log(level, "[%s] %s: observed %s, expected %s%s", r.severity, r.name, r.observed, r.expected, msg)
    counts = {s: sum(1 for r in failed if r.severity == s) for s in (ERROR, WARN, INFO)}
    log.info(
        "data quality: %d checks, %d passed, %d errors, %d warnings, %d info",
        len(results),
        len(results) - len(failed),
        counts[ERROR],
        counts[WARN],
        counts[INFO],
    )
