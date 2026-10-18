from __future__ import annotations

import hashlib

import pytest

from apple_health.manifest import Workspace, raw_inventory, read_json, write_json


def test_raw_inventory(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_bytes(b"hello")
    (tmp_path / "sub" / "b.gpx").write_bytes(b"x")
    inv = raw_inventory(tmp_path, hash_files=True)
    assert [f["path"] for f in inv] == ["a.txt", "sub/b.gpx"]
    assert inv[0]["size_bytes"] == 5
    assert inv[0]["sha256"] == hashlib.sha256(b"hello").hexdigest()
    assert raw_inventory(tmp_path, hash_files=False)[0]["sha256"] is None


def test_json_roundtrip(tmp_path):
    write_json(tmp_path / "x" / "m.json", {"b": 1, "a": "é"})
    assert read_json(tmp_path / "x" / "m.json") == {"a": "é", "b": 1}


def test_workspace_publish_replaces_layer(tmp_path):
    wh = tmp_path / "wh"
    ws1 = Workspace(wh, "run1")
    (ws1.layer("staging") / "t.parquet").write_text("v1")
    ws1.publish("staging")
    ws1.cleanup()
    assert (wh / "staging" / "t.parquet").read_text() == "v1"

    ws2 = Workspace(wh, "run2")
    (ws2.layer("staging") / "t.parquet").write_text("v2")
    assert (wh / "staging" / "t.parquet").read_text() == "v1"  # untouched until publish
    ws2.publish("staging")
    ws2.cleanup()
    assert (wh / "staging" / "t.parquet").read_text() == "v2"
    assert not (wh / ".tmp").exists()
    assert not (wh / ".trash").exists()


def test_publish_missing_layer_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        Workspace(tmp_path, "r").publish("curated")
