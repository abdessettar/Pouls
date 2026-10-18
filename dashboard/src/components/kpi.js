/**
 * Turns a tile computed by kpis.js into a KPI tile: value formatting, the change chip against your
 * usual period of the same length (with metric-specific wording and "no real change" thresholds),
 * and the reference chip.
 */
import {kpiTile} from "./tile.js";
import {num, hm, clock, signed, date} from "./format.js";

/** How each KPI prints. threshold: changes this small (in the delta's unit) stay neutral. */
const SPEC = {
  steps: {value: (v) => num(v), threshold: 2},
  active_energy: {value: (v) => num(v), unit: "kcal", threshold: 2},
  exercise: {value: (v) => num(v), unit: "min", threshold: 2},
  rings: {value: (v) => num(v), abs: (d) => `${signed(d)} d`, threshold: 0},
  resting_hr: {value: (v) => num(v), unit: "bpm", abs: (d) => `${signed(d)} bpm`, threshold: 1},
  hrv: {value: (v) => num(v), unit: "ms", abs: (d) => `${signed(d)} ms`, threshold: 2},
  vo2max: {value: (v) => num(v, 1), unit: "mL/min·kg", abs: (d) => signed(d, 1), threshold: 0.4},
  respiratory_rate: {value: (v) => num(v, 1), unit: "/min", abs: (d) => signed(d, 1), threshold: 0.3},
  asleep: {value: (v) => hm(v), unit: "", abs: (d) => `${signed(d)} min`, threshold: 10},
  bedtime: {value: (v) => clock(v), unit: "", abs: (d) => (Math.abs(d * 60) < 1 ? "same" : `${Math.round(Math.abs(d * 60))} min ${d > 0 ? "later" : "earlier"}`), scale: 60, threshold: 10},
  training: {value: (v) => num(v, 1), unit: "h", threshold: 5},
  running: {value: (v) => num(v, 1), unit: "km", threshold: 5}
};

function changeText(k, delta) {
  const s = SPEC[k.key] ?? {};
  if (delta == null) return "";
  if (k.delta === "rel") return `${signed(delta)}%`;
  return s.abs ? s.abs(delta) : signed(delta, 1);
}

function referenceChip(ref) {
  if (!ref || !ref.current_label) return null;
  const status = ref.in_target ? "in" : ref.warning ? "out" : null;
  const pct = ref.percentile && ref.percentile.label !== ref.current_label ? `\n${ref.percentile.label}: ${ref.percentile.population}` : "";
  return {text: ref.current_label, status, title: `${ref.population}${pct}`};
}

/** k: a computeKpi() result; reference: a referenceAt() result. */
export function kpiToTile(k, {href, reference} = {}) {
  const s = SPEC[k.key] ?? {value: (v) => num(v)};
  const show = (v) => (v == null ? "–" : s.value(v));
  // Rings: the share of days, shown as a count of the range's days.
  const asDays = (v) => (v == null ? null : v * k.days);
  const value = k.stat === "share" ? asDays(k.value) : k.value;
  const delta = k.stat === "share" ? (k.change == null ? null : k.change * k.days) : k.change;
  const usual = k.stat === "share" ? asDays(k.usual) : k.usual;
  const change = {
    label: "vs usual",
    title: k.usual == null ? "" : `Your usual ${k.days} days: the median of every ${k.days}-day period since ${date(k.since)} (${k.windows} periods)`,
    delta: delta == null ? null : delta * (s.scale ?? 1),
    text: changeText(k, delta),
    better: k.better,
    threshold: s.threshold ?? 0
  };
  const statText = {median: "median day", rate_week: "per 7 days", share: "", last: k.valueDay ? `estimate of ${date(k.valueDay)}` : ""}[k.stat];
  const foot = [statText, usual != null ? `usual ${show(usual)}` : null].filter(Boolean).join(" · ");
  return kpiTile({
    label: k.label,
    domain: k.domain,
    value: show(value),
    unit: k.stat === "share" ? `of ${k.days} days` : s.unit ?? k.unit,
    changes: k.usual == null ? [] : [change],
    reference: referenceChip(reference),
    spark: k.spark.length > 1 ? {values: k.spark} : null,
    foot,
    href
  });
}
