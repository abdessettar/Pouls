/**
 * Date range picker shared by the pages: quick presets plus From / To dates. Use with view():
 *
 *   const r = view(rangePicker({first: meta.first_day, last: meta.data_through, value: "12 months"}));
 *   rows.filter((d) => within(r, d.local_date))
 *
 * The value is {from, to} as "YYYY-MM-DD" strings (inclusive), so ISO dates compare as text.
 * The range is kept in the address (?from=&to=), so a reload or a shared link keeps it.
 */
import {html} from "npm:htl";
import {range as rangeText} from "./format.js";

const DAY = 864e5;
export const iso = (d) => new Date(d).toISOString().slice(0, 10);
export const addDays = (s, n) => iso(Date.parse(s) + n * DAY);
export const spanDays = (r) => Math.round((Date.parse(r.to) - Date.parse(r.from)) / DAY) + 1;
export const within = (r, d) => d != null && d.slice(0, 10) >= r.from && d.slice(0, 10) <= r.to;
/** Months ("YYYY-MM-01") the range touches. */
export const monthIn = (r, m) => m.slice(0, 7) >= r.from.slice(0, 7) && m.slice(0, 7) <= r.to.slice(0, 7);
/** Weeks (Monday "YYYY-MM-DD") overlapping the range. */
export const weekIn = (r, w) => w >= addDays(r.from, -6) && w <= r.to;
/** Periods {start, end} overlapping the range. */
export const overlaps = (r, a, b) => a.slice(0, 10) <= r.to && b.slice(0, 10) >= r.from;
export const describe = (r) => rangeText(r.from, r.to);

export const PRESETS = {
  "28 days": (first, last) => ({from: addDays(last, -27), to: last}),
  "3 months": (first, last) => ({from: addDays(last, -90), to: last}),
  "12 months": (first, last) => ({from: addDays(last, -364), to: last}),
  "2 years": (first, last) => ({from: addDays(last, -729), to: last}),
  "This year": (first, last) => ({from: `${last.slice(0, 4)}-01-01`, to: last}),
  All: (first, last) => ({from: first, to: last})
};

/** Update some query parameters, keeping the others (null removes one). */
export function setParams(params) {
  const u = new URL(location.href);
  for (const [k, v] of Object.entries(params)) (v == null ? u.searchParams.delete(k) : u.searchParams.set(k, v));
  history.replaceState(null, "", u);
}

export function rangePicker({first, last, value = "All", presets = ["28 days", "3 months", "12 months", "2 years", "This year", "All"], label = "Dates"} = {}) {
  const clamp = (s) => (s < first ? first : s > last ? last : s);
  const fromPreset = (name) => {
    const r = PRESETS[name](first, last);
    return {from: clamp(r.from), to: clamp(r.to)};
  };
  const initial = typeof value === "string" ? fromPreset(value) : value;
  const q = new URLSearchParams(location.search);
  const ok = (s) => /^\d{4}-\d{2}-\d{2}$/.test(s ?? "");
  const start = ok(q.get("from")) && ok(q.get("to")) ? {from: clamp(q.get("from")), to: clamp(q.get("to"))} : initial;

  const fromInput = html`<input type="date" min=${first} max=${last} value=${start.from}>`;
  const toInput = html`<input type="date" min=${first} max=${last} value=${start.to}>`;
  const buttons = presets.map((name) => html`<button type="button" data-preset=${name}>${name}</button>`);
  const root = html`<div class="range" role="group" aria-label=${label}>
    <span class="range-label">${label}</span>
    <span class="range-presets">${buttons}</span>
    <label class="range-date"><span>From</span>${fromInput}</label>
    <label class="range-date"><span>To</span>${toInput}</label>
  </div>`;

  const mark = () => {
    for (const b of buttons) {
      const p = fromPreset(b.dataset.preset);
      b.classList.toggle("on", p.from === root.value.from && p.to === root.value.to);
    }
  };
  const set = (r, {notify = true} = {}) => {
    let {from, to} = {from: clamp(r.from), to: clamp(r.to)};
    if (from > to) [from, to] = [to, from];
    root.value = {from, to};
    fromInput.value = from;
    toInput.value = to;
    mark();
    if (notify) {
      setParams({from, to});
      root.dispatchEvent(new Event("input", {bubbles: true}));
    }
  };
  for (const b of buttons) b.addEventListener("click", () => set(fromPreset(b.dataset.preset)));
  for (const input of [fromInput, toInput]) {
    input.addEventListener("change", () => {
      if (ok(fromInput.value) && ok(toInput.value)) set({from: fromInput.value, to: toInput.value});
    });
  }
  set(start, {notify: false});
  return root;
}
