"""Source contract: detect changes in Apple's export format before they corrupt the warehouse.

Two stages:
* ``header_checks`` — cheap, before parsing (root element, export format version).
* ``inventory_checks`` — on the element/attribute/type inventory collected while parsing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from apple_health.config import Config
from apple_health.parse.hk_format import (
    DECLARED_UNHANDLED_TOP_LEVEL,
    GPX_VERSION,
    HANDLED_TOP_LEVEL,
    KNOWN_ATTRS,
    KNOWN_CHILDREN,
    KNOWN_GPX_EXTENSIONS,
)
from apple_health.quality.checks import ERROR, INFO, WARN, CheckResult, result
from apple_health.transform.units import is_convertible

LAYER = "source"


def read_header(xml_path: Path, nbytes: int = 256 * 1024) -> dict[str, Any]:
    """Root element, locale and HealthKit export version from the start of export.xml."""
    with xml_path.open("rb") as f:
        head = f.read(nbytes).decode("utf-8", errors="replace")
    version = re.search(r"HealthKit Export Version:\s*(\d+)", head)
    # The internal DTD subset ends with "]>"; the root element is the first real tag after it.
    body = head.split("]>", 1)[1] if "<!DOCTYPE" in head and "]>" in head else head
    root = re.search(r"<(?![!?/])([A-Za-z_][\w.-]*)", body)
    locale = re.search(r'<HealthData[^>]*\blocale="([^"]*)"', head)
    return {
        "root": root.group(1) if root else None,
        "export_version": int(version.group(1)) if version else None,
        "locale": locale.group(1) if locale else None,
    }


def header_checks(header: dict[str, Any], cfg: Config) -> list[CheckResult]:
    expected = cfg.settings.expected_export_version
    return [
        result("root_element", LAYER, ERROR, header["root"] == "HealthData", header["root"], "HealthData"),
        result(
            "export_version",
            LAYER,
            ERROR,
            header["export_version"] == expected,
            header["export_version"],
            expected,
            "export format changed: verify the parser, then update source.expected_export_version",
        ),
    ]


def _fmt(items: dict[str, int] | list[str], limit: int = 20) -> str:
    keys = sorted(items)
    s = ", ".join(f"{k} ({items[k]})" if isinstance(items, dict) else k for k in keys[:limit])
    return s + (f", … (+{len(keys) - limit})" if len(keys) > limit else "") if keys else "none"


def inventory_checks(inv: dict[str, Any], cfg: Config) -> list[CheckResult]:
    out: list[CheckResult] = []
    top = inv["top_level"]

    unknown_top = {t: n for t, n in top.items() if t not in HANDLED_TOP_LEVEL | DECLARED_UNHANDLED_TOP_LEVEL}
    declared = {t: n for t, n in top.items() if t in DECLARED_UNHANDLED_TOP_LEVEL}
    out.append(
        result(
            "unknown_top_level_elements",
            LAYER,
            WARN,
            not unknown_top,
            _fmt(unknown_top),
            "none",
            "captured in stg_other_element",
        )
    )
    out.append(
        result(
            "unhandled_declared_elements",
            LAYER,
            WARN,
            not declared,
            _fmt(declared),
            "none",
            "DTD-declared elements without dedicated tables; captured in stg_other_element",
        )
    )
    out.append(
        result(
            "export_date_present", LAYER, ERROR, top.get("ExportDate", 0) == 1, top.get("ExportDate", 0), 1
        )
    )

    unknown_children: dict[str, int] = {}
    for path, n in inv["children"].items():
        parent, child = path.split(">", 1)
        if parent in KNOWN_CHILDREN and child not in KNOWN_CHILDREN[parent]:
            unknown_children[path] = n
    out.append(
        result(
            "unknown_child_elements",
            LAYER,
            WARN,
            not unknown_children,
            _fmt(unknown_children),
            "none",
            "captured in stg_other_element",
        )
    )

    unknown_attrs: dict[str, int] = {}
    for tag, attrs in inv["attributes"].items():
        known = set(KNOWN_ATTRS.get(tag, ()))
        if tag not in KNOWN_ATTRS:
            continue
        for a, n in attrs.items():
            if a not in known:
                unknown_attrs[f"{tag}@{a}"] = n
    out.append(
        result(
            "unknown_attributes",
            LAYER,
            WARN,
            not unknown_attrs,
            _fmt(unknown_attrs),
            "none",
            "kept in extra_attrs (JSON) columns",
        )
    )

    types = inv["record_types"]
    unknown_types = {t: sum(u.values()) for t, u in types.items() if t not in cfg.types}
    out.append(
        result(
            "unknown_record_types",
            LAYER,
            WARN,
            not unknown_types,
            _fmt(unknown_types),
            "none",
            "loaded generically; add them to config/types.toml",
        )
    )

    bad_units: dict[str, int] = {}
    converted_units: dict[str, int] = {}
    for t, units in types.items():
        spec = cfg.types.get(t)
        if spec is None or spec.kind != "quantity":
            continue
        for u, n in units.items():
            unit = u or None
            if unit == spec.unit:
                continue
            if is_convertible(unit, spec.unit):
                converted_units[f"{t} [{u}->{spec.unit}]"] = n
            else:
                bad_units[f"{t} [{u}]"] = n
    out.append(
        result(
            "record_units_convertible",
            LAYER,
            ERROR,
            not bad_units,
            _fmt(bad_units),
            "none",
            "unit differs from types.toml and no conversion is known",
        )
    )
    out.append(
        result(
            "record_units_converted",
            LAYER,
            INFO,
            not converted_units,
            _fmt(converted_units),
            "none",
            "values converted to the canonical unit",
        )
    )

    gpx = inv.get("gpx")
    if gpx is not None:
        versions = {v: n for v, n in gpx["versions"].items() if v != GPX_VERSION}
        out.append(result("gpx_version", LAYER, WARN, not versions, _fmt(versions), GPX_VERSION))
        multi = {k: n for k, n in gpx["tracks_segments"].items() if k != "1/1"}
        out.append(
            result(
                "gpx_single_track_segment",
                LAYER,
                WARN,
                not multi,
                _fmt(multi),
                "1/1 per file",
                "files with several tracks/segments are flattened in order",
            )
        )
        ext = {e: n for e, n in gpx["extensions"].items() if e not in KNOWN_GPX_EXTENSIONS}
        out.append(
            result(
                "gpx_unknown_extensions",
                LAYER,
                WARN,
                not ext,
                _fmt(ext),
                "none",
                "kept in stg_gpx_point.extra_ext (JSON)",
            )
        )
        out.append(
            result(
                "gpx_parse_errors", LAYER, ERROR, not gpx["parse_errors"], _fmt(gpx["parse_errors"]), "none"
            )
        )

    routes = inv.get("routes")
    if routes is not None:
        out.append(
            result(
                "route_files_exist",
                LAYER,
                WARN,
                not routes["missing_files"],
                _fmt(routes["missing_files"]),
                "none",
                "WorkoutRoute references without a GPX file",
            )
        )
        out.append(
            result(
                "gpx_files_referenced",
                LAYER,
                WARN,
                not routes["unreferenced_files"],
                _fmt(routes["unreferenced_files"]),
                "none",
                "GPX files no WorkoutRoute refers to",
            )
        )
        out.append(
            result(
                "route_files_shared",
                LAYER,
                INFO,
                not routes["shared_files"],
                _fmt(routes["shared_files"]),
                "none",
                "several WorkoutRoutes reference one file (minute-resolution file names collide)",
            )
        )
    return out
