# Pouls: Apple Health → Parquet, dashboards and a coach

Turn your Apple Health export into something you can use: a local data warehouse, a dashboard site
to read it, and an AI coach that works from it. Everything runs on your own computer.

1. **The pipeline** turns an Apple Health export (`export.xml` + `workout-routes/*.gpx`) into
   validated, analytics-ready Parquet tables with Python, uv and Polars. Layers in `warehouse/`:
   `staging` (lossless copy of the source) → `curated` (cleaned, keyed, correct local times) →
   `derived` (priority-resolved aggregates, sleep sessions, coverage) → `marts` (one row per day,
   week or month, plus analytics tables for the dashboards and the coach).
2. **The dashboards (Pouls)** are a local Observable Framework site over the marts: an overview of
   any period against your usual one, all-time trends and records, and pages for activity, heart,
   sleep, training, workouts, running and places (routes on a map). Where a published reference
   exists (VO2max for your age and sex, recommended sleep, WHO activity guidelines…), charts show it
   next to your own normal range. [More below](#dashboard-pouls).
3. **The coach (Pouls Coach)** is Claude, in Claude Code or Claude Desktop, acting as a lifestyle and
   sports coach. A local MCP server gives it summaries of your history and a journal on this
   computer (goals, habits, check-ins, weekly plans). Results are redacted first, so places, routes,
   time zones, device names and your identity never reach it. [More below](#coach-pouls-coach).

Docs: tables and columns in [`docs/data_dictionary.md`](docs/data_dictionary.md) (generated), the
export quirks the pipeline handles in [`docs/source_notes.md`](docs/source_notes.md), and the
design decisions in [`docs/decisions/`](docs/decisions/).

**How this was built.** Development was sped up with [Claude Code](https://claude.com/claude-code).
Since it is a personal project built quickly, we did not bother to separate the data engineering side
from the analytics side: the pipeline, the marts, the dashboard data builders and the coach live in
one Python package (`apple_health`) and one repository, with the dashboard site in `dashboard/`.

## Setup

```bash
uv sync          # Python 3.12, polars, lxml (+ pytest, ruff for development)
uv run pytest    # fast tests on a synthetic mini export
```

Then set `default_timezone` in `config/settings.toml` to your home time zone (an IANA name such as
`Europe/Berlin` or `America/New_York`). It is used for samples the export gives no zone for.

## Running

1. On the iPhone: Health → profile → *Export All Health Data*; unzip `export.zip` into `data/`
   (`data/export.xml`, `data/workout-routes/`). `data/` is git-ignored and never modified.
2. Run everything:

   ```bash
   uv run apple-health all
   ```

   | Command | What it does | Time on a multi-year export |
   |---|---|---|
   | `parse` | raw → `warehouse/staging/` (lossless), source contract + reconciliation | a minute or two |
   | `build` | staging → `warehouse/curated/`, `derived/` and `marts/`, data-quality checks | under a minute |
   | `check` | re-run all data-quality checks on the published warehouse | seconds |
   | `diff` | drift report between the latest two exports | <1 s |
   | `all` | `parse` + `build` + `diff` | a few minutes |
   | `dictionary` | regenerate `docs/data_dictionary.md` | |

   Global options: `--raw-dir`, `--warehouse-dir`, `--config-dir`, `-v`.

A step only publishes its layer when no **error**-level check failed; the previous layer stays in place
otherwise. Exit codes: 0 ok, 1 checks failed, 2 missing input.

## Dropping in a new export

Replace the contents of `data/` with the new unzipped export and run `uv run apple-health all`.
Then read the end of the log and the drift report:

- **Errors** (nothing published) usually mean Apple changed the format: a new export version, a unit
  without a known conversion, unparsable timestamps. Inspect, adapt the code or `config/`, re-run.
  A new export version must be acknowledged by updating `source.expected_export_version`.
- **Warnings** (published) flag suspicious data: unknown types or attributes (add them to
  `config/types.toml` / `config/metadata_keys.toml`), outlier rates, failed reconciliations.
- **Drift report**: new/removed types, units, sources, metadata keys, and samples that vanished from
  history compared with the previous export.

Results are kept in `warehouse/_meta/`: `runs/` (manifests with checksums and row counts), `dq/` (one
Parquet file of check results per run), `profiles/` and `snapshots/` (per export), `diffs/`.

## Using the data

Start with the daily marts: `marts/mart_daily.parquet` has one row per local day (no gaps) with
activity, rings, heart, sleep of the night ending that day, workouts, sound exposure and gait;
`mart_weekly` / `mart_monthly` roll it up. Filter on `is_valid_wear_day` for Watch-based comparisons.
Metric definitions: `src/apple_health/marts/metrics.py` and `docs/decisions/0005-daily-marts.md`.

```python
import polars as pl

daily = pl.read_parquet("warehouse/marts/mart_daily.parquet").filter(pl.col("is_valid_wear_day"))
trend = daily.select("local_date", "resting_hr_bpm", "hrv_sdnn_sleep_ms", "sleep_asleep_min", "steps")

wh = "warehouse"
hr = (
    pl.scan_parquet(f"{wh}/curated/fct_quantity_sample", hive_partitioning=True)
    .filter(pl.col("type") == "HeartRate")
    .collect()
)
steps = pl.read_parquet(f"{wh}/derived/agg_quantity_daily.parquet").filter(pl.col("type") == "StepCount")
```

The same files can be queried from DuckDB, e.g.
`SELECT * FROM read_parquet('warehouse/curated/fct_quantity_sample/*/*.parquet', hive_partitioning = true)`.

## Dashboard (Pouls)

A local dashboard site over the warehouse, built with Observable Framework (`dashboard/`; decision in
[`docs/decisions/0006-dashboard-and-references.md`](docs/decisions/0006-dashboard-and-references.md)).
It runs on this computer only.

Pages: **Overview** (a period against your usual period of the same length), **All time**,
**Activity**, **Heart**, **Sleep**, **Training**, **Workouts** (pick a kind of workout, e.g. indoor
cycling, and open any session), **Running** (with a run detail map), **Places**
(every GPS route on a map), **Every day** (filter, chart and download any daily metric) and
**Notes** (definitions, reference bands and their sources, coverage, what is not shown).

```bash
scripts/refresh-dashboard.sh   # apple-health all, clear the loader cache, build the site
cd dashboard
npm install          # once (Node 18+)
npm run dev          # live preview on http://127.0.0.1:3000
npm run build        # static site in dashboard/dist/ (+ checks)
npm run serve        # serve dist/ on http://127.0.0.1:3001 (pages always re-checked, assets cached)
npm run serve:lan    # serve dist/ to other devices on the home network (prints the address)
npm run clean        # drop cached loader output after rebuilding the warehouse
```

**Other devices at home.** `npm run serve:lan` (or `scripts/refresh-dashboard.sh --lan`) binds to
this machine's Wi-Fi or Ethernet address only, not to VPN or Tailscale interfaces, and prints the
link to open on a phone or tablet on the same network (bookmark it). There is no password, so use it
on your own network and stop it with Ctrl+C when done. To reach it through a VPN such as Tailscale instead,
pass this machine's address on that network: `npm run serve:lan -- --host 100.x.y.z`.

If the other device cannot load the page, check in this order:

1. **Same network.** The device is on the home Wi-Fi, not mobile data or a guest network.
2. **Firewall.** `sudo ufw status`; if it is active, allow the port for the local network only:
   `sudo ufw allow from 192.168.0.0/24 to any port 3001 proto tcp` (use your own subnet).
3. **VPN.** A VPN client can block incoming local connections. Look for a "local network sharing"
   or "allow LAN" setting in the client and turn it on.
4. **Router.** "AP isolation" or "client isolation" stops Wi-Fi devices from reaching each other;
   turn it off for the home network.
5. **Address changed.** The router can hand out a new address; the script prints the current one.
   A DHCP reservation in the router keeps the bookmark stable.
6. **Works in one browser, not another.** The other browser kept a page from before a rebuild
   (older versions of the server did not ask browsers to re-check pages). Reload it once
   with Ctrl+Shift+R, or clear the site's data for that address.

Every page has a date range (presets or From / To, kept in the address bar). The Overview compares
each tile with your usual period of the same length. Map areas are named after nearby cities from
GeoNames (CC BY 4.0): `scripts/fetch-place-names.sh` downloads the public list once into the
git-ignored `reference/` folder (the refresh script does it when missing); without it areas keep
time-zone names.

Loaders (`dashboard/src/data/*.py`) call `apple_health.dashboard.*` with the repository's `.venv`;
`APPLE_HEALTH_WAREHOUSE` points them at another warehouse. `dist/` and the loader cache contain your
data and are git-ignored. Framework telemetry is disabled in the npm scripts. The only requests that
leave the computer while browsing are OpenStreetMap map tiles for the area shown on Places and in the
run detail; npm packages and the GeoNames city list are downloaded at build time.

Reference bands (population norms and guidelines, by age and sex from the Health profile) come from
`config/references.toml`, which cites each source; the build turns them into `mart_reference`. They
help read the numbers; they are not medical advice.

## Coach (Pouls Coach)

An AI lifestyle and sports coach in Claude Code, working from your history and a journal kept on this
computer (decision: [`docs/decisions/0007-coach.md`](docs/decisions/0007-coach.md); the coaching
method: [`src/apple_health/coach/method.md`](src/apple_health/coach/method.md)).

**Start.** Open this project in Claude Code. It offers to enable the `pouls-coach` MCP server from
`.mcp.json` (it runs `uv run apple-health-coach`); accept, then:

| Command | What happens |
|---|---|
| `/coach` | a coaching session; the first one is a short interview (goals, health, schedule, what you enjoy, food and sleep), then a first week's plan |
| `/checkin` | two minutes a day: habits kept, weight if you weighed, energy, soreness, sleep; then today's session or an easier one |
| `/review` | once a week, after a fresh export: plan against what happened, habits, weight trend, recovery, next week's plan |

**Weekly routine.** Export from the Health app, run `scripts/refresh-dashboard.sh`, then `/review`.
Between exports, tell the coach how things went in `/checkin`.

**Coach page.** Pouls has a Coach page (plan, habits, weight, check-ins). Served by `npm run serve` or
`npm run serve:lan`, it reads the journal live, so it is current on your phone.

**What reaches Claude.** Only what the coach's tools return during a conversation: summaries and
workout details (heart rate per minute, zones, splits). Never GPS, routes, areas or time zones (just
"away from home"), device or app names (just their kind), your name or date of birth (just your age).
`src/apple_health/coach/redact.py` enforces this and is tested. The journal is
`coach/journal.sqlite` (git-ignored).

**Claude Desktop** (macOS, Windows) can use the same server: add to its MCP configuration
`{"mcpServers": {"pouls-coach": {"command": "uv", "args": ["--directory", "/path/to/apple_health",
"run", "apple-health-coach"]}}}`; the commands appear there as prompts.

The coach is not a doctor: it says so, tells you to seek care for warning signs and to see a GP
before raising intensity if anything in your health calls for it.

## Configuration (`config/`)

| File | Purpose |
|---|---|
| `settings.toml` | paths, default / export time zone, source priority, thresholds (incl. valid wear day) |
| `types.toml` | HealthKit type registry: canonical unit, aggregation (cumulative / discrete), plausible range, category labels, workout-statistic columns |
| `metadata_keys.toml` | metadata unit normalisation and keys promoted to typed columns |
| `references.toml` | reference bands for the dashboard: values, populations, age and sex groups, citations |
| `settings.toml` `[coach]` | where the coach's journal lives |

## Privacy

The export contains health data, the owner's name (in device names), date of birth, Bluetooth
identifiers and GPS tracks. `data/` and `warehouse/` are git-ignored; test fixtures are synthetic.
Curated tables strip the owner's name from source/device names (enforced by a check) and drop device
identifiers; the raw names remain in staging and `dim_source.source_name_raw`. `dim_profile` and
`fct_route_point` are the most sensitive tables.

## Development

```bash
uv run pytest                    # unit + integration tests (synthetic fixture)
uv run pytest -m real_data       # smoke test on the real export in data/ (a few minutes)
uv run pytest -m dashboard       # builds the dashboard against the fixture (needs dashboard/node_modules)
uv run ruff check . && uv run ruff format --check .
```

Package layout: `parse/` (XML/GPX → staging), `transform/` (curated + derived), `marts/` (metric
registry, daily and analytics marts, references), `dashboard/` (page data builders), `quality/`
(contract, reconciliation, checks, drift), `schemas.py` (table definitions), `build.py` /
`pipeline.py` (steps).

Adding a daily metric: add a `Metric` to `marts/metrics.py` (definition + rollup rule), compute it in
`marts/daily.py`, run `uv run apple-health dictionary`; weekly/monthly columns follow automatically.

## Licence

MIT, see [`LICENSE`](LICENSE). The bundled Inter font is under the SIL Open Font Licence
(`dashboard/src/fonts/OFL.txt`).
