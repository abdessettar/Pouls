"""Workouts and their children; routes and GPS points; workout <-> sample bridge."""

from __future__ import annotations

import logging

import polars as pl

from apple_health.schemas import warehouse_tables
from apple_health.transform.context import BuildContext
from apple_health.transform.keys import iso_utc, stable_id
from apple_health.transform.metadata import attach_promoted, parse_metadata, promoted_columns
from apple_health.transform.registry import short_name
from apple_health.transform.samples import TZ_KEY, localise
from apple_health.transform.time import parse_hk_ts, to_local
from apple_health.transform.units import DURATION_TO_SECONDS

log = logging.getLogger(__name__)

GPX_TS_FORMAT = "%Y-%m-%dT%H:%M:%S%.fZ"
EARTH_RADIUS_M = 6_371_008.8
_TRUE = ["1", "true", "YES", "yes"]
_FALSE = ["0", "false", "NO", "no"]


def _seconds(value: str, unit: str) -> pl.Expr:
    factor = pl.col(unit).replace_strict(DURATION_TO_SECONDS, default=None, return_dtype=pl.Float64)
    return pl.col(value).cast(pl.Float64, strict=False) * factor


def _f(col: str) -> pl.Expr:
    return pl.col(col).cast(pl.Float64, strict=False)


def _first_meta(md: pl.DataFrame, kind: str, key: str, by: list[str], alias: str) -> pl.DataFrame:
    return (
        md.filter((pl.col("owner_kind") == kind) & (pl.col("key") == key))
        .sort([*by, "ordinal"])
        .group_by(by, maintain_order=True)
        .agg(pl.col("value_raw").first().alias(alias))
    )


