# 0004 — Layers, full rebuilds and publishing

**Status:** accepted

## Decision
- `data/` is read-only. `staging/` is a lossless string mirror of the source (parsing the multi-GB XML is
  the slow step and is isolated from all modelling decisions). `curated/` holds all decisions;
  `derived/` a few conformed aggregates.
- Each export is a full snapshot, so each run is a full rebuild (a few minutes for a multi-year export).
- A run writes into `warehouse/.tmp/<run_id>/` and renames finished layers into place only when no
  error-level data-quality check failed; the previous layer stays intact otherwise.
- Every build writes an export profile and an id snapshot to `_meta/`; `diff` compares exports.

## Consequences
Simple, idempotent operation; no incremental state to corrupt. Peak memory of the build is a few GB for
an export of a few million samples.
