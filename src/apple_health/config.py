"""Load and validate the TOML configuration in ``config/``."""

from __future__ import annotations

import tomllib
import zoneinfo
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

AGGREGATIONS = {"cumulative", "discrete", "category"}
KINDS = {"quantity", "category"}
PROMOTED_TYPES = {"float", "int", "bool", "string"}
PROMOTION_TARGETS = {"sample", "workout"}
WORKOUT_STATISTICS = {"sum", "average", "minimum", "maximum"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CategoryValue:
    label: str
    ordinal: int | None


@dataclass(frozen=True)
class TypeSpec:
    identifier: str
    kind: str
    unit: str | None
    aggregation: str
    min: float | None
    max: float | None
    values: dict[str, CategoryValue] = field(default_factory=dict)


@dataclass(frozen=True)
class MetadataKeySpec:
    key: str
    canonical_unit: str | None = None
    scale: float | None = None
    promote: str | None = None
    type: str = "string"
    targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalyticsSettings:
    baseline_metrics: tuple[str, ...]
    rolling_short_days: int
    rolling_long_days: int
    normal_range_days: int
    baseline_days: int
    baseline_min_days: int
    strain_z: float
    late_workout_hours: float
    zone_weights: tuple[float, ...]
    acute_days: int
    chronic_days: int
    run_split_m: float
    best_effort_m: tuple[float, ...]
    track_resolution_m: float
    area_cluster_km: float
    place_names_file: Path | None  # GeoNames cities file; areas fall back to time-zone cities without it
    place_name_radius_km: float


@dataclass(frozen=True)
class Settings:
    raw_dir: Path
    warehouse_dir: Path
    expected_export_version: int
    xml_file: str
    routes_dir: str
    default_timezone: str
    export_timezone: str
    tz_evidence_from: tuple[str, ...]
    source_priority: tuple[str, ...]
    source_kind_priority: tuple[str, ...]
    source_kinds: dict[str, str]
    chunk_rows: int
    gpx_workers: int
    hash_files: bool
    route_match_tolerance_s: float
    route_max_speed_mps: float
    route_max_horizontal_accuracy_m: float
    sleep_session_gap_minutes: int
    valid_day_min_worn_hours: int
    outlier_max_rate: float
    activity_reconciliation_tolerance: float
    activity_reconciliation_min_match_rate: float
    hrv_beat_tolerance_s: float
    snapshots_keep: int
    analytics: AnalyticsSettings
    coach_journal: Path  # the coach's local journal (SQLite); personal, git-ignored

    @property
    def xml_path(self) -> Path:
        return self.raw_dir / self.xml_file

    @property
    def routes_path(self) -> Path:
        return self.raw_dir / self.routes_dir


@dataclass(frozen=True)
class Config:
    settings: Settings
    types: dict[str, TypeSpec]
    workout_statistics: dict[str, dict[str, str]]
    metadata_keys: dict[str, MetadataKeySpec]
    config_dir: Path

    def with_paths(self, raw_dir: Path | None = None, warehouse_dir: Path | None = None) -> Config:
        s = self.settings
        s = replace(
            s,
            raw_dir=Path(raw_dir) if raw_dir else s.raw_dir,
            warehouse_dir=Path(warehouse_dir) if warehouse_dir else s.warehouse_dir,
        )
        return replace(self, settings=s)

    def promoted_keys(self, target: str) -> list[MetadataKeySpec]:
        return [m for m in self.metadata_keys.values() if m.promote and target in m.targets]


def default_config_dir() -> Path:
    # src/apple_health/config.py -> project root / config
    return Path(__file__).resolve().parents[2] / "config"


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"missing config file: {path}")
    with path.open("rb") as f:
        return tomllib.load(f)


