"""Stream ``export.xml`` into lossless staging tables.

Constant memory: every top-level element is handled on its ``end`` event, then cleared and
detached from the tree. Values are written exactly as found (strings); elements or attributes the
parser does not know are preserved (``stg_other_element`` / ``extra_attrs``) and counted in the
inventory that feeds the source contract.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any

from lxml import etree

from apple_health.io import TableWriter
from apple_health.parse.hk_format import KNOWN_ATTRS
from apple_health.schemas import (
    ACTIVITY_SUMMARY_ATTRS,
    RECORD_ATTRS,
    SENSITIVITY_POINT_ATTRS,
    STAGING_TABLES,
    WORKOUT_ATTRS,
)

log = logging.getLogger(__name__)

XML_TABLES = [
    "stg_export",
    "stg_me",
    "stg_record",
    "stg_record_metadata",
    "stg_hrv_beat",
    "stg_workout",
    "stg_workout_metadata",
    "stg_workout_activity",
    "stg_workout_event",
    "stg_workout_statistic",
    "stg_workout_zone",
    "stg_workout_route",
    "stg_workout_record_ref",
    "stg_activity_summary",
    "stg_audiogram",
    "stg_audiogram_metadata",
    "stg_audiogram_point",
    "stg_other_element",
]

_SAMPLE_ATTRS = ("sourceName", "sourceVersion", "device", "creationDate", "startDate", "endDate")
_ACTIVITY_ATTRS = ("uuid", "startDate", "endDate", "duration", "durationUnit")
_EVENT_ATTRS = ("type", "date", "duration", "durationUnit")
_STAT_ATTRS = ("type", "startDate", "endDate", "sum", "average", "minimum", "maximum", "unit")
_ZONE_ATTRS = ("minimum", "maximum", "duration", "durationUnit")


class _Ordinals:
    __slots__ = ("activity", "event", "group", "record", "route", "statistic", "zone")

    def __init__(self) -> None:
        self.activity = self.event = self.group = self.record = self.route = self.statistic = self.zone = 0


class ExportXmlParser:
    def __init__(self, out_dir: Path, chunk_rows: int) -> None:
        self.w = {name: TableWriter(STAGING_TABLES[name], out_dir, chunk_rows) for name in XML_TABLES}
        self.top_level: Counter[str] = Counter()
        self.elements: Counter[str] = Counter()
        self.children: Counter[str] = Counter()
        self.record_types: Counter[tuple[str | None, str | None]] = Counter()
        self._attr_sigs: Counter[tuple[str, tuple[str, ...]]] = Counter()
        self._extra_cache: dict[tuple[str, tuple[str, ...]], tuple[str, ...]] = {}
        self.n_record = self.n_workout = self.n_summary = self.n_audiogram = self.n_other = 0
        self.export_date: str | None = None
        self.locale: str | None = None

    # -- helpers --------------------------------------------------------------------------------
    def _attrs(self, tag: str, el: etree._Element) -> str | None:
        """Count the element's attribute signature; return unknown attributes as JSON (or None)."""
        a = el.attrib
        sig = tuple(a.keys())
        key = (tag, sig)
        self._attr_sigs[key] += 1
        extra = self._extra_cache.get(key)
        if extra is None:
            known = KNOWN_ATTRS.get(tag, ())
            extra = tuple(k for k in sig if k not in known)
            self._extra_cache[key] = extra
        if not extra:
            return None
        return json.dumps({k: a[k] for k in extra}, ensure_ascii=False, sort_keys=True)

    def _other(self, el: etree._Element, parent_tag: str, parent_nr: int | None) -> None:
        self.w["stg_other_element"].add(
            self.n_other,
            parent_tag,
            parent_nr,
            el.tag,
            json.dumps(dict(el.attrib), ensure_ascii=False, sort_keys=True),
            etree.tostring(el, encoding="unicode", with_tail=False),
        )
        self.n_other += 1

    # -- top-level handlers -----------------------------------------------------------------------
    def _record(self, el: etree._Element) -> None:
        nr = self.n_record
        a = el.attrib
        extra = self._attrs("Record", el)
        t, unit = a.get("type"), a.get("unit")
        self.w["stg_record"].add(
            nr,
            t,
            unit,
            a.get("value"),
            a.get("sourceName"),
            a.get("sourceVersion"),
            a.get("device"),
            a.get("creationDate"),
            a.get("startDate"),
            a.get("endDate"),
            extra,
        )
        self.record_types[(t, unit)] += 1
        if len(el):
            meta = self.w["stg_record_metadata"]
            m_ord = 0
            for ch in el:
                ctag = ch.tag
                self.children["Record>" + ctag] += 1
                if ctag == "MetadataEntry":
                    self._attrs(ctag, ch)
                    meta.add(nr, m_ord, ch.get("key"), ch.get("value"))
                    m_ord += 1
                elif ctag == "HeartRateVariabilityMetadataList":
                    self._attrs(ctag, ch)
                    self._hrv(ch, nr)
                else:
                    self._other(ch, "Record", nr)
        self.n_record += 1

    def _hrv(self, el: etree._Element, nr: int) -> None:
        hrv = self.w["stg_hrv_beat"]
        b_ord = 0
        for b in el:
            btag = b.tag
            self.children["HeartRateVariabilityMetadataList>" + btag] += 1
            if btag == "InstantaneousBeatsPerMinute":
                self._attrs(btag, b)
                hrv.add(nr, b_ord, b.get("bpm"), b.get("time"))
                b_ord += 1
            else:
                self._other(b, "HeartRateVariabilityMetadataList", nr)

    def _workout(self, el: etree._Element) -> None:
        nr = self.n_workout
        a = el.attrib
        extra = self._attrs("Workout", el)
        self.w["stg_workout"].add(nr, *(a.get(k) for k in WORKOUT_ATTRS), extra)
        o = _Ordinals()
        m_ord = 0
        for ch in el:
            t = ch.tag
            self.children["Workout>" + t] += 1
            if t == "MetadataEntry":
                self._attrs(t, ch)
                self.w["stg_workout_metadata"].add(nr, "workout", None, m_ord, ch.get("key"), ch.get("value"))
                m_ord += 1
            elif t == "WorkoutEvent":
                self._event(ch, nr, None, o)
            elif t == "WorkoutStatistics":
                self._statistic(ch, nr, None, o)
            elif t == "WorkoutZoneGroup":
                self._zones(ch, nr, None, o)
            elif t == "WorkoutRoute":
                self._route(ch, nr, o)
            elif t == "WorkoutActivity":
                self._activity(ch, nr, o)
            elif t == "Record":
                self._attrs("Record", ch)
                self.w["stg_workout_record_ref"].add(nr, o.record, *(ch.get(k) for k in RECORD_ATTRS))
                o.record += 1
            else:
                self._other(ch, "Workout", nr)
        self.n_workout += 1

    def _event(self, el: etree._Element, nr: int, act: int | None, o: _Ordinals) -> None:
        extra = self._attrs("WorkoutEvent", el)
        self.w["stg_workout_event"].add(nr, o.event, act, *(el.get(k) for k in _EVENT_ATTRS), extra)
        m_ord = 0
        for ch in el:
            self.children["WorkoutEvent>" + ch.tag] += 1
            if ch.tag == "MetadataEntry":
                self._attrs(ch.tag, ch)
                self.w["stg_workout_metadata"].add(
                    nr, "event", o.event, m_ord, ch.get("key"), ch.get("value")
                )
                m_ord += 1
            else:
                self._other(ch, "WorkoutEvent", nr)
        o.event += 1

    def _statistic(self, el: etree._Element, nr: int, act: int | None, o: _Ordinals) -> None:
        extra = self._attrs("WorkoutStatistics", el)
        self.w["stg_workout_statistic"].add(nr, o.statistic, act, *(el.get(k) for k in _STAT_ATTRS), extra)
        for ch in el:
            self.children["WorkoutStatistics>" + ch.tag] += 1
            self._other(ch, "WorkoutStatistics", nr)
        o.statistic += 1

    def _zones(self, el: etree._Element, nr: int, act: int | None, o: _Ordinals) -> None:
        self._attrs("WorkoutZoneGroup", el)
        gtype, gsource, gunit = el.get("type"), el.get("source"), el.get("unit")
        for z in el:
            self.children["WorkoutZoneGroup>" + z.tag] += 1
            if z.tag == "WorkoutZone":
                self._attrs("WorkoutZone", z)
                self.w["stg_workout_zone"].add(
                    nr, o.zone, act, o.group, gtype, gsource, gunit, *(z.get(k) for k in _ZONE_ATTRS)
                )
                o.zone += 1
            else:
                self._other(z, "WorkoutZoneGroup", nr)
        o.group += 1

    def _route(self, el: etree._Element, nr: int, o: _Ordinals) -> None:
        extra = self._attrs("WorkoutRoute", el)
        path = None
        m_ord = 0
        for ch in el:
            t = ch.tag
            self.children["WorkoutRoute>" + t] += 1
            if t == "FileReference" and path is None:
                self._attrs(t, ch)
                path = ch.get("path")
            elif t == "MetadataEntry":
                self._attrs(t, ch)
                self.w["stg_workout_metadata"].add(
                    nr, "route", o.route, m_ord, ch.get("key"), ch.get("value")
                )
                m_ord += 1
            else:
                self._other(ch, "WorkoutRoute", nr)
        self.w["stg_workout_route"].add(nr, o.route, *(el.get(k) for k in _SAMPLE_ATTRS), path, extra)
        o.route += 1

    def _activity(self, el: etree._Element, nr: int, o: _Ordinals) -> None:
        extra = self._attrs("WorkoutActivity", el)
        act = o.activity
        self.w["stg_workout_activity"].add(nr, act, *(el.get(k) for k in _ACTIVITY_ATTRS), extra)
        m_ord = 0
        for ch in el:
            t = ch.tag
            self.children["WorkoutActivity>" + t] += 1
            if t == "MetadataEntry":
                self._attrs(t, ch)
                self.w["stg_workout_metadata"].add(nr, "activity", act, m_ord, ch.get("key"), ch.get("value"))
                m_ord += 1
            elif t == "WorkoutEvent":
                self._event(ch, nr, act, o)
            elif t == "WorkoutStatistics":
                self._statistic(ch, nr, act, o)
            elif t == "WorkoutZoneGroup":
                self._zones(ch, nr, act, o)
            else:
                self._other(ch, "WorkoutActivity", nr)
        o.activity += 1

    def _activity_summary(self, el: etree._Element) -> None:
        extra = self._attrs("ActivitySummary", el)
        self.w["stg_activity_summary"].add(
            self.n_summary, *(el.get(k) for k in ACTIVITY_SUMMARY_ATTRS), extra
        )
        for ch in el:
            self.children["ActivitySummary>" + ch.tag] += 1
            self._other(ch, "ActivitySummary", self.n_summary)
        self.n_summary += 1

    def _audiogram(self, el: etree._Element) -> None:
        nr = self.n_audiogram
        extra = self._attrs("Audiogram", el)
        self.w["stg_audiogram"].add(nr, el.get("type"), *(el.get(k) for k in _SAMPLE_ATTRS), extra)
        m_ord = p_ord = 0
        for ch in el:
            t = ch.tag
            self.children["Audiogram>" + t] += 1
            if t == "MetadataEntry":
                self._attrs(t, ch)
                self.w["stg_audiogram_metadata"].add(nr, m_ord, ch.get("key"), ch.get("value"))
                m_ord += 1
            elif t == "SensitivityPoint":
                self._attrs(t, ch)
                self.w["stg_audiogram_point"].add(nr, p_ord, *(ch.get(k) for k in SENSITIVITY_POINT_ATTRS))
                p_ord += 1
            else:
                self._other(ch, "Audiogram", nr)
        self.n_audiogram += 1

    def _me(self, el: etree._Element) -> None:
        self._attrs("Me", el)
        for k, v in el.attrib.items():
            self.w["stg_me"].add(k, v)
        for ch in el:
            self.children["Me>" + ch.tag] += 1
            self._other(ch, "Me", None)

    def _export_date(self, el: etree._Element) -> None:
        self._attrs("ExportDate", el)
        self.export_date = el.get("value")

    # -- driver ---------------------------------------------------------------------------------
    def parse(self, xml_path: Path, export_version: int | None) -> dict[str, Any]:
        handlers = {
            "Record": self._record,
            "Workout": self._workout,
            "ActivitySummary": self._activity_summary,
            "Audiogram": self._audiogram,
            "Me": self._me,
            "ExportDate": self._export_date,
        }
        t0 = time.monotonic()
        ctx = etree.iterparse(
            str(xml_path),
            events=("start", "end"),
            huge_tree=True,
            load_dtd=False,
            resolve_entities=False,
            no_network=True,
            remove_comments=True,
            remove_pis=True,
        )
        depth = 0
        root: etree._Element | None = None
        elements = self.elements
        for event, el in ctx:
            if event == "start":
                if depth == 0:
                    root = el
                    self._attrs(el.tag, el)
                    self.locale = el.get("locale")
                depth += 1
                elements[el.tag] += 1
                continue
            depth -= 1
            if depth != 1:
                continue
            tag = el.tag
            self.top_level[tag] += 1
            handler = handlers.get(tag)
            if handler is None:
                self._other(el, "HealthData", None)
            else:
                handler(el)
            el.clear()
            while el.getprevious() is not None:
                del root[0]  # type: ignore[index]
            if self.n_record and self.n_record % 1_000_000 == 0 and tag == "Record":
                log.info("  %d records parsed (%.0fs)", self.n_record, time.monotonic() - t0)
        del ctx

        self.w["stg_export"].add(self.export_date, self.locale, export_version)
        rows = {name: w.close() for name, w in self.w.items()}
        log.info(
            "parsed %s in %.1fs: %d records, %d workouts",
            xml_path.name,
            time.monotonic() - t0,
            self.n_record,
            self.n_workout,
        )
        return self.inventory(rows)

    def inventory(self, rows: dict[str, int]) -> dict[str, Any]:
        attributes: dict[str, Counter[str]] = {}
        for (tag, sig), n in self._attr_sigs.items():
            c = attributes.setdefault(tag, Counter())
            for a in sig:
                c[a] += n
        record_types: dict[str, dict[str, int]] = {}
        for (t, unit), n in self.record_types.items():
            record_types.setdefault(t or "", {})[unit or ""] = n
        return {
            "export_date": self.export_date,
            "locale": self.locale,
            "top_level": dict(self.top_level),
            "elements": dict(self.elements),
            "children": dict(self.children),
            "attributes": {t: dict(c) for t, c in attributes.items()},
            "record_types": record_types,
            "rows": rows,
        }


def parse_export_xml(
    xml_path: Path, out_dir: Path, chunk_rows: int, export_version: int | None
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return ExportXmlParser(out_dir, chunk_rows).parse(xml_path, export_version)
