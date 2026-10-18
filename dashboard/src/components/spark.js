/**
 * Sparkline: a small unsmoothed line with an end dot, no axes. Nulls break the line.
 * values: [{date, value}] or plain numbers.
 */
import * as Plot from "npm:@observablehq/plot";

export function sparkline(values, {color = "currentColor", width = 220, height = 34, band} = {}) {
  const data = (values ?? []).map((v, i) => (typeof v === "number" || v == null ? {x: i, y: v} : {x: v.date ?? i, y: v.value}));
  const present = data.filter((d) => d.y != null && Number.isFinite(d.y));
  if (present.length < 2) return document.createElement("div");
  const last = present.at(-1);
  return Plot.plot({
    width,
    height,
    margin: 3,
    axis: null,
    x: {type: data[0].x instanceof Date ? "utc" : "linear"},
    y: {zero: false, nice: false, ...(band ? {domain: [Math.min(band[0], ...present.map((d) => d.y)), Math.max(band[1], ...present.map((d) => d.y))]} : {})},
    style: {background: "transparent", overflow: "visible"},
    marks: [
      band ? Plot.rectY([band], {y1: (b) => b[0], y2: (b) => b[1], fill: "var(--reference)"}) : null,
      Plot.line(data, {x: "x", y: "y", stroke: color, strokeWidth: 1.6, curve: "linear"}),
      Plot.dot([last], {x: "x", y: "y", r: 2.5, fill: color})
    ]
  });
}
