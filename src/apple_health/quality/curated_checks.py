"""Data-quality checks on the curated/derived outputs of a build."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from apple_health.quality.checks import ERROR, INFO, WARN, CheckResult, result
from apple_health.schemas import Table
from apple_health.transform.context import BuildContext

LAYER = "curated"


def key_checks(ctx: BuildContext, tables: dict[str, Table]) -> list[CheckResult]:
    """Primary keys unique and not null; foreign keys resolve (null FKs are allowed)."""
    out: list[CheckResult] = []
    for name, t in tables.items():
        if name not in ctx.rows or not t.primary_key:
            continue
        lf = ctx.scan(t)
        pk = list(t.primary_key)
        stats = (
            lf.select(
                pl.len().alias("n"),
                pl.struct(pk).n_unique().alias("unique"),
                pl.any_horizontal([pl.col(c).is_null() for c in pk]).sum().alias("nulls"),
            )
            .collect()
            .row(0, named=True)
        )
        dupes = stats["n"] - stats["unique"]
        out.append(result(f"pk_unique_{name}", t.layer, ERROR, dupes == 0, f"{dupes} duplicate keys", 0))
        out.append(result(f"pk_not_null_{name}", t.layer, ERROR, stats["nulls"] == 0, stats["nulls"], 0))
        for col, parent, parent_col in t.foreign_keys:
            if parent not in ctx.rows:
                continue
            orphans = (
                lf.select(col)
                .filter(pl.col(col).is_not_null())
                .unique()
                .join(ctx.scan(parent).select(pl.col(parent_col).alias(col)), on=col, how="anti")
                .select(pl.len())
                .collect()
                .item()
            )
            out.append(
                result(
                    f"fk_{name}.{col}->{parent}",
                    t.layer,
                    ERROR,
                    orphans == 0,
                    f"{orphans} unmatched values",
                    0,
                )
            )
    return out


def privacy_checks(ctx: BuildContext) -> list[CheckResult]:
    """Normalised source and device names must not keep a possessive (owner) prefix."""
    from apple_health.transform.sources import POSSESSIVE

    names = pl.concat(
        [
            ctx.scan("dim_source").select(pl.col("source_name").alias("name")),
            ctx.scan("dim_device").select("name"),
        ]
    )
    n = names.filter(pl.col("name").str.contains(POSSESSIVE)).select(pl.len()).collect().item()
    return [
        result(
            "owner_name_stripped",
            LAYER,
            ERROR,
            n == 0,
            f"{n} names with a possessive",
            0,
            "dim_source.source_name / dim_device.name must not contain the owner's name",
        )
    ]


def sample_checks(ctx: BuildContext) -> list[CheckResult]:
    s: dict[str, Any] = ctx.stats
    out: list[CheckResult] = []
    failures = {k: v for k, v in s.get("record_timestamp_parse_failures", {}).items() if v}
    out.append(result("record_timestamps_parse", LAYER, ERROR, not failures, failures or 0, 0))
    offsets = s.get("record_timestamp_offsets", [])
    out.append(
        result(
            "record_timestamp_single_offset",
            LAYER,
            WARN,
            len(offsets) <= 1,
            offsets,
            "1 offset",
            "the export renders all instants in the export-time offset; several offsets is new",
        )
    )
    out.append(
        result(
            "quantity_values_numeric",
            LAYER,
            ERROR,
            s.get("quantity_value_cast_failures", 0) == 0,
            s.get("quantity_value_cast_failures", 0),
            0,
        )
    )
    d = s.get("record_dedup")
    if d:
        written = ctx.rows.get("fct_quantity_sample", 0) + ctx.rows.get("fct_category_sample", 0)
        ok = d["raw"] - d["exact_duplicates_dropped"] - d["rewrites_dropped"] == d["final"] == written
        out.append(
            result(
                "dedup_accounting",
                LAYER,
                ERROR,
                ok,
                f"{d} -> written {written}",
                "raw - dropped = final = written",
            )
        )
        out.append(
            result(
                "dedup_dropped",
                LAYER,
                INFO,
                True,
                f"{d['exact_duplicates_dropped']} exact, {d['rewrites_dropped']} rewrites",
            )
        )
    invalid = s.get("tz_evidence", {}).get("invalid_zone_names", [])
    out.append(result("tz_evidence_valid_zones", LAYER, WARN, not invalid, invalid or "none", "none"))

    q = ctx.scan("fct_quantity_sample")
    rates = (
        q.group_by("type")
        .agg(pl.len().alias("n"), pl.col("is_outlier").sum().alias("outliers"))
        .with_columns((pl.col("outliers") / pl.col("n")).alias("rate"))
        .filter(pl.col("rate") > ctx.cfg.settings.outlier_max_rate)
        .sort("type")
        .collect()
    )
    observed = ", ".join(f"{r['type']} {r['outliers']}/{r['n']}" for r in rates.iter_rows(named=True))
    out.append(
        result(
            "quantity_outlier_rate",
            LAYER,
            WARN,
            rates.height == 0,
            observed or "none",
            f"<= {ctx.cfg.settings.outlier_max_rate:.2%} per type",
        )
    )
    tz = (
        pl.concat([q.select("tz_source"), ctx.scan("fct_category_sample").select("tz_source")])
        .group_by("tz_source")
        .len()
        .collect()
    )
    shares = {r["tz_source"]: r["len"] for r in tz.iter_rows(named=True)}
    out.append(
        result(
            "tz_resolution",
            LAYER,
            INFO,
            True,
            shares,
            "",
            "samples by time-zone source (explicit / inferred / default)",
        )
    )
    return out


def workout_checks(ctx: BuildContext) -> list[CheckResult]:
    s: dict[str, Any] = ctx.stats
    tol = ctx.cfg.settings.route_match_tolerance_s
    out = [
        result(
            "workout_timestamps_parse",
            LAYER,
            ERROR,
            s.get("workout_timestamp_parse_failures", 0) == 0,
            s.get("workout_timestamp_parse_failures", 0),
            0,
        ),
        result(
            "workout_duplicates",
            LAYER,
            WARN,
            s.get("workout_duplicates_dropped", 0) == 0,
            s.get("workout_duplicates_dropped", 0),
            0,
            "identical workouts (same type/source/start/end) dropped",
        ),
        result(
            "route_point_timestamps_parse",
            LAYER,
            ERROR,
            s.get("route_point_time_parse_failures", 0) == 0,
            s.get("route_point_time_parse_failures", 0),
            0,
        ),
        result(
            "route_points_assigned",
            LAYER,
            WARN,
            s.get("route_points_without_route", 0) == 0,
            s.get("route_points_without_route", 0),
            0,
            "GPX points whose file no WorkoutRoute references",
        ),
        result(
            "route_point_duplicates",
            LAYER,
            INFO,
            s.get("route_point_duplicates_dropped", 0) == 0,
            s.get("route_point_duplicates_dropped", 0),
            0,
            "exact duplicate GPS points dropped",
        ),
        result(
            "nested_records_linked",
            LAYER,
            WARN,
            s.get("nested_records_unmatched", 0) == 0,
            f"{s.get('nested_records_unmatched', 0)} of {s.get('nested_records', 0)} unmatched",
            0,
            "records nested in workouts are expected to duplicate top-level records",
        ),
    ]
    stat = ctx.scan("fct_workout_statistic")
    unconverted = (
        stat.filter(pl.col("raw_unit").is_not_null() & pl.col("unit").is_null())
        .select(pl.len())
        .collect()
        .item()
    )
    out.append(
        result(
            "workout_statistic_units",
            LAYER,
            ERROR,
            unconverted == 0,
            unconverted,
            0,
            "statistics whose unit cannot be converted to the type's canonical unit",
        )
    )
    window = (
        ctx.scan("fct_route_point")
        .group_by("route_id")
        .agg(pl.col("ts_utc").min().alias("p0"), pl.col("ts_utc").max().alias("p1"))
        .join(ctx.scan("fct_workout_route").select("route_id", "start_utc", "end_utc"), on="route_id")
        .filter(
            (pl.col("p0") < pl.col("start_utc") - pl.duration(seconds=tol))
            | (pl.col("p1") > pl.col("end_utc") + pl.duration(seconds=tol))
        )
        .select(pl.len())
        .collect()
        .item()
    )
    out.append(
        result(
            "route_points_within_route_window",
            LAYER,
            WARN,
            window == 0,
            f"{window} routes",
            0,
            f"GPS points outside the route's start/end ± {tol:g}s",
        )
    )
    missing = (
        ctx.scan("fct_workout_route")
        .filter(pl.col("file_exists") & ~pl.col("owns_file_points"))
        .select(pl.len())
        .collect()
        .item()
    )
    out.append(
        result(
            "routes_without_points",
            LAYER,
            INFO,
            missing == 0,
            missing,
            0,
            "routes whose GPX file was claimed by another route (file-name collision)",
        )
    )
    overlaps = (
        ctx.scan("fct_workout")
        .filter(pl.col("overlaps_workout_id").is_not_null())
        .select(pl.len())
        .collect()
        .item()
    )
    out.append(
        result(
            "overlapping_workouts",
            LAYER,
            INFO,
            overlaps == 0,
            overlaps,
            0,
            "workouts overlapping another workout (e.g. two apps recording one session)",
        )
    )
    return out


def export_zone_check(ctx: BuildContext) -> CheckResult:
    """The configured export zone must render the export instant with the export's own offset."""
    tz = ctx.cfg.settings.export_timezone
    raw = ctx.stg("stg_export")["export_date"][0]
    try:
        rendered = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S %z")
        ok = rendered.astimezone(ZoneInfo(tz)).utcoffset() == rendered.utcoffset()
        observed = (
            f"{tz} -> {rendered.astimezone(ZoneInfo(tz)).strftime('%z')} vs export {rendered.strftime('%z')}"
        )
    except (TypeError, ValueError):
        ok, observed = False, f"unparsable export date {raw!r}"
    return result(
        "export_timezone_consistent",
        LAYER,
        WARN,
        ok,
        observed,
        "same offset",
        "time.export_timezone is used to read HRV beat times; set it to the zone of the exporting device",
    )