def build_workouts(ctx: BuildContext) -> None:
    cfg = ctx.cfg
    tables = warehouse_tables(cfg)
    assert ctx.dim_source is not None and ctx.device_map is not None and ctx.unit_conversions is not None

    wk = ctx.stg("stg_workout").with_columns(
        parse_hk_ts("startDate").alias("start_utc"),
        parse_hk_ts("endDate").alias("end_utc"),
        parse_hk_ts("creationDate").alias("created_utc"),
    )
    ctx.stats["workout_timestamp_parse_failures"] = wk.select(
        (pl.col("startDate").is_not_null() & pl.col("start_utc").is_null()).sum()
        + (pl.col("endDate").is_not_null() & pl.col("end_utc").is_null()).sum()
    ).item()
    wk = wk.with_columns(
        stable_id("workoutActivityType", "sourceName", iso_utc("start_utc"), iso_utc("end_utc")).alias(
            "workout_id"
        )
    )
    n_raw = wk.height
    wk = wk.sort("workout_nr").unique("workout_id", keep="first", maintain_order=True)
    ctx.stats["workout_duplicates_dropped"] = n_raw - wk.height
    ids = wk.select("workout_nr", "workout_id")

    # -- metadata (all owners) ----------------------------------------------------------------
    wmd = parse_metadata(ctx.stg("stg_workout_metadata"), cfg).join(ids, on="workout_nr", how="inner")
    wmd = wmd.with_columns(pl.col("owner_ordinal").fill_null(0), pl.lit(ctx.export_id).alias("export_id"))
    ctx.write(tables["fct_workout_metadata"], wmd)

    # -- activities ---------------------------------------------------------------------------
    act = ctx.stg("stg_workout_activity").join(ids, on="workout_nr", how="inner")
    interval = {
        "interval_step_key_path": "WOIntervalStepKeyPath",
        "interval_step_successful": "WOIntervalStepSuccessful",
    }
    for alias, key in interval.items():
        meta = _first_meta(wmd, "activity", key, ["workout_nr", "owner_ordinal"], alias)
        act = act.join(meta.rename({"owner_ordinal": "ordinal"}), on=["workout_nr", "ordinal"], how="left")
    act = act.with_columns(
        pl.coalesce("uuid", stable_id("workout_id", pl.col("ordinal").cast(pl.String))).alias("activity_id"),
        parse_hk_ts("startDate").alias("start_utc"),
        parse_hk_ts("endDate").alias("end_utc"),
        _seconds("duration", "durationUnit").alias("duration_s"),
        pl.when(pl.col("interval_step_successful").is_in(_TRUE))
        .then(True)
        .when(pl.col("interval_step_successful").is_in(_FALSE))
        .then(False)
        .otherwise(None)
        .alias("interval_step_successful"),
        pl.lit(ctx.export_id).alias("export_id"),
    )
    ctx.write(tables["fct_workout_activity"], act)
    act_map = act.select("workout_nr", pl.col("ordinal").alias("activity_ordinal"), "activity_id")

    # -- events, statistics, zones --------------------------------------------------------------
    def children(name: str) -> pl.DataFrame:
        return (
            ctx.stg(name)
            .join(ids, on="workout_nr", how="inner")
            .join(act_map, on=["workout_nr", "activity_ordinal"], how="left")
            .with_columns(pl.lit(ctx.export_id).alias("export_id"))
        )

    ev = children("stg_workout_event").with_columns(
        short_name("type").alias("event_type"),
        parse_hk_ts("date").alias("event_utc"),
        _seconds("duration", "durationUnit").alias("duration_s"),
    )
    ctx.write(tables["fct_workout_event"], ev)

    conv = ctx.unit_conversions.rename({"type_identifier": "type", "raw_unit": "unit"})
    st = children("stg_workout_statistic").join(conv, on=["type", "unit"], how="left", nulls_equal=True)
    st = st.with_columns(
        [
            (_f(c) * pl.col("factor") + pl.col("offset")).alias(c)
            for c in ("sum", "average", "minimum", "maximum")
        ]
    ).with_columns(
        pl.col("type").alias("type_identifier"),
        short_name("type").alias("type"),
        parse_hk_ts("startDate").alias("start_utc"),
        parse_hk_ts("endDate").alias("end_utc"),
        pl.col("unit").alias("raw_unit"),
        pl.col("canonical_unit").alias("unit"),
    )
    ctx.write(tables["fct_workout_statistic"], st)

    zones = children("stg_workout_zone").with_columns(
        short_name("group_type").alias("zone_type"),
        pl.col("group_source").alias("zone_source"),
        pl.col("group_unit").alias("unit"),
        _f("minimum").alias("minimum"),
        _f("maximum").alias("maximum"),
        _seconds("duration", "durationUnit").alias("duration_s"),
    )
    ctx.write(tables["fct_workout_zone"], zones)

    # -- workouts --------------------------------------------------------------------------------
    explicit_tz = _first_meta(wmd, "workout", TZ_KEY, ["workout_nr"], "__hk_tz")
    w = (
        wk.join(
            ctx.dim_source.select(pl.col("source_name_raw").alias("sourceName"), "source_id"),
            on="sourceName",
            how="left",
        )
        .join(ctx.device_map, on="device", how="left")
        .join(explicit_tz, on="workout_nr", how="left")
        .with_columns(
            pl.col("workoutActivityType").alias("activity_type_identifier"),
            short_name("workoutActivityType").alias("activity_type"),
            pl.col("sourceVersion").alias("source_version"),
            _seconds("duration", "durationUnit").alias("duration_s"),
            ((pl.col("end_utc") - pl.col("start_utc")).dt.total_microseconds() / 1e6).alias("elapsed_s"),
            _f("totalDistance").alias("total_distance"),
            pl.col("totalDistanceUnit").alias("total_distance_unit"),
            _f("totalEnergyBurned").alias("total_energy_burned"),
            pl.col("totalEnergyBurnedUnit").alias("total_energy_burned_unit"),
            pl.lit(ctx.export_id).alias("export_id"),
        )
    )
    w = localise(w, ctx, "__hk_tz")
    wmeta_workout = wmd.filter(pl.col("owner_kind") == "workout")
    w = attach_promoted(
        w, promoted_columns(wmeta_workout, "workout_nr", "workout", cfg), "workout_nr", "workout", cfg
    )

    # statistics pivot (workout level only), per config/types.toml [workout_statistics]
    top = st.filter(pl.col("activity_id").is_null())
    for ident, stats in cfg.workout_statistics.items():
        sel = top.filter(pl.col("type_identifier") == ident).sort("workout_id", "ordinal")
        piv = sel.group_by("workout_id", maintain_order=True).agg(
            [pl.col(stat).first().alias(col) for stat, col in stats.items()]
        )
        w = w.join(piv, on="workout_id", how="left")

    counts = [
        act.group_by("workout_id").agg(pl.len().cast(pl.Int32).alias("n_activities")),
        ev.group_by("workout_id").agg(
            pl.len().cast(pl.Int32).alias("n_events"),
            (pl.col("event_type") == "Pause").sum().cast(pl.Int32).alias("n_pauses"),
        ),
    ]
    for c in counts:
        w = w.join(c, on="workout_id", how="left")
    route_counts = build_routes(ctx, w.select("workout_nr", "workout_id", "tz_name"), wmd)
    w = w.join(route_counts, on="workout_id", how="left").with_columns(
        pl.col("n_activities", "n_events", "n_pauses", "n_routes").fill_null(0),
        pl.col("has_route").fill_null(False),
    )
    w = w.join(_overlaps(w), on="workout_id", how="left")
    ctx.write(tables["fct_workout"], w)

    build_workout_sample_bridge(ctx, ids)


