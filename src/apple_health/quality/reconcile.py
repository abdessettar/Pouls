"""Staging reconciliation: did the parser see — and write — every element?"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apple_health.quality.checks import ERROR, CheckResult, result

LAYER = "staging"

# Elements whose total count (all depths) is verified with an independent byte scan.
SCANNED_TAGS = ("Record", "Workout", "ActivitySummary", "InstantaneousBeatsPerMinute")


def count_tags(
    path: Path, tags: tuple[str, ...] = SCANNED_TAGS, chunk_size: int = 64 * 1024 * 1024
) -> dict[str, int]:
    """Count ``<Tag `` occurrences in a file without parsing it (independent of the XML parser)."""
    patterns = {t: f"<{t} ".encode() for t in tags}
    counts = dict.fromkeys(tags, 0)
    tails = dict.fromkeys(tags, b"")
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            for t, p in patterns.items():
                buf = tails[t] + chunk
                counts[t] += buf.count(p)
                tails[t] = buf[-(len(p) - 1) :]
    return counts


def _sum(children: dict[str, int], *paths: str) -> int:
    return sum(children.get(p, 0) for p in paths)


def parquet_rows(stg_dir: Path) -> dict[str, int]:
    """Row counts read back from the written staging files (not the writers' counters)."""
    import polars as pl

    return {
        p.stem: pl.scan_parquet(p).select(pl.len()).collect().item()
        for p in sorted(stg_dir.glob("stg_*.parquet"))
    }


def staging_checks(inv: dict[str, Any], byte_counts: dict[str, int] | None) -> list[CheckResult]:
    """``inv["rows"]`` must hold row counts read back from the written files (``parquet_rows``)."""
    out: list[CheckResult] = []
    rows, top, ch = inv["rows"], inv["top_level"], inv["children"]
    expected = {
        "stg_record": top.get("Record", 0),
        "stg_workout": top.get("Workout", 0),
        "stg_activity_summary": top.get("ActivitySummary", 0),
        "stg_audiogram": top.get("Audiogram", 0),
        "stg_record_metadata": _sum(ch, "Record>MetadataEntry"),
        "stg_hrv_beat": _sum(ch, "HeartRateVariabilityMetadataList>InstantaneousBeatsPerMinute"),
        "stg_workout_record_ref": _sum(ch, "Workout>Record"),
        "stg_workout_activity": _sum(ch, "Workout>WorkoutActivity"),
        "stg_workout_event": _sum(ch, "Workout>WorkoutEvent", "WorkoutActivity>WorkoutEvent"),
        "stg_workout_statistic": _sum(ch, "Workout>WorkoutStatistics", "WorkoutActivity>WorkoutStatistics"),
        "stg_workout_zone": _sum(ch, "WorkoutZoneGroup>WorkoutZone"),
        "stg_workout_route": _sum(ch, "Workout>WorkoutRoute"),
        "stg_workout_metadata": _sum(
            ch,
            "Workout>MetadataEntry",
            "WorkoutActivity>MetadataEntry",
            "WorkoutEvent>MetadataEntry",
            "WorkoutRoute>MetadataEntry",
        ),
        "stg_audiogram_metadata": _sum(ch, "Audiogram>MetadataEntry"),
        "stg_audiogram_point": _sum(ch, "Audiogram>SensitivityPoint"),
    }
    for table, n in expected.items():
        out.append(result(f"rows_{table}", LAYER, ERROR, rows.get(table) == n, rows.get(table), n))
    gpx = inv.get("gpx")
    if gpx is not None:
        n_files = gpx["files_found"] - len(gpx["parse_errors"])
        out.append(
            result(
                "rows_stg_gpx_file",
                LAYER,
                ERROR,
                rows.get("stg_gpx_file") == n_files,
                rows.get("stg_gpx_file"),
                n_files,
            )
        )
        out.append(
            result(
                "rows_stg_gpx_point",
                LAYER,
                ERROR,
                rows.get("stg_gpx_point") == gpx["points"],
                rows.get("stg_gpx_point"),
                gpx["points"],
            )
        )
    if byte_counts is not None:
        for tag, n in byte_counts.items():
            parsed = inv["elements"].get(tag, 0)
            out.append(
                result(
                    f"byte_scan_{tag}",
                    LAYER,
                    ERROR,
                    parsed == n,
                    parsed,
                    n,
                    "elements parsed vs. '<Tag ' occurrences in the raw file",
                )
            )
    return out
