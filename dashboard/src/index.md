---
title: Overview
---

```js
import {pageHeader} from "./components/page.js";
import {tiles} from "./components/tile.js";
import {kpiToTile} from "./components/kpi.js";
import {computeKpi} from "./components/kpis.js";
import {referenceAt} from "./components/references.js";
import {rangePicker, within, spanDays, describe} from "./components/range.js";
import {BASE} from "./components/marks.js";
import {num, hm, date, dateShort, range, plural} from "./components/format.js";
import {barcode, compact} from "./components/barcode.js";
const meta = FileAttachment("data/meta.json").json();
const OV = FileAttachment("data/overview.json").json();
const SLEEP = FileAttachment("data/barcode.json").json();
```

```js
const HREF = {activity: "./activity.html", heart: "./heart.html", sleep: "./sleep.html", training: "./training.html", running: "./running.html"};
```

${pageHeader({eyebrow: "At a glance", title: "Overview", subtitle: "Pick a period; each tile compares it with your usual period of the same length.", meta})}

```js
const r = view(rangePicker({first: meta.first_day, last: meta.data_through, value: "28 days"}));
```

```js
const n = spanDays(r);
const days = OV.days.filter((d) => within(r, d.d)).map((d) => ({...d, date: new Date(d.d)}));
const results = OV.kpis.map((k) => computeKpi(k, OV.days, r));
const workouts = OV.workouts.filter((w) => within(r, w.d));
const daily = n <= 92;
display(html`<p class="insight">${describe(r)} · ${plural(n, "day")}, ${num(days.filter((d) => d.valid).length)} with the Watch worn. <span class="card-note">"Usual" is the median over every ${n}-day period in your history: hover a change chip for details.</span></p>`);
```

```js
display(tiles(results.map((k) => kpiToTile(k, {href: HREF[k.domain], reference: k.reference ? referenceAt(OV.references[k.reference], r.to, k.value) : null}))));
```

<div class="grid grid-cols-3">
<div class="card grid-colspan-1">
<div class="card-head"><h3 class="card-title">Highlights</h3></div>

```js
const top = (key) => days.filter((d) => d[key] != null).reduce((a, b) => (a == null || b[key] > a[key] ? b : a), null);
const streak = (() => {
  let best = {n: 0}, cur = {n: 0};
  for (const d of days) {
    if (d.rings) cur = {n: cur.n + 1, start: cur.n ? cur.start : d.d, end: d.d};
    else cur = {n: 0};
    if (cur.n > best.n) best = cur;
  }
  return best;
})();
const vo2In = d3.max(days, (d) => d.vo2max);
const vo2Before = d3.max(OV.days.filter((d) => d.d < r.from), (d) => d.vo2max);
const below = days.filter((d) => d.hrv != null && d.hrv_lo != null && d.hrv < d.hrv_lo).length;
const above = days.filter((d) => d.hrv != null && d.hrv_hi != null && d.hrv > d.hrv_hi).length;
const strained = days.filter((d) => d.z_hrv != null && d.z_rhr != null && d.z_hrv <= -OV.strain_z && d.z_rhr >= OV.strain_z).length;
const longest = workouts.reduce((a, b) => (a == null || b.min > a.min ? b : a), null);
const lines = [];
const s = top("steps"), sl = top("asleep");
if (s) lines.push(html`<li>Most steps on <b>${dateShort(s.d)}</b>: ${num(s.steps)}.</li>`);
if (sl) lines.push(html`<li>Longest night: <b>${hm(sl.asleep)}</b>, waking on ${dateShort(sl.d)}.</li>`);
if (streak.n > 1) lines.push(html`<li>All rings closed <b>${streak.n} days in a row</b> (${range(streak.start, streak.end)}).</li>`);
else if (streak.n === 1) lines.push(html`<li>All rings closed on one day (${dateShort(streak.start)}).</li>`);
if (vo2In != null && (vo2Before == null || vo2In > vo2Before)) lines.push(html`<li><b>VO2max high</b> in this period: ${num(vo2In, 1)} mL/min·kg.</li>`);
if (below || above) lines.push(html`<li>${plural(below, "night")} with HRV <b>below your normal range</b>, ${above} above it.</li>`);
if (strained) lines.push(html`<li>${plural(strained, "day")} with low HRV and high resting heart rate together.</li>`);
lines.push(workouts.length ? html`<li>${plural(workouts.length, "workout")}${longest ? html`; the longest ${num(longest.min)} min (${longest.label.toLowerCase()}, ${dateShort(longest.d)})` : ""}.</li>` : html`<li>No workouts recorded.</li>`);
display(html`<ul class="highlights">${lines}</ul>`);
```

</div>
<div class="card grid-colspan-2">
<div class="card-head"><h3 class="card-title">Steps, ${daily ? "day by day" : "week by week"}</h3><span class="card-note">${daily ? "bars faded where the Watch was barely worn" : "median of valid wear days in each week"}</span></div>

