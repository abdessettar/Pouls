---
title: Notes
---

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {num, pct, hm, date, month, plural} from "./components/format.js";
const meta = FileAttachment("data/meta.json").json();
const N = FileAttachment("data/notes.json").json();
```

```js
const D = (s) => new Date(s);
const through = D(meta.data_through);
const S = N.settings;
const SRC = new Map(N.reference_sources.map((s) => [s.source_id, s]));
// How to read each reference metric: label, unit and number format.
const REF = {
  vo2max: ["VO2max", "mL/kg/min", (v) => num(v, 1)],
  resting_hr: ["Resting heart rate", "bpm", (v) => num(v)],
  hrv_sdnn: ["HRV (SDNN)", "ms", (v) => num(v)],
  hr_recovery: ["Heart-rate recovery, 1 min", "bpm", (v) => num(v)],
  respiratory_rate: ["Breathing rate", "/min", (v) => num(v)],
  spo2: ["Blood oxygen", "", (v) => pct(v)],
  sleep_duration: ["Time asleep", "", (v) => hm(v)],
  sleep_efficiency: ["Sleep efficiency", "", (v) => pct(v)],
  deep_sleep_share: ["Deep sleep share", "", (v) => pct(v)],
  rem_sleep_share: ["REM sleep share", "", (v) => pct(v)],
  exercise_minutes_week: ["Exercise minutes per week", "min", (v) => num(v)],
  vigorous_minutes_week: ["Vigorous minutes per week", "min", (v) => num(v)],
  steps: ["Steps per day", "", (v) => num(v)],
  walking_speed: ["Walking speed", "km/h", (v) => num(v, 2)],
  double_support: ["Double support time", "", (v) => pct(v)],
  training_load_ratio: ["Acute to chronic load", "", (v) => num(v, 2)]
};
const ORDER = Object.keys(REF);
const fmtRange = (m, b) => {
  const [, u, f] = REF[m] ?? ["", "", (v) => num(v, 1)];
  const s = b.lo == null ? `below ${f(b.hi)}` : b.hi == null ? `${f(b.lo)} or more` : `${f(b.lo)} to ${f(b.hi)}`;
  return u ? `${s} ${u}` : s;
};
const current = N.references.filter((b) => D(b.valid_from) <= through && D(b.valid_to) >= through);
const sets = d3.groups(current, (b) => b.metric, (b) => `${b.kind}|${b.source_id}`)
  .sort((a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]));
