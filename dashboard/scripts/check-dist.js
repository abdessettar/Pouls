#!/usr/bin/env node
// Post-build checks, run by `npm run build` after `observable build`.
//
// 1. Every page in the sidebar was built.
// 2. Every JSON data file parses (so no NaN / Infinity slipped through a loader).
// 3. Size budgets per data file, and nothing above 25 MB.
import {existsSync, readdirSync, readFileSync, statSync} from "node:fs";
import {join} from "node:path";

const DIST = process.env.POULS_OUTPUT ?? "dist";
const PAGES = ["index", "coach", "all-time", "activity", "heart", "sleep", "training", "workouts", "running", "places", "every-day", "notes"];
const MB = 1024 * 1024;
// Budgets by data-file stem (the name before Framework's content hash).
const BUDGETS = {meta: 0.05 * MB, overview: 1.5 * MB, daily: 2 * MB, tracks: 15 * MB};
const DEFAULT_BUDGET = 5 * MB;
const HARD_LIMIT = 25 * MB;

let failed = false;
const fail = (msg) => { failed = true; console.error(`check-dist: ${msg}`); };

for (const p of PAGES) if (!existsSync(join(DIST, `${p}.html`))) fail(`missing page ${p}.html`);

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

const files = walk(DIST);
for (const f of files) {
  const size = statSync(f).size;
  if (size > HARD_LIMIT) fail(`${f} is ${(size / MB).toFixed(1)} MB (limit 25 MB)`);
}
const dataFiles = files.filter((f) => f.includes(`${join("_file", "data")}`));
for (const f of dataFiles) {
  const base = f.split("/").pop();
  const stem = base.replace(/\.[0-9a-f]{8}\.[a-z]+$/, "").replace(/\.[a-z]+$/, "");
  const budget = BUDGETS[stem] ?? DEFAULT_BUDGET;
  const size = statSync(f).size;
  if (size > budget) fail(`${base} is ${(size / 1024).toFixed(0)} KB, over its ${(budget / 1024).toFixed(0)} KB budget`);
  if (f.endsWith(".json")) {
    try { JSON.parse(readFileSync(f, "utf8")); } catch (e) { fail(`${base} is not valid JSON: ${e.message}`); }
  }
}
if (failed) process.exit(1);
console.log(`check-dist: ${PAGES.length} pages, ${dataFiles.length} data files ok`);
