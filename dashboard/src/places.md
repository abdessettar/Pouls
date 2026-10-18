---
title: Places
---

<link rel="stylesheet" href="./vendor/leaflet.css">

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {createMap, decode} from "./components/map.js";
import {num, date, month, hm, pace, plural} from "./components/format.js";
import {rangePicker, within, overlaps, describe} from "./components/range.js";
const meta = FileAttachment("data/meta.json").json();
const P = FileAttachment("data/places.json").json();
const tracks = FileAttachment("data/tracks.json").json();
const OV = FileAttachment("data/overview.json").json();
```

```js
// Leaflet draws on a canvas, so these are real colours rather than CSS variables; strong enough to
// stand out on the greyed basemap.
const GROUP_COLOR = {walking: "#15803d", running: "#ea580c", other: "#4338ca"};
const GROUP_LABEL = {walking: "Walking", running: "Running", other: "Other"};
const groupOf = (g) => (g === "walking" || g === "running" ? g : "other");
const home = P.home_tz.split("/").at(-1).replace("_", " ");
```

${pageHeader({eyebrow: "Routes and trips", title: "Places", subtitle: html`Every workout with GPS on a map, and the time spent away from home. Map tiles come from OpenStreetMap while you view this page; your routes stay on this machine. Area names: <a href="https://www.geonames.org/" target="_blank" rel="noopener">GeoNames</a> (CC BY 4.0).`, meta})}

```js
const r = view(rangePicker({first: meta.first_day, last: meta.data_through, value: "All"}));
```

```js
const inRange = P.routes.filter((x) => within(r, x.local_date));
const areas = d3.rollups(inRange, (v) => ({
  area_name: v[0].area_name, routes: v.length, km: d3.sum(v, (x) => x.distance_km),
  first: d3.min(v, (x) => x.local_date), last: d3.max(v, (x) => x.local_date),
  min_lat: d3.min(v, (x) => x.center_lat), max_lat: d3.max(v, (x) => x.center_lat),
  min_lon: d3.min(v, (x) => x.center_lon), max_lon: d3.max(v, (x) => x.center_lon)
}), (x) => x.area_id).map(([area_id, a]) => ({area_id, ...a})).sort((a, b) => b.routes - a.routes);
```

<div class="filters">

```js
const area = view(Inputs.select(areas, {label: "Area", format: (a) => `${a.area_name} · ${plural(a.routes, "route")}`, value: areas[0]}));
```

```js
const groups = view(Inputs.checkbox(["walking", "running", "other"], {label: "Show", value: ["walking", "running", "other"], format: (g) => GROUP_LABEL[g]}));
```

</div>

```js
const visible = inRange.filter((x) => groups.includes(groupOf(x.activity_group)));
```

<div class="card" style="padding:0;overflow:hidden">

```js
const m = createMap({height: 600});
display(m.element);
const NORMAL = {weight: 2.5, opacity: 0.55}, HOVER = {weight: 5, opacity: 0.95}, PICKED = {weight: 6, opacity: 1};
let picked = null;
for (const x of visible) {
  const enc = tracks[x.route_id];
  if (!enc) continue;
  const line = m.L.polyline(decode(enc), {color: GROUP_COLOR[groupOf(x.activity_group)], ...NORMAL, renderer: m.renderer});
  line.bindPopup(`<b>${date(x.local_date)}</b> · ${x.activity_type.replace(/([a-z])([A-Z])/g, "$1 $2")}<br>${num(x.distance_km, 2)} km · ${hm(x.duration_min)}${x.distance_km ? ` · ${pace(x.duration_min * 60 / x.distance_km)}` : ""}${x.elevation_gain_m ? `<br>${num(x.elevation_gain_m)} m climbed` : ""}${x.activity_group === "running" ? `<br><a href="./running.html?run=${x.workout_id}">Open run</a>` : ""}`);
  line.on("mouseover", () => line !== picked && line.setStyle(HOVER));
  line.on("mouseout", () => line !== picked && line.setStyle(NORMAL));
  // A clicked route stays highlighted until its popup closes or another route is clicked.
  line.on("click", () => {
    if (picked && picked !== line) picked.setStyle(NORMAL);
    picked = line;
    line.setStyle(PICKED).bringToFront();
  });
  line.on("popupclose", () => {
    if (picked === line) picked = null;
    line.setStyle(NORMAL);
  });
  line.addTo(m.map);
}
if (area) requestAnimationFrame(() => m.map.fitBounds([[area.min_lat, area.min_lon], [area.max_lat, area.max_lon]], {padding: [24, 24], maxZoom: 15}));
invalidation.then(() => m.map.remove());
```

</div>

<div class="legend" style="margin:8px 0 18px">${["walking", "running", "other"].map((g) => html`<span class="legend-item"><span class="swatch" style="background:${GROUP_COLOR[g]}"></span>${GROUP_LABEL[g]}</span>`)}<span class="legend-item">${plural(visible.length, "route")} in ${describe(r)} · overlapping routes read darker · click a route to keep it highlighted and see its details</span></div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Areas</h3><span class="card-note">routes grouped by where they start</span></div>

```js
display(html`<table class="t"><thead><tr><th>Area</th><th class="num">Routes</th><th class="num">km</th><th>First</th><th>Last</th></tr></thead><tbody>${areas.map((a) => html`<tr><td>${a.area_name}</td><td class="num">${num(a.routes)}</td><td class="num">${num(a.km)}</td><td class="card-note">${month(a.first)}</td><td class="card-note">${month(a.last)}</td></tr>`)}</tbody></table>`);
```

<p class="source">Areas are clusters of route centres within 25 km, named after the city nearby that best combines size and closeness.</p>
</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Away from home</h3><span class="card-note">valid wear days, medians</span></div>

```js
const days = OV.days.filter((d) => within(r, d.d) && d.valid);
const side = (away) => {
  const v = days.filter((d) => !!d.away === away);
  return v.length ? {days: v.length, steps: d3.median(v, (d) => d.steps), asleep: d3.median(v, (d) => d.asleep), workout: d3.mean(v, (d) => d.workout_min ?? 0), rhr: d3.median(v, (d) => d.rhr), hrv: d3.median(v, (d) => d.hrv)} : null;
};
const H = side(false), A = side(true);
const row = (label, k, f) => html`<tr><td>${label}</td><td class="num">${H?.[k] != null ? f(H[k]) : "–"}</td><td class="num">${A?.[k] != null ? f(A[k]) : "–"}</td></tr>`;
display(html`<table class="t"><thead><tr><th></th><th class="num">Home</th><th class="num">Away</th></tr></thead><tbody>
  ${row("Days", "days", (v) => num(v))}
  ${row("Steps", "steps", (v) => num(v))}
  ${row("Asleep", "asleep", (v) => hm(v))}
  ${row("Training per day", "workout", (v) => `${num(v)} min`)}
  ${row("Resting heart rate", "rhr", (v) => `${num(v)} bpm`)}
  ${row("Night HRV", "hrv", (v) => `${num(v, 1)} ms`)}
</tbody></table>`);
const zones = d3.rollups(OV.days.filter((d) => within(r, d.d) && d.away), (v) => v.length, (d) => d.tz_name).sort((a, b) => b[1] - a[1]);
display(html`<p class="card-note" style="margin-top:10px">${zones.length ? zones.map(([tz, n]) => `${tz.split("/").at(-1).replace("_", " ")}: ${plural(n, "day")}`).join(" · ") : "No days away in this range."}</p>`);
```

<p class="source">"Home" is your home time zone, ${home} (time.default_timezone in settings.toml), not an address: a day is away when most of its readings carry another time zone. Moving house within the same time zone changes nothing here; the map's areas show where routes actually were.</p>
</div>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">Trips</h3><span class="card-note">periods spent outside the home time zone</span></div>

```js
const trips = P.trips.periods.filter((t) => overlaps(r, t.start, t.end)).map((t) => ({...t, s: new Date(t.start), e: new Date(t.end), place: t.tz_name.split("/").at(-1).replace("_", " ")})).filter((t) => t.e - t.s >= 864e5);
display(trips.length ? resize((width) => Plot.plot({
  ...BASE, width, height: 160, marginLeft: 80,
  x: {type: "utc", label: null},
  y: {label: null, domain: [...new Set(trips.map((t) => t.place))]},
  marks: [
    Plot.barX(trips, {x1: "s", x2: "e", y: "place", fill: "var(--places)", rx: 2, insetTop: 4, insetBottom: 4}),
    Plot.tip(trips, Plot.pointer({x1: "s", x2: "e", y: "place", title: (t) => `${t.place}\n${date(t.start)} – ${date(t.end)}\n${plural(Math.round((t.e - t.s) / 864e5), "day")}`}))
  ]
})) : html`<p class="card-note">No trips of a day or more in this range.</p>`);
```

<p class="source">Inferred from the time zone recorded with workouts and sleep; trips shorter than a day are left out. The time zone's name (e.g. Amsterdam, for all of the Netherlands) is the zone, not necessarily the city you were in; the areas above name the places.</p>
</div>

<div class="card">
<div class="card-head"><h3 class="card-title">All routes</h3><span class="card-note">current filters · sortable</span></div>

```js
display(Inputs.table(visible.slice().reverse(), {
  columns: ["local_date", "activity_type", "area_name", "distance_km", "duration_min", "elevation_gain_m"],
  header: {local_date: "Date", activity_type: "Type", area_name: "Area", distance_km: "km", duration_min: "Minutes", elevation_gain_m: "Climb (m)"},
  format: {local_date: (d) => date(d), activity_type: (t) => t.replace(/([a-z])([A-Z])/g, "$1 $2"), distance_km: (v) => num(v, 2), duration_min: (v) => num(v), elevation_gain_m: (v) => (v == null ? "–" : num(v))},
  rows: 14,
  select: false
}));
```

</div>
