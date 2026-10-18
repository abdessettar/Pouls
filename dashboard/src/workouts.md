---
title: Workouts
---

<link rel="stylesheet" href="./vendor/leaflet.css">

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {createMap, decode} from "./components/map.js";
import {num, hm, pace, date, month, plural} from "./components/format.js";
import {rangePicker, within, describe, setParams} from "./components/range.js";
const meta = FileAttachment("data/meta.json").json();
const W = FileAttachment("data/workouts.json").json();
const HR = FileAttachment("data/workout_hr.json").json();
const TRACKS = FileAttachment("data/tracks.json");
```

```js
const D = (s) => new Date(s);
const through = D(meta.data_through);
const GROUP_COLOR = {walking: "var(--activity)", running: "var(--running)", strength: "var(--strength)", cycling: "var(--cycling)", other: "var(--sleep)"};
const ZC = ["#a7f3d0", "#6ee7b7", "#fcd34d", "#fb923c", "#e11d48"];
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const clockOf = (s) => s.slice(11, 16);
const daysBetween = (a, b) => Math.round((b - a) / 864e5);
const swimPace = (s) => (s.distance_km ? (s.duration_min * 60) / (s.distance_km * 10) : null);
const mmss = (sec) => `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")}`;
const params = new URLSearchParams(location.search);