def summary_checks(ctx: BuildContext) -> list[CheckResult]:
    s: dict[str, Any] = ctx.stats
    cfg = ctx.cfg.settings
    hrv = s.get("hrv_beats", {})
    out = [
        export_zone_check(ctx),
        result(
            "hrv_beat_times_parse",
            LAYER,
            ERROR,
            hrv.get("time_parse_failures", 0) == 0,
            hrv.get("time_parse_failures", 0),
            0,
        ),
        result(
            "hrv_beats_within_parent",
            LAYER,
            WARN,
            hrv.get("outside_parent_interval", 0) == 0,
            hrv.get("outside_parent_interval", 0),
            0,
            f"beats outside their measurement's start/end ± {cfg.hrv_beat_tolerance_s:g}s",
        ),
    ]
    bad_units = [u for u, ok in s.get("activity_summary_energy_units", {}).items() if not ok]
    out.append(
        result("activity_summary_units", LAYER, ERROR, not bad_units, bad_units or "none", "kcal-convertible")
    )
    out.append(
        result(
            "activity_summary_dates_parse",
            LAYER,
            ERROR,
            s.get("activity_summary_date_parse_failures", 0) == 0,
            s.get("activity_summary_date_parse_failures", 0),
            0,
        )
    )

    days = ctx.scan("fct_activity_summary").select("local_date", "active_energy_kcal").collect()
    if days.height:
        span = (days["local_date"].max() - days["local_date"].min()).days + 1  # type: ignore[operator]
        gaps = span - days["local_date"].n_unique()
        out.append(result("activity_summary_no_gaps", LAYER, WARN, gaps == 0, f"{gaps} missing days", 0))
        # Cross-check of the time-zone handling: Watch-priority active energy per local day vs. the rings.
        energy = (
            ctx.scan("fct_quantity_sample")
            .filter((pl.col("type") == "ActiveEnergyBurned") & pl.col("is_priority_source"))
            .group_by("local_date")
            .agg(pl.col("value").sum().alias("samples_kcal"))
            .collect()
        )
        j = days.filter(pl.col("active_energy_kcal") > 0).join(energy, on="local_date", how="left")
        if j.height:
            rel = (pl.col("samples_kcal").fill_null(0) - pl.col("active_energy_kcal")).abs() / pl.col(
                "active_energy_kcal"
            )
            rate = j.select((rel <= cfg.activity_reconciliation_tolerance).mean()).item()
            out.append(
                result(
                    "activity_summary_reconciliation",
                    LAYER,
                    WARN,
                    rate >= cfg.activity_reconciliation_min_match_rate,
                    f"{rate:.1%} of {j.height} days within {cfg.activity_reconciliation_tolerance:.0%}",
                    f">= {cfg.activity_reconciliation_min_match_rate:.0%}",
                    "daily ActiveEnergyBurned (priority source, local dates) vs. ActivitySummary",
                )
            )
    pts = ctx.scan("fct_audiogram_point").select("frequency_unit", "level_unit").unique().collect()
    odd = [r for r in pts.rows() if r != ("Hz", "dBHL")]
    out.append(result("audiogram_units", LAYER, WARN, not odd, odd or "none", "Hz / dBHL"))
    n_profile = ctx.rows.get("dim_profile", 0)
    out.append(result("profile_single_row", LAYER, WARN, n_profile == 1, n_profile, 1))
    return out


