from __future__ import annotations

import pytest

from apple_health.coach.redact import LeakError, check, clean, safe


def test_clean_drops_places_devices_and_identity():
    raw = {
        "date": "2024-01-01",
        "center_lat": 52.5,
        "Lon": 13.4,
        "route_id": "abc",
        "tz_name": "Europe/Berlin",
        "source_name": "Someone's Apple Watch",
        "date_of_birth": "1990-01-01",
        "workouts": [{"id": "w1", "polyline": "_p~iF", "start_lat": 1.0, "kind": "Running"}],
    }
    assert clean(raw) == {"date": "2024-01-01", "workouts": [{"id": "w1", "kind": "Running"}]}


def test_check_refuses_what_clean_cannot_see():
    with pytest.raises(LeakError, match="time zone"):
        check({"note": "back from Africa/Lagos"})
    with pytest.raises(LeakError, match="forbidden field"):
        check([{"ok": 1}, {"device_name": "x"}])
    assert safe({"kind": "Cycling:indoor", "away_from_home": True}) == {
        "kind": "Cycling:indoor",
        "away_from_home": True,
    }