// A grid of buttons, one per kind of workout, that behaves like an input for view().
function kindPicker(kinds, value) {
  const root = html`<div class="kind-grid">${kinds.map((k) => html`<button type="button" class="kind" data-key=${k.key} style="--accent:${GROUP_COLOR[k.group] ?? "var(--muted)"}">
    <span class="kind-name"><span class="swatch" style="background:var(--accent)"></span>${k.label}</span>
    <span class="kind-meta">${plural(k.sessions, "session")} · last ${month(k.last)}</span>
  </button>`)}</div>`;
  root.value = value;
  const mark = () => root.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.key === root.value));
  root.addEventListener("click", (e) => {
    const b = e.target.closest("button.kind");
    if (!b || b.dataset.key === root.value) return;
    root.value = b.dataset.key;
    mark();
    setParams({type: root.value, id: null});
    root.dispatchEvent(new Event("input", {bubbles: true}));
  });
  mark();
  return root;
}
```

${pageHeader({eyebrow: "Every kind of workout", title: "Workouts", subtitle: "Pick a kind of workout to see how often, how long and how hard, and open any session.", meta})}

```js
const r = view(rangePicker({first: meta.first_day, last: meta.data_through, value: "All"}));
```

```js
// Kinds with at least one session in the range, counted for the range.
const kindsIn = W.kinds.map((k) => {
  const v = W.sessions.filter((s) => s.kind === k.key && within(r, s.d));
  return {...k, sessions: v.length, last: v.at(-1)?.d, total: k.sessions};
}).filter((k) => k.sessions > 0).sort((a, b) => b.sessions - a.sessions);
const wantedKind = params.get("type");
```

```js
if (!kindsIn.length) display(html`<p class="insight">No workouts in ${describe(r)}.</p>`);
const kindKey = view(kindPicker(kindsIn, kindsIn.some((k) => k.key === wantedKind) ? wantedKind : kindsIn[0]?.key));
```

```js
const K = kindsIn.find((k) => k.key === kindKey);
// Apple records the weather at the start of every workout; it only describes outdoor ones.
const outdoor = K.outdoor;
const color = GROUP_COLOR[K.group] ?? "var(--muted)";
const S = W.sessions.filter((s) => s.kind === kindKey && within(r, s.d)).map((s) => ({
  ...s,
  date: D(s.d),
  hour: +s.start.slice(11, 13) + +s.start.slice(14, 16) / 60,
  dow: (D(s.d).getUTCDay() + 6) % 7,
  zones: [1, 2, 3, 4, 5].map((z) => s[`zone${z}_min`] ?? 0),
  speedv: K.speed === "pace" ? s.pace_s_per_km : K.speed === "speed" ? s.speed_kmh : K.speed === "swim" ? swimPace(s) : null,
  ...(outdoor ? {} : {weather_temperature_c: null, weather_humidity_pct: null})
}));
const values = (key) => S.map((s) => s[key]).filter((v) => v != null);
const med = (key) => d3.median(values(key));
const lastYear = S.filter((s) => s.date > new Date(+through - 365 * 864e5));
const gaps = d3.pairs(S, (a, b) => daysBetween(a.date, b.date)).filter((g) => g > 0);
const speedFmt = K.speed === "pace" ? (v) => pace(v) : K.speed === "swim" ? (v) => `${mmss(v)} /100 m` : (v) => `${num(v, 1)} km/h`;
const every = (g) => (g <= 1.5 ? "almost daily" : g < 14 ? `every ${Math.round(g)} days` : g < 60 ? `every ${Math.round(g / 7)} weeks` : `every ${Math.round(g / 30)} months`);
// Median gap for regular habits; when sessions come in bursts, say so instead of a misleading "every 2 days".
function rhythm(gs) {
  if (gs.length < 2) return null;
  const mid = d3.median(gs), mean = d3.mean(gs);
  return mean > 3 * mid ? `in bursts: half the gaps are ${plural(Math.round(mid), "day")} or less, but on average ${every(mean).replace("almost daily", "every day")}` : `typically ${every(mid)}`;
}
```

```js
const first = S[0], last = S.at(-1);
const sinceLast = daysBetween(last.date, through);
display(html`<p class="insight"><b>${plural(S.length, "session")}</b> of ${K.label.toLowerCase()} in ${describe(r)}, from ${date(first.d)} to ${date(last.d)}${sinceLast > 0 ? html` (${plural(sinceLast, "day")} ago)` : ""}${rhythm(gaps) ? html`, ${rhythm(gaps)}` : ""}. A typical session lasts <b>${hm(med("duration_min"))}</b>${med("avg_hr_bpm") ? html` at <b>${num(med("avg_hr_bpm"))} bpm</b>` : ""}${med("distance_km") ? html` and covers <b>${num(med("distance_km"), 1)} km</b>` : ""}.</p>`);
const tiles = [
  ["Sessions", num(S.length), S.length === K.total ? "all of them" : `of ${num(K.total)} in all`],
  ["Total time", hm(d3.sum(S, (s) => s.duration_min)), `${num(d3.sum(S, (s) => s.duration_min) / 60, 1)} hours`],
  ["Typical session", hm(med("duration_min")), S.length >= 4 ? `middle half ${hm(d3.quantile(values("duration_min"), 0.25))}–${hm(d3.quantile(values("duration_min"), 0.75))}` : `longest ${hm(d3.max(values("duration_min")))}`],
  med("avg_hr_bpm") ? ["Heart rate", `${num(med("avg_hr_bpm"))} bpm`, med("max_hr_bpm") ? `peaks around ${num(med("max_hr_bpm"))} bpm` : "median of session averages"] : null,
  med("active_energy_kcal") ? ["Energy", `${num(med("active_energy_kcal"))} kcal`, `per session · ${num(d3.sum(values("active_energy_kcal")))} kcal in all`] : null,
  med("distance_km") ? ["Distance", `${num(d3.sum(values("distance_km")), 0)} km`, `${num(med("distance_km"), 1)} km per session`] : null,
  K.speed && med("speedv") ? [K.speed === "speed" ? "Speed" : "Pace", speedFmt(med("speedv")), "median"] : null,
  med("avg_mets") ? ["Intensity", `${num(med("avg_mets"), 1)} METs`, "Apple's average, median"] : null
].filter(Boolean);
display(html`<div class="totals">${tiles.map(([label, value, sub]) => html`<div class="total"><span class="total-value">${value}</span><span class="total-label">${label}</span><span class="card-note" style="font-size:11.5px">${sub}</span></div>`)}</div>`);
```

<div class="card">
<div class="card-head"><h3 class="card-title">Sessions over time</h3><span class="card-note">sessions per month</span></div>

```js
const byMonth = d3.rollups(S, (v) => ({n: v.length, min: d3.sum(v, (s) => s.duration_min)}), (s) => +d3.utcMonth(s.date)).map(([m, v]) => ({month: new Date(m), ...v}));
const byYear = d3.rollups(S, (v) => v.length, (s) => s.date.getUTCFullYear());
display(resize((width) => Plot.plot({
  ...BASE, width, height: 170,
  x: {type: "utc", label: null, domain: [d3.utcMonth.offset(d3.utcMonth(first.date), -1), d3.utcMonth.offset(D(r.to), 1)]},
  y: {grid: true, label: null, tickFormat: (v) => (Number.isInteger(v) ? v : "")},
  marks: [
    Plot.rectY(byMonth, {x1: "month", x2: (d) => d3.utcMonth.offset(d.month, 1), y: "n", fill: color, insetLeft: 1, insetRight: 1}),
    Plot.ruleY([0]),
    Plot.tip(byMonth, Plot.pointerX({x1: "month", x2: (d) => d3.utcMonth.offset(d.month, 1), y: "n", title: (d) => `${month(d.month)}\n${plural(d.n, "session")} · ${hm(d.min)}`}))
  ]
})));
display(html`<p class="card-note">${byYear.map(([y, n]) => `${y}: ${n}`).join(" · ")}</p>`);
```

</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Length of each session</h3><span class="card-note">dots: sessions · line: median</span></div>

```js
display(resize((width) => Plot.plot({
  ...BASE, width, height: 220,
  x: {type: "utc"},
  y: {grid: true, label: null, zero: true, tickFormat: (v) => hm(v)},
  marks: [
    Plot.ruleY([med("duration_min")], {stroke: "var(--ink-2)", strokeDasharray: "4 3"}),
    Plot.dot(S, {x: "date", y: "duration_min", r: S.length > 200 ? 1.8 : 3, fill: color, fillOpacity: S.length > 200 ? 0.4 : 0.8}),
    Plot.tip(S, Plot.pointer({x: "date", y: "duration_min", title: (s) => `${date(s.d)} ${clockOf(s.start)}\n${hm(s.duration_min)}`}))
  ]
})));
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Heart rate</h3><span class="card-note">dot: average · bar: lowest to highest</span></div>

