---
title: Activity
---

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {calendar} from "./components/calendar.js";
import {num, pct, month, date, plural} from "./components/format.js";
import {rangePicker, within, monthIn, weekIn, describe} from "./components/range.js";
const meta = FileAttachment("data/meta.json").json();
const act = FileAttachment("data/activity.json").json();
const HOURLY = FileAttachment("data/hourly.json").json();
```

```js
const D = (s) => new Date(s);
const watchFrom = D(act.watch_from);
const through = D(meta.data_through);
// Target bands for your age group at the end of the range.
const refBands = (key) => (act.references[key] ?? []).filter((b) => b.is_target && b.valid_from <= r.to && b.valid_to >= r.to);
```

${pageHeader({eyebrow: "Movement", title: "Activity", subtitle: "How much and when I move, and how I walk.", meta})}

```js
const r = view(rangePicker({first: meta.first_day, last: meta.data_through, value: "All"}));
```

```js
// Monthly charts take every month the range touches; weekly and daily ones take the range itself.
const end = D(r.to);
const cal = act.calendar.filter((d) => within(r, d.local_date));
const hours = HOURLY.filter((d) => within(r, d.d));
```

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Steps per day</h3><span class="card-note">monthly median, band: middle half of days</span></div>

```js
const ms = act.monthly_steps.filter((d) => monthIn(r, d.month)).map((d) => ({...d, date: D(d.month)}));
const typical = d3.median(cal.filter((d) => d.steps >= 100), (d) => d.steps);
const stepRefs = refBands("steps");
display(html`<p class="insight">Typical day in ${describe(r)}: <b>${num(typical)} steps</b>${stepRefs.length ? html`; the reference band marks ${stepRefs[0].label.toLowerCase()}` : ""}.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 260,
  x: {type: "utc"},
  y: {grid: true, label: null, tickFormat: (d) => (d ? `${d / 1000}k` : "0")},
  marks: [
    ...stepRefs.map((b) => Plot.rectY([b], {y1: (b) => b.lo ?? 0, y2: (b) => b.hi ?? b.lo, fill: "var(--reference)"})),
    ms.length && ms[0].date < watchFrom ? Plot.rectX([{x1: ms[0].date, x2: watchFrom}], {x1: "x1", x2: "x2", fill: "var(--nodata)"}) : null,
    ms.length && ms[0].date < watchFrom ? Plot.text([{x: new Date((+ms[0].date + +watchFrom) / 2)}], {x: "x", frameAnchor: "top", dy: 6, text: () => "iPhone only", fill: "var(--muted)", fontSize: 11}) : null,
    Plot.areaY(ms, {x: "date", y1: "p25", y2: "p75", fill: "var(--activity)", fillOpacity: 0.15, curve: "step-after"}),
    Plot.line(ms, {x: "date", y: "median", stroke: "var(--activity)", strokeWidth: 1.75, curve: "step-after"}),
    Plot.tip(ms, Plot.pointerX({x: "date", y: "median", title: (d) => `${month(d.date)}\nmedian ${num(d.median)} steps\nmiddle half ${num(d.p25)}–${num(d.p75)}\n${d.n} days`}))
  ]
})));
```

<p class="source">Days under 100 steps are left out (phone not carried, Watch off). Before the Watch, steps come from the iPhone alone and read lower.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Exercise minutes per week</h3><span class="card-note">weeks with 5+ days worn</span></div>

```js
const ex = act.weekly_exercise.filter((d) => weekIn(r, d.week_start)).map((d) => ({...d, date: D(d.week_start)}));
const exRef = refBands("exercise_minutes_week");
const inBand = exRef.length ? ex.filter((d) => d.exercise_min >= (exRef[0].lo ?? 0)).length : null;
display(html`<p class="insight">${!ex.length ? "No complete weeks in this range." : exRef.length ? html`<b>${inBand} of ${plural(ex.length, "week")}</b> reached ${exRef[0].label.toLowerCase()}; median <b>${num(d3.median(ex, (d) => d.exercise_min))} min</b>.` : html`Median week: <b>${num(d3.median(ex, (d) => d.exercise_min))} min</b>.`}</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 260,
  x: {type: "utc"},
  y: {grid: true, label: null},
  marks: [
    ...exRef.map((b) => Plot.rectY([b], {y1: (b) => b.lo ?? 0, y2: (b) => b.hi ?? b.lo, fill: "var(--reference)"})),
    Plot.rectY(ex, {x1: (d) => d.date, x2: (d) => new Date(+d.date + 6 * 864e5), y: "exercise_min", fill: "var(--activity)", fillOpacity: 0.8}),
    Plot.lineY(ex, Plot.windowY(8, {x: "date", y: "exercise_min", stroke: "var(--ink-2)", strokeWidth: 1.25})),
    Plot.tip(ex, Plot.pointerX({x: "date", y: "exercise_min", title: (d) => `Week of ${date(d.week_start)}\n${num(d.exercise_min)} exercise min`}))
  ]
})));
```

<p class="source">Line: 8-week moving average. Apple exercise minutes are minutes at brisk-walk intensity or above.</p>
</div>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Every day</h3>

```js
const calMetric = view(Inputs.radio(new Map([["Steps", "steps"], ["Active energy", "active_energy"], ["Exercise minutes", "exercise"]]), {value: "steps"}));
```

</div>

```js
const CAL = {steps: ["steps", (v) => num(v)], active_energy: ["kcal", (v) => num(v)], exercise: ["min", (v) => num(v)]};
display(resize((width) => calendar(cal.map((d) => ({local_date: d.local_date, value: d[calMetric]})), {width, label: CAL[calMetric][0], format: CAL[calMetric][1]})));
```

<p class="source">Darker = more. Rows are years, columns are weeks (Monday at the top).</p>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">The shape of a day</h3><span class="card-note">${plural(hours.length, "valid wear day")}</span></div>

```js
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const shapeRows = d3.range(1, 8).flatMap((dow) => {
  const ds = hours.filter((d) => d.dow === dow);
  return d3.range(24).map((hour) => ({dow, hour, steps: ds.length ? d3.mean(ds, (d) => d.steps[hour]) : null, n: ds.length}));
}).filter((d) => d.steps != null);
const peak = d3.greatest(shapeRows, (d) => d.steps);
display(peak ? html`<p class="insight">Busiest hour: <b>${DOW[peak.dow - 1]} ${String(peak.hour).padStart(2, "0")}:00</b>, ${num(peak.steps)} steps on average.</p>` : html`<p class="card-note">No valid wear days in this range.</p>`);
const hiSteps = d3.quantile(shapeRows.map((d) => d.steps), 0.98) || 1;
display(resize((width) => Plot.plot({
  ...BASE, width, height: 230, marginLeft: 40,
  x: {domain: d3.range(24), tickFormat: (h) => (h % 3 ? "" : `${String(h).padStart(2, "0")}h`), label: null},
  y: {domain: d3.range(1, 8), tickFormat: (d) => DOW[d - 1], label: null},
  padding: 0.06,
  marks: [
    Plot.cell(shapeRows, {x: "hour", y: "dow", fill: "var(--activity)", fillOpacity: (d) => 0.08 + 0.92 * Math.min(1, d.steps / hiSteps), rx: 2}),
    Plot.tip(shapeRows, Plot.pointer({x: "hour", y: "dow", title: (d) => `${DOW[d.dow - 1]} ${String(d.hour).padStart(2, "0")}:00\n${num(d.steps)} steps on average (${d.n} days)`}))
  ]
})));
```

<p class="source">Mean steps per local hour on valid wear days.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Weekdays and weekends</h3><span class="card-note">mean steps per hour</span></div>

```js
const KIND_COLOR = {Weekday: "var(--activity)", Weekend: "var(--heart)"};
const profile = ["Weekday", "Weekend"].flatMap((kind) => {
  const ds = hours.filter((d) => (d.dow >= 6) === (kind === "Weekend"));
  return ds.length ? d3.range(24).map((hour) => ({kind, hour, steps: d3.mean(ds, (d) => d.steps[hour])})) : [];
});
display(resize((width) => Plot.plot({
  ...BASE, width, height: 230,
  x: {domain: [0, 23], ticks: 8, tickFormat: (h) => `${String(h).padStart(2, "0")}h`, label: null},
  y: {grid: true, label: null},
  marks: [
    Plot.gridY({stroke: "var(--grid)"}),
    Plot.line(profile, {x: "hour", y: "steps", stroke: (d) => KIND_COLOR[d.kind], z: "kind", strokeWidth: 2}),
    Plot.tip(profile, Plot.pointerX({x: "hour", y: "steps", z: "kind", title: (d) => `${d.kind} ${String(d.hour).padStart(2, "0")}:00\n${num(d.steps)} steps`}))
  ]
})));
display(html`<div class="legend"><span class="legend-item"><span class="swatch" style="background:var(--activity)"></span>Weekday</span><span class="legend-item"><span class="swatch" style="background:var(--heart)"></span>Weekend</span></div>`);
```

</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Activity rings</h3><span class="card-note">share of days each goal was met</span></div>

```js
const RING = [["move_met", "Move", "var(--heart)"], ["exercise_met", "Exercise", "var(--activity)"], ["stand_met", "Stand", "var(--places)"]];
const ringDays = cal.filter((d) => d.all_met != null);
const ringMonths = d3.rollups(ringDays, (v) => v, (d) => d.local_date.slice(0, 7)).filter(([, v]) => v.length >= 10).sort(([a], [b]) => d3.ascending(a, b));
const rings = ringMonths.flatMap(([m, v]) => RING.map(([k, label, color]) => ({date: D(`${m}-01`), share: d3.mean(v, (d) => (d[k] ? 1 : 0)), label, color})));
// Longest runs of consecutive days inside the range.
function longestRun(key) {
  let best = {n: 0}, cur = {n: 0}, prev = null;
  for (const d of ringDays) {
    const next = prev && +D(d.local_date) - +D(prev) === 864e5;
    if (d[key]) cur = next && cur.n ? {n: cur.n + 1, start: cur.start, end: d.local_date} : {n: 1, start: d.local_date, end: d.local_date};
    else cur = {n: 0};
    if (cur.n > best.n) best = cur;
    prev = d.local_date;
  }
  return best;
}
const streaks = [["all_met", "Longest streak closing all rings"], ["exercise_met", "Longest streak closing the exercise ring"], ["move_met", "Longest streak closing the move ring"]].map(([k, label]) => ({label, ...longestRun(k)})).filter((s) => s.n > 0);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 240, marginRight: 70,
  x: {type: "utc"},
  y: {domain: [0, 1], tickFormat: (d) => pct(d), grid: true, label: null},
  marks: [
    Plot.line(rings, {x: "date", y: "share", z: "label", stroke: "color", strokeWidth: 1.6}),
    Plot.text(rings.filter((d) => +d.date === +d3.max(rings, (x) => x.date)), {x: "date", y: "share", text: "label", dx: 6, textAnchor: "start", fill: "color", fontWeight: 600}),
    Plot.tip(rings, Plot.pointerX({x: "date", y: "share", z: "label", title: (d) => `${month(d.date)} · ${d.label}: ${pct(d.share)} of days`}))
  ]
})));
display(html`<table class="t" style="margin-top:10px">${streaks.map((s) => html`<tr><td>${s.label}</td><td class="num"><b>${plural(s.n, "day")}</b></td><td class="num card-note">${date(s.start)} – ${date(s.end)}</td></tr>`)}</table>`);
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Daylight</h3><span class="card-note">median minutes per day (Watch, watchOS 10 and later)</span></div>

