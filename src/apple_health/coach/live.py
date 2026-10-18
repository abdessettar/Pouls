"""The Coach page's data: plan, habits, weight, check-ins and notes from the journal.

Served live by dashboard/scripts/serve.py at /coach.json (so the page is current on the phone without
rebuilding the site), and written at build time by the coach.json loader as a fallback snapshot. It
stays on this machine and the home network: nothing here is sent to Claude.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from apple_health.coach import rules
from apple_health.coach.journal import Journal

ENV_JOURNAL = "APPLE_HEALTH_COACH_JOURNAL"  # as the MCP server


def _weights(j: Journal, health: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day = {
        str(e["date"]): {"day": str(e["date"]), "kg": e["kg"], "source": "apple_health"} for e in health
    }
    by_day.update({e["day"]: {"day": e["day"], "kg": e["kg"], "source": "journal"} for e in j.weights()})
    return [by_day[d] for d in sorted(by_day)]


def payload(
    j: Journal, health_weights: list[dict[str, Any]], data_through: Any = None, today: date | None = None
) -> dict[str, Any]:
    today = today or date.today()
    s = j.summary(days=28, today=today.isoformat())
    weights = _weights(j, health_weights)
    next_monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "data_through": None if data_through is None else str(data_through),
        "profile": s["profile"],
        "plan": s["current_plan"],
        "next_plan": j.plan(next_monday.isoformat()),
        "habits": s["habits"],
        "habit_log": s["habit_log"],
        "habit_progress": rules.habit_progress(s["habits"], s["habit_log"], today),
        "checkins": s["checkins"],
        "sessions": s["sessions"],
        "notes": s["notes"][:12],
        "weights": weights,
        "weight_trend": rules.weight_trend(weights, today),
    }


def build(journal_path: Any = None) -> dict[str, Any]:
    """Everything for the page, reading the journal and the warehouse's weigh-ins."""
    from apple_health.coach import context
    from apple_health.config import load_config
    from apple_health.dashboard import Warehouse

    wh = Warehouse.locate()
    env = os.environ.get(ENV_JOURNAL)
    j = Journal(journal_path or (Path(env) if env else load_config().settings.coach_journal))
    try:
        try:
            health = context.weight(wh)["entries"]
            through = context.data_through(wh)
        except FileNotFoundError:
            health, through = [], None
        return payload(j, health, through)
    finally:
        j.close()
