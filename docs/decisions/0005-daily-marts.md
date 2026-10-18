# 0005 — Daily marts: grain and metric definitions

**Status:** accepted

## Context
Most analyses work per day. Several daily numbers are easy to get subtly wrong: double-counted
sources, the wrong local day, a night split across two dates, averaging decibels, days the Watch was
not worn looking like sedentary days.

## Decision
- `mart_daily` has one row per local calendar day from the first to the last day with data, **without
  gaps**; days without data keep nulls (no imputation). Weekly and monthly marts roll it up.
- Every column is defined once in `src/apple_health/marts/metrics.py` (type, definition, rollup rule).
  Schemas, the data dictionary and the rollups are generated from that registry.
- **Wear:** a local hour is worn when it has at least one Apple Watch heart-rate sample (stand-hour
  records exist for every hour and cannot signal wear). `is_valid_wear_day` = at least
  `marts.valid_day_min_worn_hours` (16) worn hours. Watch-based comparisons should filter on it.
- **Sleep belongs to the day you wake up:** sleep columns describe the primary session ending that
  day; other sessions ending that day are naps. Clock times are hours after the previous midnight
  (`bedtime_h` 23.5 = 23:30, 24.5 = 00:30) so they can be averaged across midnight.
- **HRV:** `hrv_sdnn_ms` averages all of the day's readings (taken at varying activity levels);
  `hrv_sdnn_sleep_ms` averages only readings during that night's sleep and is the comparable series.
  Respiratory rate is taken during sleep as well.
- **Apple daily estimates** (resting HR, walking HR average): the latest estimate of the day.
  VO2max: the day's mean and `vo2max_asof`, the latest estimate on or before the day.
- **Activity totals** come from the priority-resolved `agg_quantity_daily` (no iPhone + Watch double
  counting). **Workouts** recorded by several apps for one session count once (best-ranked source).
- **Sound levels** are energy averages weighted by measurement duration
  (10·log10 of the mean of 10^(L/10)), also when rolling up.
- Rollups never fill missing days; sums come with a `_daily_avg` over days that have a value, and each
  period reports `n_days` and `n_valid_wear_days`.

## Consequences
Column names carry units, so a different canonical unit needs a code change (guarded by the
`mart_units_as_expected` check). Day attribution uses the start time for everything except sleep
(wake-up date) and wrist temperature (end of the night).
