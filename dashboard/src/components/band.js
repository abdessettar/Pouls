/**
 * "Your normal" chart: daily values as faint dots, the 28-day median as the line, your normal range
 * (rolling 10th-90th percentile) as a band, and population reference bands behind everything.
 *
 * rows: [{d: "YYYY-MM-DD", v, m, lo, hi}]   refs: bands from mart_reference (valid_from/valid_to/lo/hi)
 */
import * as d3 from "npm:d3";
import * as Plot from "npm:@observablehq/plot";
import {BASE} from "./marks.js";
import {date} from "./format.js";

const D = (s) => new Date(s);

const ordinal = (n) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ({1: "st", 2: "nd", 3: "rd"})[n % 10] ?? "th"}`;

/**
 * Reference marks clipped to the x domain and to the bands' validity (they step with age groups).
 * Guideline bands (kind "range") are shaded: target bands darker, warning bands tinted. Percentile
 * tables are drawn as dotted lines at each percentile, labelled at the right ("50th"). A metric with
 * both shows its guideline bands only; the percentile goes in the text.
 */
export function referenceMarks(refs, {x0, x1, yDomain, labels = true}) {
  if (!refs?.length) return [];
  const [ymin, ymax] = yDomain;
  if (refs.some((b) => b.kind !== "percentile")) refs = refs.filter((b) => b.kind !== "percentile");
  const clip = (b) => ({...b, x1: new Date(Math.max(+D(b.valid_from), +x0)), x2: new Date(Math.min(+D(b.valid_to), +x1))});
  const rects = refs
    .filter((b) => b.kind !== "percentile")
    .map(clip)
    .map((r) => ({...r, y1: Math.max(r.lo ?? ymin, ymin), y2: Math.min(r.hi ?? ymax, ymax)}))
    .filter((r) => r.x1 < r.x2 && r.y2 > r.y1);
  const edges = refs
    .filter((b) => b.kind === "percentile" && b.lo != null && b.lo > ymin && b.lo < ymax)
    .map(clip)
    .filter((r) => r.x1 < r.x2)
    .map((r) => ({...r, y: r.lo, tag: `${ordinal(+r.band.match(/p(\d+)/)[1])}`}));
  const latest = d3.max([...rects, ...edges], (r) => +r.x2);
  const marks = [
    Plot.rect(rects, {
      x1: "x1", x2: "x2", y1: "y1", y2: "y2",
      fill: (r) => (r.is_warning ? "var(--bad)" : "var(--reference-line)"),
      fillOpacity: (r) => (r.is_target ? 0.1 : r.is_warning ? 0.07 : 0.035)
    }),
    Plot.ruleY(rects.filter((r) => r.lo != null && r.lo > ymin), {x1: "x1", x2: "x2", y: "lo", stroke: "var(--reference-line)", strokeOpacity: 0.5, strokeDasharray: "2 3"}),
    Plot.ruleY(edges, {x1: "x1", x2: "x2", y: "y", stroke: "var(--reference-line)", strokeOpacity: 0.55, strokeDasharray: "1 3"})
  ];
  if (labels) {
    marks.push(Plot.text(rects.filter((r) => +r.x2 === latest && r.y2 - r.y1 > (ymax - ymin) * 0.06), {
      x: "x2", y: (r) => (r.y1 + r.y2) / 2, text: "label", dx: -4, textAnchor: "end", fill: "var(--muted)", fontSize: 10.5
    }));
    marks.push(Plot.text(edges.filter((r) => +r.x2 === latest), {
      x: "x2", y: "y", text: "tag", dx: -2, dy: -6, textAnchor: "end", fill: "var(--muted)", fontSize: 10
    }));
  }
  return marks;
}

export function bandChart(rows, {width, height = 240, color, unit = "", refs = [], format = (v) => v.toFixed(0), yFormat, from} = {}) {
  const data = rows.map((r) => ({...r, date: D(r.d)})).filter((r) => !from || r.date >= from);
  if (data.length < 2) return document.createTextNode("Not enough data.");
  const x0 = data[0].date, x1 = data.at(-1).date;
  const values = data.flatMap((r) => [r.v, r.lo, r.hi]).filter((v) => v != null);
  const [lo, hi] = [d3.quantile(values, 0.005), d3.quantile(values, 0.995)];
  const pad = (hi - lo) * 0.08;
  const yDomain = [lo - pad, hi + pad];
  return Plot.plot({
    ...BASE, width, height,
    x: {type: "utc", domain: [x0, x1]},
    y: {domain: yDomain, label: null, tickFormat: yFormat, clamp: true},
    marks: [
      ...referenceMarks(refs, {x0, x1, yDomain}),
      Plot.gridY({stroke: "var(--grid)"}),
      Plot.areaY(data, {x: "date", y1: "lo", y2: "hi", fill: color, fillOpacity: 0.14, curve: "step"}),
      Plot.dot(data, {x: "date", y: "v", r: 1.4, fill: color, fillOpacity: 0.35}),
      Plot.line(data, {x: "date", y: "m", stroke: color, strokeWidth: 1.9}),
      Plot.tip(data, Plot.pointerX({x: "date", y: "m", title: (r) => `${date(r.d)}\nday: ${r.v == null ? "–" : format(r.v)} ${unit}\n28-day median: ${r.m == null ? "–" : format(r.m)} ${unit}${r.lo != null ? `\nyour normal: ${format(r.lo)}–${format(r.hi)}` : ""}`}))
    ]
  });
}

/** Last value and the latest normal range, for insight lines. */
export function latest(rows) {
  const withM = rows.filter((r) => r.m != null);
  return withM.at(-1) ?? null;
}
