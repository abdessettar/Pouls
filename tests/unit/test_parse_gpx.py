from __future__ import annotations

import json
import shutil

import polars as pl

from apple_health.parse.gpx import parse_gpx_dir, parse_gpx_file


def test_parse_gpx_file(fixture_export):
    res = parse_gpx_file(fixture_export / "workout-routes" / "route_2023-07-28_7.20am.gpx")
    assert res["error"] is None
    _name, _size, _sha, version, creator, meta_time, track, n_trk, n_seg, n_pts = res["file"]
    assert (version, creator, track, n_trk, n_seg, n_pts) == (
        "1.1",
        "Apple Health Export",
        "Route 2023-07-28 7:20am",
        1,
        1,
        4,
    )
    assert meta_time == "2025-05-05T16:31:53Z"
    first = res["points"][0]
    assert first[:8] == (
        "route_2023-07-28_7.20am.gpx",
        0,
        0,
        0,
        "46.000000",
        "6.000000",
        "200.0",
        "2023-07-28T05:00:04Z",
    )
    assert first[8:12] == ("3.0", "0.0", "2.0", "1.0")
    assert json.loads(res["points"][-1][12]) == {"cadence": "170"}
    assert res["ext"]["cadence"] == 1


def test_sentinels_are_kept_raw(fixture_export):
    res = parse_gpx_file(fixture_export / "workout-routes" / "route_2023-01-15_9.30am.gpx")
    courses = [p[9] for p in res["points"]]
    vaccs = [p[11] for p in res["points"]]
    assert "-1.000000" in courses and "-1.000000" in vaccs
    assert len(res["points"]) == 7


def test_malformed_file_reports_error(tmp_path):
    p = tmp_path / "bad.gpx"
    p.write_text("<gpx><trk>")
    res = parse_gpx_file(p)
    assert res["file"] is None and res["error"].startswith("bad.gpx")


def test_parallel_equals_serial(tmp_path, fixture_export):
    src = fixture_export / "workout-routes"
    routes = tmp_path / "routes"
    routes.mkdir()
    for i in range(30):  # 60 files: above the threshold for the process pool
        for f in src.glob("*.gpx"):
            shutil.copy(f, routes / f"{i:02d}_{f.name}")
    serial, parallel = tmp_path / "s", tmp_path / "p"
    inv_s = parse_gpx_dir(routes, serial, chunk_rows=50, workers=1)
    inv_p = parse_gpx_dir(routes, parallel, chunk_rows=50, workers=4)
    assert inv_s == inv_p
    assert inv_s["files_found"] == 60 and inv_s["points"] == 30 * 11
    for t in ("stg_gpx_file", "stg_gpx_point"):
        assert pl.read_parquet(serial / f"{t}.parquet").equals(pl.read_parquet(parallel / f"{t}.parquet"))


def test_missing_routes_dir(tmp_path):
    inv = parse_gpx_dir(tmp_path / "none", tmp_path / "out", chunk_rows=10)
    assert inv["files_found"] == 0
    assert pl.read_parquet(tmp_path / "out" / "stg_gpx_point.parquet").height == 0
