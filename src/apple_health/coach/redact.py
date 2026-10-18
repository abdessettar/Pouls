"""The guard on what leaves this machine (docs/decisions/0007-coach.md).

Every tool result goes through safe(): clean() drops fields that could locate or identify you, and
check() refuses the result if anything of the kind is still there. Summaries never include GPS points,
routes, areas, time zones, device or app names, your name or your date of birth.
"""

from __future__ import annotations

import re
from typing import Any

FORBIDDEN_KEYS = {
    # places
    "lat",
    "lon",
    "latitude",
    "longitude",
    "polyline",
    "route",
    "route_id",
    "track",
    "tracks",
    "area_id",
    "area_name",
    "tz_name",
    "timezone",
    "time_zone",
    "hk_time_zone",
    # devices, apps, identity
    "source_name",
    "source_name_raw",
    "device",
    "device_id",
    "device_name",
    "hardware",
    "name",
    "owner",
    "date_of_birth",
}
FORBIDDEN_SUFFIXES = ("_lat", "_lon", "_latitude", "_longitude")
# IANA zone names ("Europe/Berlin") inside any text.
TZ_NAME = re.compile(
    r"\b(?:Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific)/[A-Za-z_]+"
)


class LeakError(ValueError):
    """A result still holds something that must not leave this machine."""


def _forbidden(key: str) -> bool:
    k = key.lower()
    return k in FORBIDDEN_KEYS or k.endswith(FORBIDDEN_SUFFIXES)


def clean(obj: Any) -> Any:
    """A copy without forbidden fields."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if not _forbidden(str(k))}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def check(obj: Any, path: str = "$") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _forbidden(str(k)):
                raise LeakError(f"forbidden field {path}.{k}")
            check(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            check(v, f"{path}[{i}]")
    elif isinstance(obj, str) and TZ_NAME.search(obj):
        raise LeakError(f"time zone name in {path}")


def safe(obj: Any) -> Any:
    out = clean(obj)
    check(out)
    return out
