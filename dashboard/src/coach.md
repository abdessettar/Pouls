---
title: Coach
---

```js
import {pageHeader} from "./components/page.js";
import {BASE} from "./components/marks.js";
import {num, date, dateShort, plural} from "./components/format.js";
const meta = FileAttachment("data/meta.json").json();
const SNAPSHOT = FileAttachment("data/coach.json").json();
```

```js
// Live from the journal when the site is served by scripts/serve.py; else the build-time snapshot.
const C = await fetch("./coach.json", {cache: "no-store"})
  .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
  .then((d) => ({...d, live: true}))
  .catch(() => ({...SNAPSHOT, live: false}));
const P = C.profile ?? {};
const D = (s) => new Date(s);
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const started = Object.keys(P).length || C.plan || C.habits.length || C.weights.length;
```

${pageHeader({eyebrow: "Pouls Coach", title: "Coach", subtitle: "Your goals, this week's plan, habits, weight and check-ins, as kept by Pouls Coach in Claude.", meta})}

```js
display(html`<p class="card-note">${C.live ? html`Live from the coach's journal (${C.generated_at.replace("T", " ")}).` : html`Snapshot from the last build (${C.generated_at.replace("T", " ")}); serve the site with <code>npm run serve</code> or <code>npm run serve:lan</code> for live data.`}${C.data_through ? html` Health data through ${date(C.data_through)}.` : ""}</p>`);
```

```js
if (!started) display(html`<div class="card"><h3 class="card-title">No coaching yet</h3><p>In Claude Code, open this project and run <code>/coach</code>. The first session is a short interview about your goals, health, schedule and habits; the coach then proposes a first week. Afterwards, <code>/checkin</code> takes two minutes a day and <code>/review</code> plans each week.</p></div>`);
```

<div class="grid grid-cols-3">
<div class="card">
<div class="card-head"><h3 class="card-title">Goals</h3><span class="card-note">${P.phase ? `phase: ${P.phase}` : ""}</span></div>

```js
const goal = (label, v) => (v ? html`<p style="margin:0 0 10px"><span class="card-note">${label}</span><br><b>${typeof v === "string" ? v : JSON.stringify(v)}</b></p>` : "");
display(html`${goal("Next 12 weeks", P.main_goal)}${goal("Next 4 weeks", P.goal_4_weeks)}${goal("Why", P.why)}${P.goal_weight_kg ? goal("Goal weight", `${num(P.goal_weight_kg, 1)} kg`) : ""}${!P.main_goal && !P.goal_4_weeks ? html`<p class="card-note">Goals appear here after the first <code>/coach</code> session.</p>` : ""}`);
const extra = Object.entries(P).filter(([k]) => !["main_goal", "goal_4_weeks", "why", "phase", "goal_weight_kg"].includes(k));
if (extra.length) display(html`<details><summary class="card-note">Everything the coach knows (${extra.length})</summary><table class="t" style="margin-top:6px">${extra.map(([k, v]) => html`<tr><td class="card-note">${k.replaceAll("_", " ")}</td><td>${typeof v === "string" ? v : JSON.stringify(v)}</td></tr>`)}</table></details>`);
```

</div>
<div class="card grid-colspan-2">
<div class="card-head"><h3 class="card-title">${C.plan ? `Week of ${date(C.plan.week_start)}` : "This week"}</h3><span class="card-note">${C.next_plan ? html`next week planned` : ""}</span></div>

```js
const plan = C.plan?.plan ?? {};
const sessions = (plan.sessions ?? []).slice().sort((a, b) => DAYS.indexOf(String(a.day).slice(0, 3)) - DAYS.indexOf(String(b.day).slice(0, 3)));
const today = DAYS[(D(C.today).getUTCDay() + 6) % 7];
display(C.plan ? html`
  ${C.plan.rationale ? html`<p class="insight">${C.plan.rationale}</p>` : ""}
  ${sessions.length ? html`<table class="t"><thead><tr><th>Day</th><th>Session</th><th class="num">Minutes</th><th>Intensity</th><th>Details</th></tr></thead><tbody>${sessions.map((s) => html`<tr style="${String(s.day).startsWith(today) ? "font-weight:600" : ""}"><td>${s.day}</td><td>${s.type ?? s.session ?? ""}</td><td class="num">${s.minutes ?? s.duration_min ?? ""}</td><td>${s.intensity ?? ""}</td><td class="card-note">${s.details ?? s.notes ?? ""}</td></tr>`)}</tbody></table>` : ""}
  <p class="card-note" style="margin-top:10px">${[plan.steps_target ? `Daily steps: ${num(plan.steps_target)}` : null, plan.habits_focus ? `Habits in focus: ${[].concat(plan.habits_focus).join(", ")}` : null, plan.notes ?? null].filter(Boolean).join(" · ")}</p>` : html`<p class="card-note">No plan yet: the coach saves one at the end of the first session and at each weekly review.</p>`);
```

