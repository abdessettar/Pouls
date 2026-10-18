"""The coaching journal: what you tell the coach, and what it decides, kept on this machine.

A small SQLite file (standard library only; path in config/settings.toml [coach]): your profile and
goals, habits and their daily yes/no, check-ins, weigh-ins, weekly plans, how sessions felt, and the
coach's own notes. It is git-ignored: it is personal.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS habit (
    id TEXT PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL,
    started_on TEXT NOT NULL, ended_on TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS habit_log (
    day TEXT NOT NULL, habit_id TEXT NOT NULL REFERENCES habit(id), done INTEGER NOT NULL,
    PRIMARY KEY (day, habit_id));
CREATE TABLE IF NOT EXISTS checkin (
    day TEXT PRIMARY KEY, energy INTEGER, soreness INTEGER, sleep_quality INTEGER, notes TEXT,
    updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS weight (
    day TEXT PRIMARY KEY, kg REAL NOT NULL, note TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plan (
    week_start TEXT PRIMARY KEY, plan TEXT NOT NULL, rationale TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, description TEXT NOT NULL,
    workout_id TEXT, rpe INTEGER, felt TEXT, pain TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS note (
    id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, text TEXT NOT NULL, created_at TEXT NOT NULL);
"""
HABIT_KINDS = ("food", "drink", "sleep", "activity", "other")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _day(d: str | date | None) -> str:
    if d is None:
        return date.today().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return date.fromisoformat(d).isoformat()


