"""Export profiles and drift detection between exports.

Every build writes a profile of its export (types, units, sources, metadata keys, category values,
element inventory, counts) and a snapshot of its sample/workout ids. ``diff`` compares the latest
two exports: new or vanished structures, shrinking counts, and samples that disappeared from
history (an export is a full snapshot, so earlier samples should still be present).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import polars as pl

from apple_health.manifest import META, read_json, write_json
from apple_health.transform.context import BuildContext

log = logging.getLogger(__name__)

PROFILES = "profiles"
SNAPSHOTS = "snapshots"


def _safe(export_id: str) -> str:
    return export_id.replace(":", "").replace(".", "")


def export_profile(ctx: BuildContext) -> dict[str, Any]:
    q = ctx.scan("fct_quantity_sample").select("type", "unit", "source_id", "start_utc")
    c = ctx.scan("fct_category_sample").select(
        "type", pl.lit(None, dtype=pl.String).alias("unit"), "source_id", "start_utc"
    )
    sources = ctx.scan("dim_source").select("source_id", "source_name")
    per_type = (
        pl.concat([q, c])
        .join(sources, on="source_id", how="left")
        .group_by("type")
        .agg(
            pl.len().alias("count"),
            pl.col("unit").drop_nulls().unique().sort().alias("units"),
            pl.col("source_name").drop_nulls().unique().sort().alias("sources"),
            pl.col("start_utc").min().dt.strftime("%Y-%m-%d").alias("first"),
            pl.col("start_utc").max().dt.strftime("%Y-%m-%d").alias("last"),
        )
        .sort("type")
        .collect()
    )
    types = {
        r["type"]: {
            "count": r["count"],
            "units": r["units"],
            "sources": r["sources"],
            "first": r["first"],
            "last": r["last"],
        }
        for r in per_type.iter_rows(named=True)
    }

    def counts(lf: pl.LazyFrame, *cols: str) -> dict[str, int]:
        df = lf.group_by(*cols).len().collect()
        return {"/".join(str(r[k]) for k in cols): r["len"] for r in df.iter_rows(named=True)}

    inventory = read_json(ctx.staging / "_inventory.json")
    return {
        "export_id": ctx.export_id,
        "export_version": inventory.get("header", {}).get("export_version"),
        "types": types,
        "record_metadata_keys": counts(ctx.scan("fct_sample_metadata"), "key"),
        "workout_metadata_keys": counts(ctx.scan("fct_workout_metadata"), "owner_kind", "key"),
        "category_values": counts(ctx.scan("fct_category_sample"), "type", "label"),
        "workout_types": counts(ctx.scan("fct_workout"), "activity_type"),
        "elements": {
            "top_level": inventory["top_level"],
            "children": inventory["children"],
            "attributes": {t: sorted(a) for t, a in inventory["attributes"].items()},
        },
        "rows": dict(sorted(ctx.rows.items())),
    }


def write_profile_and_snapshot(ctx: BuildContext, profile: dict[str, Any]) -> None:
    meta = ctx.cfg.settings.warehouse_dir / META
    name = _safe(ctx.export_id)
    write_json(meta / PROFILES / f"{name}.json", profile)
    snap = meta / SNAPSHOTS / name
    snap.mkdir(parents=True, exist_ok=True)
    pl.concat(
        [
            ctx.scan("fct_quantity_sample").select("sample_id", "type"),
            ctx.scan("fct_category_sample").select("sample_id", "type"),
        ]
    ).sink_parquet(snap / "sample_ids.parquet", compression="zstd")
    ctx.scan("fct_workout").select("workout_id", "activity_type").sink_parquet(snap / "workout_ids.parquet")
    keep = ctx.cfg.settings.snapshots_keep
    snaps = sorted(p for p in (meta / SNAPSHOTS).iterdir() if p.is_dir())
    for old in snaps[:-keep] if keep > 0 else []:
        shutil.rmtree(old)
        log.info("removed old id snapshot %s", old.name)


def list_profiles(warehouse_dir: Path) -> list[Path]:
    d = warehouse_dir / META / PROFILES
    return sorted(d.glob("*.json")) if d.is_dir() else []


def _set_diff(old: list[str] | set[str], new: list[str] | set[str]) -> dict[str, list[str]]:
    o, n = set(old), set(new)
    return {"added": sorted(n - o), "removed": sorted(o - n)}


def diff_profiles(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Structural and count differences between two export profiles (empty lists = no change)."""
    out: dict[str, Any] = {"from": old["export_id"], "to": new["export_id"]}
    out["export_version"] = (
        {"from": old["export_version"], "to": new["export_version"]}
        if old["export_version"] != new["export_version"]
        else None
    )
    out["types"] = _set_diff(old["types"], new["types"])
    unit_changes, source_changes, shrunk = {}, {}, {}
    for t in sorted(set(old["types"]) & set(new["types"])):
        a, b = old["types"][t], new["types"][t]
        if a["units"] != b["units"]:
            unit_changes[t] = {"from": a["units"], "to": b["units"]}
        sd = _set_diff(a["sources"], b["sources"])
        if sd["added"] or sd["removed"]:
            source_changes[t] = sd
        if b["count"] < a["count"]:
            shrunk[t] = {"from": a["count"], "to": b["count"]}
    out["unit_changes"] = unit_changes
    out["source_changes"] = source_changes
    out["shrinking_types"] = shrunk
    for key in ("record_metadata_keys", "workout_metadata_keys", "category_values", "workout_types"):
        out[key] = _set_diff(old[key], new[key])
    oe, ne = old["elements"], new["elements"]
    out["top_level_elements"] = _set_diff(oe["top_level"], ne["top_level"])
    out["child_elements"] = _set_diff(oe["children"], ne["children"])
    attrs: dict[str, dict[str, list[str]]] = {}
    for tag in sorted(set(oe["attributes"]) | set(ne["attributes"])):
        d = _set_diff(oe["attributes"].get(tag, []), ne["attributes"].get(tag, []))
        if d["added"] or d["removed"]:
            attrs[tag] = d
    out["attributes"] = attrs
    out["row_changes"] = {
        t: {"from": old["rows"].get(t), "to": n} for t, n in new["rows"].items() if old["rows"].get(t) != n
    }
    return out