</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Habits</h3><span class="card-note">last 14 days · ✓ done · ✗ not · blank: not logged</span></div>

```js
const days14 = d3.range(13, -1, -1).map((i) => new Date(D(C.today) - i * 864e5).toISOString().slice(0, 10));
const logOf = new Map(C.habit_log.map((r) => [`${r.habit_id}|${r.day}`, r.done]));
const prog = new Map(C.habit_progress.habits.map((h) => [h.habit_id, h]));
display(C.habits.length ? html`<div style="overflow-x:auto"><table class="t habit-grid"><thead><tr><th>Habit</th>${days14.map((d) => html`<th class="num">${dateShort(d).split(" ")[0]}</th>`)}<th class="num">Done</th></tr></thead><tbody>
  ${C.habits.map((h) => html`<tr><td>${h.label}</td>${days14.map((d) => {
    const v = logOf.get(`${h.id}|${d}`);
    return html`<td class="num" style="color:${v === 1 || v === true ? "var(--good)" : v === 0 || v === false ? "var(--bad)" : "var(--faint)"}">${v === 1 || v === true ? "✓" : v === 0 || v === false ? "✗" : ""}</td>`;
  })}<td class="num">${prog.get(h.id)?.share == null ? "–" : `${Math.round(prog.get(h.id).share * 100)}%`}</td></tr>`)}
