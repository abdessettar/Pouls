/**
 * Formatting for everything the site prints: numbers, deltas, durations, clock times, dates.
 * Every function returns "–" for missing values so a tile never prints "NaN".
 */

export const MISSING = "–";
const LOCALE = "en-GB";
const isNil = (v) => v == null || Number.isNaN(v) || !Number.isFinite(v);

/** 8,500 · 1.5 · 0.97 (digits: fixed decimals; default: integer). */
export function num(v, digits = 0) {
  if (isNil(v)) return MISSING;
  return v.toLocaleString(LOCALE, {minimumFractionDigits: digits, maximumFractionDigits: digits});
}

/** Compact: 950 · 8.5k · 12k · 1.2M */
export function compact(v) {
  if (isNil(v)) return MISSING;
  const a = Math.abs(v);
  const s = a >= 1e6 ? `${(a / 1e6).toFixed(1).replace(/\.0$/, "")}M`
    : a >= 1e4 ? `${Math.round(a / 1e3)}k`
    : a >= 1e3 ? `${(a / 1e3).toFixed(1).replace(/\.0$/, "")}k`
    : `${Math.round(a)}`;
  return v < 0 ? `−${s}` : s;
}

/** 0.973 -> "97.3%" (input is a fraction). */
export function pct(fraction, digits = 0) {
  if (isNil(fraction)) return MISSING;
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** Signed number with a true minus: +2.1 / −0.4 / 0 */
export function signed(v, digits = 0) {
  if (isNil(v)) return MISSING;
  const r = Number(v.toFixed(digits));
  if (r === 0) return (0).toFixed(digits);
  return `${r > 0 ? "+" : "−"}${Math.abs(r).toLocaleString(LOCALE, {minimumFractionDigits: digits, maximumFractionDigits: digits})}`;
}

/** Signed relative change: +6% / −3% (a, b: current and reference values). */
export function relChange(current, reference, digits = 0) {
  if (isNil(current) || isNil(reference) || reference === 0) return null;
  return (current / reference - 1) * 100;
}

/** Minutes -> "7 h 27 min" (or "45 min"). */
export function hm(minutes) {
  if (isNil(minutes)) return MISSING;
  const m = Math.round(minutes);
  const h = Math.floor(Math.abs(m) / 60);
  const r = Math.abs(m) % 60;
  const sign = m < 0 ? "−" : "";
  return h ? `${sign}${h} h ${String(r).padStart(2, "0")} min` : `${sign}${r} min`;
}

/** Minutes -> "7:27" (compact h:mm). */
export function hmm(minutes) {
  if (isNil(minutes)) return MISSING;
  const m = Math.round(Math.abs(minutes));
  return `${minutes < 0 ? "−" : ""}${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
}

/** Clock hours after midnight (22.5, or 24.5 for 00:30 the next day) -> "22:30" / "00:30". */
export function clock(hours) {
  if (isNil(hours)) return MISSING;
  const total = Math.round(hours * 60);
  const m = ((total % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

/** Pace in min/km from seconds per km -> "5:42 /km". */
export function pace(secondsPerKm) {
  if (isNil(secondsPerKm)) return MISSING;
  const s = Math.round(secondsPerKm);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} /km`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
  "October", "November", "December"];

/** A "YYYY-MM-DD" string or Date -> Date at UTC midnight (dates are local calendar days). */
export function day(d) {
  if (d instanceof Date) return d;
  if (d == null) return null;
  const [y, m, dd] = String(d).slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, dd));
}

/** "5 May 2025" */
export function date(d) {
  const x = day(d);
  return x ? `${x.getUTCDate()} ${MONTHS[x.getUTCMonth()]} ${x.getUTCFullYear()}` : MISSING;
}

/** "5 Oct" */
export function dateShort(d) {
  const x = day(d);
  return x ? `${x.getUTCDate()} ${MONTHS[x.getUTCMonth()]}` : MISSING;
}

/** "May 2025" */
export function month(d) {
  const x = day(d);
  return x ? `${MONTHS_LONG[x.getUTCMonth()]} ${x.getUTCFullYear()}` : MISSING;
}

/** "8 Apr – 5 May 2025" (year printed once when both ends share it). */
export function range(a, b) {
  const x = day(a), y = day(b);
  if (!x || !y) return MISSING;
  const sameYear = x.getUTCFullYear() === y.getUTCFullYear();
  return `${sameYear ? dateShort(x) : date(x)} – ${date(y)}`;
}

/** "1 day" / "28 days" */
export const plural = (n, one, many = `${one}s`) => `${num(n)} ${Math.round(n) === 1 ? one : many}`;
