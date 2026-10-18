from __future__ import annotations

from datetime import date

import pytest

from apple_health.config import ConfigError, default_config_dir
from apple_health.marts.references import (
    RefSet,
    birthday,
    load_references,
    ordinal,
    percentile_bands,
    validity,
    who,
)


@pytest.fixture(scope="module")
def refs():
    return load_references(default_config_dir())


def _set(sets, metric, kind="range", sex=None, ages=None):
    found = [s for s in sets if s.metric == metric and s.kind == kind and s.sex == sex and s.ages == ages]
    assert len(found) == 1, (metric, kind, sex, ages)
    return {b.band: b for b in found[0].bands}


def test_every_set_has_a_source_and_valid_bands(refs):
    sources, sets = refs
    assert {s.source_id for s in sets} <= set(sources)
    assert {s.metric for s in sets} == {
        "vo2max",
        "resting_hr",
        "hrv_sdnn",
        "hr_recovery",
        "respiratory_rate",
        "spo2",
        "sleep_duration",
        "sleep_efficiency",
        "deep_sleep_share",
        "rem_sleep_share",
        "exercise_minutes_week",
        "vigorous_minutes_week",
        "steps",
        "walking_speed",
        "double_support",
        "training_load_ratio",
    }
    assert all(v["citation"] and v["url"].startswith("https://") for v in sources.values())


def test_transcribed_values(refs):
    _, sets = refs
    # FRIEND 2015 table 3 (mL/kg/min): women 30-39 median, men 20-29 95th percentile.
    women30 = _set(sets, "vo2max", "percentile", "Female", (30, 39))
    assert (women30["p25_p50"].lo, women30["p25_p50"].hi) == (25.3, 30.2)
    assert _set(sets, "vo2max", "percentile", "Male", (20, 29))["above_p95"].lo == 66.3
    # NHANES resting pulse: women 20-39 median 74, open top age group.
    nhanes = _set(sets, "resting_hr", "percentile", "Female", (20, 39))
    assert nhanes["p50_p75"].lo == 74 and nhanes["p50_p75"].hi == 82
    assert _set(sets, "resting_hr", "percentile", "Male", (80, 120))["below_p5"].hi == 51
    clinical = _set(sets, "resting_hr")["normal"]
    assert (clinical.lo, clinical.hi, clinical.is_target) == (60, 100, True)
    # Scaled units: NSF hours -> minutes, Bohannon cm/s -> km/h, percentages -> fractions.
    nsf = _set(sets, "sleep_duration", ages=(26, 64))
    assert (nsf["recommended"].lo, nsf["recommended"].hi) == (420, 540)
    assert nsf["long"].lo == 600 and nsf["short"].is_warning
    speed = _set(sets, "walking_speed", sex="Female", ages=(30, 39))["average"]
    assert speed.lo == pytest.approx(119.3 * 0.036) and speed.hi == pytest.approx(148.2 * 0.036)
    assert _set(sets, "spo2")["normal"].lo == pytest.approx(0.95)
    efficiency = _set(sets, "sleep_efficiency", ages=(26, 120))
    assert efficiency["good"].lo == pytest.approx(0.85) and efficiency["not_good"].hi == pytest.approx(0.75)
    # Whole-number categories cover the whole unit: "12 bpm or less" is below 13.
    assert _set(sets, "hr_recovery")["abnormal"].hi == 13
    who_ = _set(sets, "exercise_minutes_week")["guideline"]
    assert (who_.lo, who_.hi) == (150, 300)
    assert _set(sets, "steps", ages=(60, 120))["plateau"].lo == 6000
    sweet = _set(sets, "training_load_ratio")["sweet_spot"]
    assert (sweet.lo, sweet.hi) == (0.8, 1.3)


def test_ordinal_and_percentile_bands():
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 95)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "13th",
        "21st",
        "22nd",
        "95th",
    ]
    bands = percentile_bands([25, 50, 75], [10.0, 20.0, 30.0])
    assert [(b.band, b.label, b.lo, b.hi) for b in bands] == [
        ("below_p25", "Below the 25th percentile", None, 10.0),
        ("p25_p50", "25th–50th percentile", 10.0, 20.0),
        ("p50_p75", "50th–75th percentile", 20.0, 30.0),
        ("above_p75", "Above the 75th percentile", 30.0, None),
    ]
    assert who("Female", (30, 39)) == "Women aged 30–39"
    assert who("Male", (80, 120)) == "Men aged 80 and over"


def test_birthday_and_validity():
    assert birthday(date(1992, 2, 29), 30) == date(2022, 3, 1)
    span = (date(2019, 6, 1), date(2023, 7, 31))
    dob = date(1990, 1, 1)

    def s(ages, sex=None):
        return RefSet("m", "range", "src", "", ages, sex, ())

    assert validity(s((20, 29)), dob, "Female", span) == (date(2019, 6, 1), date(2019, 12, 31))
    assert validity(s((30, 39)), dob, "Female", span) == (date(2020, 1, 1), date(2023, 7, 31))
    assert validity(s((40, 49)), dob, "Female", span) is None
    assert validity(s((30, 39), "Male"), dob, "Female", span) is None
    assert validity(s(None), dob, None, span) == span  # adults: from 18, before the span
    assert validity(s((30, 39)), None, "Female", span) is None  # age groups need a date of birth
    assert validity(s(None), None, None, span) == span


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            '[[set]]\nmetric = "x"\nkind = "range"\nsource = "nope"\n'
            'bands = [{band = "a", label = "A", lo = 1}]',
            "unknown source",
        ),
        ('[[set]]\nmetric = "x"\nkind = "other"\nsource = "s"', "kind must be"),
        (
            '[[set]]\nmetric = "x"\nkind = "range"\nsource = "s"\n'
            'bands = [{band = "a", label = "A", hi = 10}, {band = "b", label = "B", lo = 5}]',
            "overlap",
        ),
        (
            '[[set]]\nmetric = "x"\nkind = "range"\nsource = "s"\n'
            'bands = [{band = "a", label = "A", lo = 5, hi = 5}]',
            "lo >= hi",
        ),
        (
            '[[set]]\nmetric = "x"\nkind = "percentile"\nsource = "s"\npercentiles = [50, 25]\n'
            'rows = [{sex = "Female", ages = [20, 29], values = [1, 2]}]',
            "must increase",
        ),
        (
            '[[set]]\nmetric = "x"\nkind = "range"\nsource = "s"\n'
            'rows = [{sex = "F", bands = [{band = "a", label = "A", lo = 1}]}]',
            "sex must be",
        ),
    ],
)
def test_invalid_references_are_rejected(tmp_path, body, message):
    (tmp_path / "references.toml").write_text('[sources.s]\ncitation = "C"\nurl = "https://x"\n\n' + body)
    with pytest.raises(ConfigError, match=message):
        load_references(tmp_path)