```js
const withHr = S.filter((s) => s.avg_hr_bpm != null);
display(withHr.length ? resize((width) => Plot.plot({
  ...BASE, width, height: 220,
  x: {type: "utc"},
  y: {grid: true, label: null, zero: false},
  marks: [
    Plot.ruleX(withHr.filter((s) => s.max_hr_bpm != null), {x: "date", y1: (s) => s.min_hr_bpm ?? s.avg_hr_bpm, y2: "max_hr_bpm", stroke: color, strokeOpacity: withHr.length > 200 ? 0.12 : 0.35, strokeWidth: withHr.length > 200 ? 1 : 2}),
    Plot.dot(withHr, {x: "date", y: "avg_hr_bpm", r: withHr.length > 200 ? 1.6 : 3, fill: color}),
    Plot.tip(withHr, Plot.pointer({x: "date", y: "avg_hr_bpm", title: (s) => `${date(s.d)}\naverage ${num(s.avg_hr_bpm)} bpm${s.max_hr_bpm ? `\nhighest ${num(s.max_hr_bpm)} bpm` : ""}`}))
  ]
})) : html`<p class="card-note">No heart rate recorded for these sessions (often the case when an app other than the Watch logged them).</p>`);
```

</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Intensity</h3><span class="card-note">minutes in each heart-rate zone</span></div>