```js
const weekOf = (d) => d3.utcMonday.floor(d.date);
const stepRows = daily
  ? days.map((d) => ({date: d.date, steps: d.steps, valid: d.valid, label: date(d.d)}))
  : d3.rollups(days.filter((d) => d.valid && d.steps != null), (v) => d3.median(v, (d) => d.steps), weekOf).map(([w, v]) => ({date: w, steps: v, valid: true, label: `week of ${date(w)}`})).sort((a, b) => a.date - b.date);
const usualSteps = results.find((k) => k.key === "steps")?.value;
display(resize((width) => Plot.plot({
  ...BASE, width, height: 200,
  x: {type: "utc", label: null},
  y: {grid: true, tickFormat: (d) => (d ? `${d / 1000}k` : "0"), label: null},
  marks: [
    Plot.rectY(stepRows, {x1: "date", x2: (d) => new Date(+d.date + (daily ? 1 : 7) * 864e5), y: "steps", fill: "var(--activity)", fillOpacity: (d) => (d.valid ? 0.9 : 0.3), insetLeft: 1, insetRight: 1, rx: 2}),
    usualSteps ? Plot.ruleY([usualSteps], {stroke: "var(--muted)", strokeDasharray: "4 3"}) : null,
    usualSteps ? Plot.text([usualSteps], {y: (d) => d, frameAnchor: "right", dy: -6, text: (d) => `median ${num(d)}`, fill: "var(--muted)", fontSize: 11, textAnchor: "end"}) : null,
    Plot.tip(stepRows, Plot.pointerX({x1: "date", x2: (d) => new Date(+d.date + (daily ? 1 : 7) * 864e5), y: "steps", title: (d) => `${d.label}\n${num(d.steps)} steps${d.valid ? "" : "\n(Watch barely worn)"}`}))
  ]
})));
```

</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Nights</h3><span class="card-note">each bar is one night, coloured by sleep stage</span></div>

```js
const nightsIn = SLEEP.barcode.filter((x) => within(r, x.d));
const shown = nightsIn.slice(-180);
display(shown.length ? resize((width) => barcode(compact(shown, SLEEP.stage_codes), {width})) : html`<p class="card-note">No nights in this period.</p>`);
display(nightsIn.length > shown.length ? html`<p class="source">The last 180 of ${num(nightsIn.length)} nights; the <a href="./sleep.html">Sleep</a> page shows them all.</p>` : html``);
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Resting heart rate and HRV</h3><span class="card-note">shaded: your normal range</span></div>

```js
function dayLine(y, lo, hi, color, unit, width) {
  const rows = days.filter((d) => d[y] != null);
  return rows.length < 2 ? html`<p class="card-note">No data in this period.</p>` : Plot.plot({
    ...BASE, width, height: 130, marginTop: 10,
    x: {type: "utc", ticks: 4, label: null},
    y: {grid: true, nice: true, zero: false, label: null},
    marks: [
      Plot.areaY(days, {x: "date", y1: lo, y2: hi, fill: color, fillOpacity: 0.12, curve: "step"}),
      Plot.line(rows, {x: "date", y, stroke: color, strokeWidth: rows.length > 120 ? 1.2 : 1.75}),
      rows.length <= 120 ? Plot.dot(rows, {x: "date", y, r: 2.5, fill: color}) : null,
      Plot.tip(rows, Plot.pointerX({x: "date", y, title: (d) => `${date(d.d)}\n${num(d[y])} ${unit}${d[lo] != null ? `\nnormal ${num(d[lo])}–${num(d[hi])}` : ""}`}))
    ]
  });
}
display(html`<p class="card-note" style="margin:0 0 2px">Resting heart rate, bpm. Normal range: 10th to 90th percentile of your previous 90 days.</p>`);
display(resize((width) => dayLine("rhr", "rhr_lo", "rhr_hi", "var(--heart)", "bpm", width)));
display(html`<p class="card-note" style="margin:8px 0 2px">HRV during sleep, ms</p>`);
display(resize((width) => dayLine("hrv", "hrv_lo", "hrv_hi", "var(--sleep)", "ms", width)));
```

</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Workouts</h3><span class="card-note">minutes per ${daily ? "day" : "week"}</span></div>

```js
const wRows = daily
  ? days.map((d) => ({date: d.date, min: d.workout_min ?? 0, list: workouts.filter((w) => w.d === d.d)}))
  : d3.rollups(days, (v) => ({min: d3.sum(v, (d) => d.workout_min ?? 0), list: workouts.filter((w) => v.some((d) => d.d === w.d))}), weekOf).map(([w, v]) => ({date: w, ...v})).sort((a, b) => a.date - b.date);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 160,
  x: {type: "utc", label: null},
  y: {grid: true, label: null},
  marks: [
    Plot.rectY(wRows, {x1: "date", x2: (d) => new Date(+d.date + (daily ? 1 : 7) * 864e5), y: "min", fill: "var(--training)", insetLeft: 1, insetRight: 1, rx: 2}),
    Plot.tip(wRows.filter((d) => d.min), Plot.pointerX({x1: "date", x2: (d) => new Date(+d.date + (daily ? 1 : 7) * 864e5), y: "min", title: (d) => `${daily ? date(d.date) : `week of ${date(d.date)}`}\n${num(d.min)} min${d.list.length <= 6 ? `: ${d.list.map((w) => w.label.toLowerCase()).join(", ")}` : ` in ${d.list.length} workouts`}`}))
  ]
})));
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Where I was</h3><span class="card-note">days by time zone</span></div>

```js
const zones = d3.rollups(days, (v) => ({days: v.length, away: !!v[0].away}), (d) => d.tz_name).sort((a, b) => b[1].days - a[1].days);
display(html`<table class="t"><thead><tr><th>Time zone</th><th class="num">Days</th></tr></thead><tbody>${zones.map(([tz, z]) => html`<tr><td>${(tz ?? "unknown").split("/").at(-1).replace("_", " ")}${z.away ? html` <span class="chip" style="margin-left:6px">away</span>` : ""}</td><td class="num">${z.days}</td></tr>`)}</tbody></table>`);
```

<p class="source"><a href="./places.html">Places</a> shows the routes on a map.</p>
</div>
</div>
