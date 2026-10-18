"""Records -> fct_quantity_sample, fct_category_sample, fct_sample_metadata (+ dimensions)."""

from __future__ import annotations

import logging

import polars as pl

from apple_health.schemas import warehouse_tables
from apple_health.transform.context import BuildContext
from apple_health.transform.keys import iso_utc, stable_id
from apple_health.transform.metadata import attach_promoted, parse_metadata, promoted_columns
from apple_health.transform.registry import (
    build_dim_category_value,
    build_dim_data_type,
    unit_conversions,
)
from apple_health.transform.sources import build_devices, build_dim_source
from apple_health.transform.time import (
    build_timezone_periods,
    parse_hk_ts,
    resolve_timezone,
    to_local,
    valid_zone,
)

log = logging.getLogger(__name__)

SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
TZ_KEY = "HKTimeZone"

NATURAL_KEY = ["type", "sourceName", "start_utc", "end_utc", "value", "unit"]
# All attributes, with the device's memory pointer stripped. Instants stand in for the raw
# timestamp strings (identical within one export, which renders every instant in one offset).
EXACT_KEY = [
    "type",
    "unit",
    "value",
    "sourceName",
    "sourceVersion",
    "device_norm",
    "created_utc",
    "start_utc",
    "end_utc",
    "extra_attrs",
]


def _parse_times(df: pl.DataFrame, cols: dict[str, str]) -> tuple[pl.DataFrame, dict[str, int]]:
    """Parse raw timestamp columns; return frame and per-column failure counts."""
    df = df.with_columns(parse_hk_ts(raw).alias(out) for raw, out in cols.items())
    failures = df.select(
        (pl.col(raw).is_not_null() & pl.col(out).is_null()).sum().alias(raw) for raw, out in cols.items()
    ).row(0, named=True)
    return df, failures


def build_sources_and_devices(ctx: BuildContext) -> None:
    names, devices = [], []
    for t in ("stg_record", "stg_workout", "stg_workout_route", "stg_audiogram"):
        df = ctx.stg(t)
        names.append(df["sourceName"])
        devices.append(df["device"])
    ctx.dim_source = build_dim_source(pl.concat(names), ctx.cfg)
    dim_device, ctx.device_map = build_devices(pl.concat(devices))
    tables = warehouse_tables(ctx.cfg)
    ctx.write(tables["dim_source"], ctx.dim_source)
    ctx.write(tables["dim_device"], dim_device)


def build_tz_periods(ctx: BuildContext, rec: pl.DataFrame, md: pl.DataFrame) -> None:
    evidence = []
    use = set(ctx.cfg.settings.tz_evidence_from)
    if use & {"sleep", "record"}:
        rec_tz = md.filter(pl.col("key") == TZ_KEY).join(
            rec.select("record_nr", "type", "start_utc"), on="record_nr"
        )
        if "record" not in use:
            rec_tz = rec_tz.filter(pl.col("type") == SLEEP)
        evidence.append(
            rec_tz.select(pl.col("start_utc").alias("instant_utc"), pl.col("value_raw").alias("tz_name"))
        )
    if "workout" in use:
        wk = ctx.stg("stg_workout").select("workout_nr", parse_hk_ts("startDate").alias("instant_utc"))
        wk_tz = (
            ctx.stg("stg_workout_metadata")
            .filter((pl.col("owner_kind") == "workout") & (pl.col("key") == TZ_KEY))
            .join(wk, on="workout_nr")
            .select("instant_utc", pl.col("value").alias("tz_name"))
        )
        evidence.append(wk_tz)
    ev = (
        pl.concat(evidence)
        if evidence
        else pl.DataFrame(schema={"instant_utc": pl.Datetime("us", "UTC"), "tz_name": pl.String})
    )
    invalid = ev.filter(valid_zone("tz_name").is_null() & pl.col("tz_name").is_not_null())
    ctx.stats["tz_evidence"] = {"n": ev.height, "invalid_zone_names": sorted(set(invalid["tz_name"]))}
    ctx.tz_periods = build_timezone_periods(ev)
    ctx.write(warehouse_tables(ctx.cfg)["dim_timezone_period"], ctx.tz_periods)


