"""Parse ``workout-routes/*.gpx`` into ``stg_gpx_file`` / ``stg_gpx_point`` (in parallel)."""

from __future__ import annotations

import hashlib
import json
import logging
import multiprocessing
import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from lxml import etree

from apple_health.io import TableWriter
from apple_health.parse.hk_format import GPX_NS, KNOWN_GPX_EXTENSIONS
from apple_health.schemas import STAGING_TABLES

log = logging.getLogger(__name__)

_NS = f"{{{GPX_NS}}}"
_KNOWN_EXT = frozenset(KNOWN_GPX_EXTENSIONS)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else str(tag)


def parse_gpx_file(path: Path) -> dict[str, Any]:
    """Parse one GPX file into plain Python rows (runs in a worker process)."""
    name = path.name
    try:
        data = path.read_bytes()
        root = etree.fromstring(
            data, parser=etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True)
        )
        ext_counts: Counter[str] = Counter()
        points: list[tuple[Any, ...]] = []
        tracks = root.findall(f"{_NS}trk")
        n_segments = 0
        seq = 0
        for ti, trk in enumerate(tracks):
            for si, seg in enumerate(trk.findall(f"{_NS}trkseg")):
                n_segments += 1
                for pt in seg.iterfind(f"{_NS}trkpt"):
                    ext_vals = dict.fromkeys(KNOWN_GPX_EXTENSIONS)
                    extra = None
                    ext = pt.find(f"{_NS}extensions")
                    if ext is not None:
                        other = {}
                        for e in ext:
                            tag = _local(e.tag)
                            ext_counts[tag] += 1
                            if tag in _KNOWN_EXT:
                                ext_vals[tag] = e.text
                            else:
                                other[tag] = e.text
                        if other:
                            extra = json.dumps(other, ensure_ascii=False, sort_keys=True)
                    points.append(
                        (
                            name,
                            ti,
                            si,
                            seq,
                            pt.get("lat"),
                            pt.get("lon"),
                            pt.findtext(f"{_NS}ele"),
                            pt.findtext(f"{_NS}time"),
                            ext_vals["speed"],
                            ext_vals["course"],
                            ext_vals["hAcc"],
                            ext_vals["vAcc"],
                            extra,
                        )
                    )
                    seq += 1
        file_row = (
            name,
            len(data),
            hashlib.sha256(data).hexdigest(),
            root.get("version"),
            root.get("creator"),
            root.findtext(f"{_NS}metadata/{_NS}time"),
            tracks[0].findtext(f"{_NS}name") if tracks else None,
            len(tracks),
            n_segments,
            seq,
        )
        return {
            "file": file_row,
            "points": points,
            "ext": dict(ext_counts),
            "shape": f"{len(tracks)}/{n_segments}",
            "error": None,
        }
    except (OSError, etree.XMLSyntaxError) as e:
        return {"file": None, "points": [], "ext": {}, "shape": None, "error": f"{name}: {e}"}


def parse_gpx_dir(routes_dir: Path, out_dir: Path, chunk_rows: int, workers: int = 0) -> dict[str, Any]:
    t0 = time.monotonic()
    files = sorted(routes_dir.glob("*.gpx")) if routes_dir.is_dir() else []
    fw = TableWriter(STAGING_TABLES["stg_gpx_file"], out_dir, chunk_rows)
    pw = TableWriter(STAGING_TABLES["stg_gpx_point"], out_dir, chunk_rows)
    versions: Counter[str] = Counter()
    shapes: Counter[str] = Counter()
    extensions: Counter[str] = Counter()
    errors: list[str] = []
    points_parsed = 0

    def consume(res: dict[str, Any]) -> None:
        nonlocal points_parsed
        if res["error"]:
            errors.append(res["error"])
            return
        fw.add(*res["file"])
        versions[res["file"][3] or ""] += 1
        shapes[res["shape"]] += 1
        extensions.update(res["ext"])
        points_parsed += res["file"][9]
        for p in res["points"]:
            pw.add(*p)

    n_workers = workers or os.cpu_count() or 1
    if n_workers == 1 or len(files) < 50:
        for f in files:
            consume(parse_gpx_file(f))
    else:
        # spawn, not fork: the parent is multi-threaded (Polars), and forking it can deadlock.
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx) as pool:
            for res in pool.map(parse_gpx_file, files, chunksize=16):
                consume(res)

    n_files, n_points = fw.close(), pw.close()
    log.info("parsed %d GPX files (%d points) in %.1fs", n_files, n_points, time.monotonic() - t0)
    return {
        "files_found": len(files),
        "points": points_parsed,
        "versions": dict(versions),
        "tracks_segments": dict(shapes),
        "extensions": dict(extensions),
        "parse_errors": errors,
    }


def route_inventory(stg_dir: Path) -> dict[str, list[str]]:
    """Cross-reference WorkoutRoute file references with the GPX files that were parsed."""
    import polars as pl

    refs = (
        pl.read_parquet(stg_dir / "stg_workout_route.parquet")
        .select(pl.col("file_path").str.split("/").list.last().alias("file_name"))
        .drop_nulls()
    )
    files = set(pl.read_parquet(stg_dir / "stg_gpx_file.parquet")["file_name"])
    referenced = set(refs["file_name"])
    shared = refs.group_by("file_name").len().filter(pl.col("len") > 1)["file_name"].sort().to_list()
    return {
        "missing_files": sorted(referenced - files),
        "unreferenced_files": sorted(files - referenced),
        "shared_files": shared,
    }
