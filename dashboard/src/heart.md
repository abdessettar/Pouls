---
title: Heart
---

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {bandChart, referenceMarks, latest} from "./components/band.js";
import {num, pct, date, month, plural} from "./components/format.js";
import {rangePicker, within, describe} from "./components/range.js";
const meta = FileAttachment("data/meta.json").json();
const H = FileAttachment("data/heart.json").json();
const HOURLY = FileAttachment("data/hourly.json").json();
```

```js
const D = (s) => new Date(s);
const refs = H.references;
const refNow = (key, day) => (refs[key] ?? []).filter((b) => D(b.valid_from) <= day && D(b.valid_to) >= day);
const hit = (value) => (b) => (b.lo == null || value >= b.lo) && (b.hi == null || value < b.hi);
// Where a value sits: the population percentile when there is a table, else the guideline band.
const where = (key, value, day, kind) => {
  const rows = refNow(key, day);
  const of = (k) => rows.filter((b) => (b.kind === "percentile") === (k === "percentile")).find(hit(value));
  return kind ? of(kind) : of("percentile") ?? of("range");
};
const through = D(meta.data_through);
```

${pageHeader({eyebrow: "Cardio fitness and recovery", title: "Heart", subtitle: "Resting heart rate, HRV, VO2max and recovery, against my own normal and population references.", meta})}

```js
const r = view(rangePicker({first: meta.first_day, last: meta.data_through, value: "2 years"}));
```

```js
// Rolling medians and normal ranges are computed over the whole history, then cut to the range.
const series = Object.fromEntries(Object.entries(H.series).map(([k, rows]) => [k, rows.filter((d) => within(r, d.d))]));
const end = D(r.to);
function insight(key, refKey, unit, f, better) {
  const l = latest(series[key]);
  if (!l) return "";
  const pctBand = refKey ? where(refKey, l.m, D(l.d), "percentile") : null;
  const range = refKey ? where(refKey, l.m, D(l.d), "range") : null;
  const u = unit ? ` ${unit}` : "";
  return html`28-day median on ${date(l.d)}: <b>${f(l.m)}${u}</b>; your normal then (previous 90 days) was ${f(l.lo)} to ${f(l.hi)}${u}.${pctBand ? html` Population: <b>${pctBand.label.toLowerCase()}</b> (${pctBand.population}).` : ""}${range ? html` Reference range: <b>${range.label}</b> (${range.population}).` : ""}`;
}
```

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Resting heart rate</h3><span class="card-note">bpm · line: 28-day median · band: your normal</span></div>
<p class="insight">${insight("resting_hr", "resting_hr", "bpm", (v) => num(v))}</p>

```js
display(resize((width) => bandChart(series.resting_hr, {width, color: "var(--heart)", unit: "bpm", refs: refs.resting_hr})));
```

<p class="source">Apple's daily resting heart rate estimate. Lower is generally better for cardiovascular fitness.</p>
<p class="how"><b>How to read.</b> Each dot is a day, the line the 28-day median and the shaded band your normal range. Grey bands are population references. A line drifting down over months usually means better fitness; a rise lasting a few days often comes with illness, poor sleep, alcohol, heat or hard training.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Heart-rate variability during sleep</h3><span class="card-note">SDNN, ms</span></div>
<p class="insight">${insight("hrv", "hrv_sdnn", "ms", (v) => num(v))}</p>

```js
display(resize((width) => bandChart(series.hrv, {width, color: "var(--sleep)", unit: "ms", refs: refs.hrv_sdnn})));
```

<p class="source">Mean of the Watch's SDNN readings during each night's sleep. HRV is very individual: compare with your own normal first. Published norms come from 5-minute clinical recordings, so the reference band is only indicative for the Watch's shorter readings.</p>
<p class="how"><b>How to read.</b> Higher is generally better, and single nights jump around, so follow the line rather than the dots. Several nights below your band suggest your body is under strain (illness, short sleep, alcohol, hard training); a line rising over months goes with better recovery and fitness.</p>
</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">VO2max</h3><span class="card-note">mL/min·kg · dots: estimates · line: 90-day median</span></div>

```js
// The 90-day median uses estimates before the range too, so the line starts at its true value.
const voAll = H.vo2max.map((x) => ({...x, date: D(x.d)}));
const voLineAll = voAll.map((x) => ({date: x.date, d: x.d, m: d3.median(voAll.filter((y) => y.date <= x.date && y.date > new Date(+x.date - 90 * 864e5)), (y) => y.v)}));
const vo = voAll.filter((x) => within(r, x.d));
const voLine = voLineAll.filter((x) => within(r, x.d));
const voLast = voLine.at(-1);
const voBand = voLast ? where("vo2max", voLast.m, voLast.date) : null;
display(html`<p class="insight">Latest 90-day median <b>${num(voLast?.m, 1)}</b>${voBand ? html`: <b>${voBand.label.toLowerCase()}</b> (${voBand.population})` : ""}.</p>`);
display(vo.length < 2 ? html`<p class="card-note">No VO2max estimates in this range.</p>` : resize((width) => {
  const ys = vo.map((r) => r.v);
  const yDomain = [d3.min(ys) - 2, d3.max(ys) + 2];
  return Plot.plot({
    ...BASE, width, height: 240,
    x: {type: "utc", domain: d3.extent(vo, (r) => r.date)},
    y: {domain: yDomain, label: null},
    marks: [
      ...referenceMarks(refs.vo2max, {x0: vo[0].date, x1: vo.at(-1).date, yDomain}),
      Plot.gridY({stroke: "var(--grid)"}),
      Plot.dot(vo, {x: "date", y: "v", r: 1.8, fill: "var(--heart)", fillOpacity: 0.4}),
      Plot.line(voLine, {x: "date", y: "m", stroke: "var(--heart)", strokeWidth: 1.9}),
      Plot.tip(vo, Plot.pointerX({x: "date", y: "v", title: (r) => `${date(r.d)}\nestimate ${num(r.v, 1)}`}))
    ]
  });
}));
```

<p class="source">Apple estimates VO2max during outdoor walks, runs and hikes. Dotted lines: population percentiles for your age and sex; they step when you change age group.</p>
<p class="how"><b>How to read.</b> Dots are Apple's estimates, the line their 90-day median. A dotted line marks a population percentile: at the 50th, half of people your age and sex score lower. Rising means better aerobic fitness; small changes are within the estimate's noise.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Heart-rate recovery</h3><span class="card-note">bpm drop one minute after a workout</span></div>

```js
const rec = H.recovery.map((x) => ({...x, date: D(x.d)})).filter((x) => x.group !== "unmatched" && within(r, x.d));
const GROUP_COLOR = {walking: "var(--activity)", running: "var(--running)", strength: "var(--strength)", cycling: "var(--cycling)", other: "var(--muted)"};
const recRef = refNow("hr_recovery", end);
const byGroup = d3.rollups(rec, (v) => ({median: d3.median(v, (d) => d.v), n: v.length}), (d) => d.group).sort((a, b) => b[1].n - a[1].n);
display(html`<p class="insight">${byGroup.map(([g, s], i) => html`${i ? " · " : ""}after ${g}: median <b>${num(s.median)} bpm</b> (${s.n})`)}.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 240,
  x: {type: "utc"},
  y: {grid: true, label: null},
  marks: [
    ...recRef.filter((b) => b.hi != null && !b.is_target).map((b) => Plot.rectY([b], {y1: (b) => b.lo ?? 0, y2: "hi", fill: "var(--bad)", fillOpacity: 0.08})),
    ...recRef.filter((b) => b.hi != null && !b.is_target).map((b) => Plot.text([b], {y: "hi", frameAnchor: "left", dy: -6, dx: 4, text: (b) => b.label, fill: "var(--muted)", fontSize: 10.5, textAnchor: "start"})),
    Plot.dot(rec, {x: "date", y: "v", r: 2, fill: (d) => GROUP_COLOR[d.group] ?? "var(--muted)", fillOpacity: 0.55}),
    Plot.lineY(rec, Plot.windowY({k: 30, reduce: "median"}, {x: "date", y: "v", stroke: "var(--ink-2)", strokeWidth: 1.4})),
    Plot.tip(rec, Plot.pointer({x: "date", y: "v", title: (d) => `${date(d.d)} after ${d.group}\n${num(d.v)} bpm drop`}))
  ]
})));
display(html`<div class="legend">${byGroup.map(([g]) => html`<span class="legend-item"><span class="swatch" style="background:${GROUP_COLOR[g] ?? "var(--muted)"}"></span>${g}</span>`)}<span class="legend-item">line: median of 30 readings</span></div>`);
```

<p class="how"><b>How to read.</b> How far your heart rate falls in the minute after a workout ends; a bigger drop is better. Readings in the red band (12 bpm or less) were linked to higher risk in clinical exercise tests. Walks often show smaller drops than hard sessions simply because the heart rate was lower to begin with.</p>

</div>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Recovery strip</h3><span class="card-note">daily deviation from your previous 60 days (standard deviations)</span></div>

```js
const days = H.strain.days.map((x) => ({...x, date: D(x.d)})).filter((x) => within(r, x.d));
const strained = days.filter((d) => d.strained).length;
display(html`<p class="insight"><b>${plural(strained, "day")}</b> in ${describe(r)} with HRV at least ${H.strain_z} SD below and resting heart rate at least ${H.strain_z} SD above your baseline: often a sign of illness, poor sleep, alcohol, travel or hard training.</p>`);
const strip = days.flatMap((d) => [
  {date: d.date, row: "HRV", z: d.z_hrv, good: d.z_hrv != null ? d.z_hrv >= 0 : null, d},
  {date: d.date, row: "Resting HR", z: d.z_rhr, good: d.z_rhr != null ? d.z_rhr <= 0 : null, d}
]).filter((r) => r.z != null);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 120, marginLeft: 80,
  x: {type: "utc"},
  y: {domain: ["HRV", "Resting HR"], label: null, tickSize: 0},
  marks: [
    Plot.tickX(strip, {x: "date", y: "row", stroke: (r) => (r.good ? "var(--better)" : "var(--bad)"), strokeOpacity: (r) => Math.min(1, 0.15 + Math.abs(r.z) / 2.5), strokeWidth: Math.max(1.5, width / 400)}),
    Plot.dot(days.filter((d) => d.strained), {x: "date", y: () => "Resting HR", dy: 18, r: 2.5, fill: "var(--bad)"}),
    Plot.tip(strip, Plot.pointer({x: "date", y: "row", title: (r) => `${date(r.d.d)}\nHRV z ${num(r.d.z_hrv, 1)} · resting HR z ${num(r.d.z_rhr, 1)}${r.d.strained ? "\nstrained" : ""}`}))
  ]
})));
```

<p class="source">Blue: better than your baseline (higher HRV, lower resting HR); red: worse. Dots under the strip mark strained days.</p>
<p class="how"><b>How to read.</b> Each thin column is a day: HRV on the top row, resting heart rate below, coloured by how far each sits from your previous 60 days (stronger colour = further). A red stretch in both rows at once is the pattern to notice; isolated red days are normal.</p>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Breathing rate during sleep</h3><span class="card-note">breaths per minute</span></div>
<p class="insight">${insight("respiratory_rate", "respiratory_rate", "/min", (v) => num(v, 1))}</p>

```js
display(resize((width) => bandChart(series.respiratory_rate, {width, color: "var(--heart)", unit: "/min", refs: refs.respiratory_rate, format: (v) => v.toFixed(1)})));
```

<p class="how"><b>How to read.</b> Usually very steady from night to night. A rise of a breath per minute or more that lasts several nights, especially with a higher resting heart rate, is worth noticing; the grey band is the clinical range while awake.</p>

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Blood oxygen</h3><span class="card-note">daily median SpO2</span></div>
<p class="insight">${insight("spo2", "spo2", "", (v) => pct(v, 1))}</p>

```js
display(resize((width) => bandChart(series.spo2, {width, color: "var(--heart)", refs: refs.spo2, format: (v) => pct(v, 1), yFormat: (v) => pct(v, 1)})));
```

<p class="source">Watch spot readings (mostly at night). Readings vary with fit and movement; the median is shown.</p>
<p class="how"><b>How to read.</b> Most nights sit at 95–100%. A single low reading is common (a loose band, movement); a run of low nights is what would matter.</p>
</div>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Heart rate through the day</h3><span class="card-note">mean heart rate per local hour, by year · valid wear days</span></div>

```js
const hdays = HOURLY.filter((d) => within(r, d.d));
const yrs = [...new Set(hdays.map((d) => +d.d.slice(0, 4)))].sort().slice(-5);
// Distinct hues for the years; the latest one in the page's heart colour.
const PALETTE = ["#0d9488", "#d97706", "#7c3aed", "#2563eb"];
const YC = [...PALETTE.slice(0, yrs.length - 1).reverse(), "var(--heart)"].slice(-yrs.length);
const hh = yrs.flatMap((y) => {
  const ds = hdays.filter((d) => +d.d.slice(0, 4) === y);
  return d3.range(24).map((hour) => ({year: y, hour, hr: d3.mean(ds, (d) => d.hr[hour]), n: ds.length})).filter((x) => x.hr != null);
});
display(resize((width) => Plot.plot({
  ...BASE, width, height: 240, marginRight: 50,
  x: {domain: [0, 23], ticks: 12, tickFormat: (h) => `${String(h).padStart(2, "0")}h`, label: null},
  y: {grid: true, label: null, zero: false},
  marks: [
    Plot.line(hh, {x: "hour", y: "hr", z: "year", stroke: (d) => YC[yrs.indexOf(d.year)], strokeWidth: (d) => (d.year === yrs.at(-1) ? 2.2 : 1.4)}),
    Plot.tip(hh, Plot.pointerX({x: "hour", y: "hr", z: "year", title: (d) => `${d.year} · ${String(d.hour).padStart(2, "0")}:00\n${num(d.hr)} bpm`}))
  ]
})));
display(html`<div class="legend">${yrs.map((y, i) => html`<span class="legend-item"><span class="swatch" style="background:${YC[i]}"></span>${y}</span>`)}</div>`);
```

<p class="how"><b>How to read.</b> One line per year (within the range): the average heart rate for each hour. The night-time dip shows your resting level and the daytime curve follows activity. A whole curve sitting lower than earlier years is consistent with better fitness; a range inside one year shows a single line.</p>

</div>
