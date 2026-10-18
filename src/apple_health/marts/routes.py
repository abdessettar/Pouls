"""mart_route (route summaries with area clusters) and mart_route_track (thinned points for the map)."""

from __future__ import annotations

import io
import logging
import zipfile
from collections import Counter
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import polars as pl

from apple_health.marts.analytics_tables import MART_ROUTE, MART_ROUTE_TRACK
from apple_health.marts.training import activity_group
from apple_health.transform.context import BuildContext

log = logging.getLogger(__name__)

EARTH_M = 6_371_008.8
ELEVATION_HYSTERESIS_M = 2.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_M * asin(sqrt(min(1.0, a)))


def elevation_gain(elevations: list[float | None], threshold: float = ELEVATION_HYSTERESIS_M) -> float | None:
    """Positive climb with a dead band, so GPS altitude noise does not add up."""
    vals = [e for e in elevations if e is not None]
    if not vals:
        return None
    ref, gain = vals[0], 0.0
    for e in vals[1:]:
        if e - ref >= threshold:
            gain += e - ref
            ref = e
        elif ref - e >= threshold:
            ref = e
    return gain


def thin(seg: list[float | None], keep_every_m: float) -> list[int]:
    """Indices to keep: the first point, then one whenever keep_every_m was covered, and the last."""
    keep, acc = [0], 0.0
    for i in range(1, len(seg)):
        acc += seg[i] or 0.0
        if acc >= keep_every_m:
            keep.append(i)
            acc = 0.0
    if len(seg) > 1 and keep[-1] != len(seg) - 1:
        keep.append(len(seg) - 1)
    return keep


def cluster(centres: list[tuple[float, float]], radius_km: float) -> list[int]:
    """Greedy clustering in order: join the first cluster whose running centre is within radius_km."""
    centers: list[list[float]] = []  # [lat, lon, n]
    labels = []
    for lat, lon in centres:
        for k, c in enumerate(centers):
            if haversine_m(lat, lon, c[0], c[1]) <= radius_km * 1000:
                c[0] = (c[0] * c[2] + lat) / (c[2] + 1)
                c[1] = (c[1] * c[2] + lon) / (c[2] + 1)
                c[2] += 1
                labels.append(k)
                break
        else:
            centers.append([lat, lon, 1])
            labels.append(len(centers) - 1)
    return labels


def load_places(path: Path) -> list[tuple[str, float, float, int]]:
    """GeoNames cities (zip or txt): (name, lat, lon, population)."""
    raw = path.read_bytes()
    if path.suffix == ".zip":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            raw = z.read(next(n for n in z.namelist() if n.endswith(".txt")))
    out = []
    for line in raw.decode("utf-8").splitlines():
        f = line.split("\t")
        if len(f) > 14:
            out.append((f[1], float(f[4]), float(f[5]), int(f[14] or 0)))
    return out


def place_name(
    lat: float, lon: float, places: list[tuple[str, float, float, int]], radius_km: float
) -> str | None:
    """The city that best combines size and closeness: population / (1 + distance / 10 km)^2, among
    cities within radius_km (a big city 20 km away beats a suburb next door); else the nearest one."""
    best, nearest = None, None
    for name, plat, plon, pop in places:
        if abs(plat - lat) > 1.0 or abs(plon - lon) > 1.5:
            continue
        d = haversine_m(lat, lon, plat, plon) / 1000
        score = pop / (1 + d / 10) ** 2
        if d <= radius_km and (best is None or score > best[0]):
            best = (score, name)
        if d <= 100 and (nearest is None or d < nearest[0]):
            nearest = (d, name)
    return best[1] if best else nearest[1] if nearest else None


