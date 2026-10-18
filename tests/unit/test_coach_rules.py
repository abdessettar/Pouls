from __future__ import annotations

from datetime import date

from apple_health.coach.rules import check_plan, habit_progress, readiness, weight_trend

TODAY = date(2025, 5, 10)


def day(**kw):
    return {
        "date": "2025-05-09",
        "z_hrv": 0.0,
        "z_resting_hr": 0.0,
        "asleep_min": 450,
        "load_ratio": 1.0,
        **kw,
    }


def test_readiness_levels():
    assert readiness([day()], None, TODAY)["level"] == "go"
    assert readiness([day(z_hrv=-1.2, z_resting_hr=1.1)], None, TODAY)["level"] == "easy"
    assert readiness([day(z_hrv=-1.6, z_resting_hr=1.7)], None, TODAY)["level"] == "rest"
    assert readiness([day(load_ratio=1.6)], None, TODAY)["level"] == "rest"
    assert readiness([day(asleep_min=300)], {"energy": 4}, TODAY)["level"] == "easy"
    assert readiness([day()], {"soreness": 5}, TODAY)["level"] == "rest"
    stale = readiness([day(date="2025-05-01", z_hrv=-3, z_resting_hr=3)], {"energy": 4}, TODAY)
    assert (
        stale["level"] == "go" and stale["recovery_data_age_days"] == 9 and "check-in only" in stale["note"]
    )


def test_check_plan_caps_increases_but_allows_a_restart():
    assert check_plan(110, [0, 0, 0, 0])["ok"]  # restarting from nothing: the floor applies
    out = check_plan(300, [150, 160, 170, 180])
    assert not out["ok"] and out["allowed_max_minutes"] == 198
    hard = check_plan(150, [140, 140], planned_hard_minutes=60)
    assert not hard["ok"] and "hard minutes" in hard["issues"][0]
    assert check_plan(150, [140, 140], planned_hard_minutes=60, phase="build")["ok"]


def test_weight_trend():
    assert weight_trend([])["entries"] == 0
    entries = [{"day": f"2025-04-{d:02d}", "kg": 100.0} for d in (8, 10, 12)] + [
        {"day": f"2025-05-{d:02d}", "kg": 98.0} for d in (6, 8, 10)
    ]
    t = weight_trend(entries, TODAY)
    assert t["avg_7d_kg"] == 98.0 and t["avg_7d_kg_4_weeks_ago"] == 100.0
    assert t["rate_pct_per_week"] == -0.5 and t["verdict"].startswith("On track")
    fast = weight_trend([{"day": "2025-04-12", "kg": 100.0}, {"day": "2025-05-10", "kg": 94.0}], TODAY)
    assert fast["verdict"].startswith("Losing faster")


def test_habit_progress():
    habits = [{"id": "water", "label": "Water"}]
    log = [{"habit_id": "water", "day": f"2025-05-{d:02d}", "done": d != 3} for d in range(1, 11)]
    p = habit_progress(habits, log, TODAY)
    assert p["habits"][0]["share"] == 0.9 and p["ready_for_next_habit"]
    short = habit_progress(habits, log[:5], TODAY)
    assert not short["ready_for_next_habit"]  # too few days logged to judge
    assert habit_progress([], [], TODAY)["ready_for_next_habit"]
