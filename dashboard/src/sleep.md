---
title: Sleep
---

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {barcode, compact, STAGE_COLOR} from "./components/barcode.js";
import {num, pct, hm, clock, month, date, signed, plural} from "./components/format.js";
import {rangePicker, within, spanDays, describe} from "./components/range.js";
const meta = FileAttachment("data/meta.json").json();
const S = FileAttachment("data/sleep.json").json();
const BC = FileAttachment("data/barcode.json").json();
```

```js
const D = (s) => new Date(s);
const refs = S.references;
const refNow = (key, day) => (refs[key] ?? []).filter((b) => b.valid_from <= day && b.valid_to >= day);
const target = (key) => refNow(key, r.to).find((b) => b.is_target);
const med = (rows, key) => d3.median(rows, (d) => d[key]);
```

${pageHeader({eyebrow: "Nights", title: "Sleep", subtitle: "How long, how regular and how deep, and what goes with better nights. Each night belongs to the day you wake up.", meta})}

```js
const r = view(rangePicker({first: meta.first_day, last: meta.data_through, value: "12 months"}));
```

```js
const N = S.nights.filter((n) => within(r, n.d));
// Charts group nights by week for ranges up to six months, by month beyond.
const weekly = spanDays(r) <= 183;
const bucketOf = (n) => (weekly ? d3.utcMonday.floor(D(n.d)) : D(`${n.d.slice(0, 7)}-01`));
const minNights = weekly ? 3 : S.min_nights;
const label = (d) => (weekly ? `week of ${date(d)}` : month(d));
const M = d3.rollups(N, (v) => v, (n) => +bucketOf(n)).filter(([, v]) => v.length >= minNights).map(([b, v]) => {
  const wd = v.filter((n) => !n.weekend), we = v.filter((n) => n.weekend), staged = v.filter((n) => n.staged);
  const midWd = med(wd, "mid"), midWe = med(we, "mid");
  return {
    date: new Date(b), nights: v.length,
    asleep_median: med(v, "asleep"), asleep_p25: d3.quantile(v, 0.25, (n) => n.asleep), asleep_p75: d3.quantile(v, 0.75, (n) => n.asleep),
    share_7h: d3.mean(v, (n) => (n.asleep >= 420 ? 1 : 0)), efficiency: med(v, "eff"),
    bed_weekday: med(wd, "bed"), bed_weekend: med(we, "bed"), wake_weekday: med(wd, "wake"), wake_weekend: med(we, "wake"),
    social_jetlag_min: midWd != null && midWe != null ? (midWe - midWd) * 60 : null,
    bedtime_variability_min: d3.median(v.filter((n) => n.dev != null), (n) => Math.abs(n.dev)),
    staged_nights: staged.length, deep: med(staged, "deep"), rem: med(staged, "rem"), core: med(staged, "core"), awake: med(staged, "awake")
  };
}).sort((a, b) => a.date - b.date);
const unit = weekly ? "weekly" : "monthly";
```

<div class="card">
<div class="card-head"><h3 class="card-title">Night by night</h3><span class="card-note">${plural(N.length, "night")}${N.length > 365 ? " · the last 365 shown" : ""}</span></div>

```js
const bars = BC.barcode.filter((x) => within(r, x.d)).slice(-365);
display(bars.length ? resize((width) => barcode(compact(bars, BC.stage_codes), {width})) : html`<p class="card-note">No nights in this range.</p>`);
```

<p class="source">Bars run from falling asleep (or getting into bed) to waking up, coloured by sleep stage. The vertical line is midnight. Stages are recorded from ${month(S.stages_from)}; earlier nights show the whole session.</p>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Time asleep</h3><span class="card-note">${unit} median · band: middle half of nights</span></div>

```js
const sdRef = target("sleep_duration");
display(html`<p class="insight">In ${describe(r)}: median <b>${hm(med(N, "asleep"))}</b>; <b>${pct(d3.mean(N, (n) => (n.asleep >= 420 ? 1 : 0)))}</b> of nights reached 7 hours${sdRef ? html` (recommended for adults: ${sdRef.label.toLowerCase()})` : ""}.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 250,
  x: {type: "utc"},
  y: {grid: true, label: null, tickFormat: (v) => `${Math.floor(v / 60)}h${String(Math.round(v % 60)).padStart(2, "0")}`},
  marks: [
    sdRef ? Plot.rectY([sdRef], {y1: (b) => b.lo, y2: (b) => b.hi, fill: "var(--reference-line)", fillOpacity: 0.14}) : null,
    Plot.areaY(M, {x: "date", y1: "asleep_p25", y2: "asleep_p75", fill: "var(--sleep)", fillOpacity: 0.15, curve: "step-after"}),
    Plot.line(M, {x: "date", y: "asleep_median", stroke: "var(--sleep)", strokeWidth: 1.8, curve: "step-after"}),
    Plot.tip(M, Plot.pointerX({x: "date", y: "asleep_median", title: (d) => `${label(d.date)}\nmedian ${hm(d.asleep_median)}\nmiddle half ${hm(d.asleep_p25)}–${hm(d.asleep_p75)}\n${pct(d.share_7h)} of ${d.nights} nights ≥ 7 h`}))
  ]
})));
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Sleep efficiency</h3><span class="card-note">${unit} median: asleep / (asleep + awake)</span></div>

```js
const effRef = target("sleep_efficiency");
display(html`<p class="insight">Median <b>${pct(med(N, "eff"))}</b>${effRef ? html`; ${effRef.label.toLowerCase()} is the usual mark of good sleep quality` : ""}.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 250,
  x: {type: "utc"},
  y: {grid: true, label: null, tickFormat: (v) => pct(v), domain: [Math.min(0.75, d3.min(M, (d) => d.efficiency) ?? 0.75), 1]},
  marks: [
    effRef ? Plot.rectY([effRef], {y1: (b) => b.lo, y2: (b) => b.hi ?? 1, fill: "var(--reference-line)", fillOpacity: 0.14}) : null,
    Plot.line(M, {x: "date", y: "efficiency", stroke: "var(--sleep)", strokeWidth: 1.8}),
    Plot.tip(M, Plot.pointerX({x: "date", y: "efficiency", title: (d) => `${label(d.date)}\n${pct(d.efficiency, 1)}`}))
  ]
})));
```

<p class="source">Share of the sleep session spent asleep. Before sleep stages (no awake segments recorded) it is asleep time over the session span.</p>
</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">When I sleep</h3><span class="card-note">${unit} median bedtime and wake-up</span></div>

```js
const clockRows = M.flatMap((d) => [
  {date: d.date, v: d.bed_weekday, s: "Bedtime, weekdays", c: "var(--sleep)", dash: null},
  {date: d.date, v: d.bed_weekend, s: "Bedtime, weekends", c: "var(--sleep)", dash: "4 3"},
  {date: d.date, v: d.wake_weekday == null ? null : d.wake_weekday + 24, s: "Wake-up, weekdays", c: "var(--training)", dash: null},
  {date: d.date, v: d.wake_weekend == null ? null : d.wake_weekend + 24, s: "Wake-up, weekends", c: "var(--training)", dash: "4 3"}
]);
const wdN = N.filter((n) => !n.weekend), weN = N.filter((n) => n.weekend);
const jet = med(weN, "mid") != null && med(wdN, "mid") != null ? (med(weN, "mid") - med(wdN, "mid")) * 60 : null;
display(html`<p class="insight">In bed around <b>${clock(med(wdN, "bed"))}</b> on weekdays and <b>${clock(med(weN, "bed"))}</b> at weekends${jet != null ? html`; sleep shifts <b>${num(Math.abs(jet))} min</b> ${jet >= 0 ? "later" : "earlier"} at weekends (social jet lag)` : ""}.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 260,
  x: {type: "utc"},
  y: {grid: true, label: null, tickFormat: (v) => clock(v), reverse: true},
  marks: [
    ...["Bedtime, weekdays", "Bedtime, weekends", "Wake-up, weekdays", "Wake-up, weekends"].map((s) => {
      const rows = clockRows.filter((x) => x.s === s);
      return Plot.line(rows, {x: "date", y: "v", stroke: rows[0]?.c, strokeDasharray: rows[0]?.dash, strokeWidth: 1.6});
    }),
    Plot.tip(clockRows.filter((x) => x.v != null), Plot.pointer({x: "date", y: "v", title: (d) => `${label(d.date)}\n${d.s}: ${clock(d.v)}`}))
  ]
})));
display(html`<div class="legend"><span class="legend-item"><span class="swatch" style="background:var(--sleep)"></span>Bedtime</span><span class="legend-item"><span class="swatch" style="background:var(--training)"></span>Wake-up</span><span class="legend-item">solid: weekdays · dashed: weekends</span></div>`);
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Regularity</h3><span class="card-note">minutes</span></div>

