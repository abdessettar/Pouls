"""mart_run (runs with efficiency, form, best efforts) and mart_run_split (per-kilometre splits)."""

from __future__ import annotations

from bisect import bisect_left
from math import floor

import polars as pl

from apple_health.marts.analytics_tables import MART_RUN, MART_RUN_SPLIT
from apple_health.transform.context import BuildContext

MAX_RUN_SPEED_MPS = 10.0  # GPS jumps faster than this are not counted as distance


def clean_cumulative(t: list[float], seg: list[float | None]) -> list[float]:
    """Cumulative distance from segment distances, ignoring implausible jumps."""
    cum = [0.0]
    for i in range(1, len(t)):
        d = seg[i] or 0.0
        # GPS times have one-second resolution, so several points can share a second.
        dt = max(t[i] - t[i - 1], 1.0)
        if d / dt > MAX_RUN_SPEED_MPS:
            d = 0.0
        cum.append(cum[-1] + d)
    return cum


def best_effort(cum: list[float], t: list[float], meters: float) -> float | None:
    """Shortest time covering ``meters`` (two pointers over cumulative distance)."""
    best = None
    i = 0
    for j in range(len(cum)):
        while i + 1 <= j and cum[j] - cum[i + 1] >= meters:
            i += 1
        if cum[j] - cum[i] >= meters:
            dt = t[j] - t[i]
            if dt > 0 and (best is None or dt < best):
                best = dt
    return best


def _interp(cum: list[float], ys: list[float | None], target: float) -> float | None:
    k = bisect_left(cum, target)
    if k == 0:
        return ys[0]
    if k >= len(cum):
        return ys[-1]
    a, b = ys[k - 1], ys[k]
    if a is None or b is None:
        return b if a is None else a
    span = cum[k] - cum[k - 1]
    return a if span == 0 else a + (b - a) * (target - cum[k - 1]) / span


def splits(
    cum: list[float], t: list[float], ele: list[float | None], split_m: float, min_last_m: float = 100.0
) -> list[dict[str, float | None]]:
    total = cum[-1]
    marks = [split_m * k for k in range(1, floor(total / split_m) + 1)]
    if total - (marks[-1] if marks else 0.0) >= min_last_m:
        marks.append(total)
    out = []
    d0, t0, e0 = 0.0, t[0], _interp(cum, ele, 0.0)
    for m in marks:
        t1, e1 = _interp(cum, t, m), _interp(cum, ele, m)  # type: ignore[arg-type]
        dist = m - d0
        dur = (t1 or t0) - t0
        out.append(
            {
                "distance_m": dist,
                "duration_s": dur,
                "pace_s_per_km": dur / (dist / 1000) if dist > 0 else None,
                "elevation_change_m": (e1 - e0) if (e0 is not None and e1 is not None) else None,
                "t0": t0,
                "t1": t1,
            }
        )
        d0, t0, e0 = m, t1 or t0, e1
    return out


def build_runs(ctx: BuildContext) -> None:
    a = ctx.cfg.settings.analytics
    stats = ctx.scan("fct_workout").select(
        "workout_id",
        pl.col("running_power_avg_w").alias("power_w"),
        pl.col("running_stride_length_avg_m").alias("stride_m"),
        pl.col("running_ground_contact_time_avg_ms").alias("ground_contact_ms"),
        pl.col("running_vertical_oscillation_avg_cm").alias("vertical_oscillation_cm"),
    )
    runs = (
        ctx.scan("mart_workout")
        .filter((pl.col("activity_type") == "Running") & pl.col("is_counted") & (pl.col("distance_km") > 0))
        .join(stats, on="workout_id", how="left")
        .with_columns(
            pl.when(pl.col("avg_hr_bpm") > 0)
            .then((pl.col("distance_km") * 1000 / pl.col("duration_min")) / pl.col("avg_hr_bpm"))
            .otherwise(None)
            .alias("m_per_beat")
        )
        .collect()
    )
    ids = runs["workout_id"].to_list()
    routes = ctx.scan("fct_workout_route").filter(
        pl.col("workout_id").is_in(ids) & pl.col("owns_file_points")
    )
    pts = (
        ctx.scan("fct_route_point")
        .join(routes.select("route_id", "workout_id"), on="route_id")
        .select(
            "workout_id",
            "seq",
            (pl.col("ts_utc").dt.epoch("ms") / 1000).alias("t"),
            "segment_dist_m",
            "elevation_m",
        )
        # by time, not file order: a workout can have several routes (one GPX file each)
        .sort("workout_id", "t", "seq")
        .collect()
    )
    hr = (
        ctx.scan("fct_quantity_sample")
        .filter(pl.col("type") == "HeartRate")
        .select((pl.col("start_utc").dt.epoch("ms") / 1000).alias("t"), "value")
        .filter(pl.col("t") >= (runs["start_utc"].min().timestamp() if runs.height else 0))  # type: ignore[union-attr]
        .sort("t")
        .collect()
    )
    hr_t, hr_v = hr["t"].to_list(), hr["value"].to_list()

    def hr_mean(t0: float, t1: float) -> float | None:
        i, j = bisect_left(hr_t, t0), bisect_left(hr_t, t1)
        vals = hr_v[i:j]
        return sum(vals) / len(vals) if vals else None

    best_cols = {d: f"best_{int(d / 1000)}k_s" for d in a.best_effort_m}
    best_rows, split_rows = [], []
    for (wid,), g in pts.group_by("workout_id", maintain_order=True):
        t = g["t"].to_list()
        if len(t) < 2:
            continue
        cum = clean_cumulative(t, g["segment_dist_m"].to_list())
        best_rows.append({"workout_id": wid, **{c: best_effort(cum, t, d) for d, c in best_cols.items()}})
        for k, s in enumerate(splits(cum, t, g["elevation_m"].to_list(), a.run_split_m), start=1):
            split_rows.append(
                {
                    "workout_id": wid,
                    "split": k,
                    "distance_m": s["distance_m"],
                    "duration_s": s["duration_s"],
                    "pace_s_per_km": s["pace_s_per_km"],
                    "elevation_change_m": s["elevation_change_m"],
                    "avg_hr_bpm": hr_mean(s["t0"], s["t1"]) if s["t1"] is not None else None,  # type: ignore[arg-type]
                    "start_offset_s": s["t0"] - t[0],  # type: ignore[operator]
                }
            )
    best_schema = {"workout_id": pl.String, **{c: pl.Float64 for c in best_cols.values()}}
    best = pl.DataFrame(best_rows, schema=best_schema)
    for c in ("best_1k_s", "best_5k_s", "best_10k_s"):
        if c not in best.columns:
            best = best.with_columns(pl.lit(None, dtype=pl.Float64).alias(c))
    out = runs.join(best, on="workout_id", how="left").with_columns(
        pl.col("workout_id").is_in(best["workout_id"].implode()).alias("has_route")
    )
    ctx.write(MART_RUN, out)
    split_schema = {
        "workout_id": pl.String,
        "split": pl.Int32,
        "distance_m": pl.Float64,
        "duration_s": pl.Float64,
        "pace_s_per_km": pl.Float64,
        "elevation_change_m": pl.Float64,
        "avg_hr_bpm": pl.Float64,
        "start_offset_s": pl.Float64,
    }
    ctx.write(MART_RUN_SPLIT, pl.DataFrame(split_rows, schema=split_schema))
