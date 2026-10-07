"""Bind a Polar HR sequence to explicitly timestamped TCX export values.

This read-only evidence does not certify acquisition quality, the provider's
native clock semantics, historical feature availability or training readiness.
"""

import hashlib
import io
import json
import re
import zipfile
import zlib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from app.services.heart_rate_sample_validation import (
    build_training_session_heart_rate_validation,
)

TIMEBASE_VERSION = "0.1.0"
TCX_NAMESPACE = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
NS = {"t": TCX_NAMESPACE}
MAX_IMPORT_BYTES = 16 * 1024 * 1024
MAX_XML_ELEMENTS = 500_000
MAX_XML_DEPTH = 64
MAX_TRACKPOINTS = 100_000
MAX_ACTIVITIES = 32
MAX_ARCHIVE_MEMBERS = 16
_ISO_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?\Z"
)


class _Rejected(ValueError):
    pass


class _BoundedTreeBuilder(ET.TreeBuilder):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.element_count = 0

    def doctype(self, name, pubid, system):
        raise _Rejected("TCX_DTD_NOT_ALLOWED")

    def start(self, tag, attrs):
        self.depth += 1
        self.element_count += 1
        if self.depth > MAX_XML_DEPTH or self.element_count > MAX_XML_ELEMENTS:
            raise _Rejected("TCX_XML_STRUCTURE_LIMIT_EXCEEDED")
        return super().start(tag, attrs)

    def end(self, tag):
        self.depth -= 1
        return super().end(tag)


