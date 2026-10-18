"""Derived, generally useful aggregates that are easy to get wrong (double counting, local days)."""

from __future__ import annotations

import polars as pl

from apple_health.schemas import warehouse_tables
from apple_health.transform.context import BuildContext
from apple_health.transform.keys import iso_utc, stable_id
from apple_health.transform.time import to_local

CUMULATIVE = "cumulative"
SLEEP = "SleepAnalysis"
ASLEEP = {"Core": "core_s", "Deep": "deep_s", "REM": "rem_s", "AsleepUnspecified": "asleep_unspecified_s"}


def _samples(ctx: BuildContext) -> pl.LazyFrame:
    types = ctx.scan("dim_data_type").select("type", "aggregation")
    sources = ctx.scan("dim_source").select("source_id", "source_name")
    return (
        ctx.scan("fct_quantity_sample")
        .select(
            "type",
            "local_date",
            pl.col("start_local").dt.hour().cast(pl.Int32).alias("hour"),
            "value",
            "unit",
            "source_id",
            "is_priority_source",
            "is_outlier",
        )
        .join(types, on="type", how="left")
        .join(sources, on="source_id", how="left")
        .with_columns((pl.col("aggregation") == CUMULATIVE).fill_null(False).alias("__cum"))
    )


def _stats() -> list[pl.Expr]:
    prio = pl.col("is_priority_source")
    return [
        pl.col("aggregation").first(),
        pl.col("unit").first(),
        pl.col("__cum").first(),
        pl.col("value").filter(prio).sum().alias("__cum_value"),
        pl.col("value").mean().alias("__mean"),
        pl.col("value").min().alias("value_min"),
        pl.col("value").max().alias("value_max"),
        pl.len().cast(pl.Int64).alias("n_samples"),
        pl.col("source_id").n_unique().cast(pl.Int32).alias("n_sources"),
        pl.col("is_outlier").sum().cast(pl.Int64).alias("n_outliers"),
        pl.col("value").sum().alias("__all_sum"),
        pl.col("source_name").filter(prio).unique().sort().alias("__sources"),
    ]


def _finish(df: pl.LazyFrame) -> pl.LazyFrame:
    cum = pl.col("__cum")
    return df.with_columns(
        pl.when(cum).then(pl.col("__cum_value")).otherwise(pl.col("__mean")).alias("value"),
        pl.when(cum).then(pl.col("__all_sum")).otherwise(None).alias("value_all_sources_sum"),
        pl.when(cum).then(pl.col("__sources")).otherwise(None).alias("sources_used"),
    )


def build_quantity_aggregates(ctx: BuildContext) -> None:
    tables = warehouse_tables(ctx.cfg)
    samples = _samples(ctx)
    hourly = _finish(samples.group_by("type", "local_date", "hour").agg(_stats())).collect()
    ctx.write(tables["agg_quantity_hourly"], hourly)

    daily = (
        samples.group_by("type", "local_date")
        .agg(*_stats(), pl.col("value").median().alias("__median"))
        .drop("__cum_value", "__sources")
    )
    # Cumulative types: sum of the hourly priority-resolved values (priority is decided per hour).
    resolved = (
        hourly.lazy()
        .filter(pl.col("__cum"))
        .group_by("type", "local_date")
        .agg(
            pl.col("value").sum().alias("__cum_value"),
            pl.col("sources_used").explode().drop_nulls().unique().sort().alias("__sources"),
        )
    )
    daily = (
        daily.join(resolved, on=["type", "local_date"], how="left")
        .pipe(_finish)
        .with_columns(pl.when(pl.col("__cum")).then(None).otherwise(pl.col("__median")).alias("value_median"))
    )
    ctx.write(tables["agg_quantity_daily"], daily.collect())