```js
const reg = M.flatMap((d) => [
  {date: d.date, v: d.social_jetlag_min, s: "Social jet lag (weekend midpoint − weekday midpoint)"},
  {date: d.date, v: d.bedtime_variability_min, s: "Bedtime variability (median deviation from the previous week)"}
]).filter((x) => x.v != null);
display(html`<p class="insight">Bedtime typically differs by <b>${num(d3.median(N.filter((n) => n.dev != null), (n) => Math.abs(n.dev)))} min</b> from the previous week's median. Smaller is more regular.</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 260,
  x: {type: "utc"},
  y: {grid: true, label: null},
  color: {domain: [...new Set(reg.map((x) => x.s))], range: ["var(--sleep)", "var(--places)"]},
  marks: [
    Plot.ruleY([0], {stroke: "var(--border-strong)"}),
    Plot.line(reg, {x: "date", y: "v", stroke: "s", strokeWidth: 1.6}),
    Plot.tip(reg, Plot.pointerX({x: "date", y: "v", stroke: "s", title: (d) => `${label(d.date)}\n${d.s}: ${num(d.v)} min`}))
  ]
})));
display(html`<div class="legend"><span class="legend-item"><span class="swatch" style="background:var(--sleep)"></span>Social jet lag</span><span class="legend-item"><span class="swatch" style="background:var(--places)"></span>Bedtime variability</span></div>`);
```

</div>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Sleep stages</h3><span class="card-note">${unit} median share of time asleep (awake: share of the session)</span></div>

```js
const deepRef = target("deep_sleep_share"), remRef = target("rem_sleep_share");
const SM = M.filter((d) => d.staged_nights >= minNights);
const stageRows = SM.flatMap((d) => [["Deep", d.deep], ["REM", d.rem], ["Core", d.core], ["Awake", d.awake]].map(([stage, v]) => ({date: d.date, stage, v})));
const staged = N.filter((n) => n.staged);
display(staged.length ? html`<p class="insight">Deep <b>${pct(med(staged, "deep"))}</b>${deepRef ? html` (good: ${deepRef.label})` : ""}, REM <b>${pct(med(staged, "rem"))}</b>${remRef ? html` (good: ${remRef.label})` : ""}, core ${pct(med(staged, "core"))}, over ${plural(staged.length, "night")} with stages.</p>` : html`<p class="card-note">No nights with sleep stages in this range (stages start in ${month(S.stages_from)}).</p>`);
display(resize((width) => Plot.plot({
  ...BASE, width, height: 260, marginRight: 60,
  x: {type: "utc"},
  y: {grid: true, label: null, tickFormat: (v) => pct(v)},
  marks: [
    deepRef ? Plot.rectY([deepRef], {y1: "lo", y2: "hi", fill: "var(--stage-deep)", fillOpacity: 0.08}) : null,
    remRef ? Plot.rectY([remRef], {y1: "lo", y2: "hi", fill: "var(--stage-rem)", fillOpacity: 0.12}) : null,
    Plot.line(stageRows, {x: "date", y: "v", z: "stage", stroke: (d) => STAGE_COLOR[d.stage], strokeWidth: 1.8}),
    SM.length ? Plot.text(stageRows.filter((d) => +d.date === +SM.at(-1).date), {x: "date", y: "v", text: "stage", dx: 6, textAnchor: "start", fill: (d) => STAGE_COLOR[d.stage], fontWeight: 600}) : null,
    Plot.tip(stageRows, Plot.pointer({x: "date", y: "v", z: "stage", title: (d) => `${label(d.date)}\n${d.stage}: ${pct(d.v, 1)}`}))
  ]
})));
```

<p class="source">Watch sleep stages from ${month(S.stages_from)}. Consumer wearables estimate stages from movement and heart rate; they track laboratory sleep studies only approximately.</p>
</div>

## What goes with better nights

<p class="card-note">Each card splits the nights of the range into two groups and compares their medians: time asleep, efficiency, night-time HRV and the share of deep sleep. Days the Watch was barely worn are left out. These are associations in your own data, not causes; the night counts say how much each comparison rests on.</p>

```js
function diffChip(a, b, f, better = "higher", threshold = 0) {
  if (a == null || b == null) return "";
  const d = a - b;
  const tone = Math.abs(d) <= threshold ? "" : (d > 0) === (better === "higher") ? "good" : "bad";
  return html`<span class="chip ${tone}">${f(d)}</span>`;
}
const A = N.filter((n) => n.prev_valid);
const thirds = (key) => {
  const v = A.map((n) => n[key]).filter((x) => x != null).sort(d3.ascending);
  return v.length >= 6 ? [d3.quantileSorted(v, 1 / 3), d3.quantileSorted(v, 2 / 3)] : [null, null];
};
const [stepsLo, stepsHi] = thirds("prev_steps");
const [dayLo, dayHi] = thirds("prev_daylight");
const k = (v) => `${num(v / 1000, v < 10000 ? 1 : 0)}k steps`;
const worked = A.filter((n) => n.prev_workouts > 0);
const COMPARE = [
  {title: "After a workout day", about: "Nights after a day with at least one workout, against nights after a day without.", rows: A, test: (n) => (n.prev_workouts ?? 0) > 0, yes: "Workout day", no: "Rest day"},
  {title: "Late workouts", about: "Workout days only: nights after a workout that ended less than 3 hours before bedtime, against nights after an earlier one.", rows: worked, test: (n) => n.late_workout ?? null, yes: "< 3 h before bed", no: "Earlier"},
  {title: "After active days", about: "Nights after your most active third of days (by steps) against your least active third; the middle third is left out to sharpen the contrast.", rows: A.filter((n) => stepsLo != null && n.prev_steps != null && (n.prev_steps >= stepsHi || n.prev_steps <= stepsLo)), test: (n) => n.prev_steps >= stepsHi, yes: stepsHi != null ? `≥ ${k(stepsHi)}` : "Active", no: stepsLo != null ? `≤ ${k(stepsLo)}` : "Quiet"},
  {title: "After more daylight", about: "Nights after the third of days with the most time in daylight against the third with the least (the Watch measures daylight from September 2023).", rows: A.filter((n) => dayLo != null && n.prev_daylight != null && (n.prev_daylight >= dayHi || n.prev_daylight <= dayLo)), test: (n) => n.prev_daylight >= dayHi, yes: dayHi != null ? `≥ ${num(dayHi)} min` : "More", no: dayLo != null ? `≤ ${num(dayLo)} min` : "Less"},
  {title: "Away from home", about: "Nights spent in another time zone than home (or right after arriving), against nights at home.", rows: A, test: (n) => !!n.away, yes: "Away", no: "Home"},
  {title: "Weekend nights", about: "Friday and Saturday nights (waking up on Saturday or Sunday) against the other nights of the week.", rows: A, test: (n) => !!n.weekend, yes: "Weekend", no: "Weekday"}
];
const stats = (v) => ({nights: v.length, asleep: med(v, "asleep"), eff: med(v, "eff"), hrv: med(v, "hrv"), deep: med(v.filter((n) => n.staged), "deep")});
display(html`<div class="grid grid-cols-3">${COMPARE.map((c) => {
  const yes = stats(c.rows.filter((n) => c.test(n) === true)), no = stats(c.rows.filter((n) => c.test(n) === false));
  return html`<div class="card"><div class="card-head"><h3 class="card-title">${c.title}</h3></div>
    <p class="card-note" style="margin:0 0 8px">${c.about}</p>
    <table class="t">
      <thead><tr><th></th><th class="num">${c.yes}</th><th class="num">${c.no}</th><th class="num">Difference</th></tr></thead>
      <tbody>
        <tr><td>Nights</td><td class="num">${num(yes.nights)}</td><td class="num">${num(no.nights)}</td><td></td></tr>
        <tr><td>Asleep</td><td class="num">${hm(yes.asleep)}</td><td class="num">${hm(no.asleep)}</td><td class="num">${diffChip(yes.asleep, no.asleep, (d) => `${signed(d)} min`, "higher", 5)}</td></tr>
        <tr><td>Efficiency</td><td class="num">${pct(yes.eff, 1)}</td><td class="num">${pct(no.eff, 1)}</td><td class="num">${diffChip(yes.eff, no.eff, (d) => `${signed(d * 100, 1)} pt`, "higher", 0.005)}</td></tr>
        <tr><td>Night HRV</td><td class="num">${num(yes.hrv, 1)} ms</td><td class="num">${num(no.hrv, 1)} ms</td><td class="num">${diffChip(yes.hrv, no.hrv, (d) => `${signed(d, 1)} ms`, "higher", 1)}</td></tr>
        <tr><td>Deep share</td><td class="num">${pct(yes.deep, 1)}</td><td class="num">${pct(no.deep, 1)}</td><td class="num">${diffChip(yes.deep, no.deep, (d) => `${signed(d * 100, 1)} pt`, "higher", 0.005)}</td></tr>
      </tbody>
    </table></div>`;
})}</div>`);
```
