"""Guardrails the coach calls rather than improvises (the method in method.md).

Plain functions over plain data: readiness from recovery and the day's check-in, a check of a week's
plan against what was actually done, the weight trend from a 7-day average, and whether the habits
hold well enough to add the next one. The thresholds are deliberately conservative.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean
from typing import Any

STRAIN_Z = 1.0  # as analytics.strain_z
SHORT_NIGHT_MIN = 360  # under 6 h asleep
RATIO_HIGH, RATIO_DANGER = 1.3, 1.5  # acute/chronic load (Gabbett 2016)
WEEKLY_INCREASE = 0.10
RESTART_FLOOR_MIN = 120  # minutes a week always allowed when restarting from little or nothing
LOSS_FAST, LOSS_TARGET_LO = 1.0, 0.25  # % of body weight per week
HABIT_HOLDS = 0.8  # share of logged days done
HABIT_MIN_DAYS = 10  # of the last 14


def readiness(
    recovery_days: list[dict[str, Any]], checkin: dict[str, Any] | None, today: date
) -> dict[str, Any]:
    """'go', 'easy' or 'rest', with the reasons. Uses the latest recovery day if it is recent."""
    reasons_rest: list[str] = []
    reasons_easy: list[str] = []
    latest = recovery_days[-1] if recovery_days else None
    age = None if latest is None else (today - date.fromisoformat(str(latest["date"]))).days
    if latest is not None and age is not None and age <= 2:
        zh, zr = latest.get("z_hrv"), latest.get("z_resting_hr")
        if zh is not None and zr is not None:
            if zh <= -1.5 * STRAIN_Z and zr >= 1.5 * STRAIN_Z:
                reasons_rest.append("HRV well below and resting heart rate well above your baseline")
            elif zh <= -STRAIN_Z and zr >= STRAIN_Z:
                reasons_easy.append("HRV below and resting heart rate above your baseline")
        if (latest.get("asleep_min") or 10**6) < SHORT_NIGHT_MIN:
            reasons_easy.append("under 6 hours of sleep")
        ratio = latest.get("load_ratio")
        if ratio is not None and ratio >= RATIO_DANGER:
            reasons_rest.append(f"training load ratio {ratio:.2f} (1.5 or more: injury risk rises)")
        elif ratio is not None and ratio > RATIO_HIGH:
            reasons_easy.append(f"training load ratio {ratio:.2f} (above 1.3)")
    c = checkin or {}
    if (c.get("soreness") or 0) >= 5 or c.get("energy") == 1:
        reasons_rest.append("very sore or exhausted today")
    elif (c.get("soreness") or 0) >= 4 or c.get("energy") == 2:
        reasons_easy.append("sore or low on energy today")
    level = "rest" if reasons_rest else "easy" if reasons_easy else "go"
    return {
        "level": level,
        "reasons": reasons_rest + reasons_easy,
        "recovery_data_age_days": age,
        "note": None
        if age is not None and age <= 2
        else (
            "The export is older than two days: readiness rests on today's check-in only; ask how they slept."
        ),
    }


def check_plan(
    planned_minutes: float,
    recent_weekly_minutes: list[float],
    planned_hard_minutes: float = 0,
    phase: str = "restart",
) -> dict[str, Any]:
    """Is next week's volume a sensible step from the last weeks? recent_weekly_minutes: oldest first."""
    last = recent_weekly_minutes[-1] if recent_weekly_minutes else 0.0
    avg4 = mean(recent_weekly_minutes[-4:]) if recent_weekly_minutes else 0.0
    allowed = max(max(last, avg4) * (1 + WEEKLY_INCREASE), RESTART_FLOOR_MIN)
    issues = []
    if planned_minutes > allowed:
        issues.append(
            f"{planned_minutes:.0f} min planned; up to {allowed:.0f} min keeps the increase within "
            f"{WEEKLY_INCREASE:.0%} of recent weeks (or {RESTART_FLOOR_MIN} min when restarting)"
        )
    if phase == "restart" and planned_minutes and planned_hard_minutes / planned_minutes > 0.2:
        issues.append("in the restart phase keep hard minutes (zone 4-5, breathless) under 20% of the week")
    return {"ok": not issues, "allowed_max_minutes": round(allowed), "issues": issues}


def weight_trend(entries: list[dict[str, Any]], today: date | None = None) -> dict[str, Any]:
    """7-day averages and the rate of change (% of body weight per week) over the last four weeks."""
    if not entries:
        return {"entries": 0, "note": "No weigh-ins yet: two or three a week, same time of day, are enough."}
    points = sorted((date.fromisoformat(str(e["day"])), float(e["kg"])) for e in entries)
    today = today or points[-1][0]

    def avg_at(d: date) -> float | None:
        vals = [kg for day, kg in points if d - timedelta(days=6) <= day <= d]
        return mean(vals) if vals else None

    now = avg_at(today)
    then = avg_at(today - timedelta(days=28))
    rate = None if now is None or then is None else (now - then) / then * 100 / 4
    if rate is None:
        verdict = "Not enough weigh-ins four weeks apart for a trend yet."
    elif rate < -LOSS_FAST:
        verdict = "Losing faster than 1% a week: ease off the deficit to protect muscle and energy."
    elif rate <= -LOSS_TARGET_LO:
        verdict = "On track: a steady loss of about 0.25-1% a week."
    elif rate < LOSS_TARGET_LO:
        verdict = "Stable: fine for maintenance; for loss, tighten one habit rather than everything."
    else:
        verdict = "Gaining: look at the habits that slipped before changing the plan."
    return {
        "entries": len(points),
        "latest": {"day": points[-1][0].isoformat(), "kg": points[-1][1]},
        "avg_7d_kg": None if now is None else round(now, 1),
        "avg_7d_kg_4_weeks_ago": None if then is None else round(then, 1),
        "rate_pct_per_week": None if rate is None else round(rate, 2),
        "verdict": verdict,
    }


def habit_progress(habits: list[dict[str, Any]], log: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Each active habit's last 14 days, and whether it is time to add the next one."""
    start = (today - timedelta(days=13)).isoformat()
    out = []
    for h in habits:
        rows = [r for r in log if r["habit_id"] == h["id"] and r["day"] >= start]
        done = sum(1 for r in rows if r["done"])
        share = done / len(rows) if rows else None
        out.append(
            {
                "habit_id": h["id"],
                "label": h["label"],
                "days_logged": len(rows),
                "days_done": done,
                "share": None if share is None else round(share, 2),
                "holds": bool(rows)
                and len(rows) >= HABIT_MIN_DAYS
                and share is not None
                and share >= HABIT_HOLDS,
            }
        )
    ready = bool(out) and all(h["holds"] for h in out)
    return {
        "habits": out,
        "ready_for_next_habit": ready or not out,
        "rule": f"add a habit when every current one is done on {HABIT_HOLDS:.0%} of at least "
        f"{HABIT_MIN_DAYS} logged days out of the last 14",
    }