def _resolve(base: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (base / path).resolve()


def _analytics(a: dict[str, Any], root: Path) -> AnalyticsSettings:
    out = AnalyticsSettings(
        baseline_metrics=tuple(a["baseline_metrics"]),
        rolling_short_days=int(a["rolling_short_days"]),
        rolling_long_days=int(a["rolling_long_days"]),
        normal_range_days=int(a["normal_range_days"]),
        baseline_days=int(a["baseline_days"]),
        baseline_min_days=int(a["baseline_min_days"]),
        strain_z=float(a["strain_z"]),
        late_workout_hours=float(a["late_workout_hours"]),
        zone_weights=tuple(float(w) for w in a["zone_weights"]),
        acute_days=int(a["acute_days"]),
        chronic_days=int(a["chronic_days"]),
        run_split_m=float(a["run_split_m"]),
        best_effort_m=tuple(float(d) for d in a["best_effort_m"]),
        track_resolution_m=float(a["track_resolution_m"]),
        area_cluster_km=float(a["area_cluster_km"]),
        place_names_file=_resolve(root, a["place_names_file"]) if a.get("place_names_file") else None,
        place_name_radius_km=float(a.get("place_name_radius_km", 50)),
    )
    if len(out.zone_weights) != 5:
        raise ConfigError("settings.toml: analytics.zone_weights needs five weights (zones 1-5)")
    if out.chronic_days <= out.acute_days:
        raise ConfigError("settings.toml: analytics.chronic_days must exceed acute_days")
    return out


def _settings(raw: dict[str, Any], root: Path) -> Settings:
    try:
        tz = raw["time"]["default_timezone"]
        settings = Settings(
            raw_dir=_resolve(root, raw["paths"]["raw_dir"]),
            warehouse_dir=_resolve(root, raw["paths"]["warehouse_dir"]),
            expected_export_version=int(raw["source"]["expected_export_version"]),
            xml_file=raw["source"]["xml_file"],
            routes_dir=raw["source"]["routes_dir"],
            default_timezone=tz,
            export_timezone=raw["time"].get("export_timezone") or tz,
            tz_evidence_from=tuple(raw["time"]["evidence_from"]),
            source_priority=tuple(raw["sources"]["priority"]),
            source_kind_priority=tuple(raw["sources"]["kind_priority"]),
            source_kinds=dict(raw["sources"].get("kinds", {})),
            chunk_rows=int(raw["parse"]["chunk_rows"]),
            gpx_workers=int(raw["parse"]["gpx_workers"]),
            hash_files=bool(raw["manifest"]["hash_files"]),
            route_match_tolerance_s=float(raw["routes"]["match_tolerance_s"]),
            route_max_speed_mps=float(raw["routes"]["max_speed_mps"]),
            route_max_horizontal_accuracy_m=float(raw["routes"]["max_horizontal_accuracy_m"]),
            sleep_session_gap_minutes=int(raw["sleep"]["session_gap_minutes"]),
            valid_day_min_worn_hours=int(raw["marts"]["valid_day_min_worn_hours"]),
            outlier_max_rate=float(raw["quality"]["outlier_max_rate"]),
            activity_reconciliation_tolerance=float(raw["quality"]["activity_reconciliation_tolerance"]),
            activity_reconciliation_min_match_rate=float(
                raw["quality"]["activity_reconciliation_min_match_rate"]
            ),
            hrv_beat_tolerance_s=float(raw["quality"]["hrv_beat_tolerance_s"]),
            snapshots_keep=int(raw["snapshots"]["keep"]),
            analytics=_analytics(raw["analytics"], root),
            coach_journal=_resolve(root, raw.get("coach", {}).get("journal", "coach/journal.sqlite")),
        )
    except KeyError as e:
        raise ConfigError(f"settings.toml: missing key {e}") from e
    for zone in (tz, settings.export_timezone):
        try:
            zoneinfo.ZoneInfo(zone)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as e:
            raise ConfigError(f"settings.toml: unknown time zone {zone!r}") from e
    unknown_kinds = set(settings.source_kinds.values()) - set(settings.source_kind_priority)
    if unknown_kinds:
        raise ConfigError(f"settings.toml: source kinds {unknown_kinds} missing from kind_priority")
    if not 0 <= settings.valid_day_min_worn_hours <= 24:
        raise ConfigError("settings.toml: marts.valid_day_min_worn_hours must be within 0..24")
    if settings.chunk_rows <= 0:
        raise ConfigError("settings.toml: parse.chunk_rows must be positive")
    return settings


def infer_kind(identifier: str) -> str:
    """Kind of a HealthKit type identifier from its prefix (quantity unless a category)."""
    return "category" if identifier.startswith("HKCategoryTypeIdentifier") else "quantity"


def _types(raw: dict[str, Any]) -> dict[str, TypeSpec]:
    out: dict[str, TypeSpec] = {}
    for ident, spec in raw.get("types", {}).items():
        kind = spec.get("kind", infer_kind(ident))
        agg = spec.get("aggregation")
        if kind not in KINDS:
            raise ConfigError(f"types.toml: {ident}: unknown kind {kind!r}")
        if agg not in AGGREGATIONS:
            raise ConfigError(f"types.toml: {ident}: aggregation must be one of {sorted(AGGREGATIONS)}")
        if (kind == "category") != (agg == "category"):
            raise ConfigError(f"types.toml: {ident}: category types need aggregation='category'")
        if kind == "quantity" and not spec.get("unit"):
            raise ConfigError(f"types.toml: {ident}: quantity types need a unit")
        values = {
            v: CategoryValue(label=d["label"], ordinal=d.get("ordinal"))
            for v, d in spec.get("values", {}).items()
        }
        out[ident] = TypeSpec(
            identifier=ident,
            kind=kind,
            unit=spec.get("unit"),
            aggregation=agg,
            min=spec.get("min"),
            max=spec.get("max"),
            values=values,
        )
    return out


def _workout_statistics(raw: dict[str, Any], types: dict[str, TypeSpec]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    seen: set[str] = set()
    for ident, spec in raw.get("workout_statistics", {}).items():
        if ident not in types:
            raise ConfigError(f"types.toml: workout_statistics.{ident} has no [types.{ident}] entry")
        bad = set(spec) - WORKOUT_STATISTICS
        if bad:
            raise ConfigError(f"types.toml: workout_statistics.{ident}: unknown statistics {bad}")
        for col in spec.values():
            if col in seen:
                raise ConfigError(f"types.toml: workout statistic column {col!r} defined twice")
            seen.add(col)
        out[ident] = dict(spec)
    return out


def _metadata_keys(raw: dict[str, Any]) -> dict[str, MetadataKeySpec]:
    out: dict[str, MetadataKeySpec] = {}
    promoted: dict[tuple[str, str], str] = {}
    for key, spec in raw.get("keys", {}).items():
        m = MetadataKeySpec(
            key=key,
            canonical_unit=spec.get("canonical_unit"),
            scale=spec.get("scale"),
            promote=spec.get("promote"),
            type=spec.get("type", "string"),
            targets=tuple(spec.get("targets", ())),
        )
        if m.type not in PROMOTED_TYPES:
            raise ConfigError(f"metadata_keys.toml: {key}: type must be one of {sorted(PROMOTED_TYPES)}")
        if m.promote and not m.targets:
            raise ConfigError(f"metadata_keys.toml: {key}: promoted keys need targets")
        if set(m.targets) - PROMOTION_TARGETS:
            raise ConfigError(f"metadata_keys.toml: {key}: targets must be within {PROMOTION_TARGETS}")
        for t in m.targets:
            if (t, m.promote) in promoted:
                raise ConfigError(f"metadata_keys.toml: column {m.promote!r} promoted twice on {t}")
            promoted[(t, m.promote)] = key
        out[key] = m
    return out


def load_config(config_dir: Path | None = None) -> Config:
    config_dir = Path(config_dir) if config_dir else default_config_dir()
    root = config_dir.resolve().parent
    settings = _settings(_read(config_dir / "settings.toml"), root)
    types_raw = _read(config_dir / "types.toml")
    types = _types(types_raw)
    return Config(
        settings=settings,
        types=types,
        workout_statistics=_workout_statistics(types_raw, types),
        metadata_keys=_metadata_keys(_read(config_dir / "metadata_keys.toml")),
        config_dir=config_dir.resolve(),
    )
