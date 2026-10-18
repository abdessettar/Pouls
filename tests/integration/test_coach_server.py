from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest
from mcp import Client

from apple_health.coach import server as coach_server
from apple_health.dashboard import ENV_WAREHOUSE


@pytest.fixture
def coach(built_warehouse, tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_WAREHOUSE, str(built_warehouse))
    monkeypatch.setenv(coach_server.ENV_JOURNAL, str(tmp_path / "journal.sqlite"))
    return coach_server.server


def call(server, *steps):
    """Run tool calls in order against the in-process server; returns their results."""

    async def run():
        out = []
        async with Client(server) as c:
            for name, args in steps:
                r = await c.call_tool(name, args)
                text = r.content[0].text if r.content else ""
                out.append(
                    (r.is_error, text if r.is_error else r.structured_content or json.loads(text or "null"))
                )
        return out

    return asyncio.run(run())


def test_tools_are_listed(coach):
    async def names():
        async with Client(coach) as c:
            return {t.name for t in (await c.list_tools()).tools}

    assert asyncio.run(names()) >= {
        "get_status",
        "get_history",
        "get_recovery",
        "list_workouts",
        "get_workout",
        "get_weight",
        "get_references",
        "get_journal",
        "update_profile",
        "set_habit",
        "log_checkin",
        "log_weight",
        "save_plan",
        "log_session",
        "add_note",
        "get_method",
        "check_readiness",
        "check_plan",
        "habit_progress",
    }


def test_method_prompts_and_guardrails(coach):
    async def run():
        async with Client(coach) as c:
            prompts = {p.name for p in (await c.list_prompts()).prompts}
            method = (await c.call_tool("get_method", {})).content[0].text
            plan = await c.call_tool(
                "check_plan", {"planned_minutes": 500, "recent_weekly_minutes": [100, 100]}
            )
            ready = await c.call_tool("check_readiness", {})
            return prompts, method, plan.structured_content, ready.is_error, ready.structured_content

    prompts, method, plan, ready_err, ready = asyncio.run(run())
    assert prompts == {"coach", "checkin", "review"}
    assert "## Onboarding" in method and "not medical advice" in method
    assert not plan["ok"] and plan["allowed_max_minutes"] == 120
    assert not ready_err and ready["level"] in {"go", "easy", "rest"}


def test_reading_and_writing(coach):
    (err, status), (err2, refusal), _, (err3, day), (err4, weight), (err5, journal) = call(
        coach,
        ("get_status", {}),
        ("log_checkin", {"day": "2023-07-28", "habits": {"no_such_habit": True}}),
        ("set_habit", {"habit_id": "protein", "label": "Protein at each meal", "on": "2023-07-01"}),
        ("log_checkin", {"habits": {"protein": True}, "weight_kg": 80.0, "energy": 4}),  # today
        ("get_weight", {}),
        ("get_journal", {}),
    )
    assert not err and status["profile"]["age"] == 33 and "date_of_birth" not in json.dumps(status)
    assert err2 and "unknown habits" in refusal  # refused, nothing written
    assert not err3 and day["habits"] == {"protein": True} and day["weight_kg"] == 80.0
    assert (
        not err4 and {"day": date.today().isoformat(), "kg": 80.0, "source": "journal"} in weight["entries"]
    )
    assert not err5 and journal["habit_adherence"]["protein"]["days_done"] == 1
