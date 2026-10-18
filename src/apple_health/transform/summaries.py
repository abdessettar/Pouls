"""HRV beats, activity summaries, profile, audiograms and the date dimension."""

from __future__ import annotations

import re

import polars as pl

from apple_health.schemas import warehouse_tables
from apple_health.transform.context import BuildContext
from apple_health.transform.keys import iso_utc, stable_id
from apple_health.transform.time import hrv_beat_times, parse_hk_ts, to_local
from apple_health.transform.units import conversion

HRV_TYPE = "HeartRateVariabilitySDNN"
_PROFILE_PREFIX = "HKCharacteristicTypeIdentifier"
_PROFILE_VALUE_PREFIXES = r"^(HKBiologicalSex|HKBloodType|HKFitzpatrickSkinType)"


def _f(col: str) -> pl.Expr:
    return pl.col(col).cast(pl.Float64, strict=False)


def _masked(col: str) -> pl.Expr:
    return pl.col(col).replace_strict({"YES": True, "NO": False}, default=None, return_dtype=pl.Boolean)


def build_hrv_beats(ctx: BuildContext) -> None:
    tol = ctx.cfg.settings.hrv_beat_tolerance_s
    parents = (
        ctx.scan("fct_quantity_sample")
        .filter(pl.col("type") == HRV_TYPE)
        .select("record_nr", "sample_id", "start_utc", "end_utc", "tz_name")
        .collect()
    )
    raw = ctx.stg("stg_hrv_beat")
    export_tz = ctx.cfg.settings.export_timezone
    beats = raw.join(parents, on="record_nr", how="inner").with_columns(
        pl.lit(export_tz).alias("__export_tz")
    )
    beats = hrv_beat_times(beats, [export_tz], tz_col="__export_tz")
    zones = beats["tz_name"].unique().drop_nulls().to_list()
    beats = beats.with_columns(
        to_local("beat_utc", "tz_name", zones).alias("beat_local"),
        pl.col("bpm").cast(pl.Float64, strict=False).alias("bpm"),
        pl.lit(ctx.export_id).alias("export_id"),
    )
    beats = beats.with_columns(
        (60000.0 / pl.col("bpm")).alias("rr_interval_ms_approx"),
        (
            (pl.col("beat_utc") >= pl.col("start_utc") - pl.duration(seconds=tol))
            & (pl.col("beat_utc") <= pl.col("end_utc") + pl.duration(seconds=tol))
        )
        .fill_null(False)
        .alias("within_parent_interval"),
    )
    ctx.stats["hrv_beats"] = {
        "raw": raw.height,
        "of_dropped_duplicate_records": raw.height - beats.height,
        "time_parse_failures": beats.filter(
            pl.col("time").is_not_null() & pl.col("beat_utc").is_null()
        ).height,
        "outside_parent_interval": beats.filter(~pl.col("within_parent_interval")).height,
    }
    ctx.write(warehouse_tables(ctx.cfg)["fct_hrv_beat"], beats)


def build_activity_summaries(ctx: BuildContext) -> None:
    raw = ctx.stg("stg_activity_summary")
    units = raw["activeEnergyBurnedUnit"].drop_nulls().unique().to_list()
    factors = {u: conversion(u, "kcal") for u in units}
    ctx.stats["activity_summary_energy_units"] = {u: f is not None for u, f in factors.items()}
    energy_factor = pl.col("activeEnergyBurnedUnit").replace_strict(
        {u: f[0] for u, f in factors.items() if f}, default=None, return_dtype=pl.Float64
    )
    df = raw.with_columns(
        pl.col("dateComponents").str.to_date("%Y-%m-%d", strict=False).alias("local_date"),
        (_f("activeEnergyBurned") * energy_factor).alias("active_energy_kcal"),
        (_f("activeEnergyBurnedGoal") * energy_factor).alias("active_energy_goal_kcal"),
        _f("appleMoveTime").alias("move_time_min"),
        _f("appleMoveTimeGoal").alias("move_time_goal_min"),
        _f("appleExerciseTime").alias("exercise_min"),
        _f("appleExerciseTimeGoal").alias("exercise_goal_min"),
        _f("appleStandHours").alias("stand_hours"),
        _f("appleStandHoursGoal").alias("stand_goal_hours"),
        pl.lit(ctx.export_id).alias("export_id"),
    ).with_columns(
        (
            (pl.col("active_energy_kcal").fill_null(0) == 0)
            & (pl.col("exercise_min").fill_null(0) == 0)
            & (pl.col("stand_hours").fill_null(0) == 0)
            & (pl.col("move_time_min").fill_null(0) == 0)
        ).alias("is_empty_day")
    )
    ctx.stats["activity_summary_date_parse_failures"] = df.filter(
        pl.col("dateComponents").is_not_null() & pl.col("local_date").is_null()
    ).height
    ctx.write(
        warehouse_tables(ctx.cfg)["fct_activity_summary"], df.filter(pl.col("local_date").is_not_null())
    )


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def build_dim_profile(ctx: BuildContext) -> None:
    me = ctx.stg("stg_me")
    values = {
        _snake(a.removeprefix(_PROFILE_PREFIX)): v for a, v in me.select("attribute", "value").iter_rows()
    }
    table = warehouse_tables(ctx.cfg)["dim_profile"]
    row = {c: values.get(c) for c in table.column_names if c != "export_id"}
    df = (
        pl.DataFrame([row], schema={c: pl.String for c in row})
        if me.height
        else pl.DataFrame(schema={c: pl.String for c in row})
    )
    clean = pl.col(pl.String).str.replace(_PROFILE_VALUE_PREFIXES, "")
    df = df.with_columns(clean).with_columns(
        pl.when(pl.col(pl.String) == "NotSet").then(None).otherwise(pl.col(pl.String)).name.keep()
    )
    df = df.with_columns(
        pl.col("date_of_birth").str.to_date("%Y-%m-%d", strict=False),
        pl.lit(ctx.export_id).alias("export_id"),
    )
    ctx.write(table, df)