</tbody></table></div>
<p class="card-note" style="margin-top:8px">${C.habit_progress.ready_for_next_habit ? "Your habits hold: the coach can add the next one at the weekly review." : C.habit_progress.rule}.</p>` : html`<p class="card-note">No habits yet. The coach starts with one or two food habits.</p>`);
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Weight</h3><span class="card-note">dots: weigh-ins · line: 7-day average</span></div>

```js
// The last six months; old Apple Health weigh-ins would otherwise squash the recent ones.
const ALLW = C.weights.map((w) => ({...w, date: D(w.day)}));
const since = new Date(+D(C.today) - 183 * 864e5);
const W = ALLW.some((w) => w.date >= since) ? ALLW.filter((w) => w.date >= since) : ALLW;
const older = ALLW.length - W.length;
const avg = W.map((w) => {
  const win = W.filter((x) => x.date <= w.date && x.date > new Date(+w.date - 7 * 864e5));
  return {date: w.date, kg: d3.mean(win, (x) => x.kg)};
});
const t = C.weight_trend;
display(html`<p class="insight">${W.length ? html`Latest <b>${num(t.latest.kg, 1)} kg</b> (${date(t.latest.day)})${t.avg_7d_kg != null ? html`; 7-day average <b>${num(t.avg_7d_kg, 1)} kg</b>` : ""}${t.rate_pct_per_week != null ? html`, ${t.rate_pct_per_week > 0 ? "+" : ""}${num(t.rate_pct_per_week, 2)}% a week` : ""}. ${t.verdict}` : t.note}</p>`);
display(W.length > 1 ? resize((width) => Plot.plot({
  ...BASE, width, height: 220,
  x: {type: "utc", label: null},
  y: {grid: true, label: null, zero: false, domain: d3.extent([...W.map((w) => w.kg), ...(P.goal_weight_kg ? [P.goal_weight_kg] : [])]).map((v, i) => v + (i ? 1 : -1))},
  marks: [
    P.goal_weight_kg ? Plot.ruleY([P.goal_weight_kg], {stroke: "var(--good)", strokeDasharray: "4 3"}) : null,
    P.goal_weight_kg ? Plot.text([P.goal_weight_kg], {y: (d) => d, frameAnchor: "left", dy: -6, dx: 4, text: () => "goal", fill: "var(--good)", fontSize: 11}) : null,
    Plot.line(avg, {x: "date", y: "kg", stroke: "var(--heart)", strokeWidth: 2}),
    Plot.dot(W, {x: "date", y: "kg", r: 2.6, fill: (w) => (w.source === "journal" ? "var(--heart)" : "var(--muted)"), fillOpacity: 0.7}),
    Plot.tip(W, Plot.pointerX({x: "date", y: "kg", title: (w) => `${date(w.day)}\n${num(w.kg, 1)} kg (${w.source === "journal" ? "told the coach" : "Apple Health"})`}))
  ]
})) : html``);
if (older) display(html`<p class="card-note">Last six months shown; ${plural(older, "earlier weigh-in")} (the last on ${date(ALLW[older - 1].day)}) not drawn.</p>`);
```

</div>
</div>

<div class="grid grid-cols-2">
<div class="card">
<div class="card-head"><h3 class="card-title">Check-ins</h3><span class="card-note">last 28 days · 1 (low) to 5 (high)</span></div>

```js
const CK = C.checkins.flatMap((c) => [["energy", "Energy", "var(--activity)"], ["soreness", "Soreness", "var(--bad)"], ["sleep_quality", "Sleep", "var(--sleep)"]].filter(([k]) => c[k] != null).map(([k, label, color]) => ({date: D(c.day), v: c[k], label, color})));
display(CK.length ? resize((width) => Plot.plot({
  ...BASE, width, height: 180,
  x: {type: "utc", label: null},
  y: {domain: [1, 5], ticks: 5, grid: true, label: null},
  marks: [
    Plot.line(CK, {x: "date", y: "v", z: "label", stroke: "color", strokeWidth: 1.6, marker: "dot"}),
    Plot.tip(CK, Plot.pointer({x: "date", y: "v", title: (d) => `${date(d.date)}\n${d.label}: ${d.v}`}))
  ]
})) : html`<p class="card-note">No check-ins yet: run <code>/checkin</code> in Claude Code.</p>`);
if (CK.length) display(html`<div class="legend"><span class="legend-item"><span class="swatch" style="background:var(--activity)"></span>Energy</span><span class="legend-item"><span class="swatch" style="background:var(--bad)"></span>Soreness</span><span class="legend-item"><span class="swatch" style="background:var(--sleep)"></span>Sleep</span></div>`);
const notes = C.checkins.filter((c) => c.notes).slice(-5).reverse();
if (notes.length) display(html`<ul class="highlights" style="margin-top:10px">${notes.map((c) => html`<li><span class="card-note">${dateShort(c.day)}</span> ${c.notes}</li>`)}</ul>`);
```

</div>
<div class="card">
<div class="card-head"><h3 class="card-title">Sessions and notes</h3><span class="card-note">what you told the coach, and what it noted</span></div>

```js
display(C.sessions.length ? html`<table class="t"><thead><tr><th>Date</th><th>Session</th><th class="num">Effort</th><th>Felt</th></tr></thead><tbody>${C.sessions.slice().reverse().slice(0, 10).map((s) => html`<tr><td class="card-note">${dateShort(s.day)}</td><td>${s.description}${s.pain ? html` <span class="chip bad">pain: ${s.pain}</span>` : ""}</td><td class="num">${s.rpe ?? "–"}</td><td class="card-note">${s.felt ?? ""}</td></tr>`)}</tbody></table>` : html`<p class="card-note">No sessions logged in the last 28 days.</p>`);
if (C.notes.length) display(html`<details style="margin-top:12px"><summary class="card-note">Coach's notes (${C.notes.length})</summary><ul class="highlights">${C.notes.map((n) => html`<li>${n.topic ? html`<span class="card-note">${n.topic}:</span> ` : ""}${n.text}</li>`)}</ul></details>`);
```

</div>
</div>

<p class="source">The journal lives in coach/journal.sqlite on this computer. This page shows it as it is; nothing here is sent anywhere. Not medical advice.</p>