def derived_checks(ctx: BuildContext) -> list[CheckResult]:
    layer = "derived"
    daily = ctx.scan("agg_quantity_daily")
    above = (
        daily.filter(
            (pl.col("aggregation") == "cumulative")
            & (pl.col("value") > pl.col("value_all_sources_sum") + 1e-6)
        )
        .select(pl.len())
        .collect()
        .item()
    )
    n_cov = ctx.scan("agg_data_coverage").select(pl.col("n_samples").sum()).collect().item() or 0
    n_samples = ctx.rows.get("fct_quantity_sample", 0) + ctx.rows.get("fct_category_sample", 0)
    sleep = ctx.scan("agg_sleep_session")
    inconsistent = sleep.filter(pl.col("asleep_s") > pl.col("span_s") + 1).select(pl.len()).collect().item()
    primaries = (
        sleep.group_by("sleep_date")
        .agg(pl.col("is_primary").sum().alias("n"))
        .filter(pl.col("n") != 1)
        .select(pl.len())
        .collect()
        .item()
    )
    return [
        result(
            "cumulative_resolved_not_above_naive",
            layer,
            ERROR,
            above == 0,
            above,
            0,
            "priority-resolved daily totals must not exceed the all-sources sum",
        ),
        result("coverage_counts_all_samples", layer, ERROR, n_cov == n_samples, n_cov, n_samples),
        result(
            "sleep_asleep_within_span",
            layer,
            WARN,
            inconsistent == 0,
            inconsistent,
            0,
            "sessions with more asleep time than their span (overlapping stage samples)",
        ),
        result("sleep_one_primary_per_date", layer, ERROR, primaries == 0, primaries, 0),
    ]


