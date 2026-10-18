/**
 * KPI tile: label, big value, change chips, an optional reference chip, a sparkline and a foot note.
 *
 *   kpiTile({
 *     label: "Resting HR", domain: "heart", value: "58", unit: "bpm",
 *     changes: [{label: "vs prev 28 d", delta: -1.2, text: "−1 bpm", better: "lower"}],
 *     reference: {text: "Within 60–100 bpm", status: "in"},
 *     spark: {values: [...], color: "var(--heart)"},
 *     foot: "28-day median, valid wear days"
 *   })
 *
 * `better` says which direction is good ("higher" | "lower" | null for neutral); the chip turns
 * green or red accordingly. Small changes (|delta| < threshold) stay neutral.
 */
import {html} from "npm:htl";
import {sparkline} from "./spark.js";

export const DOMAIN_COLOR = {
  activity: "var(--activity)",
  heart: "var(--heart)",
  sleep: "var(--sleep)",
  training: "var(--training)",
  running: "var(--running)",
  places: "var(--places)"
};

/** A change chip: "▲ +6% vs prev 28 d". */
export function changeChip({label, title = "", delta, text, better = "higher", threshold = 0}) {
  if (delta == null || Number.isNaN(delta)) return html`<span class="chip"><span class="chip-label">${label}</span> –</span>`;
  const up = delta > 0;
  const small = Math.abs(delta) <= threshold;
  const tone = small || better == null ? "" : (up === (better === "higher") ? "good" : "bad");
  const arrow = small ? "■" : up ? "▲" : "▼";
  return html`<span class="chip ${tone}" title="${title || label}">${arrow} ${text} <span class="chip-label">${label}</span></span>`;
}

/** A reference chip: neutral outline, a coloured dot for in / out of range. */
export function referenceChip({text, status, title = ""}) {
  const color = status === "in" ? "var(--good)" : status === "out" ? "var(--bad)" : "var(--faint)";
  return html`<span class="chip ref" title="${title}"><span class="swatch" style="background:${color};width:7px;height:7px;border-radius:50%"></span>${text}</span>`;
}

export function kpiTile({label, domain, value, unit, changes = [], reference, spark, foot, href}) {
  const accent = DOMAIN_COLOR[domain] ?? "var(--border-strong)";
  const body = html`<div class="tile" style="--accent:${accent}">
    <p class="tile-label">${label}</p>
    <p class="tile-value">${value}${unit ? html`<small>${unit}</small>` : ""}</p>
    ${changes.length || reference ? html`<div class="tile-chips">${changes.map(changeChip)}${reference ? referenceChip(reference) : ""}</div>` : ""}
    ${spark ? html`<div class="tile-spark">${sparkline(spark.values, {color: spark.color ?? accent, ...spark})}</div>` : ""}
    ${foot ? html`<p class="tile-foot">${foot}</p>` : ""}
  </div>`;
  return href ? html`<a href="${href}" style="text-decoration:none;color:inherit">${body}</a>` : body;
}

/** A row of tiles. */
export const tiles = (items) => html`<div class="tiles">${items}</div>`;
