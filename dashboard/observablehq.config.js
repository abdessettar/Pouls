import {createHash} from "node:crypto";
import {existsSync, readFileSync} from "node:fs";

// Loaders run with the repository's uv virtualenv, where the apple_health package is installed.
const PYTHON = existsSync("../.venv/bin/python") ? "../.venv/bin/python" : "python3";

/** One list drives the sidebar. */
const PAGES = [
  {name: "Overview", path: "/"},
  {name: "Coach", path: "/coach"},
  {name: "All time", path: "/all-time"},
  {name: "Activity", path: "/activity"},
  {name: "Heart", path: "/heart"},
  {name: "Sleep", path: "/sleep"},
  {name: "Training", path: "/training"},
  {name: "Workouts", path: "/workouts"},
  {name: "Running", path: "/running"},
  {name: "Places", path: "/places"},
  {name: "Every day", path: "/every-day"},
  {name: "Notes", path: "/notes"}
];

/**
 * Self-hosted Inter. Framework copies files referenced from the head (link[href]) into
 * dist/_file with a content hash, but esbuild cannot bundle font files referenced from CSS, so the
 * @font-face rules are written here with the same hash Framework applies (unhashed in preview).
 */
const PREVIEW = process.argv.includes("preview");
const FONTS = [
  {file: "inter.woff2", style: "normal", preload: true},
  {file: "inter-italic.woff2", style: "italic"}
];
function fontFaces() {
  const links = [];
  const rules = [];
  for (const f of FONTS) {
    const src = `src/fonts/${f.file}`;
    if (!existsSync(src)) continue;
    const hash = createHash("sha256").update(readFileSync(src)).digest("hex").slice(0, 8);
    const dot = f.file.lastIndexOf(".");
    const url = PREVIEW ? `/_file/fonts/${f.file}` : `/_file/fonts/${f.file.slice(0, dot)}.${hash}${f.file.slice(dot)}`;
    links.push(`<link rel="${f.preload ? "preload" : "prefetch"}" as="font" type="font/woff2" crossorigin href="/fonts/${f.file}">`);
    rules.push(`@font-face{font-family:"Inter";font-style:${f.style};font-weight:100 900;font-display:swap;src:url("${url}") format("woff2")}`);
  }
  return links.join("") + `<style>${rules.join("")}</style>`;
}

/**
 * Light / dark: follows the system setting unless the toggle in the header chose one. Set before
 * first paint so the page never flashes the wrong theme.
 */
const THEME_BOOT = `<script>(()=>{try{const t=localStorage.getItem("pouls-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;}catch{}})();</script>`;

const PULSE_ICON = (size) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h4l2.5-6 4 12 3-8 1.5 2H22"/></svg>`;
const FAVICON = "data:image/svg+xml," + encodeURIComponent(
  `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><rect width='24' height='24' rx='6' fill='#e11d48'/><path d='M3 12.5h3.5l2-5 3.5 10 2.5-7 1.3 2H21' fill='none' stroke='#fff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/></svg>`
);

function header() {
  return `<div class="topbar">
    <span class="brand-mark" aria-hidden="true">${PULSE_ICON(16)}</span>
    <button class="theme-toggle" type="button" aria-label="Toggle light and dark theme" onclick="(()=>{const r=document.documentElement;const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;r.dataset.theme=dark?'light':'dark';try{localStorage.setItem('pouls-theme',r.dataset.theme);}catch{}})()">
      <svg class="icon-sun" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
      <svg class="icon-moon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
    </button>
  </div>`;
}

export default {
  title: "Pouls",
  root: "src",
  output: process.env.POULS_OUTPUT ?? "dist",
  interpreters: {".py": [PYTHON]},
  style: "style.css",
  sidebar: true,
  toc: false,
  pager: false,
  search: false,
  // Links end in .html (and /index.html) so `npm run serve`, a plain static server, finds every page.
  preserveExtension: true,
  preserveIndex: true,
  header,
  footer: "Pouls · personal health data from Apple Health, on this computer only. Not medical advice.",
  pages: PAGES,
  head: THEME_BOOT + fontFaces() + `<link rel="icon" type="image/svg+xml" href="${FAVICON}">`
};
