# 0003 — Keys and lineage

**Status:** accepted

## Context
HealthKit records carry no UUID in the export. Keys must be reproducible across runs and across future
exports (which re-render timestamps in a possibly different offset).

## Decision
- Ids are 16-hex-character BLAKE2b digests (Python `hashlib`) of a canonical natural-key string; UTC
  instants are formatted as ISO-8601 so the export's rendering offset does not affect them. `pl.Expr.hash`
  is not used for persisted ids because it is not stable across Polars versions (it is used only for
  in-memory dedup keys).
  - sample: type, raw source name, start, end, raw value, raw unit
  - workout: activity type, raw source name, start, end
  - route: workout id, start, end
- Every curated row keeps lineage: `export_id` and the staging row number (`record_nr`, `workout_nr`).

## Consequences
Ids are stable while Apple keeps the same content; renaming the device changes source-dependent ids.
