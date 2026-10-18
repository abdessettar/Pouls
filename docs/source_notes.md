# Apple Health export — source notes

Facts about the export format that the pipeline relies on, verified against a real export
(HealthKit export version 17). Keep this file current when a new export
teaches something new. No personal values are recorded here.

## Files

| File | Use |
|---|---|
| `export.xml` | Primary source (HealthKit XML with an internal DTD). |
| `workout-routes/*.gpx` | GPS tracks of workouts (GPX 1.1, one `trk`/`trkseg` per file). |
| `export_cda.xml` | HL7 CDA rendering of 5 vital-sign types. Exact subset of `export.xml` (per-type counts identical): **not ingested**. |

## Structure

- Top-level elements present: `ExportDate`, `Me`, `Record`, `Workout`, `ActivitySummary`, `Audiogram`.
  The DTD also declares `Correlation`, `ClinicalRecord` and `VisionPrescription`, which are absent here;
  if they appear they are kept verbatim in `stg_other_element` and reported.
- Records have **no UUID**: identity is content-based (see `docs/decisions/0003-keys-and-lineage.md`).
- `Record` elements nested in `Workout` (effort scores) **duplicate** top-level records (every one of them). They are
  only used for `bridge_workout_sample`.
- Export v17 `Workout` elements have no `totalDistance` / `totalEnergyBurned` attributes; totals live in
  `WorkoutStatistics`.
- `WorkoutActivity` (intervals) is the only element with a `uuid`.

## Time

- **Every timestamp is rendered with the device's UTC offset at export time** (e.g. `+0200` on
  every record, including January). The instant is correct (GPX UTC times match route start/end), the
  wall clock is not. Local times are reconstructed from `HKTimeZone` metadata (workouts, sleep) and an
  inferred time-zone timeline (`docs/decisions/0001-time-zones.md`).
- **HRV beat times** (`InstantaneousBeatsPerMinute/@time`, `HH:MM:SS,cc`, comma decimal, no date) are
  rendered in the **export device's zone with its DST rules**, not the zone of the measurement. Proof:
  on trips to a zone without DST, every beat was off by exactly the offset difference while the export
  zone was on summer time, and none otherwise. Configured as `time.export_timezone`; a check verifies it reproduces the export offset.
- GPX `<time>` values are UTC (`…Z`). GPX **file names** encode the route's *end* time in local
  wall-clock at minute resolution, so two routes ending in the same minute collide: one file is lost
  in the export and both `WorkoutRoute`s reference the remaining one (rare).
- `ActivitySummary/@dateComponents` is a local calendar date.
- `creationDate` can be years after `endDate` (backfilled data) and occasionally before `startDate`.

## Values and units

- Exactly one unit per record type in this export (checked by the source contract).
- HealthKit `%` record values are **fractions** (OxygenSaturation 0.97).
- Metadata values embed units as text: `"101.3 kPa"`, `"68.5 degF"`, `"1000 cm"`, `"376.5 s"`,
  `"1.6 kcal/hr·kg"` (note `·`), JEFIT durations as `H:MM:SS`.
- `HKWeatherHumidity` is exported in hundredths of a percent (`"10000 %"` = 100 %).
- GPX extension sentinels: `course = -1`, `vAcc = -1` (invalid altitude).
- `appleMoveTime` is always 0 (energy-based move goal).

## Names and devices

- The Watch's source name is "<owner>’s Apple Watch" with a **U+2019 apostrophe and a no-break space
  (U+00A0) inside "Apple Watch"**. Names are whitespace-normalised before the owner prefix is stripped.
- `device` is a serialized `HKDevice` description containing a **memory pointer that differs between
  exports** and, for Bluetooth devices, a MAC address / `localIdentifier`. Both are dropped from curated
  tables; software/firmware versions are kept per sample.
