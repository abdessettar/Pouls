"""Deterministic surrogate keys.

``pl.Expr.hash`` is not stable across Polars versions, so keys are BLAKE2b digests of a canonical
string computed with ``hashlib``: the same content yields the same id in every run and export.
"""

from __future__ import annotations

from hashlib import blake2b

import polars as pl

_NULL = "\x00"
_SEP = "\x1f"


def iso_utc(col: str | pl.Expr) -> pl.Expr:
    """Canonical string for a UTC datetime column (independent of the export's rendering offset)."""
    e = pl.col(col) if isinstance(col, str) else col
    return e.dt.strftime("%Y-%m-%dT%H:%M:%S%.6fZ")


def key_string(*parts: str | pl.Expr) -> pl.Expr:
    exprs = [(pl.col(p) if isinstance(p, str) else p).cast(pl.String).fill_null(_NULL) for p in parts]
    return pl.concat_str(exprs, separator=_SEP)


def _digest(values: pl.Series) -> pl.Series:
    return pl.Series(
        values.name,
        [blake2b(v.encode(), digest_size=8).hexdigest() for v in values.to_list()],
        dtype=pl.String,
    )


def stable_id(*parts: str | pl.Expr) -> pl.Expr:
    """16-hex-char id from the given columns/expressions (strings; use ``iso_utc`` for datetimes)."""
    return key_string(*parts).map_batches(_digest, return_dtype=pl.String)


def hash_text(text: str) -> str:
    return blake2b(text.encode(), digest_size=8).hexdigest()