def history_rewrites(warehouse_dir: Path, old_id: str, new_id: str) -> dict[str, Any] | None:
    """Samples/workouts present in the older export's snapshot but missing from the newer one."""
    base = warehouse_dir / META / SNAPSHOTS
    a, b = base / _safe(old_id), base / _safe(new_id)
    if not (a.is_dir() and b.is_dir()):
        return None
    vanished = (
        pl.scan_parquet(a / "sample_ids.parquet")
        .join(pl.scan_parquet(b / "sample_ids.parquet").select("sample_id"), on="sample_id", how="anti")
        .group_by("type")
        .len()
        .collect()
    )
    wk = (
        pl.scan_parquet(a / "workout_ids.parquet")
        .join(pl.scan_parquet(b / "workout_ids.parquet").select("workout_id"), on="workout_id", how="anti")
        .select(pl.len())
        .collect()
        .item()
    )
    return {"vanished_samples_by_type": dict(vanished.rows()), "vanished_workouts": wk}


SET_DIFF_KEYS = (
    "types",
    "record_metadata_keys",
    "workout_metadata_keys",
    "category_values",
    "workout_types",
    "top_level_elements",
    "child_elements",
)


def has_changes(d: dict[str, Any]) -> bool:
    """True when the diff contains structural changes or lost history (plain growth does not count)."""
    if d.get("export_version"):
        return True
    if any(d[k]["added"] or d[k]["removed"] for k in SET_DIFF_KEYS):
        return True
    if any(d[k] for k in ("attributes", "unit_changes", "source_changes", "shrinking_types")):
        return True
    hist = d.get("history")
    return bool(hist and (hist["vanished_samples_by_type"] or hist["vanished_workouts"]))


def format_diff(d: dict[str, Any]) -> str:
    lines = [f"Drift report: export {d['from']} -> {d['to']}"]

    def add(title: str, value: Any) -> None:
        if isinstance(value, dict) and set(value) == {"added", "removed"}:
            if value["added"]:
                lines.append(f"  {title} added: {', '.join(value['added'])}")
            if value["removed"]:
                lines.append(f"  {title} REMOVED: {', '.join(value['removed'])}")
        elif value:
            lines.append(f"  {title}: {value}")

    add("export format version", d.get("export_version"))
    for key in SET_DIFF_KEYS:
        add(key.replace("_", " "), d[key])
    add("attributes", d["attributes"])
    add("unit changes", d["unit_changes"])
    add("source changes", d["source_changes"])
    add("types with FEWER samples than before", d["shrinking_types"])
    hist = d.get("history")
    if hist and (hist["vanished_samples_by_type"] or hist["vanished_workouts"]):
        lines.append(
            f"  samples missing from history: {hist['vanished_samples_by_type']}, "
            f"workouts: {hist['vanished_workouts']}"
        )
    if not has_changes(d):
        lines.append("  no structural changes")
    if d["row_changes"]:
        rows = sorted(d["row_changes"].items())
        lines.append("  row counts: " + ", ".join(f"{t} {v['from']}->{v['to']}" for t, v in rows))
    return "\n".join(lines)


def run_diff(warehouse_dir: Path) -> int:
    """Compare the two most recent export profiles; print and store the report."""
    profiles = list_profiles(warehouse_dir)
    if len(profiles) < 2:
        log.info("drift: %d export profile(s) found; need two different exports to compare", len(profiles))
        return 0
    old, new = read_json(profiles[-2]), read_json(profiles[-1])
    d = diff_profiles(old, new)
    d["history"] = history_rewrites(warehouse_dir, old["export_id"], new["export_id"])
    report = format_diff(d)
    print(report)
    write_json(warehouse_dir / META / "diffs" / f"{profiles[-2].stem}__{profiles[-1].stem}.json", d)
    return 0
