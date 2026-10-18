"""Sources (apps/devices that wrote samples) and devices (HKDevice description strings)."""

from __future__ import annotations

import re

import polars as pl

from apple_health.config import Config
from apple_health.transform.keys import hash_text, stable_id

# "<Owner>’s Apple Watch" -> "Apple Watch". The export uses U+2019 and a no-break space
# (U+00A0) inside "Apple Watch"; whitespace is normalised before matching.
OWNER_DEVICE = r"^.+?[’'`]s ((?:Apple Watch|iPhone|iPad|iPod|Mac|AirPods|Beats|HomePod)\b.*)$"
# A possessive left in a normalised name means an owner name may have survived.
POSSESSIVE = r"[’'`]s\s"

_POINTER = re.compile(r"^<<HKDevice: 0x[0-9A-Fa-f]+>,?\s*")
_FIELD_SPLIT = re.compile(r", (?=[A-Za-z][A-Za-z ]*:)")
_OWNER_DEVICE_RE = re.compile(OWNER_DEVICE)

DEVICE_FIELDS = ("name", "manufacturer", "model", "hardware", "software", "firmware")


def normalise_space(col: str | pl.Expr) -> pl.Expr:
    """Collapse any Unicode whitespace (e.g. U+00A0) to single ASCII spaces."""
    e = pl.col(col) if isinstance(col, str) else col
    return e.str.replace_all(r"\s+", " ").str.strip_chars()


def strip_owner(col: str | pl.Expr) -> pl.Expr:
    return normalise_space(col).str.replace(OWNER_DEVICE, "$1")


def _strip_owner_text(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    m = _OWNER_DEVICE_RE.match(s)
    return m.group(1) if m else s


def source_kind_expr(cfg: Config, name_col: str = "source_name") -> pl.Expr:
    name = pl.col(name_col)
    expr = pl.when(name.str.starts_with("Apple Watch")).then(pl.lit("watch"))
    expr = expr.when(name.str.starts_with("iPhone") | name.str.starts_with("iPad")).then(pl.lit("phone"))
    for src, kind in cfg.settings.source_kinds.items():
        expr = expr.when(name == src).then(pl.lit(kind))
    return expr.otherwise(pl.lit("third_party_app"))


def priority_rank_expr(cfg: Config) -> pl.Expr:
    """Lower is preferred: explicit priority list first, then by kind."""
    pri = list(cfg.settings.source_priority)
    kinds = list(cfg.settings.source_kind_priority)
    expr = pl.when(pl.lit(False)).then(pl.lit(None, dtype=pl.Int32))
    for i, name in enumerate(pri):
        expr = expr.when(pl.col("source_name") == name).then(pl.lit(i, dtype=pl.Int32))
    for j, kind in enumerate(kinds):
        expr = expr.when(pl.col("source_kind") == kind).then(pl.lit(len(pri) + j, dtype=pl.Int32))
    return expr.otherwise(pl.lit(len(pri) + len(kinds), dtype=pl.Int32))


def build_dim_source(raw_names: pl.Series, cfg: Config) -> pl.DataFrame:
    df = pl.DataFrame({"source_name_raw": raw_names.drop_nulls().unique().sort()})
    return (
        df.with_columns(
            stable_id("source_name_raw").alias("source_id"),
            strip_owner("source_name_raw").alias("source_name"),
        )
        .with_columns(source_kind_expr(cfg).alias("source_kind"))
        .with_columns(priority_rank_expr(cfg).alias("priority_rank"))
        .select("source_id", "source_name", "source_kind", "priority_rank", "source_name_raw")
    )


def parse_device(raw: str | None) -> dict[str, str | None]:
    """Fields of an HKDevice description, owner name stripped; local identifiers are dropped."""
    out: dict[str, str | None] = dict.fromkeys(DEVICE_FIELDS)
    if not raw:
        return out
    inner = _POINTER.sub("", raw.strip())
    if inner.endswith(">"):
        inner = inner[:-1]
    for part in _FIELD_SPLIT.split(inner):
        key, sep, value = part.partition(":")
        key = key.strip()
        if sep and key in out:
            out[key] = value.strip() or None
    out["name"] = _strip_owner_text(out["name"])
    return out


def device_class(d: dict[str, str | None]) -> str:
    text = " ".join(v for v in (d["name"], d["model"], d["manufacturer"]) if v).lower()
    if "watch" in text:
        return "watch"
    if "iphone" in text or "ipad" in text:
        return "phone"
    if any(w in text for w in ("airpods", "earpods", "beats", "bose", "jbl", "headphone", "wired", "audio")):
        return "audio"
    if "hrm" in text or "garmin" in text or "polar" in text or "wahoo" in text:
        return "sensor"
    return "other"


def build_devices(raw_devices: pl.Series) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Returns (dim_device, device_map). device_map: raw device string -> device_id, device_software.

    The id covers name/manufacturer/model/hardware (the device model); software and firmware
    versions change with updates and are kept on the samples instead.
    """
    dims: dict[str, dict[str, str | None]] = {}
    rows = []
    for raw in raw_devices.drop_nulls().unique().sort().to_list():
        d = parse_device(raw)
        ident = "\x1f".join(d[k] or "\x00" for k in ("name", "manufacturer", "model", "hardware"))
        device_id = hash_text(ident)
        if device_id not in dims:
            dims[device_id] = {
                "device_id": device_id,
                **{k: d[k] for k in DEVICE_FIELDS[:4]},
                "device_class": device_class(d),
            }
        rows.append(
            {"device": raw, "device_id": device_id, "device_software": d["software"] or d["firmware"]}
        )
    dim_schema = {
        "device_id": pl.String,
        "name": pl.String,
        "manufacturer": pl.String,
        "model": pl.String,
        "hardware": pl.String,
        "device_class": pl.String,
    }
    map_schema = {"device": pl.String, "device_id": pl.String, "device_software": pl.String}
    dim = pl.DataFrame(list(dims.values()), schema=dim_schema).sort("device_id")
    return dim, pl.DataFrame(rows, schema=map_schema)
