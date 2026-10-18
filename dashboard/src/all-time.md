---
title: All time
---

```js
import {pageHeader} from "./components/page.js";
import {DOMAIN_COLOR} from "./components/tile.js";
import {BASE} from "./components/marks.js";
import {num, hm, clock, date, month, signed, compact, pace} from "./components/format.js";
const meta = FileAttachment("data/meta.json").json();
const at = FileAttachment("data/alltime.json").json();
```

```js
const toDate = (s) => new Date(s);
const SPEC = Object.fromEntries(at.specs.map((s) => [s.key, s]));
const fmt = {
  steps: (v) => num(v), active_energy: (v) => num(v), exercise: (v) => num(v), resting_hr: (v) => num(v, 1),
  hrv: (v) => num(v, 1), vo2max: (v) => num(v, 1), respiratory_rate: (v) => num(v, 1), asleep: (v) => hm(v),
  bedtime: (v) => clock(v), training: (v) => num(v, 1), walking_speed: (v) => num(v, 2), daylight: (v) => num(v),
  running: (v) => num(v, 1)
};
const unitOf = (k) => (["asleep", "bedtime"].includes(k) ? "" : SPEC[k]?.unit ?? "");
// Trips of two days or more (shorter periods are mostly time-zone switches at the edges of a stay).
const trips = at.trips.map((t) => ({...t, x1: toDate(t.start), x2: toDate(t.end)})).filter((t) => t.x2 - t.x1 >= 2 * 864e5);
const events = at.events.filter((e) => e.date).map((e) => ({...e, x: toDate(e.date)}));
const totals = Object.fromEntries(at.records.filter((r) => r.kind === "total").map((r) => [r.record_id, r]));
```

${pageHeader({eyebrow: "Since the first day", title: "All time", subtitle: html`From ${date(at.first_day)} to ${date(at.data_through)}: monthly trends, years, records and seasons.`, meta})}

```js
const TOTALS = [
  ["total_steps", "Steps", (v) => compact(v)],
  ["total_distance_km", "Walked and run", (v) => `${num(v)} km`],
  ["total_running_km", "Run", (v) => `${num(v)} km`],
  ["total_workouts", "Workouts", (v) => num(v)],
  ["total_workout_hours", "Training", (v) => `${num(v)} h`],
  ["total_sleep_hours", "Asleep", (v) => `${num(v)} h`],
  ["total_flights", "Floors climbed", (v) => num(v)]
];
display(html`<div class="totals">${TOTALS.filter(([k]) => totals[k]?.value != null).map(([k, label, f]) => html`<div class="total"><span class="total-value">${f(totals[k].value)}</span><span class="total-label">${label}</span></div>`)}</div>`);
```

## Trends

<div class="filters">

```js
const firstYear = new Date(at.first_day).getUTCFullYear();
const lastYear = new Date(at.data_through).getUTCFullYear();
const fromYear = view(Inputs.select(d3.range(firstYear, lastYear + 1), {label: "From", value: firstYear, format: String}));
```

<span class="card-note">monthly values · dashed: long-run trend · shaded: trips abroad · grey band: population reference where one applies</span>
</div>

