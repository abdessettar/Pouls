# 0007 — Pouls Coach

**Status:** accepted

## Context
The warehouse holds years of activity, heart, sleep and training history. The goal is a coach that
uses it to help build a healthy routine and fitness, while keeping personal data on this computer
as far as possible.

## Decision
- **Claude as the coach, through a local MCP server.** Conversations happen in Claude Code (or
  Claude Desktop); `apple-health-coach` (MCP, stdio) gives Claude tools over the warehouse and a
  local journal. No API key, no web service.
- **A narrow, tested boundary.** Warehouse tools return compact summaries and workout details through
  `redact.safe()`, which removes and then refuses places, routes, time zones, device and app names
  and identity (age, not date of birth). Travel shows only as "away from home".
- **A local journal.** Goals, constraints, habits, check-ins, weigh-ins, weekly plans, session notes
  and the coach's notes live in `coach/journal.sqlite` (SQLite, standard library, git-ignored).
- **Guardrails in code, judgement in the model.** Readiness, the weekly volume check, the weight trend
  and habit progression are deterministic functions (`rules.py`) the coach calls; the method it
  follows is a document (`method.md`) served by `get_method`.
- **Habits, not calories.** Food is coached through a few yes/no habits added one at a time; weight
  is the outcome, read from a 7-day average.
- **Regular exports.** Fresh data comes from a new Health export (weekly works well); between exports
  the user tells the coach. Every warehouse result carries `data_through` so the coach knows how fresh it is.
- **Visible in Pouls.** A Coach page reads the journal live through the dashboard's server.

## Consequences
What Claude sees is what the tools return: changing the boundary means changing `redact.py` and its
tests. The coach is only as current as the last export plus what the user reports. It gives general
coaching, not medical advice, and is instructed to refer to a doctor for warning signs.