def _overlaps(w: pl.DataFrame) -> pl.DataFrame:
    iv = w.select("workout_id", "start_utc", "end_utc")
    other = iv.rename({"workout_id": "other_id", "start_utc": "o_start", "end_utc": "o_end"})
    pairs = iv.join_where(other, pl.col("start_utc") < pl.col("o_end"), pl.col("end_utc") > pl.col("o_start"))
    return (
        pairs.filter(pl.col("workout_id") != pl.col("other_id"))
        .with_columns(
            (pl.min_horizontal("end_utc", "o_end") - pl.max_horizontal("start_utc", "o_start")).alias(
                "overlap"
            )
        )
        .sort(["workout_id", "overlap", "other_id"], descending=[False, True, False])
        .group_by("workout_id", maintain_order=True)
        .agg(pl.col("other_id").first().alias("overlaps_workout_id"))
    )


def build_routes(ctx: BuildContext, workouts: pl.DataFrame, wmd: pl.DataFrame) -> pl.DataFrame:
    """Write fct_workout_route and fct_route_point; return per-workout route counts."""
    s = ctx.cfg.settings
    tables = warehouse_tables(ctx.cfg)
    assert ctx.dim_source is not None and ctx.device_map is not None

    sync = _first_meta(
        wmd, "route", "HKMetadataKeySyncIdentifier", ["workout_nr", "owner_ordinal"], "sync_identifier"
    )
    ro = (
        ctx.stg("stg_workout_route")
        .join(workouts, on="workout_nr", how="inner")
        .join(sync.rename({"owner_ordinal": "ordinal"}), on=["workout_nr", "ordinal"], how="left")
        .join(
            ctx.dim_source.select(pl.col("source_name_raw").alias("sourceName"), "source_id"),
            on="sourceName",
            how="left",
        )
        .join(ctx.device_map.select("device", "device_id"), on="device", how="left")
        .with_columns(
            parse_hk_ts("startDate").alias("start_utc"),
            parse_hk_ts("endDate").alias("end_utc"),
            parse_hk_ts("creationDate").alias("created_utc"),
            pl.col("file_path").str.split("/").list.last().alias("file_name"),
            pl.lit(ctx.export_id).alias("export_id"),
        )
        .with_columns(stable_id("workout_id", iso_utc("start_utc"), iso_utc("end_utc")).alias("route_id"))
    )
    files = ctx.stg("stg_gpx_file").select("file_name")
    ro = ro.with_columns(
        pl.col("file_name").is_in(files["file_name"].implode()).alias("file_exists"),
        (pl.len().over("file_name") > 1).alias("file_shared"),
    )

    pts = ctx.stg("stg_gpx_point").with_columns(
        pl.col("time")
        .str.to_datetime(GPX_TS_FORMAT, time_unit="us", time_zone="UTC", strict=False)
        .alias("ts_utc"),
        *[_f(c).alias(c) for c in ("lat", "lon", "ele", "speed", "course", "hAcc", "vAcc")],
    )
    n_pts = pts.height
    pts = pts.sort("file_name", "seq").unique(
        ["file_name", "ts_utc", "lat", "lon"], keep="first", maintain_order=True
    )
    ctx.stats["route_point_duplicates_dropped"] = n_pts - pts.height
    ctx.stats["route_point_time_parse_failures"] = pts.filter(
        pl.col("time").is_not_null() & pl.col("ts_utc").is_null()
    ).height

    # Each GPX file belongs to exactly one route: the referencing route whose time window matches best.
    ranges = pts.group_by("file_name").agg(
        pl.col("ts_utc").min().alias("p_first"), pl.col("ts_utc").max().alias("p_last")
    )
    owner = (
        ro.join(ranges, on="file_name", how="inner")
        .with_columns(
            (
                (pl.col("p_first") - pl.col("start_utc")).abs() + (pl.col("p_last") - pl.col("end_utc")).abs()
            ).alias("__score")
        )
        .sort("file_name", "__score", "ordinal")
        .group_by("file_name", maintain_order=True)
        .agg(pl.col("route_id").first(), pl.col("tz_name").first())
    )
    pts = pts.join(owner, on="file_name", how="inner")
    ctx.stats["route_points_without_route"] = n_pts - ctx.stats["route_point_duplicates_dropped"] - pts.height

    zones = pts["tz_name"].unique().drop_nulls().to_list()
    lat1, lon1 = pl.col("lat").radians(), pl.col("lon").radians()
    lat0, lon0 = lat1.shift().over("route_id"), lon1.shift().over("route_id")
    hav = ((lat1 - lat0) / 2).sin().pow(2) + lat0.cos() * lat1.cos() * ((lon1 - lon0) / 2).sin().pow(2)
    pts = (
        pts.sort("route_id", "seq")
        .with_columns(
            to_local("ts_utc", "tz_name", zones).alias("ts_local"),
            (pl.col("course") < 0).fill_null(False).alias("invalid_course"),
            (pl.col("vAcc") < 0).fill_null(False).alias("invalid_altitude"),
            (2 * EARTH_RADIUS_M * hav.sqrt().arcsin()).alias("segment_dist_m"),
        )
        .with_columns(
            pl.when(pl.col("invalid_altitude")).then(None).otherwise(pl.col("ele")).alias("elevation_m"),
            pl.when(pl.col("speed") < 0).then(None).otherwise(pl.col("speed")).alias("speed_mps"),
            pl.when(pl.col("invalid_course")).then(None).otherwise(pl.col("course")).alias("course_deg"),
            pl.col("hAcc").alias("h_acc_m"),
            pl.when(pl.col("vAcc") < 0).then(None).otherwise(pl.col("vAcc")).alias("v_acc_m"),
            pl.col("ts_utc").dt.year().cast(pl.Int64).alias("year"),
        )
        .with_columns(
            (pl.col("speed_mps") > s.route_max_speed_mps).fill_null(False).alias("speed_outlier"),
            (pl.col("h_acc_m") > s.route_max_horizontal_accuracy_m).fill_null(False).alias("low_accuracy"),
        )
    )
    per_route = pts.group_by("route_id").agg(pl.len().cast(pl.Int64).alias("n_points"))
    ctx.write(tables["fct_route_point"], pts)
    del pts

    ro = ro.join(per_route, on="route_id", how="left").with_columns(
        pl.col("n_points").fill_null(0),
        pl.col("route_id").is_in(owner["route_id"].implode()).alias("owns_file_points"),
    )
    ctx.write(tables["fct_workout_route"], ro)
    return ro.group_by("workout_id").agg(
        pl.len().cast(pl.Int32).alias("n_routes"),
        (pl.col("n_points") > 0).any().alias("has_route"),
    )


def build_workout_sample_bridge(ctx: BuildContext, ids: pl.DataFrame) -> None:
    refs = (
        ctx.stg("stg_workout_record_ref")
        .join(ids, on="workout_nr", how="inner")
        .with_columns(parse_hk_ts("startDate").alias("s"), parse_hk_ts("endDate").alias("e"))
        .with_columns(
            stable_id("type", "sourceName", iso_utc("s"), iso_utc("e"), "value", "unit").alias("sample_id")
        )
    )
    samples = pl.concat(
        [
            ctx.scan("fct_quantity_sample").select("sample_id"),
            ctx.scan("fct_category_sample").select("sample_id"),
        ]
    ).collect()
    bridge = (
        refs.join(samples, on="sample_id", how="inner")
        .select("workout_id", "sample_id", pl.lit("nested_record").alias("link_type"))
        .unique(["workout_id", "sample_id"])
    )
    ctx.stats["nested_records"] = refs.height
    ctx.stats["nested_records_unmatched"] = refs.join(samples, on="sample_id", how="anti").height
    ctx.write(warehouse_tables(ctx.cfg)["bridge_workout_sample"], bridge)