def mart_checks(ctx: BuildContext) -> list[CheckResult]:
    layer = "marts"
    daily = ctx.scan("mart_daily").select("local_date", "steps", "watch_worn_hours").collect()
    span = (daily["local_date"].max() - daily["local_date"].min()).days + 1 if daily.height else 0  # type: ignore[operator]
    gaps = span - daily.height
    agg_steps = (
        ctx.scan("agg_quantity_daily")
        .filter(pl.col("type") == "StepCount")
        .select(pl.col("value").sum())
        .collect()
        .item()
        or 0.0
    )
    daily_steps = daily["steps"].sum() or 0.0
    week_steps = ctx.scan("mart_weekly").select(pl.col("steps").sum()).collect().item() or 0.0
    month_steps = ctx.scan("mart_monthly").select(pl.col("steps").sum()).collect().item() or 0.0
    close = lambda a, b: abs(a - b) <= 1e-6 * max(1.0, abs(b))  # noqa: E731
    worn = daily.filter((pl.col("watch_worn_hours") < 0) | (pl.col("watch_worn_hours") > 24)).height
    mismatches = ctx.stats.get("mart_unit_mismatches", {})
    valid = ctx.scan("mart_daily").select(pl.col("is_valid_wear_day").mean()).collect().item()
    return [
        result(
            "mart_daily_no_gaps",
            layer,
            ERROR,
            gaps == 0 and daily["local_date"].is_unique().all(),
            f"{gaps} missing days",
            0,
        ),
        result(
            "mart_daily_steps_match_agg",
            layer,
            ERROR,
            close(daily_steps, agg_steps),
            f"{daily_steps:.1f}",
            f"{agg_steps:.1f}",
        ),
        result(
            "mart_rollups_match_daily",
            layer,
            ERROR,
            close(week_steps, daily_steps) and close(month_steps, daily_steps),
            f"weekly {week_steps:.1f}, monthly {month_steps:.1f}",
            f"{daily_steps:.1f}",
        ),
        result("mart_worn_hours_range", layer, ERROR, worn == 0, worn, 0),
        result(
            "mart_units_as_expected",
            layer,
            ERROR,
            not mismatches,
            mismatches or "none",
            "none",
            "mart columns encode units in their names; a different canonical unit needs a code change",
        ),
        result(
            "mart_valid_wear_days",
            layer,
            INFO,
            True,
            f"{(valid or 0):.1%} of days",
            "",
            "share of days with is_valid_wear_day",
        ),
    ]