def _key_hash(cols: list[str], prefix: str) -> list[pl.Expr]:
    """Two independent 64-bit row hashes (128 bits: collisions are negligible) for in-memory dedup.

    ``pl.Expr.hash`` is fine here because the hashes never leave this run (unlike ids).
    """
    return [pl.struct(cols).hash(seed=seed).alias(f"{prefix}{seed}") for seed in (0, 1)]


def deduplicate(rec: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, int]]:
    """1) drop exact duplicates; 2) collapse rewrites of the same observation (keep latest creation).

    Works on a narrow frame of key hashes to keep memory low on millions of rows.
    """
    n_raw = rec.height
    device_norm = (
        pl.col("device").str.replace(r"^<<HKDevice: 0x[0-9A-Fa-f]+>", "<<HKDevice>").alias("device_norm")
    )
    keys = rec.with_columns(device_norm).select(
        "record_nr",
        "created_utc",
        *_key_hash(EXACT_KEY, "__e"),
        *_key_hash(NATURAL_KEY, "__n"),
    )
    keys = keys.with_columns(pl.len().over("__n0", "__n1").cast(pl.Int32).alias("dup_count"))
    step1 = keys.sort("record_nr").unique(["__e0", "__e1"], keep="first", maintain_order=True)
    step2 = step1.sort(["created_utc", "record_nr"], descending=[True, True], nulls_last=True).unique(
        ["__n0", "__n1"], keep="first"
    )
    stats = {
        "raw": n_raw,
        "exact_duplicates_dropped": n_raw - step1.height,
        "rewrites_dropped": step1.height - step2.height,
        "final": step2.height,
    }
    survivors = step2.select("record_nr", "dup_count")
    out = rec.join(survivors, on="record_nr", how="inner").sort("record_nr")
    return out, stats


def localise(df: pl.DataFrame, ctx: BuildContext, explicit_col: str | None) -> pl.DataFrame:
    """Add tz_name, tz_source, start_local, end_local, local_date from start_utc/end_utc."""
    assert ctx.tz_periods is not None
    df = resolve_timezone(df, "start_utc", explicit_col, ctx.tz_periods, ctx.cfg.settings.default_timezone)
    zones = df["tz_name"].unique().drop_nulls().to_list()
    df = df.with_columns(
        to_local("start_utc", "tz_name", zones).alias("start_local"),
        to_local("end_utc", "tz_name", zones).alias("end_local"),
    )
    return df.with_columns(pl.col("start_local").dt.date().alias("local_date"))


