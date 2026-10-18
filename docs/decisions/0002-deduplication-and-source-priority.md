# 0002 — Deduplication and overlapping sources

**Status:** accepted

## Context
The export contains exact duplicate records, rewrites of the same observation, and legitimately
overlapping data from several sources (iPhone and Watch both count steps).

## Decision
1. Drop exact duplicates (all attributes equal, device memory pointer ignored).
2. Collapse rewrites — same type, source, start, end, value and unit — keeping the latest `creationDate`;
   `dup_count` records how many raw rows were collapsed.
3. Never delete overlapping data from *different* sources in curated tables. Flag it instead
   (`is_priority_source`, per type and local hour) and resolve it only in derived aggregates: for
   cumulative types the hour's value comes from the best-ranked source(s) present
   (`sources.priority`, then source kind). The naive all-sources sum is kept next to it.
4. Overlapping workouts are kept and linked (`overlaps_workout_id`).

## Consequences
Curated facts stay faithful to the source; correctness traps are solved once in the derived layer.
Hour-level priority can undercount when the Watch was worn for only part of an hour while the iPhone
recorded the rest; analyses needing more precision can work from the flagged samples.
