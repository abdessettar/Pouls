/**
 * Leaflet map on OpenStreetMap's standard tiles (no API key; light personal use with attribution, per
 * the OSM tile usage policy). In the dark theme the tile layer is inverted with a CSS filter
 * (style.css), so there is a single tile source. Routes arrive as Google encoded polylines.
 */
import * as L from "npm:leaflet";

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Decode a Google encoded polyline into [[lat, lon], ...]. */
export function decode(str, precision = 5) {
  const factor = 10 ** precision;
  const out = [];
  let i = 0, lat = 0, lon = 0;
  while (i < str.length) {
    for (let k = 0; k < 2; k++) {
      let shift = 0, result = 0, b;
      do {
        b = str.charCodeAt(i++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      const delta = result & 1 ? ~(result >> 1) : result >> 1;
      if (k === 0) lat += delta;
      else lon += delta;
    }
    out.push([lat / factor, lon / factor]);
  }
  return out;
}

/** Create a map in a new div; returns {element, map, renderer}. Call invalidation-safe cleanup via map.remove(). */
export function createMap({height = 520, center = [52.52, 13.4], zoom = 12} = {}) {
  const element = document.createElement("div");
  element.className = "map";
  element.style.height = `${height}px`;
  const map = L.map(element, {center, zoom, preferCanvas: true, zoomControl: true, attributionControl: true});
  L.tileLayer(TILE_URL, {attribution: ATTRIBUTION, maxZoom: 19, className: "osm-tiles"}).addTo(map);
  const renderer = L.canvas({padding: 0.5});
  // Leaflet measures the container on creation; re-measure once it is in the page.
  requestAnimationFrame(() => map.invalidateSize());
  return {element, map, renderer, L};
}

export {L};
