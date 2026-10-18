/**
 * Where a value sits among the reference bands (from mart_reference, via a page's data file).
 * Mirrors apple_health.dashboard.references.reference_at: guideline bands ("range") come first, the
 * population percentile table second; bands are lo <= value < hi and apply from valid_from to valid_to.
 */
const hit = (v) => (b) => (b.lo == null || v >= b.lo) && (b.hi == null || v < b.hi);

export function bandsOn(bands, day) {
  return (bands ?? []).filter((b) => b.valid_from <= day && b.valid_to >= day);
}

export function referenceAt(bands, day, value) {
  const rows = bandsOn(bands, day);
  if (!rows.length) return null;
  const ranges = rows.filter((b) => b.kind !== "percentile");
  const pcts = rows.filter((b) => b.kind === "percentile");
  const primary = ranges.length ? ranges : pcts;
  const current = value == null ? null : primary.find(hit(value));
  const pct = value == null ? null : pcts.find(hit(value));
  return {
    bands: primary,
    current_band: current?.band ?? null,
    current_label: current?.label ?? null,
    in_target: current ? !!current.is_target : null,
    warning: current ? !!current.is_warning : null,
    population: primary[0].population,
    source_id: primary[0].source_id,
    percentile: pct ? {band: pct.band, label: pct.label, population: pct.population} : null
  };
}
