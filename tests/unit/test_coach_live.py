from __future__ import annotations

import json
from datetime import date

from apple_health.coach.journal import Journal
from apple_health.coach.live import payload


def test_payload_merges_weights_and_shows_the_plan(tmp_path):
    j = Journal(tmp_path / "journal.sqlite")
    j.update_profile({"main_goal": "walk daily", "goal_weight_kg": 65})
    j.set_habit("water", "Water instead of sugary drinks", "drink", on="2025-05-01")
    j.checkin("2025-05-09", habits={"water": True}, energy=4, weight_kg=70.0)
    j.save_plan("2025-05-05", {"sessions": [{"day": "Sat", "type": "walk", "minutes": 40}]})
    j.save_plan("2025-05-12", {"sessions": []}, "next week")
    p = payload(
        j,
        [{"date": "2022-03-01", "kg": 66.0}, {"date": "2025-05-09", "kg": 69.5}],
        "2025-05-05",
        date(2025, 5, 10),
    )
    j.close()
    assert p["plan"]["week_start"] == "2025-05-05" and p["next_plan"]["rationale"] == "next week"
    # The journal wins on the same day; Apple Health fills the rest.
    assert p["weights"] == [
        {"day": "2022-03-01", "kg": 66.0, "source": "apple_health"},
        {"day": "2025-05-09", "kg": 70.0, "source": "journal"},
    ]
    assert p["habit_progress"]["habits"][0]["days_done"] == 1
    assert p["profile"]["goal_weight_kg"] == 65 and p["data_through"] == "2025-05-05"
    json.dumps(p)
