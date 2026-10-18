---
title: Running
---

<link rel="stylesheet" href="./vendor/leaflet.css">

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {createMap, decode} from "./components/map.js";
import {num, date, month, pace, hm, plural} from "./components/format.js";
import {rangePicker, within, weekIn, monthIn, describe} from "./components/range.js";
const meta = FileAttachment("data/meta.json").json();
const R = FileAttachment("data/running.json").json();
```

```js
const D = (s) => new Date(s);
const runs = R.runs.filter((x) => within(r, x.local_date)).map((x) => ({...x, date: D(x.local_date)}));
const recent = runs.slice(-20);
const minPerKm = (s) => s / 60;
const paceTick = (v) => pace(v * 60).replace(" /km", "");
```

${pageHeader({eyebrow: "Runs", title: "Running", subtitle: "Pace, efficiency, form, splits and best efforts, and any run in detail.", meta})}

```js
const r = view(rangePicker({first: meta.first_day, last: meta.data_through, value: "All"}));
```

<p class="insight">${runs.length ? html`<b>${plural(runs.length, "run")}</b> in ${describe(r)}, ${num(d3.sum(runs, (x) => x.distance_km))} km in all.` : "No runs in this range."}</p>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Pace per run</h3><span class="card-note">min/km · line: median of 10 runs</span></div>

```js
display(html`<p class="insight">Last ${Math.min(20, runs.length)} runs of the range: median pace <b>${pace(d3.median(recent, (r) => r.pace_s_per_km))}</b> over a median ${num(d3.median(recent, (r) => r.distance_km), 1)} km.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 250,
  x: {type: "utc"},
  y: {grid: true, label: null, reverse: true, tickFormat: paceTick},
  r: {range: [2, 7]},
  marks: [
    Plot.dot(runs, {x: "date", y: (r) => minPerKm(r.pace_s_per_km), r: "distance_km", fill: "var(--running)", fillOpacity: 0.45}),
    Plot.lineY(runs, Plot.windowY({k: 10, reduce: "median"}, {x: "date", y: (r) => minPerKm(r.pace_s_per_km), stroke: "var(--running)", strokeWidth: 1.8})),
    Plot.tip(runs, Plot.pointer({x: "date", y: (r) => minPerKm(r.pace_s_per_km), title: (r) => `${date(r.local_date)}\n${num(r.distance_km, 2)} km at ${pace(r.pace_s_per_km)}\navg HR ${num(r.avg_hr_bpm)}`}))
  ]
})));
```

<p class="source">Faster is higher. Dot size: distance.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Aerobic efficiency</h3><span class="card-note">metres per heartbeat</span></div>

```js
const eff = runs.filter((r) => r.m_per_beat != null);
const effNow = d3.median(eff.slice(-20), (r) => r.m_per_beat), effThen = d3.median(eff.slice(0, 20), (r) => r.m_per_beat);
display(html`<p class="insight">Last 20 runs: <b>${num(effNow, 2)} m</b> per heartbeat, against ${num(effThen, 2)} m in the first 20. Covering more ground per heartbeat at an easy effort is a sign of aerobic fitness.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 250,
  x: {type: "utc"},
  y: {grid: true, label: null, zero: false},
  marks: [
    Plot.dot(eff, {x: "date", y: "m_per_beat", r: 2.5, fill: "var(--running)", fillOpacity: 0.45}),
    Plot.lineY(eff, Plot.windowY({k: 10, reduce: "median"}, {x: "date", y: "m_per_beat", stroke: "var(--running)", strokeWidth: 1.8})),
    Plot.tip(eff, Plot.pointer({x: "date", y: "m_per_beat", title: (r) => `${date(r.local_date)}\n${num(r.m_per_beat, 2)} m/beat\n${pace(r.pace_s_per_km)} at ${num(r.avg_hr_bpm)} bpm`}))
  ]
})));
```

<p class="source">Average speed divided by average heart rate. Hills, heat and intervals lower it.</p>
</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Distance per week</h3><span class="card-note">km</span></div>

```js
const wk = R.weekly.filter((d) => weekIn(r, d.week)).map((d) => ({...d, date: D(d.week)}));
display(resize((width) => Plot.plot({
  ...BASE, width, height: 220,
  x: {type: "utc"},
  y: {grid: true, label: null},
  marks: [
    Plot.rectY(wk, {x1: "date", x2: (d) => new Date(+d.date + 6 * 864e5), y: "km", fill: "var(--running)"}),
    Plot.tip(wk, Plot.pointerX({x: (d) => new Date(+d.date + 3 * 864e5), y: "km", title: (d) => `Week of ${date(d.week)}\n${num(d.km, 1)} km in ${d.runs} runs`}))
  ]
})));
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Best efforts</h3><span class="card-note">fastest time within any run, per month</span></div>