def analytics_checks(ctx: BuildContext) -> list[CheckResult]:
    layer = "marts"
    close = lambda a, b: abs((a or 0.0) - (b or 0.0)) <= 1e-6 * max(1.0, abs(b or 0.0))  # noqa: E731
    counted = ctx.scan("mart_workout").filter(pl.col("is_counted"))
    minutes = counted.select(pl.col("duration_min").sum()).collect().item()
    trimp = counted.select(pl.col("trimp").sum()).collect().item()
    weekly = ctx.scan("mart_training_weekly").select(pl.col("minutes").sum()).collect().item()
    load = ctx.scan("mart_training_load").select(pl.col("trimp").sum()).collect().item()
    daily = ctx.scan("mart_daily").select(pl.col("workout_min").sum()).collect().item()
    nulls = (
        ctx.scan("mart_records")
        .filter(pl.col("value").is_null())
        .select("record_id")
        .collect()["record_id"]
        .to_list()
    )
    acwr = ctx.scan("mart_training_load").filter(pl.col("acwr") < 0).select(pl.len()).collect().item()
    refs = ctx.scan("mart_reference")
    unsourced = (
        refs.join(ctx.scan("mart_reference_source"), on="source_id", how="anti")
        .select(pl.len())
        .collect()
        .item()
    )
    inverted = refs.filter(pl.col("lo") >= pl.col("hi")).select(pl.len()).collect().item()
    misdated = refs.filter(pl.col("valid_from") > pl.col("valid_to")).select(pl.len()).collect().item()
    n_refs = refs.select(pl.len()).collect().item()
    stray_hr = (
        ctx.scan("mart_workout_hr")
        .join(ctx.scan("mart_workout").filter(pl.col("is_counted")), on="workout_id", how="anti")
        .select(pl.len())
        .collect()
        .item()
    )
    return [
        result(
            "training_weekly_matches_workouts",
            layer,
            ERROR,
            close(weekly, minutes),
            f"{weekly or 0:.1f} min",
            f"{minutes or 0:.1f} min",
        ),
        result(
            "training_load_matches_workouts",
            layer,
            ERROR,
            close(load, trimp),
            f"{load or 0:.1f}",
            f"{trimp or 0:.1f}",
        ),
        result(
            "daily_workouts_match_counted",
            layer,
            ERROR,
            close(daily, minutes),
            f"{daily or 0:.1f} min",
            f"{minutes or 0:.1f} min",
            "mart_daily and mart_workout must agree on which workouts count",
        ),
        result("acwr_non_negative", layer, ERROR, acwr == 0, acwr, 0),
        result(
            "records_have_values",
            layer,
            INFO,
            not nulls,
            nulls or "none",
            "none",
            "records without data (e.g. no runs long enough for a 10 km effort)",
        ),
        result(
            "workout_hr_belongs_to_counted_workouts",
            layer,
            ERROR,
            stray_hr == 0,
            stray_hr,
            0,
            "mart_workout_hr rows whose workout is missing or not counted",
        ),
        result("reference_bands_have_sources", layer, ERROR, unsourced == 0, unsourced, 0),
        result(
            "reference_bands_ordered", layer, ERROR, inverted == 0 and misdated == 0, inverted + misdated, 0
        ),
        result(
            "reference_bands_present",
            layer,
            INFO,
            n_refs > 0,
            n_refs,
            "> 0",
            "no bands: the profile has no date of birth or the export no dates",
        ),
    ]


def all_checks(ctx: BuildContext, tables: dict[str, Table]) -> list[CheckResult]:
    return (
        key_checks(ctx, tables)
        + privacy_checks(ctx)
        + sample_checks(ctx)
        + workout_checks(ctx)
        + summary_checks(ctx)
        + derived_checks(ctx)
        + mart_checks(ctx)
        + analytics_checks(ctx)
    )
