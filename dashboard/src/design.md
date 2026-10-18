---
title: Design system
---

```js
import {pageHeader, card} from "./components/page.js";
import {kpiTile, tiles, changeChip, referenceChip} from "./components/tile.js";
import {BASE, LABEL_MARGIN, axes, chartHeight, noData, referenceBand, referenceLine, labelledLine} from "./components/marks.js";
import {num, hm, clock, signed, pct} from "./components/format.js";
```

${pageHeader({eyebrow: "Internal", title: "Design system", subtitle: "Components and colours, with sample values. Not linked from the sidebar."})}

## Colours

```js
const SWATCHES = [
  ["Activity", "--activity"], ["Heart", "--heart"], ["Sleep", "--sleep"], ["Training", "--training"],
  ["Running", "--running"], ["Places", "--places"], ["Strength", "--strength"], ["Better", "--better"], ["Deep", "--stage-deep"], ["Core", "--stage-core"],
  ["REM", "--stage-rem"], ["Awake", "--stage-awake"], ["Good", "--good"], ["Bad", "--bad"]
];
display(html`<div class="legend">${SWATCHES.map(([n, v]) => html`<span class="legend-item"><span class="swatch" style="background:var(${v});width:16px;height:16px"></span>${n}</span>`)}</div>`);
```

## Tiles

```js
const wave = (n, base, amp, noise) => Array.from({length: n}, (_, i) => base + amp * Math.sin(i / 2) + noise * Math.cos(i * 1.7));
display(tiles([
  kpiTile({label: "Steps per day", domain: "activity", value: num(8500), changes: [{label: "vs prev 28 d", delta: 6.2, text: "+6%", better: "higher"}, {label: "vs last year", delta: -3.1, text: "−3%", better: "higher"}], reference: {text: "In the 8–10k band", status: "in"}, spark: {values: wave(12, 8300, 600, 200)}, foot: "28-day median, valid wear days"}),
  kpiTile({label: "Resting heart rate", domain: "heart", value: "58", unit: "bpm", changes: [{label: "vs prev 28 d", delta: -1.5, text: "−1 bpm", better: "lower"}, {label: "vs last year", delta: 0.4, text: "+0.4", better: "lower", threshold: 0.5}], reference: {text: "Within 60–100 bpm", status: "out"}, spark: {values: wave(12, 59, 1.5, 0.6)}}),
  kpiTile({label: "Time asleep", domain: "sleep", value: hm(450), changes: [{label: "vs prev 28 d", delta: 12, text: "+12 min", better: "higher"}], reference: {text: "Recommended 7–9 h", status: "in"}, spark: {values: wave(12, 440, 20, 8)}}),
  kpiTile({label: "Training per week", domain: "training", value: "4.0", unit: "h", changes: [{label: "vs prev 28 d", delta: null, text: "", better: "higher"}], spark: {values: wave(12, 4, 1, 0.4)}}),
  kpiTile({label: "Bedtime", domain: "sleep", value: clock(22.5), changes: [{label: "vs prev 28 d", delta: -0.2, text: "12 min earlier", better: null}]}),
  kpiTile({label: "Running", domain: "running", value: num(30, 1), unit: "km", foot: "Last 28 days"})
]));
```

## A chart in a card

```js
const start = Date.UTC(2023, 0, 1);
const series = Array.from({length: 40}, (_, i) => ({date: new Date(start + i * 30.4 * 864e5), value: i > 14 && i < 18 ? null : 58 + 3 * Math.sin(i / 5) - i * 0.03}));
const other = series.map((d, i) => ({...d, series: "Walking HR", value: d.value == null ? null : d.value + 40 + Math.cos(i / 3)}));
const both = [...series.map((d) => ({...d, series: "Resting HR"})), ...other];
```

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Resting and walking heart rate</h3><span class="card-note">monthly medians, sample data</span></div>
<p class="insight">Resting heart rate <b>2 bpm lower</b> than a year ago, below the adult reference range.</p>

```js
display(resize((width) => Plot.plot({
  ...BASE, width, height: chartHeight(width), marginRight: LABEL_MARGIN,
  y: {label: null, domain: [40, 110]},
  x: {type: "utc"},
  marks: [
    ...referenceBand(60, 100, {label: "Adult resting range 60–100"}),
    ...noData([{start: series[15].date, end: series[17].date}]),
    ...axes({yFormat: (d) => `${d}`}),
    ...labelledLine(both, {x: "date", y: "value", z: "series", stroke: (d) => (d.series === "Resting HR" ? "var(--heart)" : "var(--running)"), label: "series"}),
    Plot.tip(both, Plot.pointerX({x: "date", y: "value", title: (d) => `${d.series}: ${num(d.value, 1)} bpm`}))
  ]
})));
```

<p class="source">Sample data. Shaded months: no data.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Chips and a table</h3></div>

```js
display(html`<div class="tile-chips" style="margin-bottom:12px">
  ${changeChip({label: "vs prev", delta: 4, text: "+4%", better: "higher"})}
  ${changeChip({label: "vs prev", delta: 4, text: "+4%", better: "lower"})}
  ${changeChip({label: "vs prev", delta: 0.1, text: "+0.1", better: "higher", threshold: 0.5})}
  ${referenceChip({text: "In range", status: "in"})}
  ${referenceChip({text: "Below range", status: "out"})}
</div>`);
display(html`<table class="t"><thead><tr><th>Year</th><th class="num">Steps/day</th><th class="num">Resting HR</th><th class="num">Asleep</th></tr></thead>
<tbody>${[[2023, 8000, 62.0, 440], [2024, 8500, 61.0, 450], [2025, 9000, 60.0, 460]].map(([y, s, r, a]) => html`<tr><td>${y}</td><td class="num">${num(s)}</td><td class="num">${num(r, 1)}</td><td class="num">${hm(a)}</td></tr>`)}</tbody></table>`);
```

</div>
</div>