def build_audiograms(ctx: BuildContext) -> None:
    assert ctx.dim_source is not None and ctx.device_map is not None
    tables = warehouse_tables(ctx.cfg)
    ag = (
        ctx.stg("stg_audiogram")
        .with_columns(
            parse_hk_ts("startDate").alias("start_utc"),
            parse_hk_ts("endDate").alias("end_utc"),
            parse_hk_ts("creationDate").alias("created_utc"),
        )
        .with_columns(
            stable_id("type", "sourceName", iso_utc("start_utc"), iso_utc("end_utc")).alias("audiogram_id"),
            pl.lit(ctx.export_id).alias("export_id"),
        )
        .join(
            ctx.dim_source.select(pl.col("source_name_raw").alias("sourceName"), "source_id"),
            on="sourceName",
            how="left",
        )
        .join(ctx.device_map.select("device", "device_id"), on="device", how="left")
    )
    algo = (
        ctx.stg("stg_audiogram_metadata")
        .filter(pl.col("key") == "HKAlgorithmVersion")
        .group_by("audiogram_nr")
        .agg(pl.col("value").first().alias("algorithm_version"))
    )
    ag = ag.join(algo, on="audiogram_nr", how="left")
    ctx.write(tables["fct_audiogram"], ag)
    pts = (
        ctx.stg("stg_audiogram_point")
        .join(ag.select("audiogram_nr", "audiogram_id"), on="audiogram_nr", how="inner")
        .with_columns(
            _f("frequencyValue").alias("frequency_hz"),
            _f("leftEarValue").alias("left_db_hl"),
            _f("rightEarValue").alias("right_db_hl"),
            _masked("leftEarMasked").alias("left_masked"),
            _masked("rightEarMasked").alias("right_masked"),
            _f("leftEarClampingRangeLowerBound").alias("left_clamp_lower_db_hl"),
            _f("leftEarClampingRangeUpperBound").alias("left_clamp_upper_db_hl"),
            _f("rightEarClampingRangeLowerBound").alias("right_clamp_lower_db_hl"),
            _f("rightEarClampingRangeUpperBound").alias("right_clamp_upper_db_hl"),
            pl.col("frequencyUnit").alias("frequency_unit"),
            pl.coalesce("leftEarUnit", "rightEarUnit").alias("level_unit"),
        )
    )
    ctx.write(tables["fct_audiogram_point"], pts)


def build_dim_date(ctx: BuildContext) -> None:
    dates = pl.concat(
        [
            ctx.scan(t).select(pl.col("local_date").min().alias("lo"), pl.col("local_date").max().alias("hi"))
            for t in ("fct_quantity_sample", "fct_category_sample", "fct_workout", "fct_activity_summary")
        ]
    ).collect()
    lo, hi = dates["lo"].min(), dates["hi"].max()
    if lo is None:
        days = pl.DataFrame(schema={"local_date": pl.Date})
    else:
        days = pl.DataFrame({"local_date": pl.date_range(lo, hi, interval="1d", eager=True)})
    d = pl.col("local_date")
    df = days.with_columns(
        d.dt.year().cast(pl.Int32).alias("year"),
        d.dt.quarter().cast(pl.Int32).alias("quarter"),
        d.dt.month().cast(pl.Int32).alias("month"),
        d.dt.strftime("%B").alias("month_name"),
        d.dt.day().cast(pl.Int32).alias("day"),
        d.dt.weekday().cast(pl.Int32).alias("day_of_week"),
        d.dt.strftime("%A").alias("day_name"),
        d.dt.ordinal_day().cast(pl.Int32).alias("day_of_year"),
        d.dt.iso_year().cast(pl.Int32).alias("iso_year"),
        d.dt.week().cast(pl.Int32).alias("iso_week"),
        (d.dt.weekday() >= 6).alias("is_weekend"),
    )
    ctx.write(warehouse_tables(ctx.cfg)["dim_date"], df)