def build_samples(ctx: BuildContext) -> None:
    cfg = ctx.cfg
    tables = warehouse_tables(cfg)

    rec, failures = _parse_times(
        ctx.stg("stg_record"), {"startDate": "start_utc", "endDate": "end_utc", "creationDate": "created_utc"}
    )
    ctx.stats["record_timestamp_parse_failures"] = failures
    ctx.stats["record_timestamp_offsets"] = (
        rec.select(pl.col("startDate").str.slice(20).value_counts(sort=True)).unnest("startDate").rows()
    )
    rec = rec.drop("startDate", "endDate", "creationDate")

    # Registry: record types plus workout-statistic types (their units need conversions too).
    stats_types = ctx.stg("stg_workout_statistic").select(
        "type",
        "unit",
        pl.coalesce("sum", "average", "minimum", "maximum").alias("value"),
        pl.lit(False).alias("is_record"),
    )
    reg_input = pl.concat([rec.select("type", "unit", "value", pl.lit(True).alias("is_record")), stats_types])
    ctx.dim_data_type = build_dim_data_type(reg_input, cfg)
    ctx.unit_conversions = unit_conversions(ctx.dim_data_type)
    ctx.write(tables["dim_data_type"], ctx.dim_data_type)
    del reg_input

    category_types = ctx.dim_data_type.filter(pl.col("kind") == "category")["type_identifier"].implode()
    dim_cat = build_dim_category_value(
        rec.filter(pl.col("type").is_in(category_types)).select("type", "value"), cfg
    )
    ctx.write(tables["dim_category_value"], dim_cat)

    md = parse_metadata(ctx.stg("stg_record_metadata"), cfg)
    build_tz_periods(ctx, rec, md)

    rec, dedup = deduplicate(rec)
    ctx.stats["record_dedup"] = dedup
    log.info("  dedup: %s", dedup)

    assert ctx.dim_source is not None and ctx.device_map is not None
    explicit_tz = (
        md.filter(pl.col("key") == TZ_KEY)
        .sort("record_nr", "ordinal")
        .group_by("record_nr", maintain_order=True)
        .agg(pl.col("value_raw").first().alias("__hk_tz"))
    )
    dim_type = ctx.dim_data_type.select(
        pl.col("type_identifier").alias("type"),
        pl.col("type").alias("type_short"),
        "kind",
        "min_plausible",
        "max_plausible",
    )
    df = (
        rec.lazy()
        .join(dim_type.lazy(), on="type", how="left")
        .join(
            ctx.dim_source.lazy().select(
                pl.col("source_name_raw").alias("sourceName"), "source_id", "priority_rank"
            ),
            on="sourceName",
            how="left",
        )
        .join(ctx.device_map.lazy(), on="device", how="left")
        .join(explicit_tz.lazy(), on="record_nr", how="left")
        .with_columns(
            stable_id("type", "sourceName", iso_utc("start_utc"), iso_utc("end_utc"), "value", "unit").alias(
                "sample_id"
            ),
            ((pl.col("end_utc") - pl.col("start_utc")).dt.total_microseconds() / 1e6).alias("duration_s"),
            pl.lit(ctx.export_id).alias("export_id"),
        )
        .drop("device", "extra_attrs", "sourceName")
        .collect()
    )
    del rec, explicit_tz
    df = localise(df, ctx, "__hk_tz")
    promoted = promoted_columns(md, "record_nr", "sample", cfg)
    df = attach_promoted(df, promoted, "record_nr", "sample", cfg)
    del promoted
    df = df.rename({"type": "type_identifier", "type_short": "type", "sourceVersion": "source_version"})
    ids = df.select("record_nr", "sample_id")

    # -- quantities ------------------------------------------------------------------------------
    assert ctx.unit_conversions is not None
    q = (
        df.lazy()
        .filter(pl.col("kind") == "quantity")
        .join(
            ctx.unit_conversions.lazy().rename({"raw_unit": "unit"}),
            on=["type_identifier", "unit"],
            how="left",
            nulls_equal=True,
        )
        .with_columns(pl.col("value").cast(pl.Float64, strict=False).alias("__v"))
        .collect()
    )
    ctx.stats["quantity_value_cast_failures"] = q.select(
        (pl.col("value").is_not_null() & pl.col("__v").is_null()).sum()
    ).item()
    q = q.with_columns(
        (pl.col("__v") * pl.col("factor") + pl.col("offset")).alias("value"),
        pl.col("unit").alias("raw_unit"),
        pl.col("canonical_unit").alias("unit"),
    ).with_columns(
        (
            (pl.col("min_plausible").is_not_null() & (pl.col("value") < pl.col("min_plausible")))
            | (pl.col("max_plausible").is_not_null() & (pl.col("value") > pl.col("max_plausible")))
        )
        .fill_null(False)
        .alias("is_outlier"),
        (
            pl.col("priority_rank")
            == pl.col("priority_rank").min().over("type", "local_date", pl.col("start_local").dt.hour())
        ).alias("is_priority_source"),
    )
    ctx.write(tables["fct_quantity_sample"], q)
    del q

    # -- categories ------------------------------------------------------------------------------
    c = (
        df.filter(pl.col("kind") == "category")
        .rename({"value": "category_value"})
        .join(
            dim_cat.select("type_identifier", "category_value", "label"),
            on=["type_identifier", "category_value"],
            how="left",
            nulls_equal=True,
        )
    )
    del df
    ctx.write(tables["fct_category_sample"], c)
    del c

    # -- metadata of surviving samples -------------------------------------------------------------
    ctx.write(tables["fct_sample_metadata"], md.join(ids, on="record_nr", how="inner"))
