# 0006 — Pouls dashboard and reference bands

**Status:** accepted

## Context
The warehouse needed a readable front end for personal use, and the numbers needed context: is a
resting heart rate of 60 good? The site runs on this computer only, so data never has to leave it,
but some context (map tiles, published norms) comes from outside.

## Decision
- **Static site, thin pages.** Observable Framework in `dashboard/`. Each page has one Python loader
  that calls a tested builder in `apple_health.dashboard`; reusable logic (baselines, TRIMP, runs,
  routes, records, references) lives in the warehouse marts, not in page code. The explorer ships
  `mart_daily` as Parquet and filters in the browser.
- **Any date range.** Each page has a From / To range kept in the address. Loaders ship rows (per
  day, night, session or route) and the page aggregates them for the range; the per-row logic stays
  in the marts. The Overview compares a range with your usual period of the same length.
- **Your normal first.** Charts show a 28-day median and a personal normal range (rolling 10th–90th
  percentile over 90 valid days) before any population reference.
- **References come from `config/references.toml`**, transcribed from the cited publication with its
  citation, URL and a note on how its measurement differs from Apple's. `mart_reference` holds the
  bands that apply to the profile's age and sex, each with `valid_from` / `valid_to`, so bands step
  on birthdays. Two kinds: guideline bands (`range`) and population percentile tables
  (`percentile`). Bands are `lo <= v < hi`; whole-number categories cover the whole unit
  ("12 bpm or less" is `v < 13`). Unit tests pin the transcribed values.
- **No band without a number.** Where a source gives none (Apple's walking steadiness classes) or is
  qualitative (Ohayon 2004 on stages), the metric has no band and Notes says why.
- **Status colours are earned.** A tile's reference dot is green only for a band the source calls
  recommended or typical and red only for one it calls abnormal or not recommended; everything else
  is neutral (a resting heart rate below 60 is not flagged).
- **Map tiles from OpenStreetMap.** The browser fetches tiles for the visible area while Places or a
  run is open; routes stay local. CARTO basemaps now need an API key; the dark theme inverts the OSM
  layer with a CSS filter instead.
- **Local by default.** `npm run serve` binds to 127.0.0.1; `dist/` and the loader cache contain the
  data and are git-ignored; Framework telemetry is off. Serving to other devices at home is opt-in
  (`npm run serve:lan`): it binds to the home-network address only, never 0.0.0.0, and has no
  authentication, so it is meant for a trusted network.

## Consequences
Rebuilding the warehouse requires clearing the loader cache (`npm run clean`, done by
`scripts/refresh-dashboard.sh`). Without a date of birth only the adult-wide bands apply; without a
biological sex, sex-specific tables are skipped. Changing a reference means editing the TOML and the
pinned test values together.
