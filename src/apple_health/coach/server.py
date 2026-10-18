"""MCP server: the coach's tools for Claude Code and Claude Desktop (stdio).

Read tools summarise the warehouse (through redact.safe: no places, time zones, devices or identity);
write tools keep the coaching journal on this machine. Registered for Claude Code in .mcp.json; run
by hand with `uv run apple-health-coach`.
"""

from __future__ import annotations

import os
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from apple_health.coach import context, rules
from apple_health.coach.journal import Journal
from apple_health.coach.redact import clean, safe
from apple_health.dashboard import Warehouse

ENV_JOURNAL = "APPLE_HEALTH_COACH_JOURNAL"

INSTRUCTIONS = """\
You are Pouls Coach, a lifestyle and sports coach working from the user's own Apple Health history
and a coaching journal kept on their computer. Before coaching, call get_journal to pick up where you
left off, and get_method for the coaching method you follow. Every warehouse result has
data_through: the history is only as fresh as the last export, so ask about the days after it.
Not medical advice: for chest pain, fainting or unusual breathlessness, tell the user to stop and seek
care; with a condition, medication or a lot of weight to lose, suggest a GP before raising intensity.
"""

server = MCPServer("pouls-coach", instructions=INSTRUCTIONS)


def _wh() -> Warehouse:
    return Warehouse.locate()


def _journal() -> Journal:
    env = os.environ.get(ENV_JOURNAL)
    if env:
        return Journal(Path(env))
    from apple_health.config import load_config

    return Journal(load_config().settings.coach_journal)


def _date(s: str | None) -> date | None:
    try:
        return None if not s else date.fromisoformat(s)
    except ValueError as e:
        raise ToolError(f"dates are YYYY-MM-DD, got {s!r}") from e


def _with_journal(fn: Any) -> Any:
    """Run fn on the journal; its validation errors go back to the coach as readable tool errors."""
    j = _journal()
    try:
        return clean(fn(j))
    except ValueError as e:
        raise ToolError(str(e)) from e
    finally:
        j.close()


# -- reading the history -------------------------------------------------------------------------


@server.tool(
    description="The last 7 and 28 days against your usual periods of the same length, plus age, sex, "
    "height and the last workout. as_of: YYYY-MM-DD (default: the last day of the export)."
)
def get_status(as_of: str | None = None) -> dict[str, Any]:
    return safe(context.status(_wh(), _date(as_of)))


@server.tool(
    description="Month by month since the first data (steps, training hours by activity, running km, "
    "strength sessions, sleep, resting HR, HRV, VO2max) and the best sustained 12 weeks of training."
)
def get_history() -> dict[str, Any]:
    return safe(context.history(_wh()))


@server.tool(
    description="Day by day recovery: resting HR and HRV with z-scores against the previous 60 days, "
    "sleep, workout minutes, training load and the acute/chronic load ratio."
)
def get_recovery(days: int = 14, as_of: str | None = None) -> dict[str, Any]:
    return safe(context.recovery(_wh(), _date(as_of), days=min(max(days, 1), 120)))


@server.tool(
    description="Counted workouts between start and end (YYYY-MM-DD; default the last 28 days of the "
    "export), newest first. kind: e.g. Running, Walking, Cycling:indoor, TraditionalStrengthTraining."
)
def list_workouts(
    start: str | None = None, end: str | None = None, kind: str | None = None
) -> dict[str, Any]:
    return safe(context.workouts(_wh(), _date(start), _date(end), kind))


@server.tool(
    description="One workout in detail: heart-rate zones, heart rate per minute and, for runs, splits per "
    "km. Never the route."
)
def get_workout(workout_id: str) -> dict[str, Any]:
    out = context.workout(_wh(), workout_id)
    if "error" in out:
        raise ToolError(out["error"])
    return safe(out)


@server.tool(
    description="Guideline and population reference bands that apply to the user now (steps, activity, "
    "sleep, resting HR, HRV, VO2max, training load ratio), with their sources."
)
def get_references() -> dict[str, Any]:
    return safe(context.references(_wh()))


@server.tool(
    description="All weigh-ins: from Apple Health (via the export) and from the journal, by day; "
    "journal entries win on the same day."
)
def get_weight() -> dict[str, Any]:
    health = context.weight(_wh())
    mine = _with_journal(lambda j: j.weights())
    by_day = {
        e["date"]: {"day": e["date"], "kg": e["kg"], "source": "apple_health"} for e in health["entries"]
    }
    by_day.update({e["day"]: {"day": e["day"], "kg": e["kg"], "source": "journal"} for e in mine})
    entries = [by_day[d] for d in sorted(by_day)]
    return safe(
        {
            "data_through": health["data_through"],
            "trend": rules.weight_trend(entries, date.today()),
            "entries": entries,
        }
    )


# -- the journal ---------------------------------------------------------------------------------


@server.tool(
    description="The coaching journal: profile and goals, active habits and adherence, recent check-ins, "
    "weigh-ins, the current plan, session notes and your own notes. Call it first in a session."
)
def get_journal(days: int = 28) -> dict[str, Any]:
    return _with_journal(lambda j: j.summary(days=min(max(days, 1), 365)))


@server.tool(
    description="Merge fields into the profile: goals, why they matter, health notes (conditions, "
    "injuries, medication, last check-up), availability, where they can train, equipment, what they "
    "enjoy, food and sleep habits. A null value removes a field."
)
def update_profile(fields: dict[str, Any]) -> dict[str, Any]:
    return _with_journal(lambda j: j.update_profile(fields))