```js
const dl = act.daylight.filter((d) => d.daylight != null && monthIn(r, d.month)).map((d) => ({...d, date: D(d.month)}));
display(resize((width) => Plot.plot({
  ...BASE, width, height: 240,
  x: {type: "utc"},
  y: {grid: true, label: null, zero: true},
  marks: [
    Plot.rectY(dl, {x: "date", interval: "month", y: "daylight", fill: "var(--training)", fillOpacity: 0.85, insetLeft: 1, insetRight: 1}),
    Plot.tip(dl, Plot.pointerX({x: "date", y: "daylight", title: (d) => `${month(d.date)}\n${num(d.daylight)} min in daylight per day`}))
  ]
})));
```

<p class="source">Time in daylight is measured by the Watch's ambient light sensor.</p>
</div>
</div>

## How I walk

```js
const gait = act.gait.filter((d) => monthIn(r, d.month)).map((d) => ({...d, date: D(d.month)}));
const speedRef = refBands("walking_speed");
function gaitCard(key, title, unit, f, refs = [], note = "") {
  const rows = gait.filter((d) => d[key] != null);
  const lastV = rows.at(-1);
  return resize((width) => html`<div class="card">
    <div class="card-head"><h3 class="card-title">${title}</h3><span class="card-note">${lastV ? html`<b style="color:var(--ink)">${f(lastV[key])}</b> ${unit} in ${month(lastV.date)}` : ""}</span></div>
    ${Plot.plot({
      ...BASE, width, height: 160, marginLeft: 44, marginTop: 8,
      x: {type: "utc", ticks: 4},
      y: {grid: true, nice: true, zero: false, label: null, ticks: 4, tickFormat: unit === "%" ? (v) => pct(v) : undefined},
      marks: [
        ...refs.map((b) => Plot.rectY([b], {y1: (b) => b.lo, y2: (b) => b.hi, fill: "var(--reference)"})),
        Plot.line(rows, {x: "date", y: key, stroke: "var(--activity)", strokeWidth: 1.6}),
        Plot.tip(rows, Plot.pointerX({x: "date", y: key, title: (d) => `${month(d.date)}\n${f(d[key])} ${unit}`}))
      ]
    })}
    ${note ? html`<p class="source">${note}</p>` : ""}
  </div>`);
}
display(html`<div class="grid grid-cols-2">
  ${gaitCard("speed", "Walking speed", "km/h", (v) => num(v, 2), speedRef.map((b) => ({...b, lo: b.lo, hi: b.hi})), speedRef.length ? `Grey band: average usual walking speed of ${speedRef[0].population.split(",")[0].toLowerCase()} (95% confidence interval).` : "")}
  ${gaitCard("step_length", "Step length", "cm", (v) => num(v, 0))}
  ${gaitCard("asymmetry", "Walking asymmetry", "%", (v) => pct(v, 1), [], "Share of steps where one side is faster or slower than the other.")}
  ${gaitCard("double_support", "Double support time", "%", (v) => pct(v, 1), refBands("double_support"), "Share of the step cycle with both feet on the ground; lower means better balance. Grey band: the typical 20–40% Apple gives for walking.")}
</div>`);
```

<p class="source">Gait metrics are measured by the iPhone while walking with it in a pocket, on level ground. Monthly medians.</p>
