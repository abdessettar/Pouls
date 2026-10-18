"""Data-type registry (dim_data_type) and category values (dim_category_value)."""

from __future__ import annotations

import polars as pl

from apple_health.config import Config, infer_kind
from apple_health.transform.units import conversion

TYPE_PREFIXES = (
    "HKQuantityTypeIdentifier",
    "HKCategoryTypeIdentifier",
    "HKCorrelationTypeIdentifier",
    "HKDataTypeIdentifier",
    "HKDataType",
    "HKWorkoutActivityType",
    "HKWorkoutEventType",
)


def short_name(col: str | pl.Expr) -> pl.Expr:
    e = pl.col(col) if isinstance(col, str) else col
    return e.str.replace(r"^(" + "|".join(TYPE_PREFIXES) + ")", "")


def build_dim_data_type(records: pl.DataFrame, cfg: Config) -> pl.DataFrame:
    """Registry of every type in config or in the data.

    ``records`` has columns type, unit, value (raw strings) and optionally ``is_record`` (False for
    rows that only contribute units, e.g. workout statistics; they are not counted).
    Unknown types get their kind from the identifier prefix, or from their values (numeric ->
    quantity), the most frequent raw unit as canonical unit and no aggregation semantics.
    """
    if "is_record" not in records.columns:
        records = records.with_columns(pl.lit(True).alias("is_record"))
    seen = records.group_by("type").agg(
        pl.col("is_record").sum().alias("n_raw"),
        pl.col("unit").drop_nulls().unique().sort().alias("raw_units"),
        pl.col("unit").drop_nulls().mode().sort().first().alias("top_unit"),
        (pl.col("value").cast(pl.Float64, strict=False).is_null() & pl.col("value").is_not_null())
        .any()
        .alias("has_non_numeric"),
    )
    seen_map = {r["type"]: r for r in seen.iter_rows(named=True)}
    rows = []
    for ident in sorted(set(cfg.types) | set(seen_map)):
        spec = cfg.types.get(ident)
        s = seen_map.get(ident)
        if spec is not None:
            kind, unit, agg, lo, hi = spec.kind, spec.unit, spec.aggregation, spec.min, spec.max
        else:
            prefix_kind = infer_kind(ident)
            kind = "category" if prefix_kind == "category" or (s and s["has_non_numeric"]) else "quantity"
            unit = s["top_unit"] if s and kind == "quantity" else None
            agg, lo, hi = ("category" if kind == "category" else None), None, None
        rows.append(
            {
                "type_identifier": ident,
                "kind": kind,
                "canonical_unit": unit,
                "aggregation": agg,
                "min_plausible": float(lo) if lo is not None else None,
                "max_plausible": float(hi) if hi is not None else None,
                "is_known": spec is not None,
                "raw_units": s["raw_units"] if s else [],
                "n_raw_records": s["n_raw"] if s else 0,
            }
        )
    schema = {
        "type_identifier": pl.String,
        "kind": pl.String,
        "canonical_unit": pl.String,
        "aggregation": pl.String,
        "min_plausible": pl.Float64,
        "max_plausible": pl.Float64,
        "is_known": pl.Boolean,
        "raw_units": pl.List(pl.String),
        "n_raw_records": pl.Int64,
    }
    return (
        pl.DataFrame(rows, schema=schema)
        .with_columns(short_name("type_identifier").alias("type"))
        .select("type_identifier", "type", *[c for c in schema if c != "type_identifier"])
    )


def unit_conversions(dim_type: pl.DataFrame) -> pl.DataFrame:
    """(type_identifier, raw_unit) -> canonical unit and linear factors; null factors = not convertible."""
    rows = []
    for r in dim_type.iter_rows(named=True):
        for u in r["raw_units"] or [None]:
            conv = conversion(u, r["canonical_unit"]) if r["canonical_unit"] else (1.0, 0.0)
            rows.append(
                {
                    "type_identifier": r["type_identifier"],
                    "raw_unit": u,
                    "canonical_unit": r["canonical_unit"] or u,
                    "factor": conv[0] if conv else None,
                    "offset": conv[1] if conv else None,
                }
            )
    schema = {
        "type_identifier": pl.String,
        "raw_unit": pl.String,
        "canonical_unit": pl.String,
        "factor": pl.Float64,
        "offset": pl.Float64,
    }
    return pl.DataFrame(rows, schema=schema)


def build_dim_category_value(category_records: pl.DataFrame, cfg: Config) -> pl.DataFrame:
    """Every (type, value) seen or configured, with a short label and HealthKit's ordinal."""
    seen = category_records.group_by("type", "value").agg(pl.len().alias("n_raw_records"))
    seen_map = {(r["type"], r["value"]): r["n_raw_records"] for r in seen.iter_rows(named=True)}
    configured = {
        (t, v): cv
        for t, spec in cfg.types.items()
        if spec.kind == "category"
        for v, cv in spec.values.items()
    }
    rows = []
    for t, v in sorted(set(seen_map) | set(configured), key=lambda k: (k[0] or "", k[1] or "")):
        cv = configured.get((t, v))
        rows.append(
            {
                "type_identifier": t,
                "category_value": v,
                "label": cv.label if cv else None,
                "ordinal": cv.ordinal if cv else None,
                "is_known": cv is not None,
                "n_raw_records": seen_map.get((t, v), 0),
            }
        )
    schema = {
        "type_identifier": pl.String,
        "category_value": pl.String,
        "label": pl.String,
        "ordinal": pl.Int32,
        "is_known": pl.Boolean,
        "n_raw_records": pl.Int64,
    }
    df = pl.DataFrame(rows, schema=schema)
    # Derived label for unconfigured values: drop "HKCategoryValue" and the type's own name.
    type_short = short_name("type_identifier")
    derived = pl.col("category_value").str.replace(r"^HKCategoryValue", "")
    derived = (
        pl.when(derived.str.starts_with(type_short))
        .then(derived.str.slice(type_short.str.len_chars()))
        .otherwise(derived)
    )
    return df.with_columns(
        type_short.alias("type"),
        pl.coalesce(pl.col("label"), derived).alias("label"),
    ).select("type_identifier", "type", "category_value", "label", "ordinal", "is_known", "n_raw_records")