@server.tool(
    description="Start (active=true) or end a habit. habit_id: short slug, e.g. protein_each_meal. "
    "kind: food, drink, sleep, activity or other."
)
def set_habit(
    habit_id: str, label: str, kind: str = "food", active: bool = True, on: str | None = None
) -> Any:
    return _with_journal(lambda j: j.set_habit(habit_id, label, kind, active, on))


@server.tool(
    description="Record a day's check-in (default today): habits done or not ({habit_id: true/false}), "
    "weight in kg, energy, soreness and sleep quality from 1 to 5, and notes. Later calls fill in "
    "the same day."
)
def log_checkin(
    day: str | None = None,
    habits: dict[str, bool] | None = None,
    weight_kg: float | None = None,
    energy: int | None = None,
    soreness: int | None = None,
    sleep_quality: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    return _with_journal(lambda j: j.checkin(day, habits, weight_kg, energy, soreness, sleep_quality, notes))


@server.tool(description="Record a weigh-in in kg (default today).")
def log_weight(kg: float, day: str | None = None, note: str | None = None) -> dict[str, Any]:
    return _with_journal(lambda j: j.log_weight(kg, day, note))


@server.tool(
    description="Save the plan for a week (week_start: a Monday). plan: free-form JSON, e.g. "
    "{sessions: [{day, type, minutes, intensity, details}], steps_target, habits_focus, notes}; "
    "rationale: why, in a sentence or two."
)
def save_plan(week_start: str, plan: dict[str, Any], rationale: str | None = None) -> Any:
    return _with_journal(lambda j: j.save_plan(week_start, plan, rationale))


@server.tool(
    description="Record how a session went (default today): what was done, effort (RPE 1-10), how it "
    "felt, any pain, and the warehouse workout_id once the export has it."
)
def log_session(
    description: str,
    day: str | None = None,
    rpe: int | None = None,
    felt: str | None = None,
    pain: str | None = None,
    workout_id: str | None = None,
) -> dict[str, Any]:
    return _with_journal(lambda j: j.log_session(description, day, rpe, felt, pain, workout_id))


@server.tool(
    description="Remember something about the user for later sessions (what works, what does not, "
    "preferences, context). topic: optional short tag."
)
def add_note(text: str, topic: str | None = None) -> dict[str, Any]:
    return _with_journal(lambda j: j.add_note(text, topic))


# -- the method and the guardrails ---------------------------------------------------------------


METHOD = files("apple_health.coach").joinpath("method.md")


@server.tool(
    description="The coaching method you follow: sessions, onboarding, planning, check-ins, reviews, "
    "food habits, safety. Read it at the start of a session."
)
def get_method() -> str:
    return METHOD.read_text(encoding="utf-8")


@server.tool(
    description="Today's readiness ('go', 'easy' or 'rest') from the latest recovery data and the day's "
    "check-in, with reasons. day: YYYY-MM-DD (default today)."
)
def check_readiness(day: str | None = None) -> dict[str, Any]:
    today = _date(day) or date.today()
    rec = context.recovery(_wh(), days=3)["days"]
    checkin = _with_journal(lambda j: j.day(today.isoformat()))["checkin"]
    return safe(rules.readiness(rec, checkin, today))


@server.tool(
    description="Check next week's plan before saving it: planned minutes of training (all sessions), "
    "hard minutes (zones 4-5), phase (restart, build, consolidate). recent_weekly_minutes: the last "
    "weeks, oldest first; by default the last four complete weeks of the export."
)
def check_plan(
    planned_minutes: float,
    planned_hard_minutes: float = 0,
    phase: str = "restart",
    recent_weekly_minutes: list[float] | None = None,
) -> dict[str, Any]:
    if recent_weekly_minutes is None:
        recent_weekly_minutes = context.recent_weekly_minutes(_wh(), weeks=4)
    return rules.check_plan(planned_minutes, recent_weekly_minutes, planned_hard_minutes, phase)


@server.tool(
    description="Each active habit over the last 14 days, and whether it is time to add the next one."
)
def habit_progress() -> dict[str, Any]:
    today = date.today()

    def run(j: Journal) -> dict[str, Any]:
        log = j.summary(days=14)["habit_log"]
        return rules.habit_progress(j.habits(), log, today)

    return _with_journal(run)


@server.prompt(description="Start a coaching session (the first one is an onboarding interview).")
def coach() -> str:
    return (
        "Start a Pouls Coach session. Call get_method and follow it, then get_journal. If the profile is "
        "empty, run the onboarding; otherwise greet me, say in two lines where things stand (get_status, "
        "the current plan) and ask what I want to work on today."
    )


@server.prompt(description="A two-minute daily check-in.")
def checkin() -> str:
    return (
        "Daily check-in, following get_method. Ask me in one message: which habits I kept, my weight if I "
        "weighed, energy and soreness (1-5) and how I slept; save it with log_checkin, then call "
        "check_readiness and tell me today's session from the current plan, or an easier one, and why."
    )


@server.prompt(description="The weekly review and next week's plan.")
def review() -> str:
    return (
        "Weekly review, following the 'Weekly review' section of get_method: plan against what happened, "
        "habit_progress, the weight trend, recovery; what went well, then next week's plan through "
        "check_plan and save_plan, and add_note for what you learned."
    )


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