def build_routes(ctx: BuildContext) -> None:
    a = ctx.cfg.settings.analytics
    routes = (
        ctx.scan("fct_workout_route")
        .filter(pl.col("owns_file_points") & (pl.col("n_points") > 0))
        .select("route_id", "workout_id")
        .join(
            ctx.scan("fct_workout").select("workout_id", "local_date", "activity_type", "tz_name"),
            on="workout_id",
        )
        .collect()
    )
    pts = (
        ctx.scan("fct_route_point")
        .join(routes.lazy().select("route_id"), on="route_id")
        .select("route_id", "seq", "ts_utc", "lat", "lon", "elevation_m", "segment_dist_m")
        .sort("route_id", "seq")
        .collect()
    )
    summary, tracks = [], []
    for (rid,), g in pts.group_by("route_id", maintain_order=True):
        lat, lon, seg = g["lat"].to_list(), g["lon"].to_list(), g["segment_dist_m"].to_list()
        ts = g["ts_utc"]
        summary.append(
            {
                "route_id": rid,
                "start_utc": ts.min(),
                "distance_km": sum(s or 0.0 for s in seg) / 1000,
                "duration_min": (ts.max() - ts.min()).total_seconds() / 60,  # type: ignore[operator, union-attr]
                "elevation_gain_m": elevation_gain(g["elevation_m"].to_list()),
                "center_lat": sum(lat) / len(lat),
                "center_lon": sum(lon) / len(lon),
                "min_lat": min(lat),
                "min_lon": min(lon),
                "max_lat": max(lat),
                "max_lon": max(lon),
                "n_points": len(lat),
            }
        )
        ele = g["elevation_m"].to_list()
        cum = [0.0]
        for x in seg[1:]:
            cum.append(cum[-1] + (x or 0.0))
        for j, i in enumerate(thin(seg, a.track_resolution_m)):
            tracks.append((rid, j, lat[i], lon[i], ele[i], cum[i]))
    schema = {
        "route_id": pl.String,
        "start_utc": pl.Datetime("us", "UTC"),
        "distance_km": pl.Float64,
        "duration_min": pl.Float64,
        "elevation_gain_m": pl.Float64,
        "center_lat": pl.Float64,
        "center_lon": pl.Float64,
        "min_lat": pl.Float64,
        "min_lon": pl.Float64,
        "max_lat": pl.Float64,
        "max_lon": pl.Float64,
        "n_points": pl.Int64,
    }
    df = pl.DataFrame(summary, schema=schema).join(routes, on="route_id").sort("start_utc")

    labels = cluster(list(zip(df["center_lat"], df["center_lon"], strict=True)), a.area_cluster_km)
    df = df.with_columns(pl.Series("__cluster", labels))
    # Area ids by size (1 = most routes). Names: the largest city near the area's centre (GeoNames),
    # else the routes' most common time-zone city (which names Rotterdam "Amsterdam").
    sizes = Counter(labels)
    order = {c: i + 1 for i, (c, _) in enumerate(sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0])))}
    places_file = a.place_names_file
    places = load_places(places_file) if places_file and places_file.is_file() else []
    if not places:
        log.info("  place names: no GeoNames file (scripts/fetch-place-names.sh); using time-zone cities")
    city = {}
    for c in sizes:
        members = df.filter(pl.col("__cluster") == c)
        named = (
            place_name(
                members["center_lat"].median(), members["center_lon"].median(), places, a.place_name_radius_km
            )
            if places
            else None
        )
        zones = members["tz_name"].drop_nulls().to_list()
        tz_city = Counter(zones).most_common(1)[0][0].split("/")[-1].replace("_", " ") if zones else "Area"
        city[c] = named or tz_city
    seen: Counter[str] = Counter()
    names = {}
    for c, _ in sorted(order.items(), key=lambda kv: kv[1]):
        seen[city[c]] += 1
        names[c] = city[c] if seen[city[c]] == 1 else f"{city[c]} {seen[city[c]]}"
    df = df.with_columns(
        pl.col("__cluster").replace_strict(order, return_dtype=pl.Int32).alias("area_id"),
        pl.col("__cluster").replace_strict(names, return_dtype=pl.String).alias("area_name"),
        activity_group().alias("activity_group"),
    )
    ctx.write(MART_ROUTE, df)
    track_schema = {
        "route_id": pl.String,
        "seq": pl.Int32,
        "lat": pl.Float64,
        "lon": pl.Float64,
        "elevation_m": pl.Float64,
        "dist_m": pl.Float64,
    }
    ctx.write(MART_ROUTE_TRACK, pl.DataFrame(tracks, schema=track_schema, orient="row"))
