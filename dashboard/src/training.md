---
title: Training
---

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {calendar} from "./components/calendar.js";
import {num, date, dateShort, month, hm, plural} from "./components/format.js";
import {rangePicker, within, weekIn, monthIn, describe, addDays} from "./components/range.js";
const meta = FileAttachment("data/meta.json").json();
const T = FileAttachment("data/training.json").json();
const W = FileAttachment("data/workouts.json").json();
```

```js
const D = (s) => new Date(s);
const through = D(meta.data_through);
const GROUPS = ["walking", "running", "strength", "cycling", "other"];
const GROUP_COLOR = {walking: "var(--activity)", running: "var(--running)", strength: "var(--strength)", cycling: "var(--cycling)", other: "var(--muted)"};
const GROUP_LABEL = {walking: "Walking", running: "Running", strength: "Strength", cycling: "Cycling", other: "Other"};
const refNow = (key) => (T.references[key] ?? []).filter((b) => b.valid_from <= r.to && b.valid_to >= r.to);
const KIND = new Map(W.kinds.map((k) => [k.key, k]));
const legend = (groups) => html`<div class="legend">${groups.map((g) => html`<span class="legend-item"><span class="swatch" style="background:${GROUP_COLOR[g]}"></span>${GROUP_LABEL[g]}</span>`)}</div>`;
```

${pageHeader({eyebrow: "Workouts", title: "Training", subtitle: "Volume, intensity, load and consistency. A session recorded by two apps counts once.", meta})}

```js
const r = view(rangePicker({first: meta.first_day, last: meta.data_through, value: "2 years"}));
```

```js
const weekly = T.weekly.filter((d) => weekIn(r, d.week_start)).map((d) => ({...d, date: D(d.week_start)}));
const weeks = d3.rollups(weekly, (v) => d3.sum(v, (d) => d.hours), (d) => +d.date).map(([t, h]) => ({date: new Date(t), hours: h}));
const last12 = addDays(r.to, -83);
const recent12 = weeks.filter((w) => w.date >= D(last12));
// Counted sessions inside the range, with their kind and activity group.
const sessions = W.sessions.filter((s) => within(r, s.d)).map((s) => ({...s, group: KIND.get(s.kind)?.group ?? "other", label: KIND.get(s.kind)?.label ?? s.kind}));
```

<div class="card">
<div class="card-head"><h3 class="card-title">Hours per week</h3><span class="card-note">by activity</span></div>
<p class="insight">Last 12 weeks of the range: <b>${num(d3.sum(recent12, (d) => d.hours) / 12, 1)} h per week</b> on average, against ${num(d3.mean(weeks, (d) => d.hours), 1)} h over the whole range.</p>

```js
display(resize((width) => Plot.plot({
  ...BASE, width, height: 260,
  x: {type: "utc"},
  y: {grid: true, label: null},
  color: {domain: GROUPS, range: GROUPS.map((g) => GROUP_COLOR[g])},
  marks: [
    Plot.rectY(weekly, Plot.stackY({x1: "date", x2: (d) => new Date(+d.date + 6 * 864e5), y: "hours", fill: "activity_group", order: GROUPS})),
    Plot.tip(weekly, Plot.pointer(Plot.stackY({x: (d) => new Date(+d.date + 3 * 864e5), y: "hours", fill: "activity_group", order: GROUPS, title: (d) => `Week of ${date(d.week_start)}\n${GROUP_LABEL[d.activity_group]}: ${num(d.hours, 1)} h, ${plural(d.sessions, "session")}`})))
  ]
})));
display(legend(GROUPS.filter((g) => weekly.some((d) => d.activity_group === g))));
```

</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Training load</h3><span class="card-note">daily TRIMP · acute 7 days vs chronic 28 days</span></div>

```js
const load = T.load.filter((d) => within(r, d.d)).map((d) => ({...d, date: D(d.d)}));
const lastLoad = load.filter((d) => d.r != null).at(-1);
const ratioRef = refNow("training_load_ratio").find((b) => b.is_target);
display(html`<p class="insight">Acute to chronic ratio on ${date(lastLoad?.d)}: <b>${num(lastLoad?.r, 2)}</b>${ratioRef ? html` (${ratioRef.label.toLowerCase()}: ${num(ratioRef.lo, 1)}–${num(ratioRef.hi, 1)})` : ""}. Above the band, load is rising faster than the body is used to; below, it is falling.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 170, marginTop: 8,
  x: {type: "utc"},
  y: {grid: true, label: null},
  marks: [
    Plot.rectY(load, {x1: "date", x2: (d) => new Date(+d.date + 864e5), y: "t", fill: "var(--training)", fillOpacity: 0.35}),
    Plot.line(load, {x: "date", y: "c", stroke: "var(--ink-2)", strokeWidth: 1.6}),
    Plot.line(load, {x: "date", y: "a", stroke: "var(--training)", strokeWidth: 1.8}),
    Plot.tip(load, Plot.pointerX({x: "date", y: "a", title: (d) => `${date(d.d)}\nTRIMP ${num(d.t)}\nacute ${num(d.a, 1)} · chronic ${num(d.c, 1)}`}))
  ]
})));
display(resize((width) => Plot.plot({
  ...BASE, width, height: 120, marginTop: 6,
  x: {type: "utc"},
  y: {grid: true, label: null, domain: [0, Math.max(2, d3.quantile(load.map((d) => d.r).filter((r) => r != null), 0.99) ?? 2)]},
  marks: [
    ratioRef ? Plot.rectY([ratioRef], {y1: "lo", y2: "hi", fill: "var(--good)", fillOpacity: 0.1}) : null,
    Plot.ruleY([1], {stroke: "var(--border-strong)"}),
    Plot.line(load, {x: "date", y: "r", stroke: "var(--training)", strokeWidth: 1.4}),
    Plot.tip(load.filter((d) => d.r != null), Plot.pointerX({x: "date", y: "r", title: (d) => `${date(d.d)}\nratio ${num(d.r, 2)}`}))
  ]
})));
display(html`<div class="legend"><span class="legend-item"><span class="swatch" style="background:var(--training)"></span>Acute (7-day mean)</span><span class="legend-item"><span class="swatch" style="background:var(--ink-2)"></span>Chronic (28-day mean)</span><span class="legend-item">bars: daily TRIMP</span></div>`);
```

<p class="source">TRIMP (Edwards): minutes in heart-rate zones 1 to 5 weighted 1 to 5. Workouts without heart-rate zones (some app-recorded strength sessions) add no load.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Time in heart-rate zones</h3><span class="card-note">minutes per month</span></div>

```js
const ZC = ["#a7f3d0", "#6ee7b7", "#fcd34d", "#fb923c", "#e11d48"];
const zm = T.zones_monthly.filter((d) => monthIn(r, d.month)).map((d) => ({...d, date: D(d.month)}))
  .flatMap((d) => [1, 2, 3, 4, 5].map((z) => ({date: d.date, zone: `Zone ${z}`, min: d[`zone${z}_min`]})));
const vig = weekly.filter((d) => d.date >= D(last12));
const vigRef = refNow("vigorous_minutes_week").find((b) => b.is_target);
display(html`<p class="insight">Last 12 weeks of the range: <b>${num(d3.sum(vig, (d) => d.vigorous_min) / 12)} min per week</b> in zones 4 and 5${vigRef ? html` (${vigRef.label.toLowerCase()})` : ""}.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 300,
  x: {type: "utc"},
  y: {grid: true, label: null},
  color: {domain: ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5"], range: ZC},
  marks: [
    Plot.rectY(zm, Plot.stackY({x: "date", interval: "month", y: "min", fill: "zone", insetLeft: 1, insetRight: 1})),
    Plot.tip(zm, Plot.pointer(Plot.stackY({x: "date", interval: "month", y: "min", fill: "zone", title: (d) => `${month(d.date)}\n${d.zone}: ${hm(d.min)}`})))
  ]
})));
display(html`<div class="legend">${ZC.map((c, i) => html`<span class="legend-item"><span class="swatch" style="background:${c}"></span>Zone ${i + 1}</span>`)}</div>`);
```

<p class="source">Apple's heart-rate zones (personal, from resting and maximum heart rate).</p>
</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Strength</h3><span class="card-note">sessions per month</span></div>

```js
const st = d3.rollups(sessions.filter((s) => s.group === "strength"), (v) => {
  const lifted = v.filter((s) => s.strength_volume_kg != null);
  return {sessions: v.length, median_min: d3.median(v, (s) => s.duration_min), volume_kg: d3.sum(lifted, (s) => s.strength_volume_kg), with_volume: lifted.length};
}, (s) => s.d.slice(0, 7)).map(([m, v]) => ({month: `${m}-01`, date: D(`${m}-01`), ...v})).sort((a, b) => a.date - b.date);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 220,
  x: {type: "utc"},
  y: {grid: true, label: null},
  marks: [
    Plot.rectY(st, {x: "date", interval: "month", y: "sessions", fill: "var(--strength)", insetLeft: 1, insetRight: 1}),
    Plot.tip(st, Plot.pointerX({x: "date", y: "sessions", title: (d) => `${month(d.date)}\n${plural(d.sessions, "session")}, median ${num(d.median_min)} min\n${d.with_volume ? `weight lifted ${num(d.volume_kg)} kg (${d.with_volume} logged in JEFIT)` : "weight lifted: not logged"}`}))
  ]
})));
```

<p class="source">Hover a month for the median session length and the total weight lifted. Only JEFIT records weight; Apple's strength workouts do not.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Effort</h3><span class="card-note">Apple workout effort score (1–10), watchOS 11 and later</span></div>

```js
const ef = d3.rollups(sessions.filter((s) => s.effort_score != null), (v) => ({median: d3.median(v, (s) => s.effort_score), p25: d3.quantile(v, 0.25, (s) => s.effort_score), p75: d3.quantile(v, 0.75, (s) => s.effort_score), n: v.length}), (s) => s.group)
  .map(([activity_group, v]) => ({activity_group, ...v})).sort((a, b) => b.n - a.n);
