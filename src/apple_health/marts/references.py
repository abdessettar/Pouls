"""mart_reference and mart_reference_source: cited reference bands for the profile's age and sex.

The bands come from config/references.toml. Age-specific sets apply from the birthday that starts
their age group to the day before the one that ends it, within the export's date span. Without a date
of birth only the sets for all adults apply; without a biological sex, sex-specific rows are skipped.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

import polars as pl

from apple_health.config import ConfigError
from apple_health.marts.analytics_tables import MART_REFERENCE, MART_REFERENCE_SOURCE
from apple_health.transform.context import BuildContext

REFERENCES_FILE = "references.toml"
KINDS = ("range", "percentile")
SEXES = ("Female", "Male")
ADULT = (18, 120)
OPEN_AGE = 120  # an age group ending here is open-ended ("80 and over")


@dataclass(frozen=True)
class Band:
    band: str
    label: str
    lo: float | None
    hi: float | None
    is_target: bool = False
    is_warning: bool = False


@dataclass(frozen=True)
class RefSet:
    metric: str
    kind: str
    source_id: str
    population: str
    ages: tuple[int, int] | None
    sex: str | None
    bands: tuple[Band, ...]


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def percentile_bands(percentiles: list[int], values: list[float]) -> list[Band]:
    """Bands between consecutive percentiles, plus the two open tails."""
    first, last = percentiles[0], percentiles[-1]
    out = [Band(f"below_p{first}", f"Below the {ordinal(first)} percentile", None, values[0])]
    for (p1, v1), (p2, v2) in pairwise(zip(percentiles, values, strict=True)):
        out.append(Band(f"p{p1}_p{p2}", f"{ordinal(p1)}–{ordinal(p2)} percentile", v1, v2))
    out.append(Band(f"above_p{last}", f"Above the {ordinal(last)} percentile", values[-1], None))
    return out


def who(sex: str | None, ages: tuple[int, int] | None) -> str:
    people = {"Female": "Women", "Male": "Men"}.get(sex or "", "Adults")
    if ages is None:
        return people
    lo, hi = ages
    return f"{people} aged {lo} and over" if hi >= OPEN_AGE else f"{people} aged {lo}–{hi}"


def _err(where: str, msg: str) -> ConfigError:
    return ConfigError(f"{REFERENCES_FILE}: {where}: {msg}")


def _band(raw: dict[str, Any], scale: float, where: str) -> Band:
    unknown = set(raw) - {"band", "label", "lo", "hi", "target", "warn"}
    if unknown:
        raise _err(where, f"unknown band keys {sorted(unknown)}")
    lo = None if raw.get("lo") is None else float(raw["lo"]) * scale
    hi = None if raw.get("hi") is None else float(raw["hi"]) * scale
    if lo is None and hi is None:
        raise _err(where, f"band {raw.get('band')!r} needs lo or hi")
    if lo is not None and hi is not None and not lo < hi:
        raise _err(where, f"band {raw.get('band')!r} has lo >= hi")
    if raw.get("target") and raw.get("warn"):
        raise _err(where, f"band {raw.get('band')!r} cannot be both target and warn")
    return Band(str(raw["band"]), str(raw["label"]), lo, hi, bool(raw.get("target")), bool(raw.get("warn")))


def _ages(raw: Any, where: str) -> tuple[int, int] | None:
    if raw is None:
        return None
    lo, hi = (int(v) for v in raw)
    if not 0 <= lo <= hi <= OPEN_AGE:
        raise _err(where, f"bad ages {raw}")
    return lo, hi


def _check_bands(bands: tuple[Band, ...], where: str) -> None:
    ids = [b.band for b in bands]
    if len(set(ids)) != len(ids):
        raise _err(where, f"duplicate band ids {ids}")
    ordered = sorted(bands, key=lambda b: -float("inf") if b.lo is None else b.lo)
    for a, b in pairwise(ordered):
        a_hi = float("inf") if a.hi is None else a.hi
        b_lo = -float("inf") if b.lo is None else b.lo
        if b_lo < a_hi:
            raise _err(where, f"bands {a.band!r} and {b.band!r} overlap")


def load_references(config_dir: Path) -> tuple[dict[str, dict[str, str]], list[RefSet]]:
    """Read and validate references.toml; returns (sources, sets with one entry per age/sex row)."""
    path = config_dir / REFERENCES_FILE
    if not path.is_file():
        raise ConfigError(f"missing config file: {path}")
    with path.open("rb") as f:
        raw = tomllib.load(f)
    sources = {
        k: {
            "short": str(v.get("short", k)),
            "citation": str(v["citation"]),
            "url": str(v.get("url", "")),
            "note": str(v.get("note", "")),
        }
        for k, v in raw.get("sources", {}).items()
    }
    sets: list[RefSet] = []
    for i, s in enumerate(raw.get("set", [])):
        where = f"set {i + 1} ({s.get('metric')})"
        if s.get("kind") not in KINDS:
            raise _err(where, f"kind must be one of {KINDS}")
        if s.get("source") not in sources:
            raise _err(where, f"unknown source {s.get('source')!r}")
        scale = float(s.get("scale", 1.0))
        rows = s.get("rows") or [{"ages": s.get("ages"), "sex": s.get("sex"), "bands": s.get("bands")}]
        for j, row in enumerate(rows):
            w = f"{where} row {j + 1}"
            sex = row.get("sex")
            if sex is not None and sex not in SEXES:
                raise _err(w, f"sex must be one of {SEXES}")
            ages = _ages(row.get("ages"), w)
            if s["kind"] == "percentile":
                pct, vals = list(s["percentiles"]), [float(v) * scale for v in row["values"]]
                if len(pct) != len(vals):
                    raise _err(w, "values and percentiles differ in length")
                if pct != sorted(set(pct)) or vals != sorted(vals) or len(set(vals)) != len(vals):
                    raise _err(w, "percentiles and values must increase")
                bands = tuple(percentile_bands(pct, vals))
            else:
                if not row.get("bands"):
                    raise _err(w, "range sets need bands")
                bands = tuple(_band(b, scale, w) for b in row["bands"])
            _check_bands(bands, w)
            population = str(s["population"]).replace("{who}", who(sex, ages))
            sets.append(RefSet(str(s["metric"]), s["kind"], s["source"], population, ages, sex, bands))
    return sources, sets


def birthday(dob: date, years: int) -> date:
    """The date someone born on ``dob`` turns ``years`` (29 February birthdays fall on 1 March)."""
    try:
        return dob.replace(year=dob.year + years)
    except ValueError:
        return date(dob.year + years, 3, 1)


def validity(
    s: RefSet, dob: date | None, sex: str | None, span: tuple[date, date]
) -> tuple[date, date] | None:
    """When a set applies within the export span, or None when it does not apply to this person."""
    if s.sex is not None and s.sex != sex:
        return None
    if dob is None:
        return span if s.ages is None else None
    lo, hi = s.ages or ADULT
    start = max(span[0], birthday(dob, lo))
    end = span[1] if hi >= OPEN_AGE else min(span[1], birthday(dob, hi + 1) - timedelta(days=1))
    return (start, end) if start <= end else None


def build_references(ctx: BuildContext) -> None:
    sources, sets = load_references(ctx.cfg.config_dir)
    profile = ctx.scan("dim_profile").select("date_of_birth", "biological_sex").collect()
    dob = profile["date_of_birth"][0] if profile.height else None
    sex = profile["biological_sex"][0] if profile.height else None
    span = ctx.scan("dim_date").select(
        pl.col("local_date").min().alias("a"), pl.col("local_date").max().alias("b")
    )
    first, last = span.collect().row(0)
    rows: list[dict[str, Any]] = []
    if first is not None:
        for s in sets:
            v = validity(s, dob, sex, (first, last))
            if v is None:
                continue
            ordered = sorted(s.bands, key=lambda b: -float("inf") if b.lo is None else b.lo)
            for seq, b in enumerate(ordered):
                rows.append(
                    {
                        "metric": s.metric,
                        "kind": s.kind,
                        "band": b.band,
                        "label": b.label,
                        "lo": b.lo,
                        "hi": b.hi,
                        "is_target": b.is_target,
                        "is_warning": b.is_warning,
                        "valid_from": v[0],
                        "valid_to": v[1],
                        "population": s.population,
                        "source_id": s.source_id,
                        "seq": seq,
                    }
                )
    ctx.write(MART_REFERENCE, pl.DataFrame(rows, schema=MART_REFERENCE.schema()))
    ctx.write(
        MART_REFERENCE_SOURCE,
        pl.DataFrame(
            [{"source_id": k, **v} for k, v in sources.items()], schema=MART_REFERENCE_SOURCE.schema()
        ),
    )
