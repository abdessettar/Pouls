"""What the coach sees: compact summaries of the warehouse for a coaching conversation.

Each function returns plain JSON-ready data with `data_through`, the last day the export covers, so
the coach knows how fresh it is. Results pass through redact.safe() in the server; nothing here
includes places, time zones, device or app names.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse, jsonable
from apple_health.dashboard.references import bands
from apple_health.dashboard.workouts import kind_label, sessions

# (key, label, unit, column in the day frame, statistic, valid wear days only, scale)
# median: median day; rate_week: total per 7 days; share: share of days; last: latest value.
METRICS = [
    ("steps", "Steps per day", "steps", "steps", "median", True, 1.0),
    ("active_energy", "Active energy per day", "kcal", "active_energy_kcal", "median", True, 1.0),
    ("exercise", "Exercise minutes per week", "min", "exercise_min", "rate_week", False, 1.0),
    ("training", "Training per week", "h", "workout_min", "rate_week", False, 1 / 60),
    ("workouts", "Workouts per week", "", "n_workouts", "rate_week", False, 1.0),
    ("strength", "Strength sessions per week", "", "strength_sessions", "rate_week", False, 1.0),
    ("running", "Running per week", "km", "run_km", "rate_week", False, 1.0),
    ("resting_hr", "Resting heart rate", "bpm", "resting_hr_bpm", "median", True, 1.0),
    ("hrv", "HRV during sleep (SDNN)", "ms", "hrv_sdnn_sleep_ms", "median", True, 1.0),
    ("asleep", "Time asleep", "min", "sleep_asleep_min", "median", True, 1.0),
    ("bedtime", "Bedtime (hours after the previous midnight)", "h", "bedtime_h", "median", True, 1.0),
    ("vo2max", "VO2max (latest estimate)", "mL/kg/min", "vo2max_asof", "last", False, 1.0),
    ("rings", "Days with all rings closed", "share", "all_rings_closed", "share", False, 1.0),
]
GROUPS = ("walking", "running", "strength", "cycling", "other")


def _days(wh: Warehouse) -> pl.DataFrame:
    """One row per day: mart_daily plus running km, strength sessions and minutes per activity group."""
    d = wh.read("marts", "mart_daily").sort("local_date")
    runs = (
        wh.read("marts", "mart_run").group_by("local_date").agg(pl.col("distance_km").sum().alias("run_km"))
    )
    w = wh.read("marts", "mart_workout").filter(pl.col("is_counted"))
    per_group = w.group_by("local_date").agg(
        (pl.col("activity_group") == "strength").sum().cast(pl.Int32).alias("strength_sessions"),
        *[
            pl.col("duration_min").filter(pl.col("activity_group") == g).sum().alias(f"{g}_min")
            for g in GROUPS
        ],
    )
    return d.join(runs, on="local_date", how="left").join(per_group, on="local_date", how="left")


def _values(d: pl.DataFrame, column: str, stat: str, valid_only: bool) -> list[float | None]:
    vals = d[column].to_list()
    valid = d["is_valid_wear_day"].to_list()
    out: list[float | None] = []
    for v, ok in zip(vals, valid, strict=True):
        if valid_only and not ok:
            out.append(None)
        elif stat == "share":
            out.append(None if v is None else float(bool(v)))
        elif stat == "rate_week":
            out.append(float(v or 0))  # no workout that day counts as zero
        else:
            out.append(None if v is None else float(v))
    return out


def _reduce(vals: list[float | None], stat: str, scale: float) -> float | None:
    have = [v for v in vals if v is not None]
    if not have:
        return None
    if stat in ("median", "share") and len(have) < max(1, len(vals) // 4):
        return None
    if stat == "median":
        return median(have) * scale
    if stat == "share":
        return sum(have) / len(have)
    if stat == "rate_week":
        return sum(have) / len(vals) * 7 * scale
    return have[-1] * scale  # last


def _usual(vals: list[float | None], n: int, stat: str, scale: float) -> float | None:
    """The median of the statistic over every n-day period (stepping n/30 days)."""
    if len(vals) < 2 * n:
        return None
    step = max(1, n // 30)
    results = [
        r
        for i in range(0, len(vals) - n + 1, step)
        if (r := _reduce(vals[i : i + n], stat, scale)) is not None
    ]
    return median(results) if len(results) >= 3 else None


def _start(d: pl.DataFrame, column: str) -> int:
    """First day the measure has data (totals before it are unknown, not zero)."""
    idx = d.with_row_index().filter(pl.col(column).is_not_null())["index"]
    return int(idx[0]) if idx.len() else d.height


def data_through(wh: Warehouse) -> date:
    return wh.read("marts", "mart_daily")["local_date"].max()  # type: ignore[return-value]


def profile(wh: Warehouse, as_of: date | None = None) -> dict[str, Any]:
    """Age (never the date of birth), sex and the latest height."""
    as_of = as_of or data_through(wh)
    p = wh.read("curated", "dim_profile")
    dob = p["date_of_birth"][0] if p.height else None
    age = None if dob is None else as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))
    h = (
        wh.scan("curated", "fct_quantity_sample")
        .filter(pl.col("type") == "Height")
        .sort("start_utc")
        .select("value")
        .collect()
    )
    return {
        "age": age,
        "sex": p["biological_sex"][0] if p.height else None,
        "height_cm": round(h["value"][-1], 1) if h.height else None,
    }


def status(wh: Warehouse, as_of: date | None = None) -> dict[str, Any]:
    """The last 7 and 28 days against your usual periods of the same length."""
    through = data_through(wh)
    as_of = min(as_of or through, through)
    d = _days(wh)
    windows = {}
    for n in (7, 28):
        start = as_of - timedelta(days=n - 1)
        sel = d.filter(pl.col("local_date").is_between(start, as_of))
        rows = []
        for key, label, unit, col, stat, valid_only, scale in METRICS:
            hist = d.slice(_start(d, col))
            vals = _values(hist, col, stat, valid_only)
            value = _reduce(_values(sel, col, stat, valid_only), stat, scale) if sel.height else None
            usual = _usual(vals, n, stat, scale)
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "unit": unit,
                    "value": value,
                    "usual": usual,
                    "change": None if value is None or usual is None else value - usual,
                }
            )
        windows[f"last_{n}_days"] = {
            "from": start,
            "to": as_of,
            "valid_wear_days": int(sel["is_valid_wear_day"].sum()),
            "days_away_from_home": int(sel["is_non_default_tz"].sum()),
            "metrics": rows,
        }
    w = wh.read("marts", "mart_workout").filter(pl.col("is_counted") & (pl.col("local_date") <= as_of))
    last = w.sort("start_utc").tail(1)
    return jsonable(
        {
            "data_through": through,
            "as_of": as_of,
            "profile": profile(wh, as_of),
            "usual_means": "median of the same measure over every period of the same length in your history",
            **windows,
            "last_workout": None
            if last.height == 0
            else {
                "date": last["local_date"][0],
                "kind": kind_label(last["activity_type"][0], last["is_indoor"][0]),
                "days_ago": (as_of - last["local_date"][0]).days,
            },
        }
    )


def history(wh: Warehouse) -> dict[str, Any]:
    """Month by month since the start, and your best sustained 12 weeks of training."""
    d = _days(wh).with_columns(pl.col("local_date").dt.month_start().alias("month"))
    weeks = pl.col("local_date").count() / 7
    monthly = (
        d.group_by("month")
        .agg(
            pl.len().alias("days"),
            pl.col("is_valid_wear_day").sum().alias("valid_wear_days"),
            pl.col("is_non_default_tz").sum().alias("days_away_from_home"),
            pl.col("steps").filter(pl.col("is_valid_wear_day")).median().round(0).alias("steps_median"),
            (pl.col("exercise_min").sum() / weeks).round(0).alias("exercise_min_per_week"),
            (pl.col("workout_min").fill_null(0).sum() / 60 / weeks).round(1).alias("training_h_per_week"),
            *[
                (pl.col(f"{g}_min").fill_null(0).sum() / 60 / weeks).round(1).alias(f"{g}_h_per_week")
                for g in GROUPS
            ],
            (pl.col("run_km").fill_null(0).sum() / weeks).round(1).alias("running_km_per_week"),
            (pl.col("strength_sessions").fill_null(0).sum() / weeks)
            .round(1)
            .alias("strength_sessions_per_week"),
            pl.col("sleep_asleep_min")
            .filter(pl.col("is_valid_wear_day"))
            .median()
            .round(0)
            .alias("asleep_min_median"),
            pl.col("resting_hr_bpm")
            .filter(pl.col("is_valid_wear_day"))
            .median()
            .round(1)
            .alias("resting_hr_median"),
            pl.col("hrv_sdnn_sleep_ms")
            .filter(pl.col("is_valid_wear_day"))
            .median()
            .round(1)
            .alias("hrv_median"),
            pl.col("vo2max").drop_nulls().last().round(1).alias("vo2max_last"),
        )
        .sort("month")
    )
    # Best sustained period: the 84 days with the most training per week.
    s = d.select("local_date", pl.col("workout_min").fill_null(0)).with_columns(
        pl.col("workout_min").rolling_sum(84).alias("roll")
    )
    peak = None
    if s["roll"].drop_nulls().len():
        end = s.filter(pl.col("roll") == s["roll"].max())["local_date"][0]
        start = end - timedelta(days=83)
        sel = d.filter(pl.col("local_date").is_between(start, end))
        valid = sel.filter(pl.col("is_valid_wear_day"))
        peak = {
            "from": start,
            "to": end,
            "training_h_per_week": round(sel["workout_min"].fill_null(0).sum() / 60 / 12, 1),
            **{f"{g}_h_per_week": round(sel[f"{g}_min"].fill_null(0).sum() / 60 / 12, 1) for g in GROUPS},
            "running_km_per_week": round(sel["run_km"].fill_null(0).sum() / 12, 1),
            "strength_sessions_per_week": round(sel["strength_sessions"].fill_null(0).sum() / 12, 1),
            "steps_median": valid["steps"].median(),
            "resting_hr_median": valid["resting_hr_bpm"].median(),
            "hrv_median": valid["hrv_sdnn_sleep_ms"].median(),
            "vo2max_last": sel["vo2max"].drop_nulls().tail(1).to_list()[0]
            if sel["vo2max"].drop_nulls().len()
            else None,
        }
    return jsonable({"data_through": data_through(wh), "best_12_weeks": peak, "months": monthly})


def recovery(wh: Warehouse, as_of: date | None = None, days: int = 14) -> dict[str, Any]:
    """Day by day: resting HR and HRV against your 60-day baseline, sleep, training load."""
    through = data_through(wh)
    as_of = min(as_of or through, through)
    start = as_of - timedelta(days=days - 1)
    d = wh.read("marts", "mart_daily").filter(pl.col("local_date").is_between(start, as_of))
    base = wh.read("marts", "mart_baselines").filter(pl.col("local_date").is_between(start, as_of))
    for metric, name in (("resting_hr_bpm", "z_resting_hr"), ("hrv_sdnn_sleep_ms", "z_hrv")):
        d = d.join(
            base.filter(pl.col("metric") == metric).select("local_date", pl.col("z").round(2).alias(name)),
            on="local_date",
            how="left",
        )
    load = wh.read("marts", "mart_training_load").select(
        "local_date", pl.col("trimp").round(0), pl.col("acwr").round(2).alias("load_ratio")
    )
    d = d.join(load, on="local_date", how="left").sort("local_date")
    rows = d.select(
        pl.col("local_date").alias("date"),
        pl.col("is_valid_wear_day").alias("watch_worn"),
        pl.col("resting_hr_bpm").round(1).alias("resting_hr"),
        "z_resting_hr",
        pl.col("hrv_sdnn_sleep_ms").round(1).alias("hrv"),
        "z_hrv",
        pl.col("sleep_asleep_min").round(0).alias("asleep_min"),
        pl.col("bedtime_h").round(2).alias("bedtime_h"),
        pl.col("workout_min").round(0),
        "trimp",
        "load_ratio",
        pl.col("is_non_default_tz").alias("away_from_home"),
    )
    return jsonable(
        {
            "data_through": through,
            "as_of": as_of,
            "notes": (
                "z = standard deviations from your previous 60 days; "
                "load_ratio = 7-day / 28-day training load"
            ),
            "days": rows,
        }
    )


def recent_weekly_minutes(wh: Warehouse, weeks: int = 4) -> list[float]:
    """Training minutes of the last complete weeks of the export, oldest first (empty weeks are 0)."""
    through = data_through(wh)
    last_monday = (
        through - timedelta(days=through.weekday() + 7)
        if through.weekday() != 6
        else through - timedelta(days=6)
    )
    starts = [last_monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    t = wh.read("marts", "mart_training_weekly").group_by("week_start").agg(pl.col("minutes").sum())
    by_week = dict(t.iter_rows())
    return [round(float(by_week.get(w, 0.0)), 0) for w in starts]


def _source_kinds(wh: Warehouse) -> dict[str, str]:
    return dict(wh.read("curated", "dim_source").select("source_name", "source_kind").iter_rows())


def workouts(
    wh: Warehouse,
    start: date | None = None,
    end: date | None = None,
    kind: str | None = None,
    limit: int = 60,
) -> dict[str, Any]:
    """Counted sessions (newest first), with what each kind records."""
    through = data_through(wh)
    end = end or through
    start = start or end - timedelta(days=27)
    kinds = _source_kinds(wh)
    s = sessions(wh).filter(pl.col("local_date").is_between(start, end))
    if kind:
        s = s.filter((pl.col("kind") == kind) | (pl.col("activity_type") == kind))
    s = s.sort("start_utc", descending=True)
    total = s.height
    out = []
    for r in s.head(limit).iter_rows(named=True):
        out.append(
            {
                "id": r["workout_id"],
                "date": r["local_date"],
                "start": r["start_local"].strftime("%H:%M") if r["start_local"] else None,
                "kind": r["kind"],
                "kind_label": kind_label(r["activity_type"], r["is_indoor"]),
                "group": r["activity_group"],
                "recorded_by": kinds.get(r["source_name"], "other"),
                "duration_min": _r(r["duration_min"], 1),
                "distance_km": _r(r["distance_km"], 2),
                "pace_s_per_km": _r(r["pace_s_per_km"], 0),
                "speed_kmh": _r(r["speed_kmh"], 1),
                "active_kcal": _r(r["active_energy_kcal"], 0),
                "avg_hr": _r(r["avg_hr_bpm"], 0),
                "max_hr": _r(r["max_hr_bpm"], 0),
                "trimp": _r(r["trimp"], 0),
                "effort_score": r["effort_score"],
                "avg_mets": _r(r["avg_mets"], 1),
                "weight_lifted_kg": _r(r["strength_volume_kg"], 0),
                "temperature_c": None if r["is_indoor"] else _r(r["weather_temperature_c"], 0),
            }
        )
    return jsonable({"data_through": through, "from": start, "to": end, "total": total, "workouts": out})


def workout(wh: Warehouse, workout_id: str) -> dict[str, Any]:
    """One session in detail: zones, heart rate per minute, splits for runs. No route."""
    s = sessions(wh).filter(pl.col("workout_id") == workout_id)
    if s.height == 0:
        return {"error": f"no counted workout {workout_id}"}
    r = s.row(0, named=True)
    hr = (
        wh.read("marts", "mart_workout_hr")
        .filter(pl.col("workout_id") == workout_id)
        .sort("minute")
        .select("minute", pl.col("hr_bpm").round(0))
    )
    per_minute: list[float | None] = [None] * (int(hr["minute"].max()) + 1) if hr.height else []
    for m, v in hr.iter_rows():
        per_minute[m] = v
    splits = (
        wh.read("marts", "mart_run_split")
        .filter(pl.col("workout_id") == workout_id)
        .sort("split")
        .select(
            pl.col("split").alias("km"),
            pl.col("distance_m").round(0),
            pl.col("pace_s_per_km").round(0),
            pl.col("avg_hr_bpm").round(0).alias("avg_hr"),
            pl.col("elevation_change_m").round(0),
        )
    )
    summary = workouts(wh, r["local_date"], r["local_date"])["workouts"]
    return jsonable(
        {
            **next(w for w in summary if w["id"] == workout_id),
            "zone_minutes": [_r(r[f"zone{i}_min"], 1) for i in range(1, 6)],
            "zone_lower_bounds_bpm": r["zone_lo"],
            "hr_per_minute": per_minute,
            "splits": splits,
        }
    )


def weight(wh: Warehouse) -> dict[str, Any]:
    """Weigh-ins recorded in Apple Health (the coach journal adds yours)."""
    w = (
        wh.scan("curated", "fct_quantity_sample")
        .filter(pl.col("type") == "BodyMass")
        .sort("start_utc")
        .select(pl.col("local_date").alias("date"), pl.col("value").round(1).alias("kg"))
        .collect()
    )
    return jsonable({"data_through": data_through(wh), "source": "apple_health", "entries": w})


REFERENCE_KEYS = (
    "steps",
    "exercise_minutes_week",
    "vigorous_minutes_week",
    "sleep_duration",
    "resting_hr",
    "hrv_sdnn",
    "vo2max",
    "training_load_ratio",
)


def references(wh: Warehouse, as_of: date | None = None) -> dict[str, Any]:
    """Guideline and population bands that apply to you now (config/references.toml)."""
    as_of = as_of or data_through(wh)
    out = {}
    for key in REFERENCE_KEYS:
        rows = [b for b in bands(wh, key) if b["valid_from"] <= as_of <= b["valid_to"]]
        out[key] = [
            {
                "kind": b["kind"],
                "label": b["label"],
                "lo": b["lo"],
                "hi": b["hi"],
                "target": b["is_target"],
                "warning": b["is_warning"],
                "population": b["population"],
                "source": b["source_id"],
            }
            for b in rows
        ]
    return jsonable({"as_of": as_of, "units": "as the warehouse: minutes, bpm, ms, mL/kg/min", "bands": out})


def _r(v: float | None, digits: int) -> float | None:
    return None if v is None else round(v, digits)