display(ef.length ? resize((width) => Plot.plot({
  ...BASE, width, height: 220, marginLeft: 80,
  x: {domain: [0, 10], grid: true, label: null},
  y: {domain: ef.map((d) => GROUP_LABEL[d.activity_group]), label: null},
  marks: [
    Plot.ruleY(ef, {x1: "p25", x2: "p75", y: (d) => GROUP_LABEL[d.activity_group], stroke: (d) => GROUP_COLOR[d.activity_group], strokeWidth: 8, strokeOpacity: 0.35}),
    Plot.dot(ef, {x: "median", y: (d) => GROUP_LABEL[d.activity_group], r: 5, fill: (d) => GROUP_COLOR[d.activity_group]}),
    Plot.text(ef, {x: "p75", y: (d) => GROUP_LABEL[d.activity_group], text: (d) => `${d.n}`, dx: 10, textAnchor: "start", fill: "var(--muted)", fontSize: 11})
  ]
})) : html`<p class="card-note">No effort scores in this range.</p>`);
```

<p class="source">Dot: median; bar: middle half of workouts; number: workouts rated.</p>
</div>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Consistency</h3><span class="card-note">workout minutes per day</span></div>

```js
const dayMin = d3.rollups(sessions, (v) => d3.sum(v, (s) => s.duration_min), (s) => s.d).map(([d, value]) => ({local_date: d, value})).sort((a, b) => d3.ascending(a.local_date, b.local_date));
// Breaks: the runs of days without a workout between workout days (and up to the end of the range).
const trainDays = dayMin.map((d) => d.local_date);
const breaks = d3.pairs(trainDays, (a, b) => ({start: addDays(a, 1), end: addDays(b, -1), days: Math.round((D(b) - D(a)) / 864e5) - 1}));
if (trainDays.length && trainDays.at(-1) < r.to) breaks.push({start: addDays(trainDays.at(-1), 1), end: r.to, days: Math.round((D(r.to) - D(trainDays.at(-1))) / 864e5), ongoing: r.to === meta.data_through});
const longestBreak = d3.greatest(breaks, (b) => b.days);
const mondays = d3.utcMonday.range(d3.utcMonday.floor(D(r.from)), d3.utcDay.offset(D(r.to), 1));
const trainedWeeks = new Set(trainDays.map((d) => +d3.utcMonday.floor(D(d))));
const years = d3.rollups(mondays, (v) => ({weeks: v.length, weeks_trained: v.filter((w) => trainedWeeks.has(+w)).length}), (w) => d3.utcThursday.ceil(w).getUTCFullYear()).map(([year, v]) => ({year, ...v}));
display(html`<p class="insight">Trained in <b>${num(trainedWeeks.size)} of ${plural(mondays.length, "week")}</b>. ${longestBreak ? html`Longest break: <b>${plural(longestBreak.days, "day")}</b> (${date(longestBreak.start)} – ${date(longestBreak.end)}${longestBreak.ongoing ? ", ongoing" : ""}).` : ""}</p>`);
display(resize((width) => calendar(dayMin, {width, color: "var(--training)", label: "min", format: (v) => num(v)})));
display(html`<table class="t" style="margin-top:12px"><thead><tr><th>Year</th><th class="num">Weeks with training</th></tr></thead><tbody>${years.map((y) => html`<tr><td>${y.year}</td><td class="num">${y.weeks_trained} / ${y.weeks}</td></tr>`)}</tbody></table>`);
```

</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Latest workouts in the range</h3><span class="card-note">click a type for that session on the <a href="./workouts.html">Workouts</a> page</span></div>

```js
display(html`<div style="overflow-x:auto"><table class="t">
  <thead><tr><th>Date</th><th>Type</th><th>Source</th><th class="num">Duration</th><th class="num">Distance</th><th class="num">Active kcal</th><th class="num">Avg HR</th><th class="num">TRIMP</th><th class="num">Effort</th></tr></thead>
  <tbody>${sessions.slice(-25).reverse().map((w) => html`<tr><td>${date(w.d)}</td><td><span class="swatch" style="background:${GROUP_COLOR[w.group]};margin-right:6px"></span><a href="./workouts.html?type=${encodeURIComponent(w.kind)}&id=${w.id}">${w.label}</a></td><td class="card-note">${w.source_name}</td><td class="num">${hm(w.duration_min)}</td><td class="num">${w.distance_km ? `${num(w.distance_km, 2)} km` : "–"}</td><td class="num">${num(w.active_energy_kcal)}</td><td class="num">${num(w.avg_hr_bpm)}</td><td class="num">${num(w.trimp)}</td><td class="num">${w.effort_score ?? "–"}</td></tr>`)}</tbody>
</table></div>`);
```

</div>