def _scale(name: str, v: int | None, lo: int, hi: int) -> int | None:
    if v is None:
        return None
    if not lo <= int(v) <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return int(v)


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # -- profile ---------------------------------------------------------------------------------
    def profile(self) -> dict[str, Any]:
        return {r["key"]: json.loads(r["value"]) for r in self.db.execute("SELECT key, value FROM profile")}

    def update_profile(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Merge fields (goals, health notes, availability, equipment, preferences...); None removes."""
        with self.db:
            for k, v in fields.items():
                if v is None:
                    self.db.execute("DELETE FROM profile WHERE key = ?", (k,))
                else:
                    self.db.execute(
                        "INSERT INTO profile VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE"
                        " SET value = excluded.value,"
                        " updated_at = excluded.updated_at",
                        (k, json.dumps(v, ensure_ascii=False), _now()),
                    )
        return self.profile()

    # -- habits ----------------------------------------------------------------------------------
    def set_habit(
        self, habit_id: str, label: str, kind: str = "food", active: bool = True, on: str | None = None
    ) -> dict[str, Any]:
        if kind not in HABIT_KINDS:
            raise ValueError(f"kind must be one of {HABIT_KINDS}")
        day = _day(on)
        with self.db:
            if active:
                self.db.execute(
                    "INSERT INTO habit (id, label, kind, started_on) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(id) DO UPDATE"
                    " SET label = excluded.label, kind = excluded.kind, ended_on = NULL",
                    (habit_id, label, kind, day),
                )
            else:
                self.db.execute("UPDATE habit SET ended_on = ? WHERE id = ?", (day, habit_id))
        return self.habits()

    def habits(self, active_only: bool = True) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM habit"
            + (" WHERE ended_on IS NULL" if active_only else "")
            + " ORDER BY started_on"
        )
        return [dict(r) for r in self.db.execute(q)]

    # -- daily -----------------------------------------------------------------------------------
    def checkin(
        self,
        day: str | None = None,
        habits: dict[str, bool] | None = None,
        weight_kg: float | None = None,
        energy: int | None = None,
        soreness: int | None = None,
        sleep_quality: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        d = _day(day)
        known = {h["id"] for h in self.habits(active_only=False)}
        unknown = set(habits or {}) - known
        if unknown:
            raise ValueError(f"unknown habits {sorted(unknown)}; add them with set_habit first")
        with self.db:
            self.db.execute(
                "INSERT INTO checkin VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(day) DO UPDATE SET"
                " energy = COALESCE(excluded.energy, energy),"
                " soreness = COALESCE(excluded.soreness, soreness),"
                " sleep_quality = COALESCE(excluded.sleep_quality, sleep_quality),"
                " notes = COALESCE(excluded.notes, notes), updated_at = excluded.updated_at",
                (
                    d,
                    _scale("energy", energy, 1, 5),
                    _scale("soreness", soreness, 1, 5),
                    _scale("sleep_quality", sleep_quality, 1, 5),
                    notes,
                    _now(),
                ),
            )
            for hid, done in (habits or {}).items():
                self.db.execute(
                    "INSERT INTO habit_log VALUES (?, ?, ?)"
                    " ON CONFLICT(day, habit_id) DO UPDATE SET done = excluded.done",
                    (d, hid, int(bool(done))),
                )
        if weight_kg is not None:
            self.log_weight(weight_kg, d)
        return self.day(d)

    def log_weight(self, kg: float, day: str | None = None, note: str | None = None) -> dict[str, Any]:
        if not 30 <= float(kg) <= 300:
            raise ValueError("weight must be between 30 and 300 kg")
        d = _day(day)
        with self.db:
            self.db.execute(
                "INSERT INTO weight VALUES (?, ?, ?, ?) ON CONFLICT(day) DO UPDATE SET kg = excluded.kg,"
                " note = COALESCE(excluded.note, note), updated_at = excluded.updated_at",
                (d, round(float(kg), 1), note, _now()),
            )
        return {"day": d, "kg": round(float(kg), 1)}

    def day(self, d: str) -> dict[str, Any]:
        c = self.db.execute("SELECT * FROM checkin WHERE day = ?", (d,)).fetchone()
        w = self.db.execute("SELECT kg FROM weight WHERE day = ?", (d,)).fetchone()
        hl = {
            r["habit_id"]: bool(r["done"])
            for r in self.db.execute("SELECT * FROM habit_log WHERE day = ?", (d,))
        }
        return {
            "day": d,
            "checkin": None
            if c is None
            else {k: c[k] for k in ("energy", "soreness", "sleep_quality", "notes")},
            "habits": hl,
            "weight_kg": None if w is None else w["kg"],
        }

    # -- plans, sessions, notes ------------------------------------------------------------------
    def save_plan(
        self, week_start: str, plan: dict[str, Any], rationale: str | None = None
    ) -> dict[str, Any]:
        ws = date.fromisoformat(week_start)
        if ws.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        with self.db:
            self.db.execute(
                "INSERT INTO plan VALUES (?, ?, ?, ?) ON CONFLICT(week_start) DO UPDATE"
                " SET plan = excluded.plan,"
                " rationale = excluded.rationale, created_at = excluded.created_at",
                (ws.isoformat(), json.dumps(plan, ensure_ascii=False), rationale, _now()),
            )
        return self.plan(ws.isoformat())

    def plan(self, week_start: str | None = None, today: str | None = None) -> dict[str, Any] | None:
        """The plan for a week (default: the latest one starting on or before today)."""
        if week_start:
            r = self.db.execute("SELECT * FROM plan WHERE week_start = ?", (week_start,)).fetchone()
        else:
            r = (
                self.db.execute(
                    "SELECT * FROM plan WHERE week_start <= ? ORDER BY week_start DESC LIMIT 1",
                    (_day(today),),
                ).fetchone()
                or self.db.execute("SELECT * FROM plan ORDER BY week_start LIMIT 1").fetchone()
            )
        return (
            None
            if r is None
            else {"week_start": r["week_start"], "plan": json.loads(r["plan"]), "rationale": r["rationale"]}
        )

    def log_session(
        self,
        description: str,
        day: str | None = None,
        rpe: int | None = None,
        felt: str | None = None,
        pain: str | None = None,
        workout_id: str | None = None,
    ) -> dict[str, Any]:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO session (day, description, workout_id, rpe, felt, pain, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_day(day), description, workout_id, _scale("rpe", rpe, 1, 10), felt, pain, _now()),
            )
        return dict(self.db.execute("SELECT * FROM session WHERE id = ?", (cur.lastrowid,)).fetchone())

    def add_note(self, text: str, topic: str | None = None) -> dict[str, Any]:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO note (topic, text, created_at) VALUES (?, ?, ?)", (topic, text, _now())
            )
        return dict(self.db.execute("SELECT * FROM note WHERE id = ?", (cur.lastrowid,)).fetchone())

    # -- reading -----------------------------------------------------------------------------------
    def weights(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute("SELECT day, kg, note FROM weight ORDER BY day")]

    def summary(self, days: int = 28, today: str | None = None) -> dict[str, Any]:
        """Everything the coach needs to pick up where it left off."""
        end = date.fromisoformat(_day(today))
        start = (end - timedelta(days=days - 1)).isoformat()
        habits = self.habits()
        log = [
            dict(r) for r in self.db.execute("SELECT * FROM habit_log WHERE day >= ? ORDER BY day", (start,))
        ]
        adherence = {}
        for h in habits:
            rows = [r for r in log if r["habit_id"] == h["id"]]
            adherence[h["id"]] = {"days_logged": len(rows), "days_done": sum(r["done"] for r in rows)}
        return {
            "today": end.isoformat(),
            "profile": self.profile(),
            "habits": habits,
            "habit_adherence": adherence,
            "checkins": [
                dict(r)
                for r in self.db.execute("SELECT * FROM checkin WHERE day >= ? ORDER BY day", (start,))
            ],
            "habit_log": log,
            "weights": [
                dict(r)
                for r in self.db.execute("SELECT day, kg FROM weight WHERE day >= ? ORDER BY day", (start,))
            ],
            "current_plan": self.plan(today=end.isoformat()),
            "sessions": [
                dict(r)
                for r in self.db.execute("SELECT * FROM session WHERE day >= ? ORDER BY day", (start,))
            ],
            "notes": [dict(r) for r in self.db.execute("SELECT * FROM note ORDER BY id DESC LIMIT 30")],
        }