```js
const EFF = [["best_1k_s", "1 km", 1, "fastest_1k"], ["best_5k_s", "5 km", 5, "fastest_5k"], ["best_10k_s", "10 km", 10, "fastest_10k"]];
// Pace in minutes per km, so the axis ticks fall on whole and half minutes.
const bm = R.best_monthly.filter((d) => monthIn(r, d.month)).flatMap((d) => EFF.map(([k, label, km]) => ({date: D(d.month), label, pace: d[k] == null ? null : d[k] / km / 60})).filter((r) => r.pace != null));
display(resize((width) => Plot.plot({
  ...BASE, width, height: 220, marginRight: 50,
  x: {type: "utc"},
  y: {grid: true, label: null, reverse: true, tickFormat: paceTick},
  color: {domain: ["1 km", "5 km", "10 km"], range: ["var(--running)", "var(--sleep)", "var(--places)"]},
  marks: [
    Plot.line(bm, {x: "date", y: "pace", stroke: "label", strokeWidth: 1.5, marker: "dot"}),
    Plot.tip(bm, Plot.pointer({x: "date", y: "pace", stroke: "label", title: (d) => `${month(d.date)} · best ${d.label}\n${pace(d.pace * 60)}`}))
  ]
})));
// Records within the range: the fastest effort over each distance among its runs.
const recs = Object.fromEntries(EFF.map(([k, , , id]) => [id, {value: d3.min(runs, (x) => x[k])}]));
const mmss = (s) => `${Math.floor(s / 3600) ? `${Math.floor(s / 3600)}:` : ""}${String(Math.floor((s % 3600) / 60)).padStart(Math.floor(s / 3600) ? 2 : 1, "0")}:${String(Math.round(s % 60)).padStart(2, "0")}`;
display(html`<div class="legend">${EFF.map(([, label, , id], i) => html`<span class="legend-item"><span class="swatch" style="background:${["var(--running)", "var(--sleep)", "var(--places)"][i]}"></span><span>${label}${recs[id]?.value ? html` · record <b>${mmss(recs[id].value)}</b>` : ""}</span></span>`)}</div>`);
```

</div>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Running form</h3><span class="card-note">per run, watchOS 9 and later · line: median of 10 runs</span></div>

```js
const FORM = [["power_w", "Power", "W", 0], ["stride_m", "Stride length", "m", 2], ["ground_contact_ms", "Ground contact", "ms", 0], ["vertical_oscillation_cm", "Vertical oscillation", "cm", 1]];
display(html`<div class="grid grid-cols-4">${FORM.map(([k, title, unit, dig]) => resize((width) => {
  const rows = runs.filter((r) => r[k] != null);
  return html`<div><p class="card-note" style="margin:0 0 4px">${title} (${unit})</p>${rows.length < 3 ? html`<p class="card-note">No data.</p>` : Plot.plot({
    ...BASE, width, height: 150, marginLeft: 38, marginTop: 6,
    x: {type: "utc", ticks: 3},
    y: {grid: true, label: null, zero: false, ticks: 4},
    marks: [
      Plot.dot(rows, {x: "date", y: k, r: 1.8, fill: "var(--running)", fillOpacity: 0.4}),
      Plot.lineY(rows, Plot.windowY({k: 10, reduce: "median"}, {x: "date", y: k, stroke: "var(--running)", strokeWidth: 1.6})),
      Plot.tip(rows, Plot.pointer({x: "date", y: k, title: (r) => `${date(r.local_date)}\n${num(r[k], dig)} ${unit}`}))
    ]
  })}</div>`;
}))}</div>`);
```

</div>

## One run in detail

```js
const withRoute = runs.filter((x) => x.has_route).reverse();
const params = new URLSearchParams(location.search);
const wanted = params.get("run");
const choice = view(Inputs.select(withRoute, {label: "Run", format: (x) => `${date(x.local_date)} · ${num(x.distance_km, 1)} km · ${pace(x.pace_s_per_km)}`, value: withRoute.find((x) => x.workout_id === wanted) ?? withRoute[0]}));
```

