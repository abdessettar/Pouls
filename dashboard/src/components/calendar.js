/**
 * Calendar heatmap: one row of weeks per year (Monday first), one cell per day. Intensity is the
 * domain colour's opacity, so it works in light and dark themes.
 * rows: [{local_date: "YYYY-MM-DD", value}]
 * domain: [lo, hi] for the opacity scale; default [0, 98th percentile]. Pass e.g. the 2nd and 98th
 * percentiles for metrics that never approach zero (heart rate, bedtime).
 */
import * as d3 from "npm:d3";
import * as Plot from "npm:@observablehq/plot";
import {BASE} from "./marks.js";
import {date} from "./format.js";

export function calendar(rows, {width, color = "var(--activity)", format = (v) => v, label = "", years, domain} = {}) {
  const data = rows.filter((r) => r.value != null).map((r) => {
    const d = new Date(r.local_date);
    const y = d.getUTCFullYear();
    return {...r, d, year: y, week: d3.utcMonday.count(d3.utcYear(d), d), dow: (d.getUTCDay() + 6) % 7};
  });
  const ys = years ?? [...new Set(data.map((d) => d.year))].sort((a, b) => b - a);
  const [lo, hi] = domain ?? [0, d3.quantile(data.map((d) => d.value), 0.98) || 1];
  const opacity = (v) => 0.12 + 0.88 * Math.min(1, Math.max(0, (v - lo) / (hi - lo || 1)));
  const cell = Math.max(6, Math.min(14, Math.floor((width - 60) / 54)));
  return Plot.plot({
    ...BASE,
    width,
    height: ys.length * (cell * 7 + 18) + 20,
    marginLeft: 44,
    marginTop: 14,
    padding: 0,
    x: {axis: null, domain: d3.range(0, 54)},
    y: {axis: null, domain: d3.range(0, 7), padding: 0.12},
    fy: {domain: ys, label: null, tickFormat: String, padding: 0.12},
    marks: [
      Plot.cell(data.filter((d) => ys.includes(d.year)), {
        x: "week", y: "dow", fy: "year", fill: color, fillOpacity: (d) => opacity(d.value), inset: 0.6, rx: 1.5
      }),
      Plot.tip(data.filter((d) => ys.includes(d.year)), Plot.pointer({x: "week", y: "dow", fy: "year", title: (d) => `${date(d.local_date)}\n${format(d.value)} ${label}`}))
    ]
  });
}