```js
const from = new Date(Date.UTC(fromYear, 0, 1));
const through = new Date(at.data_through);
// The month the data ends in is usually incomplete.
const partialMonth = new Date(Date.UTC(through.getUTCFullYear(), through.getUTCMonth(), 1));
const KEYS = ["steps", "active_energy", "exercise", "resting_hr", "hrv", "vo2max", "respiratory_rate", "asleep", "bedtime", "training", "running", "walking_speed", "daylight"];

function refRects(key, x0, x1) {
  const ref = SPEC[key]?.reference ? at.references[SPEC[key].reference] : null;
  if (!ref?.length) return [];
  return ref.filter((b) => b.is_target).map((b) => ({x1: new Date(Math.max(+toDate(b.valid_from), +x0)), x2: new Date(Math.min(+toDate(b.valid_to), +x1)), lo: b.lo, hi: b.hi})).filter((r) => r.x1 < r.x2);
}

function trendCard(key, width) {
  const spec = SPEC[key];
  const pts = (at.series[key] ?? []).map((p) => ({date: toDate(p.month_start), value: p.value})).filter((p) => p.date >= from);
  const present = pts.filter((p) => p.value != null);
  const color = DOMAIN_COLOR[spec.domain];
  const x0 = pts[0]?.date ?? from, x1 = new Date(at.data_through);
  const refs = refRects(key, x0, x1);
  const ys = present.map((p) => p.value).concat(refs.flatMap((r) => [r.lo, r.hi]).filter((v) => v != null));
  const plot = present.length < 2 ? html`<p class="card-note">Not enough data in this period.</p>` : Plot.plot({
    ...BASE, width, height: 170, marginLeft: 40, marginTop: 8,
    x: {type: "utc", domain: [x0, x1], ticks: 4},
    y: {domain: d3.extent(ys), nice: true, zero: false, label: null, tickFormat: key === "bedtime" ? (v) => clock(v) : key === "asleep" ? (v) => `${Math.floor(v / 60)}h${String(Math.round(v % 60)).padStart(2, "0")}` : undefined, ticks: 4},
    marks: [
      Plot.rect(trips.filter((t) => t.x2 > x0), {x1: "x1", x2: "x2", fill: "var(--places)", fillOpacity: 0.05}),
      refs.length ? Plot.rect(refs, {x1: "x1", x2: "x2", y1: (d) => d.lo ?? d3.min(ys), y2: (d) => d.hi ?? d3.max(ys), fill: "var(--reference)"}) : null,
      Plot.gridY({stroke: "var(--grid)", ticks: 4}),
      Plot.ruleX(events.filter((e) => e.x > x0), {x: "x", stroke: "var(--border-strong)", strokeDasharray: "2 3"}),
      Plot.linearRegressionY(present, {x: "date", y: "value", stroke: "var(--muted)", strokeDasharray: "5 4", strokeWidth: 1, ci: 0}),
      Plot.line(pts, {x: "date", y: "value", stroke: color, strokeWidth: 1.75}),
      Plot.dot(present.slice(-1), {x: "date", y: "value", r: 3, fill: color}),
      Plot.tip(present, Plot.pointerX({x: "date", y: "value", title: (d) => `${month(d.date)}\n${fmt[key](d.value)} ${unitOf(key)}`}))
    ]
  });
  const last = present.at(-1);
  return html`<div class="card">
    <div class="card-head"><h3 class="card-title">${spec.label}</h3><span class="card-note">${last ? html`<b style="color:var(--ink)">${fmt[key](last.value)}</b> ${unitOf(key)} in ${month(last.date)}${+last.date === +partialMonth ? " so far" : ""}` : ""}</span></div>
    ${plot}
  </div>`;
}
display(html`<div class="grid grid-cols-3">${KEYS.filter((k) => SPEC[k]).map((k) => resize((width) => trendCard(k, width)))}</div>`);
```

<p class="source">Milestones (dotted lines): ${events.map((e) => `${e.label} from ${month(e.x)}`).join(" · ")}. Months need 10 days with data (Watch-based series: 10 days with the Watch worn).</p>

## Year by year

```js
const YCOLS = [
  ["steps_daily_avg", "Steps/day", (v) => num(v), "higher"],
  ["active_energy_kcal_daily_avg", "Active kcal/day", (v) => num(v), "higher"],
  ["exercise_min_per_week", "Exercise min/wk", (v) => num(v), "higher"],
  ["resting_hr_bpm", "Resting HR", (v) => num(v, 1), "lower"],
  ["hrv_sdnn_sleep_ms", "Sleep HRV", (v) => num(v, 1), "higher"],
  ["vo2max", "VO2max", (v) => num(v, 1), "higher"],
  ["sleep_asleep_min", "Asleep", (v) => hm(v), "higher"],
  ["bedtime_h", "Bedtime", (v) => clock(v), null],
  ["workouts", "Workouts", (v) => num(v), "higher"],
  ["training_h", "Training h", (v) => num(v), "higher"],
  ["running_km", "Run km", (v) => num(v), "higher"],
  ["all_rings_closed_days", "Rings days", (v) => num(v), "higher"]
];
function shade(col, v, better) {
  const vals = at.years.map((y) => y[col]).filter((x) => x != null);
  if (v == null || vals.length < 2 || !better) return "";
  const [lo, hi] = d3.extent(vals);
  const t = hi === lo ? 0.5 : (v - lo) / (hi - lo);
  const good = better === "higher" ? t : 1 - t;
  return `background: color-mix(in srgb, var(--good) ${Math.round(good * 22)}%, transparent)`;
}
display(html`<div class="card" style="overflow-x:auto"><table class="t years">
  <thead><tr><th>Year</th><th class="num">Days</th>${YCOLS.map(([, label]) => html`<th class="num">${label}</th>`)}</tr></thead>
  <tbody>${at.years.map((y) => html`<tr><td><b>${y.year}</b></td><td class="num">${y.n_valid_wear_days}<span class="card-note"> / ${y.n_days}</span></td>${YCOLS.map(([col, , f, better]) => html`<td class="num" style="${shade(col, y[col], better)}">${y[col] == null ? "–" : f(y[col])}</td>`)}</tr>`)}</tbody>
