"""mart_baselines (personal normal ranges and z-scores) and mart_activity_profile (the shape of a day)."""

from __future__ import annotations

import polars as pl

from apple_health.marts.analytics_tables import MART_ACTIVITY_PROFILE, MART_BASELINES
from apple_health.transform.context import BuildContext


def build_baselines(ctx: BuildContext) -> None:
    a = ctx.cfg.settings.analytics
    metrics = list(a.baseline_metrics)
    daily = (
        ctx.scan("mart_daily")
        .filter(pl.col("is_valid_wear_day"))
        .select("local_date", *[pl.col(m).cast(pl.Float64) for m in metrics])
    )
    long = (
        daily.unpivot(on=metrics, index="local_date", variable_name="metric", value_name="value")
        .filter(pl.col("value").is_not_null())
        .sort("metric", "local_date")
    )
    v, by = pl.col("value"), "local_date"
    win = lambda days: f"{days}d"  # noqa: E731
    out = long.with_columns(
        v.rolling_median_by(by, win(a.rolling_short_days), min_samples=3)
        .over("metric")
        .alias("roll_short_median"),
        v.rolling_median_by(by, win(a.rolling_long_days), min_samples=7)
        .over("metric")
        .alias("roll_long_median"),
        v.rolling_quantile_by(
            by,
            win(a.normal_range_days),
            quantile=0.1,
            interpolation="linear",
            min_samples=a.baseline_min_days,
        )
        .over("metric")
        .alias("normal_p10"),
        v.rolling_median_by(by, win(a.normal_range_days), min_samples=a.baseline_min_days)
        .over("metric")
        .alias("normal_p50"),
        v.rolling_quantile_by(
            by,
            win(a.normal_range_days),
            quantile=0.9,
            interpolation="linear",
            min_samples=a.baseline_min_days,
        )
        .over("metric")
        .alias("normal_p90"),
        v.rolling_mean_by(by, win(a.baseline_days), closed="left", min_samples=a.baseline_min_days)
        .over("metric")
        .alias("baseline_mean"),
        v.rolling_std_by(by, win(a.baseline_days), closed="left", min_samples=a.baseline_min_days)
        .over("metric")
        .alias("baseline_sd"),
    ).with_columns(
        pl.when(pl.col("baseline_sd") > 0)
        .then((v - pl.col("baseline_mean")) / pl.col("baseline_sd"))
        .otherwise(None)
        .alias("z")
    )
    ctx.write(MART_BASELINES, out.collect())


def build_activity_profile(ctx: BuildContext) -> None:
    days = (
        ctx.scan("mart_daily").filter(pl.col("is_valid_wear_day")).select("local_date", "year", "day_of_week")
    )
    grid = days.join(pl.LazyFrame({"hour": list(range(24))}, schema={"hour": pl.Int32}), how="cross")
    hourly = (
        ctx.scan("agg_quantity_hourly")
        .filter(pl.col("type").is_in(["StepCount", "ActiveEnergyBurned", "HeartRate"]))
        .select("type", "local_date", "hour", "value")
    )

    def one(typ: str, name: str) -> pl.LazyFrame:
        return hourly.filter(pl.col("type") == typ).select("local_date", "hour", pl.col("value").alias(name))

    df = (
        grid.join(one("StepCount", "steps"), on=["local_date", "hour"], how="left")
        .join(one("ActiveEnergyBurned", "energy"), on=["local_date", "hour"], how="left")
        .join(one("HeartRate", "hr"), on=["local_date", "hour"], how="left")
        .with_columns(pl.col("steps", "energy").fill_null(0.0))
    )
    profile = df.group_by("year", "day_of_week", "hour").agg(
        pl.len().cast(pl.Int32).alias("n_days"),
        pl.col("steps").mean().alias("steps_mean"),
        pl.col("steps").median().alias("steps_median"),
        pl.col("energy").mean().alias("active_energy_mean"),
        pl.col("hr").mean().alias("hr_mean_bpm"),
        pl.col("hr").count().cast(pl.Int32).alias("hr_n_days"),
    )
    ctx.write(MART_ACTIVITY_PROFILE, profile.collect())