```js
const det = R.detail[choice.workout_id];
const splits = det.splits.map(([split, dist, dur, p, elev, hr]) => ({split, dist, dur, pace: p, elev, hr}));
const profile = det.profile.map(([dist, ele]) => ({km: dist / 1000, ele}));
// Long runs: label every 2nd, 5th... km so the ticks do not overlap.
const every = Math.max(1, Math.ceil(splits.length / 10));
const splitTicks = splits.filter((d, i) => i % every === 0).map((d) => d.split);
```

<div class="grid grid-cols-2">
<div class="card">

```js
const runMap = createMap({height: 420});
display(runMap.element);
const pts = det.polyline ? decode(det.polyline) : [];
if (pts.length) {
  const line = runMap.L.polyline(pts, {color: getComputedStyle(document.documentElement).getPropertyValue("--running").trim() || "#ea580c", weight: 4, opacity: 0.9, renderer: runMap.renderer}).addTo(runMap.map);
  runMap.L.circleMarker(pts[0], {radius: 5, color: "#16a34a", fillOpacity: 1, renderer: runMap.renderer}).addTo(runMap.map).bindTooltip("Start");
  runMap.L.circleMarker(pts.at(-1), {radius: 5, color: "#111827", fillOpacity: 1, renderer: runMap.renderer}).addTo(runMap.map).bindTooltip("Finish");
  requestAnimationFrame(() => runMap.map.fitBounds(line.getBounds(), {padding: [20, 20]}));
}
invalidation.then(() => runMap.map.remove());
```

<p class="source">${date(choice.local_date)} · ${num(choice.distance_km, 2)} km in ${hm(choice.duration_min)} · ${pace(choice.pace_s_per_km)} · ${num(choice.avg_hr_bpm)} bpm average${choice.elevation_gain_m ? ` · ${num(choice.elevation_gain_m)} m climbed` : ""}${choice.weather_temperature_c != null && !choice.is_indoor ? ` · ${num(choice.weather_temperature_c)} °C${choice.weather_humidity_pct != null ? `, ${num(choice.weather_humidity_pct)}% humidity` : ""} at the start` : ""}</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Splits</h3><span class="card-note">pace per km (faster is higher) · hover a km for its pace, heart rate and climb</span></div>

```js
display(resize((width) => Plot.plot({
  ...BASE, width, height: 200, marginTop: 24,
  x: {label: null, tickFormat: (d) => `km ${d}`, type: "point", padding: 0.4, ticks: splitTicks},
  y: {grid: true, label: null, reverse: true, tickFormat: (v) => paceTick(v / 60), nice: true},
  marks: [
    Plot.line(splits, {x: "split", y: "pace", stroke: "var(--running)", strokeWidth: 1.8}),
    Plot.dot(splits, {x: "split", y: "pace", r: 4, fill: "var(--running)"}),
    Plot.tip(splits, Plot.pointerX({x: "split", y: "pace", title: (d) => `km ${d.split}${d.dist < 990 ? ` (${num(d.dist)} m)` : ""}\n${pace(d.pace)}\n${d.hr ? `${num(d.hr)} bpm` : "no heart rate"}${d.elev != null ? `\n${d.elev > 0 ? "+" : ""}${num(d.elev, 0)} m` : ""}`}))
  ]
})));
display(html`<p class="card-note" style="margin:6px 0 2px">Heart rate per km (bpm)</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 110, marginTop: 4,
  x: {label: null, type: "point", padding: 0.4, tickFormat: (d) => `km ${d}`, ticks: splitTicks},
  y: {grid: true, label: null, zero: false, ticks: 3},
  marks: [
    Plot.line(splits.filter((d) => d.hr), {x: "split", y: "hr", stroke: "var(--heart)", strokeWidth: 1.8, marker: "dot"})
  ]
})));
display(html`<p class="card-note" style="margin:6px 0 2px">Elevation (m)</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 110, marginTop: 4,
  x: {label: null, tickFormat: (d) => `${d} km`},
  y: {grid: true, label: null, zero: false, ticks: 3},
  marks: [
    Plot.areaY(profile.filter((d) => d.ele != null), {x: "km", y: "ele", fill: "var(--running)", fillOpacity: 0.15}),
    Plot.line(profile.filter((d) => d.ele != null), {x: "km", y: "ele", stroke: "var(--running)", strokeWidth: 1.4})
  ]
})));
```

</div>
</div>
