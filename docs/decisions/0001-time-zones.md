# 0001 — Time zones and local time

**Status:** accepted

## Context
`export.xml` renders every instant with the export-time UTC offset, so wall-clock times are wrong in
winter and abroad. HealthKit stores the real zone (`HKTimeZone`) only on workouts and sleep samples.
Daily analyses need correct local dates.

## Decision
- Store every instant in UTC (`*_utc`).
- Build `dim_timezone_period` from `HKTimeZone` evidence: consecutive evidence with the same zone forms a
  period; between periods with different zones the switch is placed at the midpoint of the gap.
- Resolve each row's zone: explicit `HKTimeZone` on the row > inferred period > `time.default_timezone`.
  Record the choice in `tz_source`.
- Derive `*_local` and `local_date` from UTC with that zone (no DST ambiguity in this direction).
- HRV beat times are read in `time.export_timezone` (see source notes), then expressed in the row's zone.

## Consequences
- Daily active energy reconciles with Apple's own daily summaries on the large majority of days,
  noticeably more than with a single fixed zone.
- Long gaps without evidence inherit the surrounding zone; days on a trip without any workout or sleep
  record fall back to the nearest evidence. GPS-based inference could refine this later.
