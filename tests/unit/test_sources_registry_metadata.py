from __future__ import annotations

import polars as pl

from apple_health.transform.metadata import parse_metadata, promoted_columns
from apple_health.transform.registry import build_dim_category_value, build_dim_data_type, short_name
from apple_health.transform.samples import deduplicate
from apple_health.transform.sources import build_devices, build_dim_source, parse_device, strip_owner

WATCH = (
    "<<HKDevice: 0x600000001000>, name:Apple Watch, manufacturer:Apple Inc., model:Watch, "
    "hardware:Watch1,1, software:8.1, creation date:2020-01-01 08:00:00 +0000>"
)


def test_strip_owner():
    df = pl.DataFrame(
        {"s": ["Alex’s Apple Watch", "Sam's iPhone", "Run Tracker", "Kim’s AirPods Pro", "Bob’s Burgers"]}
    )
    assert df.select(strip_owner("s")).to_series().to_list() == [
        "Apple Watch",
        "iPhone",
        "Run Tracker",
        "AirPods Pro",
        "Bob’s Burgers",
    ]


def test_parse_device():
    d = parse_device(WATCH)
    assert d == {
        "name": "Apple Watch",
        "manufacturer": "Apple Inc.",
        "model": "Watch",
        "hardware": "Watch1,1",
        "software": "8.1",
        "firmware": None,
    }
    hrm = parse_device(
        "<<HKDevice: 0x1>, name:HRM:123, manufacturer:Acme, model:HRM1, hardware:B, "
        "firmware:1.2.3, localIdentifier:AAAAAAAA, creation date:2025-01-01 00:00:00 +0000>"
    )
    assert hrm["name"] == "HRM:123" and hrm["firmware"] == "1.2.3"
    assert "localIdentifier" not in hrm
    pods = parse_device(
        "<<HKDevice: 0x2>, name:Alex’s AirPods Pro, manufacturer:Apple Inc., model:0x2014, "
        "localIdentifier:00:11:22:33:44:55-tacl, creation date:2022-06-01 08:00:00 +0000>"
    )
    assert pods["name"] == "AirPods Pro"
    assert parse_device(None)["name"] is None


def test_device_id_ignores_pointer_and_software():
    other = WATCH.replace("0x600000001000", "0x1234").replace("software:8.1", "software:9.0")
    dim, mapping = build_devices(pl.Series([WATCH, other, None]))
    assert dim.height == 1 and dim["device_class"].item() == "watch"
    assert mapping["device_id"].n_unique() == 1
    assert sorted(mapping["device_software"].to_list()) == ["8.1", "9.0"]


def test_dim_source_priority(base_config):
    dim = build_dim_source(
        pl.Series(["Alex’s Apple Watch", "iPhone", "Bluetooth Device", "JEFIT", "Health"]), base_config
    )
    ranked = dim.sort("priority_rank")["source_name"].to_list()
    assert ranked == ["Apple Watch", "iPhone", "Bluetooth Device", "Health", "JEFIT"]
    assert dict(dim.select("source_name", "source_kind").rows())["JEFIT"] == "third_party_app"


def test_registry_unknown_types(base_config):
    records = pl.DataFrame(
        {
            "type": ["HKQuantityTypeIdentifierHeartRate", "HKQuantityTypeIdentifierNew", "HKDataTypeOdd"],
            "unit": ["count/min", "count", None],
            "value": ["60", "1", "SomeEnum"],
        }
    )
    dim = build_dim_data_type(records, base_config)
    rows = {r["type_identifier"]: r for r in dim.iter_rows(named=True)}
    assert rows["HKQuantityTypeIdentifierHeartRate"]["is_known"]
    new = rows["HKQuantityTypeIdentifierNew"]
    assert (new["kind"], new["canonical_unit"], new["aggregation"], new["is_known"]) == (
        "quantity",
        "count",
        None,
        False,
    )
    assert rows["HKDataTypeOdd"]["kind"] == "category"
    assert rows["HKQuantityTypeIdentifierStepCount"]["n_raw_records"] == 0  # configured, not seen
    assert pl.DataFrame({"t": ["HKWorkoutActivityTypeRunning"]}).select(short_name("t")).item() == "Running"


def test_category_labels(base_config):
    recs = pl.DataFrame(
        {
            "type": [
                "HKCategoryTypeIdentifierSleepAnalysis",
                "HKCategoryTypeIdentifierMindfulSession",
                "HKCategoryTypeIdentifierAppleStandHour",
            ],
            "value": [
                "HKCategoryValueSleepAnalysisAsleepREM",
                "HKCategoryValueNotApplicable",
                "HKCategoryValueAppleStandHourSomethingNew",
            ],
        }
    )
    dim = build_dim_category_value(recs, base_config)
    labels = dict(dim.select("category_value", "label").rows())
    assert labels["HKCategoryValueSleepAnalysisAsleepREM"] == "REM"
    assert labels["HKCategoryValueNotApplicable"] == "NotApplicable"
    assert labels["HKCategoryValueAppleStandHourSomethingNew"] == "SomethingNew"


def test_metadata_parsing_and_promotion(base_config):
    md = pl.DataFrame(
        {
            "owner": [1, 1, 1, 1, 2, 2],
            "ordinal": [0, 1, 2, 3, 0, 1],
            "key": [
                "HKWeatherTemperature",
                "HKWeatherHumidity",
                "HKElevationAscended",
                "HKIndoorWorkout",
                "HKIndoorWorkout",
                "Total Rest Time",
            ],
            "value": ["41 degF", "8000 %", "1250 cm", "1", "0", "0:01:30"],
        }
    )
    parsed = parse_metadata(md, base_config)
    canon = dict(zip(parsed["key"] + parsed["owner"].cast(pl.String), parsed["value_canonical"], strict=True))
    assert round(canon["HKWeatherTemperature1"], 6) == 5.0
    assert canon["HKWeatherHumidity1"] == 80.0
    assert canon["HKElevationAscended1"] == 12.5
    assert canon["Total Rest Time2"] == 90.0
    prom = promoted_columns(parsed, "owner", "workout", base_config).sort("owner")
    assert prom["is_indoor"].to_list() == [True, False]
    assert prom["weather_humidity_pct"].to_list() == [80.0, None]
    assert "hr_motion_context" not in prom.columns  # sample-only key


def test_deduplicate_rules():
    t = pl.Datetime("us", "UTC")
    base = {
        "type": "HR",
        "unit": "count/min",
        "value": "60",
        "sourceName": "W",
        "sourceVersion": "1",
        "device": "<<HKDevice: 0xA>, name:W>",
        "extra_attrs": None,
    }
    rows = [
        {**base, "record_nr": 0, "created": 1},
        {**base, "record_nr": 1, "created": 1, "device": "<<HKDevice: 0xB>, name:W>"},  # exact dup (pointer)
        {**base, "record_nr": 2, "created": 5, "sourceVersion": "2"},  # rewrite, latest creation
        {**base, "record_nr": 3, "created": 1, "value": "61"},  # different observation
    ]
    df = (
        pl.DataFrame(rows)
        .with_columns(
            pl.lit(0).cast(t).alias("start_utc"),
            pl.lit(0).cast(t).alias("end_utc"),
            pl.col("created").cast(t).alias("created_utc"),
        )
        .drop("created")
    )
    out, stats = deduplicate(df)
    assert stats == {"raw": 4, "exact_duplicates_dropped": 1, "rewrites_dropped": 1, "final": 2}
    assert out["record_nr"].to_list() == [2, 3]
    assert out["dup_count"].to_list() == [3, 1]