</table><p class="source">Days: valid wear days / days in the export. Greener cells are better years for that measure (relative to the other years).</p></div>`);
```

## Then and now

```js
display(html`<div class="card"><table class="t">
  <thead><tr><th>Measure</th><th>First 12 months</th><th class="num">Then</th><th>Last 12 months</th><th class="num">Now</th><th class="num">Change</th></tr></thead>
  <tbody>${at.then_now.map((r) => {
    const d = r.now - r.then;
    const rel = r.then ? (r.now / r.then - 1) * 100 : null;
    const tone = !r.better || Math.abs(rel ?? 0) < 2 ? "" : (d > 0) === (r.better === "higher") ? "good" : "bad";
    const f = fmt[r.key] ?? ((v) => num(v, 1));
    const u = unitOf(r.key) || (r.key === "running" ? "km" : "");
    return html`<tr><td>${r.label}</td><td class="card-note">${month(r.then_from)} – ${month(r.then_to)}</td><td class="num">${f(r.then)} ${u}</td><td class="card-note">${month(r.now_from)} – ${month(r.now_to)}</td><td class="num">${f(r.now)} ${u}</td><td class="num"><span class="chip ${tone}">${r.key === "bedtime" ? `${signed(d * 60)} min` : rel == null ? "–" : `${signed(rel)}%`}</span></td></tr>`;
  })}</tbody></table></div>`);
```

## Records

```js
const REC = at.records.filter((r) => r.kind !== "total" && r.value != null);
const mmss = (sec) => {
  const t = Math.round(sec), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), x = t % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
};
const EFFORT_M = {fastest_1k: 1000, fastest_5k: 5000, fastest_10k: 10000};
function fmtRec(r) {
  if (r.unit === "s") return `${mmss(r.value)} (${pace(r.value / (EFFORT_M[r.record_id] / 1000))})`;
  if (r.unit === "min") return hm(r.value);
  if (r.unit === "days") return `${num(r.value)} days`;
  return `${num(r.value, ["bpm", "steps", "kcal", "TRIMP"].includes(r.unit) ? 0 : 1)} ${r.unit}`;
}
const CAT = {activity: "Activity", heart: "Heart", sleep: "Sleep", training: "Training", running: "Running"};
display(html`<div class="grid grid-cols-3">${Object.entries(CAT).map(([cat, title]) => html`<div class="card">
  <div class="card-head"><h3 class="card-title">${title}</h3></div>
  <table class="t">${REC.filter((r) => r.category === cat).map((r) => html`<tr><td>${r.label}</td><td class="num"><b>${fmtRec(r)}</b></td><td class="num card-note">${r.end_date ? `${date(r.start_date)} – ${date(r.end_date)}` : date(r.start_date)}</td></tr>`)}</table>
</div>`)}</div>`);
```

## Seasons

<p class="card-note">Median month-of-year value across all years (band: lowest to highest year).</p>

```js
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const SKEYS = ["steps", "active_energy", "daylight", "asleep", "resting_hr", "hrv"].filter((k) => at.seasonality[k]);
display(html`<div class="grid grid-cols-3">${SKEYS.map((k) => resize((width) => {
  const rows = at.seasonality[k];
  const color = DOMAIN_COLOR[SPEC[k].domain];
  return html`<div class="card"><div class="card-head"><h3 class="card-title">${SPEC[k].label}</h3></div>${Plot.plot({
    ...BASE, width, height: 150, marginLeft: 40, marginTop: 8,
    x: {domain: d3.range(1, 13), tickFormat: (m) => MONTHS[m - 1], label: null, type: "point"},
    y: {nice: true, zero: false, label: null, ticks: 4, tickFormat: k === "asleep" ? (v) => `${(v / 60).toFixed(1)}h` : undefined},
    marks: [
      Plot.gridY({stroke: "var(--grid)", ticks: 4}),
      Plot.areaY(rows, {x: "month", y1: "min", y2: "max", fill: color, fillOpacity: 0.12}),
      Plot.line(rows, {x: "month", y: "median", stroke: color, strokeWidth: 1.75}),
      Plot.dot(rows, {x: "month", y: "median", r: 2.5, fill: color}),
      Plot.tip(rows, Plot.pointerX({x: "month", y: "median", title: (d) => `${["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][d.month - 1]}: ${fmt[k](d.median)} ${unitOf(k)} (${d.years} years)`}))
    ]
  })}</div>`;
}))}</div>`);
```
