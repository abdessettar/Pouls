/**
 * Overview tiles for a date range, computed from the daily history in data/overview.json.
 *
 * Each tile reduces the range's days with its statistic (median day, total per 7 days, share of
 * days, latest value). It is compared with your usual period of the same length: the same statistic
 * over every such period in your history (since that measure began), and the median of those. A
 * plain all-time median of days would say little for totals: the median week of running is zero.
 */
import * as d3 from "npm:d3";
import {spanDays, within} from "./range.js";

/** The day's value for a tile (null where it does not count: no data, or the Watch barely worn). */
function dayValue(k, day) {
  if (k.valid_only && !day.valid) return null;
  const v = day[k.column];
  if (k.stat === "share") return v == null ? null : v ? 1 : 0;
  if (k.stat === "rate_week") return v ?? 0; // no workout or run that day counts as zero
  return v ?? null;
}

/** Reduce a run of day values with the tile's statistic; null when too few days have one. */
function reduce(k, vals) {
  const have = vals.filter((v) => v != null);
  if (!have.length) return null;
  switch (k.stat) {
    case "median":
      return have.length >= Math.max(1, Math.floor(vals.length / 4)) ? d3.median(have) * k.scale : null;
    case "share":
      return have.length >= Math.max(1, Math.floor(vals.length / 4)) ? d3.mean(have) : null;
    case "rate_week":
      return (d3.sum(have) / vals.length) * 7 * k.scale;
    case "last":
      return have.at(-1) * k.scale;
  }
  throw new Error(`unknown stat ${k.stat}`);
}

/** Index of the first day the measure has data (totals before it are not zeros, just unknown). */
function startIndex(k, days) {
  const i = days.findIndex((d) => d[k.column] != null);
  return i < 0 ? days.length : i;
}

function buckets(r, n) {
  if (n <= 35) return (d) => d.d;
  if (n <= 730) return (d) => d3.utcMonday.floor(new Date(d.d)).toISOString().slice(0, 10);
  return (d) => `${d.d.slice(0, 7)}-01`;
}

export function computeKpi(k, days, r) {
  const start = startIndex(k, days);
  const usable = days.slice(start);
  const inRange = usable.filter((d) => within(r, d.d));
  const n = spanDays(r);
  const value = inRange.length ? reduce(k, inRange.map((d) => dayValue(k, d))) : null;

  // Your usual period of the same length: the statistic over every window of n days, then the median.
  let usual = null, windows = 0;
  const L = Math.min(n, inRange.length || n);
  if (usable.length >= L * 2) {
    const vals = usable.map((d) => dayValue(k, d));
    const step = Math.max(1, Math.floor(L / 30));
    const results = [];
    for (let i = 0; i + L <= vals.length; i += step) {
      const v = reduce(k, vals.slice(i, i + L));
      if (v != null) results.push(v);
    }
    windows = results.length;
    if (windows >= 3) usual = d3.median(results);
  }
  const change = value == null || usual == null ? null : k.delta === "rel" ? (usual === 0 ? null : (value / usual - 1) * 100) : value - usual;

  const key = buckets(r, n);
  const spark = d3
    .rollups(inRange, (v) => reduce(k, v.map((d) => dayValue(k, d))), key)
    .map(([b, v]) => ({date: new Date(b), value: v}))
    .sort((a, b) => a.date - b.date);

  const lastDay = inRange.filter((d) => d[k.column] != null).at(-1)?.d ?? null;
  // k.delta says how the change reads (rel: percent, abs: in the unit); change is its value.
  return {...k, value, usual, change, windows, days: L, spark, valueDay: lastDay, since: usable[0]?.d ?? null};
}
