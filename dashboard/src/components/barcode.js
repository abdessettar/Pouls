/**
 * Sleep barcode: one row per night, bars from bedtime to wake time coloured by stage. Positions
 * are hours relative to midnight of the wake-up day (negative = the evening before).
 *
 * barcode(nights)       nights from data/overview.json (ISO local times + segments)
 * barcode(compact(...)) nights from data/sleep.json (minute offsets + stage codes)
 */
import * as d3 from "npm:d3";
import * as Plot from "npm:@observablehq/plot";
import {BASE} from "./marks.js";
import {clock, hm, dateShort, date} from "./format.js";

export const STAGE_COLOR = {
  Deep: "var(--stage-deep)",
  Core: "var(--stage-core)",
  REM: "var(--stage-rem)",
  Awake: "var(--stage-awake)",
  AsleepUnspecified: "var(--stage-core)",
  InBed: "var(--stage-inbed)"
};
export const STAGE_ORDER = ["Deep", "Core", "REM", "Awake"];

const asUtc = (s) => new Date(String(s).length <= 10 ? `${s}T00:00:00Z` : `${s}Z`);
const rel = (ts, night) => (asUtc(ts) - asUtc(night)) / 3.6e6;

/** Overview format -> normalised nights [{night, label, asleep, bars: [{x1, x2, stage}]}]. */
function fromOverview(nights) {
  return nights.map((n) => ({
    night: n.night_date,
    asleep: n.asleep_min,
    bars: n.segments?.length
      ? n.segments.map((s) => ({x1: rel(s.start, n.night_date), x2: rel(s.end, n.night_date), stage: s.label}))
      : n.start_local ? [{x1: rel(n.start_local, n.night_date), x2: rel(n.end_local, n.night_date), stage: "InBed"}] : []
  }));
}

/** Sleep-page format ({d, s, e, a, g: [[start, end, code]]}) -> normalised nights. */
export function compact(rows, codes) {
  return rows.map((r) => ({
    night: r.d,
    asleep: r.a,
    bars: r.g.length ? r.g.map(([s, e, c]) => ({x1: s / 60, x2: e / 60, stage: codes[c]})) : [{x1: r.s / 60, x2: r.e / 60, stage: "InBed"}]
  }));
}

export function barcode(nights, {width, rowHeight, maxHeight = 640, legend = true} = {}) {
  const ns = nights.length && nights[0].bars ? nights : fromOverview(nights);
  const label = (n) => (ns.length > 60 ? n.night : dateShort(n.night));
  const order = ns.map(label);
  const rows = ns.flatMap((n) => n.bars.map((b) => ({...b, row: label(n), n})));
  if (!rows.length) return document.createTextNode("No nights in this period.");
  const lo = Math.min(-3, Math.floor(d3.min(rows, (r) => r.x1)));
  const hi = Math.max(9, Math.ceil(d3.max(rows, (r) => r.x2)));
  const rh = rowHeight ?? Math.max(2, Math.min(12, (maxHeight - 40) / order.length));
  const every = Math.ceil(12 / rh);
  const step = width < 520 ? 4 : 2; // hours between x ticks
  const plot = Plot.plot({
    ...BASE,
    width,
    height: Math.max(160, order.length * rh + 40),
    marginLeft: ns.length > 60 ? 76 : 52,
    x: {domain: [lo, hi], ticks: d3.range(Math.ceil(lo / step) * step, hi + 1, step), tickFormat: (h) => clock(h), label: null},
    y: {domain: order, label: null, tickSize: 0, padding: rh > 5 ? 0.18 : 0, tickFormat: (d, i) => (i % every ? "" : ns.length > 60 ? date(d) : d)},
    marks: [
      Plot.gridX({stroke: "var(--grid)"}),
      Plot.ruleX([0], {stroke: "var(--border-strong)"}),
      Plot.barX(rows, {x1: "x1", x2: "x2", y: "row", fill: (d) => STAGE_COLOR[d.stage] ?? "var(--stage-core)"}),
      Plot.tip(rows, Plot.pointer({x1: "x1", x2: "x2", y: "row", title: (d) => `${date(d.n.night)}: ${d.stage} ${clock(d.x1)}–${clock(d.x2)}\nnight asleep ${hm(d.n.asleep)}`}))
    ]
  });
  if (!legend) return plot;
  const div = document.createElement("div");
  div.append(plot);
  const lg = document.createElement("div");
  lg.className = "legend";
  for (const s of [...STAGE_ORDER, "InBed"]) {
    const item = document.createElement("span");
    item.className = "legend-item";
    item.innerHTML = `<span class="swatch" style="background:${STAGE_COLOR[s]}"></span>${s === "InBed" ? "In bed (no stages)" : s}`;
    lg.append(item);
  }
  div.append(lg);
  return div;
}