def build_sleep_sessions(ctx: BuildContext) -> None:
    gap = pl.duration(minutes=ctx.cfg.settings.sleep_session_gap_minutes)
    sources = ctx.scan("dim_source").select("source_id", "source_name", "priority_rank")
    sl = (
        ctx.scan("fct_category_sample")
        .filter(pl.col("type") == SLEEP)
        .select("start_utc", "end_utc", "duration_s", "label", "tz_name", "source_id")
        .join(sources, on="source_id", how="left")
        .sort("start_utc", "end_utc")
        .collect()
    )
    prev_end = pl.col("end_utc").cum_max().shift(1)
    sl = sl.with_columns(
        (prev_end.is_null() | (pl.col("start_utc") > prev_end + gap)).cum_sum().alias("session")
    )
    # Per session and stage: only the best-priority source that recorded this stage.
    best = pl.col("priority_rank") == pl.col("priority_rank").min().over("session", "label")
    used = sl.filter(best)
    stage = used.group_by("session").agg(
        pl.col("duration_s").filter(pl.col("label") == "InBed").sum().alias("in_bed_s"),
        *[
            pl.col("duration_s").filter(pl.col("label") == lab).sum().alias(col)
            for lab, col in ASLEEP.items()
        ],
        pl.col("duration_s").filter(pl.col("label") == "Awake").sum().alias("awake_s"),
        pl.len().cast(pl.Int64).alias("n_samples"),
        pl.col("source_name").unique().sort().alias("sources_used"),
    )
    bounds = sl.group_by("session").agg(
        pl.col("start_utc").min(),
        pl.col("end_utc").max(),
        pl.col("tz_name").sort_by("end_utc").last(),
    )
    df = bounds.join(stage, on="session")
    zones = df["tz_name"].unique().drop_nulls().to_list()
    asleep = pl.sum_horizontal(*ASLEEP.values())
    span = (pl.col("end_utc") - pl.col("start_utc")).dt.total_microseconds() / 1e6
    df = df.with_columns(
        stable_id(pl.lit("sleep"), iso_utc("start_utc")).alias("session_id"),
        to_local("start_utc", "tz_name", zones).alias("start_local"),
        to_local("end_utc", "tz_name", zones).alias("end_local"),
        span.alias("span_s"),
        asleep.alias("asleep_s"),
        (pl.col("core_s") + pl.col("deep_s") + pl.col("rem_s") > 0).alias("stage_detail_available"),
    ).with_columns(
        pl.col("end_local").dt.date().alias("sleep_date"),
        # Wearable definition: asleep / (asleep + awake) within the session. In-bed records are not used
        # (the Watch's in-bed time often equals the asleep time, which would read 100 %). Without stages
        # (no awake segments recorded) fall back to asleep / session span.
        pl.when((pl.col("asleep_s") > 0) & pl.col("stage_detail_available"))
        .then(pl.col("asleep_s") / (pl.col("asleep_s") + pl.col("awake_s")))
        .when((pl.col("asleep_s") > 0) & (pl.col("span_s") > 0))
        .then(pl.col("asleep_s") / pl.col("span_s"))
        .otherwise(None)
        .alias("sleep_efficiency"),
    )
    df = df.sort(["sleep_date", "asleep_s", "start_utc"], descending=[False, True, False]).with_columns(
        (pl.int_range(pl.len()).over("sleep_date") == 0).alias("is_primary")
    )
    ctx.write(warehouse_tables(ctx.cfg)["agg_sleep_session"], df)


def build_coverage(ctx: BuildContext) -> None:
    cols = ["type", "source_id", "local_date", "start_utc", "end_utc"]
    samples = pl.concat(
        [
            ctx.scan("fct_quantity_sample").select(cols).with_columns(pl.lit("quantity").alias("kind")),
            ctx.scan("fct_category_sample").select(cols).with_columns(pl.lit("category").alias("kind")),
        ]
    )
    cov = (
        samples.group_by("type", "kind", "source_id", "local_date")
        .agg(
            pl.len().cast(pl.Int64).alias("n_samples"),
            pl.col("start_utc").min().alias("first_start_utc"),
            pl.col("end_utc").max().alias("last_end_utc"),
        )
        .join(ctx.scan("dim_source").select("source_id", "source_name"), on="source_id", how="left")
    )
    ctx.write(warehouse_tables(ctx.cfg)["agg_data_coverage"], cov.collect())
