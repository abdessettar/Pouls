"""MetadataEntry key/value pairs: generic parsing, unit normalisation and promotion to columns."""

from __future__ import annotations

import polars as pl

from apple_health.config import Config
from apple_health.transform.units import conversion, parse_value_expr

PROMOTED_DTYPES: dict[str, pl.DataType] = {
    "float": pl.Float64(),
    "int": pl.Int64(),
    "bool": pl.Boolean(),
    "string": pl.String(),
}
_TRUE = ["1", "true", "TRUE", "True", "YES", "yes"]
_FALSE = ["0", "false", "FALSE", "False", "NO", "no"]


def _conversions(pairs: pl.DataFrame, cfg: Config) -> pl.DataFrame:
    rows = []
    for key, unit in pairs.iter_rows():
        spec = cfg.metadata_keys.get(key)
        target = spec.canonical_unit if spec and spec.canonical_unit else unit
        conv = conversion(unit, target)
        factor, offset = conv if conv else (None, None)
        if spec and spec.scale is not None and factor is not None:
            factor, offset = factor * spec.scale, offset * spec.scale
        rows.append(
            {
                "key": key,
                "value_unit": unit,
                "canonical_unit": target if conv else None,
                "__factor": factor,
                "__offset": offset,
            }
        )
    schema = {
        "key": pl.String,
        "value_unit": pl.String,
        "canonical_unit": pl.String,
        "__factor": pl.Float64,
        "__offset": pl.Float64,
    }
    return pl.DataFrame(rows, schema=schema)


def parse_metadata(md: pl.DataFrame, cfg: Config) -> pl.DataFrame:
    """Add value_num / value_unit (generic parse) and value_canonical / canonical_unit (config).

    ``md`` needs columns ``key`` and ``value`` (raw); ``value`` is renamed ``value_raw``.
    Values whose unit cannot be converted to the configured canonical unit get a null
    ``value_canonical`` (the raw value is always kept).
    """
    df = md.rename({"value": "value_raw"}).with_columns(parse_value_expr("value_raw"))
    pairs = df.filter(pl.col("value_num").is_not_null()).select("key", "value_unit").unique()
    conv = _conversions(pairs, cfg)
    df = df.join(conv, on=["key", "value_unit"], how="left", nulls_equal=True)
    return df.with_columns(
        (pl.col("value_num") * pl.col("__factor") + pl.col("__offset")).alias("value_canonical")
    ).drop("__factor", "__offset")


def _typed(spec_type: str) -> pl.Expr:
    if spec_type == "float":
        return pl.col("value_canonical")
    if spec_type == "int":
        return pl.col("value_num").cast(pl.Int64, strict=False)
    if spec_type == "bool":
        v = pl.col("value_raw").str.strip_chars()
        return pl.when(v.is_in(_TRUE)).then(True).when(v.is_in(_FALSE)).then(False).otherwise(None)
    return pl.col("value_raw")


def promoted_columns(parsed: pl.DataFrame, id_col: str, target: str, cfg: Config) -> pl.DataFrame:
    """One row per ``id_col`` with a typed column per promoted key (first entry wins).

    Always returns every promoted column, even when the key never occurs, so table schemas
    do not depend on the data.
    """
    specs = cfg.promoted_keys(target)
    ids = parsed.select(id_col).unique()
    out = ids
    for spec in specs:
        dtype = PROMOTED_DTYPES[spec.type]
        col = (
            parsed.filter(pl.col("key") == spec.key)
            .sort(id_col, "ordinal")
            .group_by(id_col, maintain_order=True)
            .agg(_typed(spec.type).first().cast(dtype).alias(spec.promote))
        )
        out = out.join(col, on=id_col, how="left")
    return out


def promoted_schema(target: str, cfg: Config) -> dict[str, pl.DataType]:
    return {s.promote: PROMOTED_DTYPES[s.type] for s in cfg.promoted_keys(target)}  # type: ignore[misc]


def attach_promoted(
    df: pl.DataFrame, promoted: pl.DataFrame, id_col: str, target: str, cfg: Config
) -> pl.DataFrame:
    """Left-join promoted columns onto ``df``; missing ids get typed nulls."""
    out = df.join(promoted, on=id_col, how="left")
    for name, dtype in promoted_schema(target, cfg).items():
        if name not in out.columns:
            out = out.with_columns(pl.lit(None, dtype=dtype).alias(name))
    return out