const earlier = N.references.filter((b) => D(b.valid_to) < through);
```

${pageHeader({eyebrow: "Definitions and sources", title: "Notes", subtitle: "How the figures are made, which references they are read against, and what is not shown.", meta})}

<div class="card">
<div class="card-head"><h3 class="card-title">Not medical advice</h3></div>

Pouls summarises what an Apple Watch and an iPhone recorded. Consumer sensors estimate heart rate, sleep stages, VO2max and blood oxygen, and those estimates have errors. References come from published populations whose measurements differ from Apple's, so they are a guide for reading the numbers, not a diagnosis. Talk to a doctor about anything that worries you, and do not change treatment because of a chart here.

</div>

## References

```js
display(html`<p class="insight">Bands for the age and sex in the Health profile on ${date(meta.data_through)}. ${earlier.length ? html`Age-specific bands change on birthdays; the charts use the band that applied on each date (${plural(d3.groups(earlier, (b) => `${b.metric}|${b.valid_from}`).length, "earlier band set")}).` : ""} Green marks the recommended or typical band, red one the source calls abnormal or not recommended.</p>`);
```

```js
const chip = (b) => (b.is_target ? html`<span class="chip ref"><span class="swatch" style="background:var(--good);width:7px;height:7px;border-radius:50%"></span>${b.label}</span>` : b.is_warning ? html`<span class="chip ref"><span class="swatch" style="background:var(--bad);width:7px;height:7px;border-radius:50%"></span>${b.label}</span>` : html`<span class="chip ref">${b.label}</span>`);
function setRow(metric, bands) {
  const b0 = bands[0];
  const src = SRC.get(b0.source_id);
  const [label] = REF[metric] ?? [metric];
  const body = b0.kind === "percentile"
    ? html`<span class="card-note">percentiles:</span> ${bands.filter((b) => b.lo != null).map((b) => html`<span class="pctl"><b>${b.band.match(/p(\d+)/)[1]}th</b> ${REF[metric]?.[2](b.lo) ?? b.lo}</span>`)}${REF[metric]?.[1] ? html` <span class="card-note">${REF[metric][1]}</span>` : ""}`
    : html`${bands.map((b) => html`<div class="band-row">${chip(b)}${/\d/.test(b.label) ? "" : html` <span class="card-note">${fmtRange(metric, b)}</span>`}</div>`)}`;
  return html`<tr>
    <td><b>${label}</b><div class="card-note">${b0.kind === "percentile" ? "population percentiles" : "guideline"}</div></td>
    <td>${body}</td>
    <td class="card-note">${b0.population}</td>
    <td><a href="${src?.url}" target="_blank" rel="noopener">${src?.short ?? b0.source_id}</a></td>
  </tr>`;
}
display(current.length ? html`<div class="card" style="overflow-x:auto"><table class="t refs">
  <thead><tr><th>Metric</th><th>Bands</th><th>Population</th><th>Source</th></tr></thead>
  <tbody>${sets.flatMap(([metric, groups]) => groups.map(([, bands]) => setRow(metric, bands)))}</tbody>
</table></div>` : html`<div class="card"><p class="card-note">No reference bands: the Health profile has no date of birth, or the warehouse was built without config/references.toml.</p></div>`);
```

<div class="card">
<div class="card-head"><h3 class="card-title">Sources</h3><span class="card-note">how each was measured, and how that compares with Apple's measurement</span></div>

```js
display(html`<div class="sources">${N.reference_sources.map((s) => html`<div class="source-row"><div class="source-short">${s.short}</div><div>${s.citation} <a href="${s.url}" target="_blank" rel="noopener">${s.url.replace(/^https:\/\//, "")}</a><div class="card-note">${s.note}</div></div></div>`)}</div>`);
```

<p class="card-note" style="margin-top:14px"><b>Also used:</b> map tiles from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors (fetched while a map is on screen) and place names from <a href="https://www.geonames.org/" target="_blank" rel="noopener">GeoNames</a> (CC BY 4.0, downloaded once by scripts/fetch-place-names.sh).</p>

</div>

## Definitions

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Days, wear and sources</h3></div>

- **Day.** A local calendar day, in the time zone the data was recorded in. A night belongs to the day you wake up.
- **Watch worn.** Hours of the day with at least one Watch heart-rate reading. A **valid wear day** has ${S.valid_day_min_worn_hours} or more; activity averages and personal baselines use valid days only, so days with the Watch off do not drag them down.
- **One value per hour.** When the Watch and the iPhone both count steps or energy in the same hour, only the higher-priority source counts (the order is under Sources and devices). Totals therefore match the Health app, not the sum of both devices.
- **Workouts that count.** A session recorded by two apps (the Watch and a gym app, say) counts once: the copy from the higher-priority source, normally the Watch.
- **Home and away.** Home is ${S.default_timezone}. A day is away when most of its readings carry another time zone; trips are the periods spent in another zone.

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Your normal</h3></div>

- **Date ranges.** Every page has its own From / To range, kept in the address bar so a reload or a link keeps it. Monthly charts include every month the range touches; rolling medians and normal ranges are computed over the whole history first, then cut to the range.
- **Your usual period (Overview).** Each tile is compared with the median of the same measure over every period of the same length in your history, since that measure began: your usual 28 days, your usual year. A plain median of days would say little for totals: the median week of running is zero.
- **28-day median.** The line on most charts: the median of the last ${S.rolling_long_days} days with a value.
- **Your normal range.** The shaded band: the 10th to 90th percentile of the last ${S.normal_range_days} valid days. A value outside it is unusual for you, not necessarily for anyone else.
- **Baseline and strain.** Each day is compared with the mean and spread of the previous ${S.baseline_days} days (at least ${S.baseline_min_days}). A strained day has HRV ${S.strain_z} standard deviation or more below baseline and resting heart rate ${S.strain_z} or more above.
- **Change chips.** The range against your usual period of the same length. Grey means the change is below a small fixed threshold for that metric.

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Heart and sleep</h3></div>

- **Resting heart rate, walking heart rate, VO2max** are Apple's own daily estimates. VO2max comes from outdoor walks, runs and hikes; days without one carry the last estimate forward where noted.
- **HRV in sleep.** The mean of the Watch's SDNN readings inside each night's sleep window. Apple takes these as short readings, so they run differently from 5-minute clinical recordings.
- **Heart-rate recovery.** Apple's one-minute drop after a workout, matched to the workout that ended just before.
- **Time asleep** excludes awake time. **Sleep efficiency** is asleep / (asleep + awake) on nights with stages; before stages (watchOS 9) it is asleep time over the session span. Nights with only "in bed" data have no asleep time.
- **Stage shares** (deep, REM, core) are shares of time asleep. Apple's deep stage corresponds to N3 in sleep studies.
- **Bedtime** is stored as hours after the previous midnight (00:30 is 24.5, so bedtimes sort in order across midnight) and **wake-up** as hours after midnight; both are shown as clock times.

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Training and places</h3></div>

- **Kinds of workout** (Workouts page) are Apple's activity types; walking, running and cycling are split into indoor and outdoor, as the Watch records them. Weather is shown for outdoor kinds only: Apple stores it for every workout.
- **Session heart rate** is the mean of all heart-rate readings in each minute of the workout, from every device that recorded one.
- **Heart-rate zones** are Apple's personal zones from the workout. **Vigorous minutes** are minutes in zones 4 and 5.
- **TRIMP (Edwards).** Minutes in zones 1 to 5 weighted ${S.zone_weights.join(", ")}; a workout without zones adds no load.
- **Acute to chronic ratio.** Mean daily TRIMP over ${S.acute_days} days divided by the mean over ${S.chronic_days} days.
- **Late workout.** A counted workout that ended less than ${S.late_workout_hours} hours before bedtime.
- **Best efforts.** The fastest 1, 5 and 10 km inside a run, from GPS after removing jumps, so they can be faster than the run's average pace.
- **Areas.** Routes whose centres lie within ${S.area_cluster_km} km of each other, named after the nearby city that best combines size and closeness (GeoNames cities with 15,000+ people).
- **Temperature outdoors** (Every day). The mean of Apple's weather at the start of the day's outdoor walks, runs, rides and hikes; days without one have none.

</div>
</div>

## Coverage

<div class="card">
<div class="card-head"><h3 class="card-title">What was recorded, month by month</h3><span class="card-note">darker = more days of the month have it</span></div>

```js
const cov = N.coverage.map((d) => ({...d, date: D(d.month)}));
display(resize((width) => Plot.plot({
  ...BASE, width, height: N.coverage_families.length * 22 + 40, marginLeft: 130,
  x: {type: "utc", label: null},
  y: {domain: N.coverage_families, label: null},
  marks: [
    Plot.rect(cov.filter((d) => d.share > 0), {x1: "date", x2: (d) => d3.utcMonth.offset(d.date, 1), y: "family", fill: "var(--sleep)", fillOpacity: (d) => 0.1 + 0.9 * d.share, inset: 0.5}),
    Plot.tip(cov.filter((d) => d.share > 0), Plot.pointer({x1: "date", x2: (d) => d3.utcMonth.offset(d.date, 1), y: "family", title: (d) => `${d.family}\n${month(d.date)}: ${pct(d.share)} of days`}))
  ]
})));
```

<p class="source">An iPhone counts steps on its own; heart, sleep stages and blood oxygen start when a Watch is worn.</p>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Sources and devices</h3><span class="card-note">in priority order</span></div>

```js
display(html`<table class="t"><thead><tr><th>Source</th><th>Kind</th><th class="num">Records</th><th>From</th><th>To</th></tr></thead><tbody>
  ${N.sources.map((s) => html`<tr><td>${s.source_name}</td><td class="card-note">${s.source_kind.replace("_", " ")}</td><td class="num">${s.records ? num(s.records) : "–"}</td><td class="card-note">${s.first ? month(s.first) : ""}</td><td class="card-note">${s.last ? month(s.last) : ""}</td></tr>`)}
</tbody></table>`);
display(html`<p class="card-note" style="margin-top:12px">Hardware: ${N.devices.map((d) => `${[d.manufacturer, d.model].filter(Boolean).join(" ")}${d.hardware?.length ? ` (${d.hardware.join(", ")})` : ""}`).join(" · ")}.</p>`);
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">What is not shown</h3><span class="card-note">in the export, but not on these pages</span></div>

```js
display(html`<table class="t"><thead><tr><th>What</th><th class="num">Records</th><th>Why</th></tr></thead><tbody>
  ${N.not_shown.map((r) => html`<tr><td>${r.what}</td><td class="num">${num(r.records)}</td><td class="card-note">${r.why}</td></tr>`)}
</tbody></table>`);
```

<p class="source">No page covers blood pressure, nutrition, ECG or cycle tracking.</p>
</div>
</div>