```js
const zoned = S.filter((s) => d3.sum(s.zones) > 0);
const zoneRows = (rows, key) => rows.flatMap((r) => r.zones.map((m, i) => ({key: r[key], zone: `Zone ${i + 1}`, min: m, r})));
const perSession = zoned.length <= 60;
const zm = perSession
  ? zoneRows(zoned.map((s, i) => ({...s, idx: i})), "idx")
  : d3.rollups(zoned, (v) => [0, 1, 2, 3, 4].map((i) => d3.sum(v, (s) => s.zones[i])), (s) => +d3.utcMonth(s.date))
      .flatMap(([m, z]) => z.map((min, i) => ({key: new Date(m), zone: `Zone ${i + 1}`, min})));
const totals = [0, 1, 2, 3, 4].map((i) => d3.sum(zoned, (s) => s.zones[i]));
const all = d3.sum(totals);
display(zoned.length ? html`<p class="insight">${totals.map((t, i) => html`${i ? " · " : ""}zone ${i + 1} <b>${num((100 * t) / all)}%</b>`)}</p>` : html`<p class="card-note">No heart-rate zones for these sessions.</p>`);
display(zoned.length ? resize((width) => Plot.plot({
  ...BASE, width, height: 200,
  x: perSession ? {type: "band", axis: null, padding: 0.15} : {type: "utc", label: null},
  y: {grid: true, label: null, tickFormat: (v) => `${v}`},
  color: {domain: ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5"], range: ZC},
  marks: [
    perSession
      ? Plot.barY(zm, {x: "key", y: "min", fill: "zone", order: "z"})
      : Plot.rectY(zm, Plot.stackY({x1: "key", x2: (d) => d3.utcMonth.offset(d.key, 1), y: "min", fill: "zone", insetLeft: 0.5, insetRight: 0.5})),
    Plot.tip(zm, Plot.pointer(perSession ? Plot.stackY({x: "key", y: "min", fill: "zone", title: (d) => `${date(d.r.d)}\n${d.zone}: ${hm(d.min)}`}) : Plot.stackY({x1: "key", x2: (d) => d3.utcMonth.offset(d.key, 1), y: "min", fill: "zone", title: (d) => `${month(d.key)}\n${d.zone}: ${hm(d.min)}`})))
  ]
})) : html``);
display(zoned.length ? html`<div class="legend">${ZC.map((c, i) => html`<span class="legend-item"><span class="swatch" style="background:${c}"></span>Zone ${i + 1}</span>`)}<span class="legend-item">${perSession ? "one bar per session, oldest first" : "per month"}</span></div>` : html``);
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">When</h3><span class="card-note">sessions by weekday and start time</span></div>

```js
const cells = d3.rollups(S, (v) => v.length, (s) => s.dow, (s) => Math.floor(s.hour)).flatMap(([dow, hs]) => hs.map(([h, n]) => ({dow: DOW[dow], h, n})));
const topDow = d3.greatest(d3.rollups(S, (v) => v.length, (s) => s.dow), (d) => d[1]);
const medHour = d3.median(S, (s) => s.hour);
display(html`<p class="insight">Most often on <b>${["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"][topDow[0]]}</b>; half the sessions start before <b>${String(Math.floor(medHour)).padStart(2, "0")}:${String(Math.round((medHour % 1) * 60)).padStart(2, "0")}</b>.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 200, marginLeft: 40,
  x: {domain: d3.range(0, 24), label: null, tickFormat: (h) => (h % 3 ? "" : `${String(h).padStart(2, "0")}h`)},
  y: {domain: DOW, label: null},
  marks: [
    Plot.cell(DOW.flatMap((d) => d3.range(0, 24).map((h) => ({dow: d, h}))), {x: "h", y: "dow", fill: "var(--grid)", inset: 1, rx: 2}),
    Plot.cell(cells, {x: "h", y: "dow", fill: color, fillOpacity: (d) => 0.2 + 0.8 * (d.n / d3.max(cells, (c) => c.n)), inset: 1, rx: 2}),
    Plot.tip(cells, Plot.pointer({x: "h", y: "dow", title: (d) => `${d.dow} ${String(d.h).padStart(2, "0")}:00–${String(d.h + 1).padStart(2, "0")}:00\n${plural(d.n, "session")}`}))
  ]
})));
```

</div>
</div>

```js
const MEASURES = [
  {key: "distance_km", label: "Distance", f: (v) => `${num(v, v < 10 ? 2 : 1)} km`},
  {key: "speedv", label: K.speed === "speed" ? "Speed" : K.speed === "swim" ? "Pace per 100 m" : "Pace", f: speedFmt, reverse: K.speed !== "speed", tick: K.speed === "pace" ? (v) => pace(v).replace(" /km", "") : K.speed === "swim" ? mmss : undefined},
  {key: "active_energy_kcal", label: "Active energy", f: (v) => `${num(v)} kcal`},
  {key: "avg_mets", label: "Average METs", f: (v) => num(v, 1)},
  {key: "trimp", label: "Training load (TRIMP)", f: (v) => num(v)},
  {key: "effort_score", label: "Effort score (1–10)", f: (v) => num(v, 1)},
  {key: "elevation_gain_m", label: "Climb", f: (v) => `${num(v)} m`},
  {key: "strength_volume_kg", label: "Weight lifted", f: (v) => `${num(v)} kg`},
  {key: "step_count", label: "Steps", f: (v) => num(v)},
  {key: "weather_temperature_c", label: "Temperature at the start", f: (v) => `${num(v)} °C`}
].filter((m) => K.speed || m.key !== "speedv").filter((m) => values(m.key).length >= 2);
```

${MEASURES.length ? html`<h2>More measures</h2>` : ""}

```js
display(html`<div class="grid grid-cols-3">${MEASURES.map((m) => {
  const rows = S.filter((s) => s[m.key] != null);
  const mid = d3.median(rows, (s) => s[m.key]);
  return html`<div class="card">
    <div class="card-head"><h3 class="card-title">${m.label}</h3><span class="card-note">median <b style="color:var(--ink)">${m.f(mid)}</b> · ${plural(rows.length, "session")}</span></div>
    ${resize((width) => Plot.plot({
      ...BASE, width, height: 140, marginLeft: 44, marginTop: 8,
      x: {type: "utc", ticks: 3},
      // With many sessions, a few odd ones (a walk paused for an hour) would flatten the rest.
      y: {grid: true, label: null, ticks: 3, reverse: m.reverse, zero: false, tickFormat: m.tick, clamp: true,
        domain: rows.length > 20 ? d3.extent([d3.quantile(rows, 0.01, (s) => s[m.key]), d3.quantile(rows, 0.99, (s) => s[m.key])]) : undefined},
      marks: [
        Plot.ruleY([mid], {stroke: "var(--ink-2)", strokeDasharray: "4 3"}),
        Plot.dot(rows, {x: "date", y: m.key, r: rows.length > 200 ? 1.5 : 2.6, fill: color, fillOpacity: rows.length > 200 ? 0.45 : 0.85}),
        Plot.tip(rows, Plot.pointer({x: "date", y: m.key, title: (s) => `${date(s.d)}\n${m.f(s[m.key])}`}))
      ]
    }))}
  </div>`;
})}</div>`);
```

## Sessions

<div class="card">
<div class="card-head"><h3 class="card-title">Every ${K.label.toLowerCase()} session</h3><span class="card-note">newest first · pick one to open it below</span></div>

```js
const newest = S.slice().reverse();
const COLS = [
  ["d", "Date", (v) => date(v)],
  ["start", "Start", (v) => clockOf(v)],
  ["duration_min", "Duration", (v) => hm(v)],
  ["distance_km", "Distance", (v) => (v == null ? "–" : `${num(v, 2)} km`)],
  ["speedv", K.speed === "speed" ? "Speed" : "Pace", (v) => (v == null ? "–" : speedFmt(v))],
  ["active_energy_kcal", "kcal", (v) => (v == null ? "–" : num(v))],
  ["avg_hr_bpm", "Avg HR", (v) => (v == null ? "–" : num(v))],
  ["max_hr_bpm", "Max HR", (v) => (v == null ? "–" : num(v))],
  ["trimp", "TRIMP", (v) => (v == null ? "–" : num(v))],
  ["effort_score", "Effort", (v) => (v == null ? "–" : num(v, 1))],
  ["avg_mets", "METs", (v) => (v == null ? "–" : num(v, 1))],
  ["weather_temperature_c", "°C", (v) => (v == null ? "–" : num(v))],
  ["source_name", "Recorded by", (v) => v]
].filter(([k]) => k === "d" || k === "start" || k === "duration_min" || k === "source_name" || S.some((s) => s[k] != null));
const picked = view(Inputs.table(newest, {
  columns: COLS.map(([k]) => k),
  header: Object.fromEntries(COLS.map(([k, h]) => [k, h])),
  format: Object.fromEntries(COLS.map(([k, , f]) => [k, f])),
  multiple: false,
  value: newest.find((s) => s.id === params.get("id")) ?? newest[0],
  required: true,
  rows: 12
}));
```

</div>

```js
const s = picked ?? newest[0];
setParams({type: kindKey, id: s.id});
const others = S.filter((o) => o.id !== s.id);
// Where this session sits among the others of its kind (needs a few to compare with).
const compare = [
  ["duration_min", "longer", "shorter"],
  ["avg_hr_bpm", "a higher average heart rate", "a lower average heart rate"],
  ["active_energy_kcal", "more energy", "less energy"],
  ["distance_km", "further", "shorter in distance"]
].map(([key, up, down]) => {
  const vs = others.map((o) => o[key]).filter((v) => v != null);
  if (s[key] == null || vs.length < 4) return null;
  const below = vs.filter((v) => v < s[key]).length / vs.length;
  return below >= 0.5 ? `${up} than ${num(100 * below)}%` : `${down} than ${num(100 * (1 - below))}%`;
}).filter(Boolean);
const stats = [
  ["Duration", hm(s.duration_min), s.elapsed_min && s.elapsed_min - s.duration_min >= 1 ? `${hm(s.elapsed_min - s.duration_min)} paused` : ""],
  s.distance_km != null ? ["Distance", `${num(s.distance_km, 2)} km`, s.speedv != null ? speedFmt(s.speedv) : ""] : null,
  s.active_energy_kcal != null ? ["Active energy", `${num(s.active_energy_kcal)} kcal`, ""] : null,
  s.avg_hr_bpm != null ? ["Heart rate", `${num(s.avg_hr_bpm)} bpm`, `${s.min_hr_bpm ? `${num(s.min_hr_bpm)}–` : "up to "}${num(s.max_hr_bpm)} bpm`] : null,
  s.trimp != null ? ["Training load", num(s.trimp), "TRIMP"] : null,
  s.effort_score != null ? ["Effort", num(s.effort_score, 1), "Apple, 1–10"] : null,
  s.avg_mets != null ? ["Intensity", `${num(s.avg_mets, 1)} METs`, ""] : null,
  s.elevation_gain_m != null ? ["Climb", `${num(s.elevation_gain_m)} m`, ""] : null,
  s.strength_volume_kg != null ? ["Weight lifted", `${num(s.strength_volume_kg)} kg`, ""] : null,
  s.step_count != null ? ["Steps", num(s.step_count), ""] : null,
  s.weather_temperature_c != null ? ["Weather", `${num(s.weather_temperature_c)} °C`, s.weather_humidity_pct != null ? `${num(s.weather_humidity_pct)}% humidity` : ""] : null,
  s.lap_length_m != null ? ["Pool", `${num(s.lap_length_m)} m lanes`, ""] : null
].filter(Boolean);
```

<div class="card">
<div class="card-head"><h3 class="card-title">${K.label}, ${date(s.d)} at ${clockOf(s.start)}</h3><span class="card-note">recorded by ${s.source_name}${s.kind.startsWith("Running") ? html` · <a href="./running.html?run=${s.id}">open in Running</a>` : ""}</span></div>

```js
display(compare.length ? html`<p class="insight">Compared with your other ${plural(others.length, `${K.label.toLowerCase()} session`)}: ${compare.join(", ")} of them.</p>` : html``);
display(html`<div class="totals">${stats.map(([label, value, sub]) => html`<div class="total"><span class="total-value">${value}</span><span class="total-label">${label}</span>${sub ? html`<span class="card-note" style="font-size:11.5px">${sub}</span>` : ""}</div>`)}</div>`);
```

```js
const series = (HR[s.id] ?? []).map((hr, m) => ({m, hr}));
const known = series.filter((p) => p.hr != null);
const sparse = known.length < series.length * 0.5;
const lo = d3.min(known, (p) => p.hr) - 6, hi = d3.max(known, (p) => p.hr) + 6;
const bands = (s.zone_lo ?? []).map((z, i, a) => ({zone: i + 1, y1: Math.max(z, lo), y2: Math.min(a[i + 1] ?? hi, hi)})).filter((b) => b.y2 > b.y1);
display(known.length < 2 ? html`<p class="card-note">No heart-rate curve for this session.</p>` : resize((width) => Plot.plot({
  ...BASE, width, height: 240,
  x: {label: null, tickFormat: (m) => `${m} min`, domain: [0, Math.max(series.length - 1, s.elapsed_min ?? 0)]},
  y: {grid: true, label: null, domain: [lo, hi]},
  marks: [
    Plot.rectY(bands, {x1: 0, x2: series.length - 1, y1: "y1", y2: "y2", fill: (b) => ZC[b.zone - 1], fillOpacity: 0.16}),
    Plot.text(bands, {x: series.length - 1, y: (b) => (b.y1 + b.y2) / 2, text: (b) => `Z${b.zone}`, textAnchor: "end", dx: -4, fill: "var(--muted)", fontSize: 10}),
    Plot.line(series, {x: "m", y: "hr", stroke: color, strokeWidth: 1.8}),
    sparse ? Plot.dot(known, {x: "m", y: "hr", r: 2.4, fill: color}) : null,
    Plot.tip(known, Plot.pointerX({x: "m", y: "hr", title: (p) => `minute ${p.m}\n${p.hr} bpm`}))
  ]
})));
display(known.length >= 2 ? html`<p class="source">Heart rate per minute${bands.length ? "; shading: the session's own heart-rate zones" : ""}${sparse ? ". The Watch took few readings in this session, so the line has gaps" : ""}.</p>` : html``);
```

```js
if (s.route_id) {
  const tracks = await TRACKS.json();
  const enc = tracks[s.route_id];
  if (enc) {
    const pts = decode(enc);
    const m = createMap({height: 320, center: pts[0], zoom: 14});
    display(m.element);
    const line = m.L.polyline(pts, {color: getComputedStyle(document.documentElement).getPropertyValue("--running").trim() || "#ea580c", weight: 4, opacity: 0.9, renderer: m.renderer}).addTo(m.map);
    requestAnimationFrame(() => m.map.fitBounds(line.getBounds(), {padding: [20, 20]}));
    invalidation.then(() => m.map.remove());
  }
}
```

</div>