def build_tcx_heart_rate_timebase(
    file_bytes: bytes,
    sample_session: Mapping | None,
    *,
    expected_session_external_id,
    sample_session_match_count: int,
    expected_exercise_external_id=None,
) -> dict:
    """Require unique source identity, full ordered values and consistent clocks.

    A coarse API start must contain the export activity start in its reported
    UTC second. A fractional API start must agree exactly. The offset is then
    derived from export timestamps, never fitted or supplied by the caller.
    """
    source = build_training_session_heart_rate_validation(
        sample_session,
        expected_session_external_id=expected_session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    result = {
        "provider": "PADDLETRAINER",
        "schema_version": "0.1",
        "timebase_version": TIMEBASE_VERSION,
        "status": "WITHHELD",
        "export_timebase_verified": False,
        "api_native_time_origin_verified": False,
        "pause_clock_semantics_verified": False,
        "acquisition_quality_verified": False,
        "training_authorized": False,
        "numeric_prediction_authorized": False,
        "session_external_id": _identity(expected_session_external_id),
        "exercise_external_id": None,
        "source_import": {},
        "input_provenance": {
            "api_source_hash": source["input_provenance"]["source_hash"],
            "api_validation_decision_hash": source["decision_hash"],
            "expected_exercise_external_id": _identity(expected_exercise_external_id),
            "source_file_sha256": hashlib.sha256(file_bytes).hexdigest()
            if isinstance(file_bytes, bytes)
            else None,
        },
        "matching_candidate_count": 0,
        "candidates": [],
        "binding": None,
        "timebase": None,
        "blocking_reasons": list(source["blocking_reasons"]),
        "limitations": [
            "EXPORT_MATCH_IS_NOT_INDEPENDENT_MEASUREMENT_VALIDATION",
            "API_NATIVE_SAMPLE_CLOCK_SEMANTICS_NOT_VERIFIED",
            "HR_PAUSE_CLOCK_SEMANTICS_NOT_VERIFIED",
            "HR_SENSOR_IDENTITY_NOT_ESTABLISHED_BY_EXPORT",
            "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED",
            "HISTORICAL_FEATURE_AVAILABILITY_NOT_ESTABLISHED",
            "DATASET_SPLIT_NOT_ASSIGNED",
        ],
        "policy": {
            "read_only": True,
            "persists_uploaded_file": False,
            "persists_timebase_evidence": False,
            "promotes_training_data_readiness": False,
            "modifies_existing_validation": False,
            "sample_values_modified": False,
            "missing_values_interpolated": False,
            "global_time_offset_configured": False,
            "archive_extracted_to_disk": False,
            "gps_coordinates_used_for_matching": False,
            "file_name_used_for_matching": False,
            "timestamp_comparison_unit": "INTEGER_MICROSECONDS",
            "start_match_policy": "SAME_REPORTED_SECOND_OR_EXACT_FRACTIONAL_START",
        },
    }
    try:
        activities, import_summary = _import(file_bytes)
        result["source_import"] = import_summary
        result["input_provenance"]["tcx_xml_sha256"] = import_summary["tcx_xml_sha256"]
    except _Rejected as exc:
        result["blocking_reasons"].append(str(exc))
        return _finish(result)
    if result["blocking_reasons"]:
        return _finish(result)
    exercises = sample_session["exercises"]
    ids = [
        _identity(_mapping(e.get("identifier")).get("id")) if isinstance(e, Mapping) else None
        for e in exercises
    ]
    if not ids or len(ids) > 64 or None in ids or len(set(ids)) != len(ids):
        result["blocking_reasons"].append("API_EXERCISE_IDENTITY_MISSING_OR_AMBIGUOUS")
        return _finish(result)
    selector = _identity(expected_exercise_external_id)
    if expected_exercise_external_id is not None and selector not in ids:
        result["blocking_reasons"].append("EXPECTED_API_EXERCISE_NOT_FOUND")
        return _finish(result)
    matches = []
    for ei, exercise in enumerate(exercises):
        if selector is not None and ids[ei] != selector:
            continue
        technical = source["exercises"][ei]
        for ai, activity in enumerate(activities):
            reasons, start, stop, values, interval = _compare(
                activity, exercise, sample_session, technical
            )
            result["candidates"].append(
                {
                    "api_exercise_index": ei,
                    "api_exercise_external_id": ids[ei],
                    "tcx_activity_index": ai,
                    "matched": not reasons,
                    "blocking_reasons": reasons,
                }
            )
            if not reasons:
                matches.append((ei, ai, activity, start, stop, values, interval))
    result["matching_candidate_count"] = len(matches)
    if len(matches) != 1:
        result["blocking_reasons"].append(
            "API_TCX_MATCH_AMBIGUOUS" if matches else "NO_VERIFIABLE_API_TCX_MATCH"
        )
        return _finish(result)
    ei, ai, activity, start, stop, values, interval = matches[0]
    times = activity["hr_times"]
    first_offset_us = _us(times[0] - start)
    result.update(
        {
            "status": "VERIFIED_EXPORT_TIMEBASE_WITH_LIMITATIONS",
            "export_timebase_verified": True,
            "exercise_external_id": ids[ei],
            "binding": {
                "api_exercise_index": ei,
                "tcx_activity_index": ai,
                "match_basis": "UNIQUE_ID_BOUND_SESSION_FULL_ORDERED_HR_AND_START_METADATA",
                "api_exercise_start_utc": start.isoformat(),
                "api_exercise_stop_utc": stop.isoformat(),
                "tcx_activity_start_utc": activity["start"].isoformat(),
                "matched_hr_sample_count": len(values),
                "ordered_value_mismatch_count": 0,
                "normalized_hr_values_sha256": _hash(
                    [str(Decimal(str(v)).normalize()) for v in values]
                ),
            },
            "timebase": {
                "source": "VALUE_MATCHED_TCX_EXPORT_TIMESTAMPS",
                "sample_count": len(times),
                "interval_ms": interval,
                "first_sample_timestamp_utc": times[0].isoformat(),
                "last_sample_timestamp_utc": times[-1].isoformat(),
                "first_sample_offset_from_api_exercise_start_us": first_offset_us,
                "first_sample_offset_from_api_exercise_start_ms": _ms(first_offset_us),
                "sample_grid_span_ms": _ms(_us(times[-1] - times[0])),
                "sample_timestamps_utc": [t.isoformat() for t in times],
            },
        }
    )
    declared = exercises[ei].get("durationMillis")
    if activity["summary"]["lap_declared_duration_sum_ms"] != declared:
        result["limitations"].append("TCX_LAP_DURATION_DIFFERS_FROM_API_DECLARED_DURATION")
    if activity["summary"]["missing_hr_point_count"]:
        result["limitations"].append("TCX_TRACKPOINTS_WITHOUT_HR_OUTSIDE_MATCHED_GRID")
    return _finish(result)


def _import(file_bytes):
    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise _Rejected("TCX_FILE_EMPTY_OR_INVALID")
    if len(file_bytes) > MAX_IMPORT_BYTES:
        raise _Rejected("TCX_IMPORT_BYTE_LIMIT_EXCEEDED")
    xml = file_bytes
    kind = "TCX_XML"
    if file_bytes.startswith(b"PK"):
        kind = "ZIP"
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                members = archive.infolist()
                if len(members) > MAX_ARCHIVE_MEMBERS:
                    raise _Rejected("TCX_ARCHIVE_MEMBER_LIMIT_EXCEEDED")
                candidates = [
                    m for m in members if not m.is_dir() and m.filename.lower().endswith(".tcx")
                ]
                if len(candidates) != 1:
                    raise _Rejected("TCX_ARCHIVE_REQUIRES_EXACTLY_ONE_TCX")
                member = candidates[0]
                path = PurePosixPath(member.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts or ":" in member.filename:
                    raise _Rejected("TCX_ARCHIVE_UNSAFE_MEMBER_PATH")
                if member.flag_bits & 1:
                    raise _Rejected("TCX_ARCHIVE_ENCRYPTED")
                if member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise _Rejected("TCX_ARCHIVE_COMPRESSION_NOT_SUPPORTED")
                if member.file_size > MAX_IMPORT_BYTES:
                    raise _Rejected("TCX_IMPORT_BYTE_LIMIT_EXCEEDED")
                with archive.open(member) as stream:
                    xml = stream.read(MAX_IMPORT_BYTES + 1)
                if len(xml) > MAX_IMPORT_BYTES:
                    raise _Rejected("TCX_IMPORT_BYTE_LIMIT_EXCEEDED")
        except _Rejected:
            raise
        except (
            zipfile.BadZipFile,
            OSError,
            RuntimeError,
            NotImplementedError,
            UnicodeError,
            ValueError,
            EOFError,
            zlib.error,
        ) as exc:
            raise _Rejected("TCX_ARCHIVE_INVALID") from exc
    try:
        parser = ET.XMLParser(target=_BoundedTreeBuilder())
        root = ET.fromstring(xml, parser=parser)
    except _Rejected:
        raise
    except (ET.ParseError, LookupError, UnicodeError, ValueError) as exc:
        raise _Rejected("TCX_XML_INVALID") from exc
    if root.tag != f"{{{TCX_NAMESPACE}}}TrainingCenterDatabase":
        raise _Rejected("TCX_V2_NAMESPACE_OR_ROOT_REQUIRED")
    activity_nodes = root.findall("t:Activities/t:Activity", NS)
    if not activity_nodes or len(activity_nodes) > MAX_ACTIVITIES:
        raise _Rejected("TCX_ACTIVITY_COUNT_INVALID")
    if (
        len(root.findall("t:Activities/t:Activity/t:Lap/t:Track/t:Trackpoint", NS))
        > MAX_TRACKPOINTS
    ):
        raise _Rejected("TCX_TRACKPOINT_LIMIT_EXCEEDED")
    activities = [_activity(a) for a in activity_nodes]
    return activities, {
        "container_kind": kind,
        "source_file_byte_count": len(file_bytes),
        "tcx_xml_byte_count": len(xml),
        "tcx_xml_sha256": hashlib.sha256(xml).hexdigest(),
        "activity_count": len(activities),
        "activities": [a["summary"] for a in activities],
    }


def _activity(node):
    reasons = []
    start = _single_time(node, "t:Id")
    if start is None:
        reasons.append("TCX_ACTIVITY_START_UNUSABLE")
    points = node.findall("t:Lap/t:Track/t:Trackpoint", NS)
    point_times, hr_times, values, presence = [], [], [], []
    for point in points:
        time = _single_time(point, "t:Time")
        if time is None:
            reasons.append("TCX_TRACKPOINT_TIMESTAMP_UNUSABLE")
        else:
            point_times.append(time)
        hr_nodes = point.findall("t:HeartRateBpm", NS)
        if not hr_nodes:
            presence.append(False)
            continue
        value_nodes = hr_nodes[0].findall("t:Value", NS)
        value = _decimal(value_nodes[0].text) if len(value_nodes) == 1 else None
        if len(hr_nodes) != 1 or value is None or value <= 0:
            reasons.append("TCX_HR_VALUE_INVALID")
            presence.append(False)
            continue
        presence.append(True)
        values.append(value)
        if time is not None:
            hr_times.append(time)
    if any(b <= a for a, b in pairwise(point_times)):
        reasons.append("TCX_TRACKPOINT_TIMESTAMPS_NOT_STRICTLY_INCREASING")
    if len(hr_times) < 2:
        reasons.append("TCX_TOO_FEW_HR_VALUES_TO_VERIFY_INTERVAL")
    if start is not None and point_times and point_times[0] < start:
        reasons.append("TCX_TRACKPOINT_PRECEDES_ACTIVITY_START")
    first = next((i for i, present in enumerate(presence) if present), None)
    last = next((i for i in range(len(presence) - 1, -1, -1) if presence[i]), None)
    leading = first if first is not None else len(points)
    trailing = len(points) - 1 - last if last is not None else 0
    laps = node.findall("t:Lap", NS)
    durations = [_decimal(lap.findtext("t:TotalTimeSeconds", namespaces=NS)) for lap in laps]
    duration_ms = (
        float(sum(durations) * 1000)
        if durations and all(d is not None and d >= 0 for d in durations)
        else None
    )
    if duration_ms is not None and not (-1e15 < duration_ms < 1e15):
        duration_ms = None
    return {
        "start": start,
        "point_times": point_times,
        "hr_times": hr_times,
        "values": values,
        "reasons": sorted(set(reasons)),
        "summary": {
            "activity_start_utc": start.isoformat() if start is not None else None,
            "lap_count": len(laps),
            "track_count": len(node.findall("t:Lap/t:Track", NS)),
            "trackpoint_count": len(points),
            "positive_finite_hr_count": len(values),
            "missing_hr_point_count": presence.count(False),
            "leading_points_without_hr": leading,
            "trailing_points_without_hr": trailing,
            "internal_points_without_hr": presence[first : last + 1].count(False)
            if first is not None
            else 0,
            "lap_declared_duration_sum_ms": duration_ms,
            "blocking_reasons": sorted(set(reasons)),
        },
    }


def _compare(activity, exercise, session, technical):
    reasons = list(activity["reasons"])
    if technical["technical_status"] != "TECHNICALLY_CLEAN_WITH_LIMITATIONS":
        reasons.append("API_HR_TECHNICAL_CHECK_NOT_CLEAN")
        return sorted(set(reasons)), None, None, [], None
    container = exercise.get("samples")
    series = container if isinstance(container, list) else _mapping(container).get("samples", [])
    hr = next(s for s in series if isinstance(s, Mapping) and s.get("type") == "HEART_RATE")
    values, interval = hr["values"], hr["intervalMillis"]
    if len(values) > MAX_TRACKPOINTS:
        reasons.append("API_HR_SLOT_LIMIT_EXCEEDED")
    if len(values) != len(activity["values"]):
        reasons.append("API_TCX_HR_COUNT_DIFFERS")
    elif any(Decimal(str(a)) != b for a, b in zip(values, activity["values"])):
        reasons.append("API_TCX_ORDERED_HR_VALUES_DIFFER")
    times = activity["hr_times"]
    if any(_us(b - a) != interval * 1000 for a, b in pairwise(times)):
        reasons.append("TCX_HR_GRID_DIFFERS_FROM_API_INTERVAL")
    start = _api_time(exercise.get("startTime"), exercise, session)
    stop = _api_time(exercise.get("stopTime"), exercise, session)
    if start is None or stop is None or stop <= start:
        reasons.append("API_EXERCISE_TIME_WINDOW_UNUSABLE")
    else:
        export_start = activity["start"]
        if export_start is not None:
            delta = _us(export_start - start)
            fractional = "." in exercise["startTime"].split("T", 1)[1]
            if (fractional and delta != 0) or (not fractional and not 0 <= delta < 1_000_000):
                reasons.append("API_TCX_ACTIVITY_START_DOES_NOT_MATCH")
        stop_slack_us = 0 if "." in exercise["stopTime"].split("T", 1)[1] else 1_000_000
        # A coarse stop accepts the reported second; a fractional stop is exact.
        outside = any(
            t < start
            or (
                t > stop
                if stop_slack_us == 0
                else t >= stop + timedelta(microseconds=stop_slack_us)
            )
            for t in activity["point_times"]
        )
        if outside:
            reasons.append("TCX_POINTS_OUTSIDE_API_EXERCISE_TIME_WINDOW")
    return sorted(set(reasons)), start, stop, values, interval


def _single_time(node, path):
    nodes = node.findall(path, NS)
    return _time(nodes[0].text) if len(nodes) == 1 else None


def _time(value):
    if not isinstance(value, str) or not _ISO_TIME.fullmatch(value.strip()):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
        return parsed.astimezone(UTC) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _api_time(value, exercise, session):
    if not isinstance(value, str) or not _ISO_TIME.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            offset = exercise.get("timezoneOffsetMinutes", session.get("timezoneOffsetMinutes"))
            if not isinstance(offset, int) or isinstance(offset, bool) or abs(offset) >= 1440:
                return None
            parsed = parsed.replace(tzinfo=timezone(timedelta(minutes=offset)))
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _decimal(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        number = Decimal(value)
        return number if number.is_finite() and -12 <= number.adjusted() <= 12 else None
    except InvalidOperation:
        return None


def _us(delta):
    return delta // timedelta(microseconds=1)


def _ms(microseconds):
    return microseconds // 1000 if microseconds % 1000 == 0 else microseconds / 1000


def _identity(value):
    return (
        str(value)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip()
        else None
    )


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def _finish(result):
    result["blocking_reasons"] = sorted(set(result["blocking_reasons"]))
    result["decision_hash"] = _hash(result)
    return result


def verify_tcx_heart_rate_timebase_evidence(
    evidence,
    sample_session,
    *,
    expected_session_external_id,
    sample_session_match_count,
    expected_exercise_external_id=None,
) -> bool:
    """Recheck stored export evidence against its current, complete API source.

    The original TCX is not replayed here. Its immutable verification decision
    must retain its hash; values, identities, clocks and every sample timestamp
    are checked again against the currently supplied API source.
    """
    try:
        if not isinstance(evidence, Mapping):
            return False
        body = dict(evidence)
        claimed_hash = body.pop("decision_hash", None)
        if claimed_hash != _hash(body):
            return False
        if (
            evidence.get("provider") != "PADDLETRAINER"
            or evidence.get("schema_version") != "0.1"
            or evidence.get("timebase_version") != TIMEBASE_VERSION
            or evidence.get("status") != "VERIFIED_EXPORT_TIMEBASE_WITH_LIMITATIONS"
            or evidence.get("export_timebase_verified") is not True
            or evidence.get("blocking_reasons") != []
        ):
            return False
        if any(
            evidence.get(flag) is not False
            for flag in (
                "training_authorized",
                "numeric_prediction_authorized",
                "acquisition_quality_verified",
                "api_native_time_origin_verified",
                "pause_clock_semantics_verified",
            )
        ):
            return False
        source = build_training_session_heart_rate_validation(
            sample_session,
            expected_session_external_id=expected_session_external_id,
            sample_session_match_count=sample_session_match_count,
        )
        provenance = evidence["input_provenance"]
        if (
            source["blocking_reasons"]
            or evidence["session_external_id"] != _identity(expected_session_external_id)
            or provenance["api_source_hash"] != source["input_provenance"]["source_hash"]
            or provenance["api_validation_decision_hash"] != source["decision_hash"]
        ):
            return False
        binding, timebase = evidence["binding"], evidence["timebase"]
        if (
            type(evidence.get("matching_candidate_count")) is not int
            or evidence["matching_candidate_count"] != 1
        ):
            return False
        if any(
            type(timebase.get(key)) is not int
            for key in (
                "sample_count",
                "interval_ms",
                "first_sample_offset_from_api_exercise_start_us",
            )
        ) or any(
            isinstance(timebase.get(key), bool)
            for key in (
                "first_sample_offset_from_api_exercise_start_ms",
                "sample_grid_span_ms",
            )
        ):
            return False
        index = binding["api_exercise_index"]
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            return False
        ids = [
            _identity(_mapping(_mapping(e).get("identifier")).get("id"))
            for e in sample_session["exercises"]
        ]
        if not ids or len(ids) > 64 or None in ids or len(set(ids)) != len(ids):
            return False
        activity_index = binding["tcx_activity_index"]
        if (
            type(activity_index) is not int
            or activity_index < 0
            or binding.get("match_basis")
            != "UNIQUE_ID_BOUND_SESSION_FULL_ORDERED_HR_AND_START_METADATA"
        ):
            return False
        matched = [c for c in evidence["candidates"] if c.get("matched") is True]
        if len(matched) != 1 or matched[0] != {
            "api_exercise_index": index,
            "api_exercise_external_id": ids[index],
            "tcx_activity_index": activity_index,
            "matched": True,
            "blocking_reasons": [],
        }:
            return False
        summary = evidence["source_import"]
        if (
            summary["tcx_xml_sha256"] != provenance["tcx_xml_sha256"]
            or summary["activity_count"] != len(summary["activities"])
            or activity_index >= summary["activity_count"]
        ):
            return False
        activity_summary = summary["activities"][activity_index]
        if (
            activity_summary["blocking_reasons"] != []
            or activity_summary["activity_start_utc"] != binding["tcx_activity_start_utc"]
            or activity_summary["positive_finite_hr_count"] != timebase["sample_count"]
        ):
            return False
        exercise = sample_session["exercises"][index]
        identity = _identity(_mapping(exercise.get("identifier")).get("id"))
        if (
            identity is None
            or evidence["exercise_external_id"] != identity
            or (
                expected_exercise_external_id is not None
                and identity != _identity(expected_exercise_external_id)
            )
        ):
            return False
        container = exercise["samples"]
        series = container if isinstance(container, list) else container["samples"]
        raw_hr = [s for s in series if s.get("type") == "HEART_RATE"]
        if len(raw_hr) != 1:
            return False
        values = raw_hr[0]["values"]
        strings = timebase["sample_timestamps_utc"]
        if not isinstance(strings, list) or len(strings) != len(values):
            return False
        times = [_time(s) for s in strings]
        if None in times or len(times) < 2:
            return False
        activity_start = _time(binding["tcx_activity_start_utc"])
        activity = {
            "start": activity_start,
            "point_times": times,
            "hr_times": times,
            "values": [Decimal(str(v)) for v in values],
            "reasons": [],
        }
        if activity_start is None or times[0] < activity_start:
            return False
        reasons, start, stop, _, interval = _compare(
            activity, exercise, sample_session, source["exercises"][index]
        )
        if (
            reasons
            or binding["api_exercise_start_utc"] != start.isoformat()
            or binding["api_exercise_stop_utc"] != stop.isoformat()
        ):
            return False
        offset = _us(times[0] - start)
        expected = {
            "source": "VALUE_MATCHED_TCX_EXPORT_TIMESTAMPS",
            "sample_count": len(times),
            "interval_ms": interval,
            "first_sample_timestamp_utc": times[0].isoformat(),
            "last_sample_timestamp_utc": times[-1].isoformat(),
            "first_sample_offset_from_api_exercise_start_us": offset,
            "first_sample_offset_from_api_exercise_start_ms": _ms(offset),
            "sample_grid_span_ms": _ms(_us(times[-1] - times[0])),
            "sample_timestamps_utc": [t.isoformat() for t in times],
        }
        if timebase != expected:
            return False
        return (
            type(binding.get("matched_hr_sample_count")) is int
            and binding["matched_hr_sample_count"] == len(values)
            and type(binding.get("ordered_value_mismatch_count")) is int
            and binding["ordered_value_mismatch_count"] == 0
            and binding["normalized_hr_values_sha256"]
            == _hash([str(Decimal(str(v)).normalize()) for v in values])
        )
    except (
        KeyError,
        IndexError,
        AttributeError,
        TypeError,
        ValueError,
        OverflowError,
        InvalidOperation,
    ):
        return False
