"""All time page: every series from its first day, years, then-and-now, records, seasonality."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl

from apple_health.dashboard import Warehouse
from apple_health.dashboard.references import bands

MIN_DAYS_PER_MONTH = 10


@dataclass(frozen=True)
class Series:
    key: str
    label: str
    domain: str
    unit: str
    expr: pl.Expr  # over mart_monthly (or the runs frame for running)
    watch: bool  # Watch-based: needs valid wear days; else any days with data
    better: str | None
    reference: str | None = None


SERIES = [
    Series(
        "steps", "Steps per day", "activity", "steps", pl.col("steps_daily_avg"), False, "higher", "steps"
    ),
    Series(
        "active_energy",
        "Active energy per day",
        "activity",
        "kcal",
        pl.col("active_energy_kcal_daily_avg"),
        True,
        "higher",
    ),
    Series(
        "exercise",
        "Exercise per week",
        "activity",
        "min",
        pl.col("exercise_min_daily_avg") * 7,
        True,
        "higher",
        "exercise_minutes_week",
    ),
    Series(
        "resting_hr",
        "Resting heart rate",
        "heart",
        "bpm",
        pl.col("resting_hr_bpm"),
        True,
        "lower",
        "resting_hr",
    ),
    Series("hrv", "HRV during sleep", "heart", "ms", pl.col("hrv_sdnn_sleep_ms"), True, "higher", "hrv_sdnn"),
    Series("vo2max", "VO2max", "heart", "mL/min·kg", pl.col("vo2max"), True, "higher", "vo2max"),
    Series(
        "respiratory_rate",
        "Breathing rate in sleep",
        "heart",
        "/min",
        pl.col("respiratory_rate_sleep"),
        True,
        None,
        "respiratory_rate",
    ),
    Series(
        "asleep", "Time asleep", "sleep", "min", pl.col("sleep_asleep_min"), True, "higher", "sleep_duration"
    ),
    Series("bedtime", "Bedtime", "sleep", "h", pl.col("bedtime_h"), True, None),
    Series(
        "training",
        "Training per week",
        "training",
        "h",
        pl.col("workout_min_daily_avg") * 7 / 60,
        True,
        "higher",
    ),
    Series(
        "walking_speed",
        "Walking speed",
        "activity",
        "km/h",
        pl.col("walking_speed_kmh"),
        False,
        "higher",
        "walking_speed",
    ),
    Series(
        "daylight", "Daylight per day", "activity", "min", pl.col("daylight_min_daily_avg"), True, "higher"
    ),
]


def monthly_series(wh: Warehouse) -> tuple[pl.DataFrame, dict[str, list[dict[str, Any]]]]:
    m = wh.read("marts", "mart_monthly").sort("month_start")
    out: dict[str, list[dict[str, Any]]] = {}
    for s in SERIES:
        ok = (
            pl.col("n_valid_wear_days") >= MIN_DAYS_PER_MONTH
            if s.watch
            else pl.col("n_days") >= MIN_DAYS_PER_MONTH
        )
        df = m.select(
            "month_start",
            pl.when(ok).then(s.expr).otherwise(None).alias("value"),
            pl.col("n_valid_wear_days").alias("n"),
        )
        first = df.filter(pl.col("value").is_not_null())["month_start"].min()
        out[s.key] = df.filter(pl.col("month_start") >= first).to_dicts() if first else []
    runs = wh.read("marts", "mart_run")
    run_m = (
        runs.group_by(pl.col("local_date").dt.month_start().alias("month_start"))
        .agg(pl.col("distance_km").sum().alias("value"), pl.len().alias("n"))
        .sort("month_start")
    )
    if run_m.height:
        grid = pl.DataFrame(
            {
                "month_start": pl.date_range(
                    run_m["month_start"].min(), m["month_start"].max(), "1mo", eager=True
                )
            }
        )
        run_m = grid.join(run_m, on="month_start", how="left").with_columns(pl.col("value", "n").fill_null(0))
    out["running"] = run_m.to_dicts()
    return m, out


def then_and_now(series: dict[str, list[dict[str, Any]]], months: int = 12) -> list[dict[str, Any]]:
    rows = []
    specs = {s.key: s for s in SERIES}
    for key, pts in series.items():
        vals = [p for p in pts if p["value"] is not None]
        if len(vals) < 2 * months:
            continue
        first, last = vals[:months], vals[-months:]
        spec = specs.get(key)
        rows.append(
            {
                "key": key,
                "label": spec.label if spec else "Running per month",
                "unit": spec.unit if spec else "km",
                "better": spec.better if spec else "higher",
                "then": sum(p["value"] for p in first) / months,
                "now": sum(p["value"] for p in last) / months,
                "then_from": first[0]["month_start"],
                "then_to": first[-1]["month_start"],
                "now_from": last[0]["month_start"],
                "now_to": last[-1]["month_start"],
            }
        )
    return rows


def seasonality(series: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    out = {}
    for key, pts in series.items():
        df = pl.DataFrame(
            pts, schema={"month_start": pl.Date, "value": pl.Float64, "n": pl.Int64}, orient="row"
        )
        df = df.filter(pl.col("value").is_not_null())
        if df.height < 24:
            continue
        out[key] = (
            df.group_by(pl.col("month_start").dt.month().alias("month"))
            .agg(
                pl.col("value").median().alias("median"),
                pl.col("value").min().alias("min"),
                pl.col("value").max().alias("max"),
                pl.len().alias("years"),
            )
            .sort("month")
            .to_dicts()
        )
    return out


def years(wh: Warehouse) -> list[dict[str, Any]]:
    y = wh.read("marts", "mart_yearly").sort("year")
    runs = (
        wh.read("marts", "mart_run")
        .group_by(pl.col("local_date").dt.year().cast(pl.Int32).alias("year"))
        .agg(pl.col("distance_km").sum().alias("running_km"))
    )
    workouts = (
        wh.read("marts", "mart_workout")
        .filter(pl.col("is_counted"))
        .group_by(pl.col("local_date").dt.year().cast(pl.Int32).alias("year"))
        .agg(pl.len().alias("workouts"), (pl.col("duration_min").sum() / 60).alias("training_h"))
    )
    return (
        y.select(
            "year",
            "n_days",
            "n_valid_wear_days",
            "steps_daily_avg",
            "active_energy_kcal_daily_avg",
            (pl.col("exercise_min_daily_avg") * 7).alias("exercise_min_per_week"),
            "resting_hr_bpm",
            "hrv_sdnn_sleep_ms",
            "vo2max",
            "sleep_asleep_min",
            "bedtime_h",
            "all_rings_closed_days",
            "distance_walking_running_km",
        )
        .join(runs, on="year", how="left")
        .join(workouts, on="year", how="left")
        .to_dicts()
    )


def trips(wh: Warehouse, default_tz: str) -> list[dict[str, Any]]:
    p = wh.read("curated", "dim_timezone_period").filter(pl.col("tz_name") != default_tz)
    return (
        p.select(
            "tz_name",
            pl.col("valid_from_utc").dt.date().alias("start"),
            pl.col("valid_to_utc").dt.date().alias("end"),
        )
        .sort("start")
        .to_dicts()
    )


def build(wh: Warehouse) -> dict[str, Any]:
    from apple_health.config import load_config
    from apple_health.dashboard.meta import build as meta_build

    cfg = load_config()
    _, series = monthly_series(wh)
    meta = meta_build(wh)
    specs = [
        {
            "key": s.key,
            "label": s.label,
            "domain": s.domain,
            "unit": s.unit,
            "better": s.better,
            "reference": s.reference,
            "watch": s.watch,
        }
        for s in SERIES
    ] + [
        {
            "key": "running",
            "label": "Running per month",
            "domain": "running",
            "unit": "km",
            "better": "higher",
            "reference": None,
            "watch": False,
        }
    ]
    refs = {s["reference"]: bands(wh, s["reference"]) for s in specs if s["reference"]}
    records = wh.read("marts", "mart_records")
    return {
        "series": series,
        "specs": specs,
        "references": refs,
        "events": [
            {"date": meta["firsts"]["watch"], "label": "Apple Watch"},
            {"date": meta["firsts"]["sleep_stages"], "label": "Sleep stages"},
            {"date": meta["firsts"]["daylight"], "label": "Daylight"},
        ],
        "trips": trips(wh, cfg.settings.default_timezone),
        "years": years(wh),
        "then_now": then_and_now(series),
        "seasonality": seasonality(series),
        "records": records.to_dicts(),
        "first_day": meta["first_day"],
        "data_through": meta["data_through"],
        "today_year": date.today().year,
    }
