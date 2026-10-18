from __future__ import annotations

import pytest

from apple_health.coach.journal import Journal


@pytest.fixture
def j(tmp_path):
    journal = Journal(tmp_path / "coach" / "journal.sqlite")
    yield journal
    journal.close()


def test_profile_merges_and_removes(j):
    j.update_profile({"goal": "lose weight", "availability": {"weekdays": "evenings"}})
    assert j.update_profile({"goal": None, "equipment": ["dumbbells"]}) == {
        "availability": {"weekdays": "evenings"},
        "equipment": ["dumbbells"],
    }


def test_checkins_fill_in_the_same_day(j):
    j.set_habit("protein", "Protein at each meal", "food", on="2025-05-01")
    j.checkin("2025-05-05", habits={"protein": True}, energy=3)
    day = j.checkin("2025-05-05", soreness=2, weight_kg=72.04, notes="tired legs")
    assert day == {
        "day": "2025-05-05",
        "checkin": {"energy": 3, "soreness": 2, "sleep_quality": None, "notes": "tired legs"},
        "habits": {"protein": True},
        "weight_kg": 72.0,
    }
    with pytest.raises(ValueError, match="unknown habits"):
        j.checkin("2025-05-05", habits={"no_sugar": True})
    with pytest.raises(ValueError, match="energy"):
        j.checkin("2025-05-05", energy=7)
    with pytest.raises(ValueError, match="weight"):
        j.log_weight(12)


def test_plans_and_summary(j):
    with pytest.raises(ValueError, match="Monday"):
        j.save_plan("2025-05-07", {"sessions": []})
    j.save_plan("2025-05-05", {"sessions": [{"day": "Tue", "type": "walk", "minutes": 30}]}, "restart")
    j.set_habit("water", "Water instead of sugary drinks", "drink", on="2025-05-05")
    j.checkin("2025-05-06", habits={"water": True})
    j.checkin("2025-05-07", habits={"water": False})
    j.log_session("30 min brisk walk", "2025-05-06", rpe=4, felt="good")
    j.add_note("Prefers mornings", "schedule")
    s = j.summary(days=7, today="2025-05-08")
    assert s["current_plan"]["plan"]["sessions"][0]["type"] == "walk"
    assert s["habit_adherence"]["water"] == {"days_logged": 2, "days_done": 1}
    assert s["sessions"][0]["rpe"] == 4 and s["notes"][0]["text"] == "Prefers mornings"
    j.set_habit("water", "Water instead of sugary drinks", active=False, on="2025-05-08")
    assert j.habits() == []
