---
title: Every day
---

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {calendar} from "./components/calendar.js";
import {num, pct, hm, clock, date, plural} from "./components/format.js";
import {rangePicker} from "./components/range.js";
const meta = FileAttachment("data/meta.json").json();
const X = FileAttachment("data/explorer.json").json();
const daily = FileAttachment("data/daily.parquet").parquet();
```

```js
const ALL = Array.from(daily, (r) => r.toJSON());
const COLS = new Map(X.columns.map((c) => [c.name, c]));
const NUMERIC = X.columns.filter((c) => c.kind === "number").map((c) => c.name);
const FMT = {int: (v) => num(v), dec1: (v) => num(v, 1), dec2: (v) => num(v, 2), pct: (v) => pct(v, 1), clock: (v) => clock(v), dur: (v) => hm(v)};
const fmt = (name) => FMT[COLS.get(name)?.format] ?? ((v) => num(v, 1));
const unit = (name) => COLS.get(name)?.unit ?? "";
const show = (name, v) => (v == null ? "–" : `${fmt(name)(v)}${unit(name) ? ` ${unit(name)}` : ""}`);
const label = (name) => COLS.get(name)?.label ?? name;
const GROUP_COLOR = {Wear: "var(--activity)", Activity: "var(--activity)", Rings: "var(--activity)", Walking: "var(--activity)", Heart: "var(--heart)", Sleep: "var(--sleep)", Workouts: "var(--training)", Sound: "var(--places)"};
const colorOf = (name) => GROUP_COLOR[COLS.get(name)?.group] ?? "var(--ink-2)";
const iso = (d) => d.toISOString().slice(0, 10);
```

${pageHeader({eyebrow: "Explorer", title: "Every day", subtitle: html`Any daily metric over any period: ${plural(ALL.length, "day")} from ${date(X.first)} to ${date(X.last)}. Filter the days, pick a metric, compare it with another, and download what you see.`, meta})}

```js
const r = view(rangePicker({first: X.first, last: X.last, value: "All"}));
```

<div class="filters">

```js
const daysOf = view(Inputs.radio(["All", "Weekdays", "Weekends"], {label: "Days", value: "All"}));
```

```js
const place = view(Inputs.radio(["Anywhere", "Home", "Away"], {label: "Where", value: "Anywhere"}));
```

```js
const validOnly = view(Inputs.toggle({label: "Valid wear days only", value: false}));
```

</div>

<div class="filters">

```js
const A = view(Inputs.select(NUMERIC, {label: "Metric", value: "steps", format: (n) => `${COLS.get(n).group} · ${label(n)}`}));
```

</div>

```js
const lo = r.from, hi = r.to;
const rows = ALL.filter((r) =>
  r.local_date >= lo && r.local_date <= hi &&
  (daysOf === "All" || (daysOf === "Weekends") === r.is_weekend) &&
  (place === "Anywhere" || (place === "Away") === r.is_non_default_tz) &&
  (!validOnly || r.is_valid_wear_day)
);
const withA = rows.filter((r) => r[A] != null);
const vals = withA.map((r) => r[A]).sort(d3.ascending);
const q = (p) => d3.quantileSorted(vals, p);
```

<div class="card">
<div class="card-head"><h3 class="card-title">${label(A)}</h3><span class="card-note">${COLS.get(A).doc}</span></div>

```js
display(html`<div class="totals">
  ${[
    ["Days in the filter", num(rows.length)],
    ["Days with a value", num(withA.length)],
    ["Median", show(A, q(0.5))],
    ["Middle half", vals.length ? `${fmt(A)(q(0.25))} to ${fmt(A)(q(0.75))}` : "–"],
    ["Lowest", show(A, vals[0])],
    ["Highest", show(A, vals.at(-1))]
  ].map(([k, v]) => html`<div class="total"><div class="total-value">${v}</div><div class="total-label">${k}</div></div>`)}
</div>`);
```

```js
const series = withA.map((r) => ({date: new Date(r.local_date), v: r[A], r}));
display(series.length < 2 ? html`<p class="card-note">Not enough days with a value in this filter.</p>` : resize((width) => Plot.plot({
  ...BASE, width, height: 260,
  x: {type: "utc"},
  y: {grid: true, label: null, zero: false, tickFormat: fmt(A), domain: vals.length > 20 ? [q(0.005), q(0.995)] : undefined, clamp: true},
  marks: [
    Plot.dot(series, {x: "date", y: "v", r: 1.6, fill: colorOf(A), fillOpacity: 0.35}),
    Plot.lineY(series, Plot.windowY({k: 28, reduce: "median", anchor: "end"}, {x: "date", y: "v", stroke: colorOf(A), strokeWidth: 1.8})),
    Plot.tip(series, Plot.pointerX({x: "date", y: "v", title: (d) => `${date(d.r.local_date)}\n${show(A, d.v)}`}))
  ]
})));
```

<p class="source">Dots: days. Line: median of the last 28 days with a value.</p>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Calendar</h3><span class="card-note">darker = higher, from the 2nd to the 98th percentile of the filter</span></div>

```js
display(withA.length ? resize((width) => calendar(withA.map((r) => ({local_date: r.local_date, value: r[A]})), {width, color: colorOf(A), format: fmt(A), label: unit(A), domain: [q(0.02), q(0.98)]})) : html`<p class="card-note">No days with a value.</p>`);
```

</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Distribution</h3><span class="card-note">days per bin</span></div>

```js
display(vals.length < 2 ? html`<p class="card-note">Not enough values.</p>` : resize((width) => Plot.plot({
  ...BASE, width, height: 260,
  x: {label: null, tickFormat: fmt(A), domain: [q(0.005), q(0.995)], clamp: true},
  y: {grid: true, label: null},
  marks: [
    Plot.rectY(withA, Plot.binX({y: "count"}, {x: (r) => Math.min(Math.max(r[A], q(0.005)), q(0.995)), fill: colorOf(A), fillOpacity: 0.8, thresholds: 30, insetLeft: 0.5, insetRight: 0.5})),
    Plot.ruleX([q(0.5)], {stroke: "var(--ink)", strokeDasharray: "3 3"}),
    Plot.text([q(0.5)], {x: (d) => d, frameAnchor: "top", dy: -2, text: (d) => `median ${fmt(A)(d)}`, fill: "var(--muted)", fontSize: 10.5, textAnchor: "start", dx: 4}),
    Plot.ruleY([0])
  ]
})));
```

<p class="source">The most extreme 0.5% at each end are folded into the outer bins.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">${label(A)} against another measure</h3><span class="card-note">same day</span></div>

<div class="filters">

```js
const B = view(Inputs.select(NUMERIC, {label: "Against", value: "sleep_asleep_min", format: (n) => `${COLS.get(n).group} · ${label(n)}`}));
```

</div>

```js
const pairs = rows.filter((r) => r[A] != null && r[B] != null);
// Spearman rank correlation: robust to outliers and to non-linear but monotonic relations.
function ranks(xs) {
  const order = d3.range(xs.length).sort((i, j) => xs[i] - xs[j]);
  const r = new Array(xs.length);
  for (let k = 0; k < order.length;) {
    let m = k;
    while (m + 1 < order.length && xs[order[m + 1]] === xs[order[k]]) m++;
    for (let t = k; t <= m; t++) r[order[t]] = (k + m) / 2;
    k = m + 1;
  }
  return r;
}
function spearman(ps) {
  if (ps.length < 10) return null;
  const ra = ranks(ps.map((r) => r[A])), rb = ranks(ps.map((r) => r[B]));
  const ma = d3.mean(ra), mb = d3.mean(rb);
  const cov = d3.sum(ra, (v, i) => (v - ma) * (rb[i] - mb));
  return cov / Math.sqrt(d3.sum(ra, (v) => (v - ma) ** 2) * d3.sum(rb, (v) => (v - mb) ** 2));
}
const rho = A === B ? null : spearman(pairs);
const strength = (r) => (Math.abs(r) < 0.1 ? "no clear relation" : Math.abs(r) < 0.3 ? "a weak" : Math.abs(r) < 0.5 ? "a moderate" : "a strong");
display(html`<p class="insight">${pairs.length < 10 ? html`Only ${plural(pairs.length, "day")} with both values.` : rho == null ? "Pick two different metrics." : html`<b>${plural(pairs.length, "day")}</b> with both. Rank correlation <b>${num(rho, 2)}</b>: ${strength(rho)}${Math.abs(rho) < 0.1 ? "" : ` ${rho > 0 ? "positive" : "negative"} relation`}.`}</p>`);
const xq = pairs.map((r) => r[B]).sort(d3.ascending), yq = pairs.map((r) => r[A]).sort(d3.ascending);
display(pairs.length < 2 ? "" : resize((width) => Plot.plot({
  ...BASE, width, height: 260,
  x: {label: null, tickFormat: fmt(B), domain: [d3.quantileSorted(xq, 0.005), d3.quantileSorted(xq, 0.995)], clamp: true},
  y: {grid: true, label: null, tickFormat: fmt(A), domain: [d3.quantileSorted(yq, 0.005), d3.quantileSorted(yq, 0.995)], clamp: true},
  marks: [
    Plot.dot(pairs, {x: B, y: A, r: 1.8, fill: colorOf(A), fillOpacity: 0.3}),
    Plot.line(pairs, Plot.binX({y: "median", filter: (bin) => bin.length >= 5}, {x: B, y: A, thresholds: 12, stroke: "var(--ink)", strokeWidth: 1.6, marker: "dot"})),
    Plot.tip(pairs, Plot.pointer({x: B, y: A, title: (r) => `${date(r.local_date)}\n${label(A)}: ${show(A, r[A])}\n${label(B)}: ${show(B, r[B])}`}))
  ]
})));
```

<p class="source">Line: median of ${label(A).toLowerCase()} in 12 bins of ${label(B).toLowerCase()} (bins with 5+ days). A correlation in your own data is not a cause.</p>
</div>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Days</h3><span class="card-note">the filtered days · click a header to sort</span></div>

<div class="filters">

```js
// Tick any number of extra columns; the panel folds away when not needed.
const extraInput = Inputs.checkbox(NUMERIC.filter((n) => n !== A && n !== B), {value: [], format: (n) => html`<span class="card-note">${COLS.get(n).group}</span> ${label(n)}`});
display(html`<details class="columns-picker"><summary>More columns</summary>${extraInput}</details>`);
```

```js
const extra = Generators.input(extraInput);
```

```js
display(Inputs.button(`Download ${plural(rows.length, "day")} as CSV`, {reduce: () => {
  const blob = new Blob([d3.csvFormat(rows)], {type: "text/csv"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `pouls-days-${lo}-to-${hi}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}}));
```

</div>

```js
const shown = ["local_date", A, ...(B === A ? [] : [B]), ...extra];
display(Inputs.table(rows.slice().reverse(), {
  columns: shown,
  header: Object.fromEntries(shown.map((n) => [n, n === "local_date" ? "Date" : `${label(n)}${unit(n) ? ` (${unit(n)})` : ""}`])),
  format: Object.fromEntries(shown.map((n) => [n, n === "local_date" ? (d) => date(d) : (v) => (v == null ? "–" : fmt(n)(v))])),
  rows: 16,
  select: false
}));
```

<p class="source">The CSV holds every column of mart_daily for the filtered days, in warehouse units (fractions for percentages, minutes, hours after midnight for times). See Notes for definitions.</p>
</div>
