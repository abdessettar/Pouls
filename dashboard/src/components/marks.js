/**
 * Shared chart conventions (Observable Plot):
 * - unsmoothed lines, an end dot, direct labels rather than legends where there are few series;
 * - horizontal grid only, quiet axes in the muted ink;
 * - a shaded band wherever nothing was recorded (lines break there, never interpolate);
 * - reference bands drawn behind the data in a neutral tint.
 */
import * as Plot from "npm:@observablehq/plot";

/** Plot options shared by every chart. */
export const BASE = {
  style: {background: "transparent", overflow: "visible", fontFamily: "var(--font)", fontSize: "12px", color: "var(--muted)"},
  marginLeft: 44,
  marginRight: 16,
  marginTop: 16,
  marginBottom: 28
};

/** Right margin for charts with direct labels at line ends. */
export const LABEL_MARGIN = 92;

/** Chart height for a card width. */
export const chartHeight = (width, {tall = false} = {}) => (width > 760 ? (tall ? 380 : 300) : width > 480 ? 260 : 220);

/** Time x-axis and a y grid in the muted ink. */
export const axes = ({yLabel = null, yFormat, xFormat} = {}) => [
  Plot.gridY({stroke: "var(--grid)", strokeOpacity: 1}),
  Plot.axisY({label: yLabel, tickFormat: yFormat, tickSize: 0, stroke: "var(--muted)"}),
  Plot.axisX({tickFormat: xFormat, tickSize: 3, stroke: "var(--muted)", label: null}),
  Plot.ruleY([0], {stroke: "transparent"})
];

/**
 * "No data" bands: [{start, end}] intervals (Dates) shaded across the plot height, with an
 * optional label on the first wide band.
 */
export function noData(intervals, {label = "no data"} = {}) {
  const rows = (intervals ?? []).map((d) => ({x1: d.start, x2: d.end}));
  return [
    Plot.rectX(rows, {x1: "x1", x2: "x2", fill: "var(--nodata)"}),
    label ? Plot.text(rows.slice(0, 1), {x: (d) => new Date((+d.x1 + +d.x2) / 2), frameAnchor: "top", dy: 6, text: () => label, fill: "var(--muted)", fontSize: 11}) : null
  ].filter(Boolean);
}

/** A horizontal reference band (lo..hi), optionally labelled at its right edge. */
export function referenceBand(lo, hi, {label} = {}) {
  return [
    Plot.rectY([{lo, hi}], {y1: "lo", y2: "hi", fill: "var(--reference)"}),
    label ? Plot.text([label], {frameAnchor: "right", y: hi, dy: -6, dx: -4, text: (d) => d, fill: "var(--muted)", fontSize: 11, textAnchor: "end"}) : null
  ].filter(Boolean);
}

/** A dashed reference line with its meaning written on it. */
export function referenceLine(y, label) {
  return [
    Plot.ruleY([y], {stroke: "var(--reference-line)", strokeDasharray: "4 3"}),
    label ? Plot.text([label], {y, frameAnchor: "right", dy: -6, dx: -4, text: (d) => d, fill: "var(--muted)", fontSize: 11, textAnchor: "end"}) : null
  ].filter(Boolean);
}

/** Line with an end dot and a direct label at its end. */
export function labelledLine(data, {x, y, z, stroke, label, strokeWidth = 1.75}) {
  const last = new Map();
  for (const d of data) if (d[y] != null) last.set(z ? d[z] : "_", d);
  const ends = [...last.values()];
  return [
    Plot.line(data, {x, y, z, stroke, strokeWidth, curve: "linear"}),
    Plot.dot(ends, {x, y, r: 3, fill: stroke}),
    label ? Plot.text(ends, {x, y, text: label, dx: 8, textAnchor: "start", fill: stroke, fontWeight: 600, fontSize: 12}) : null
  ].filter(Boolean);
}
