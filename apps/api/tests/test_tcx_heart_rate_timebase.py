import io
import json
import zipfile
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree as ET

import pytest

from app.services import tcx_heart_rate_timebase as module

N = "{" + module.TCX_NAMESPACE + "}"
START = datetime(2025, 1, 10, 9, 0, 0, 271000, tzinfo=UTC)


@pytest.fixture
def session():
    return {
        "identifier": {"id": "synthetic-session"},
        "product": {"modelName": "GENERIC DEVICE"},
        "timezoneOffsetMinutes": 60,
        "exercises": [
            {
                "identifier": {"id": "synthetic-exercise"},
                "startTime": "2025-01-10T10:00:00",
                "stopTime": "2025-01-10T10:00:15",
                "durationMillis": 15000,
                "samples": {
                    "samples": [
                        {
                            "type": "HEART_RATE",
                            "intervalMillis": 1000,
                            "values": [101.0, 103.0, 107.0, 111.0],
                        }
                    ]
                },
            }
        ],
    }


def xml_tree(values=None, *, start=START, leading=0, trailing=0, interval_us=1_000_000):
    values = [101, 103, 107, 111] if values is None else values
    root = ET.Element(N + "TrainingCenterDatabase")
    activities = ET.SubElement(root, N + "Activities")
    activity = ET.SubElement(activities, N + "Activity", Sport="Other")
    ET.SubElement(activity, N + "Id").text = start.isoformat()
    lap = ET.SubElement(activity, N + "Lap", StartTime=start.isoformat())
    ET.SubElement(lap, N + "TotalTimeSeconds").text = "15.0"
    track = ET.SubElement(lap, N + "Track")
    for i, value in enumerate([None] * leading + values + [None] * trailing):
        point = ET.SubElement(track, N + "Trackpoint")
        ET.SubElement(point, N + "Time").text = (
            start + timedelta(seconds=2, microseconds=i * interval_us)
        ).isoformat()
        if value is not None:
            hr = ET.SubElement(point, N + "HeartRateBpm")
            ET.SubElement(hr, N + "Value").text = str(value)
        ET.SubElement(point, N + "SensorState").text = "Present" if value else "Absent"
    return root


def xml_bytes(root=None, **kwargs):
    return ET.tostring(root if root is not None else xml_tree(**kwargs), encoding="utf-8")


def archived(xml, names=("anonymous.tcx",)):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.writestr(name, xml)
    return output.getvalue()


def verify(session, xml=None, **kwargs):
    return module.build_tcx_heart_rate_timebase(
        xml_bytes() if xml is None else xml,
        session,
        expected_session_external_id=kwargs.pop("identity", "synthetic-session"),
        sample_session_match_count=kwargs.pop("count", 1),
        **kwargs,
    )


def hr(session):
    return session["exercises"][0]["samples"]["samples"][0]


def points(root):
    return root.findall("t:Activities/t:Activity/t:Lap/t:Track/t:Trackpoint", module.NS)


def assert_withheld(result, reason=None):
    assert result["export_timebase_verified"] is False
    assert result["status"] == "WITHHELD"
    assert result["timebase"] is None
    assert result["binding"] is None
    if reason:
        all_reasons = result["blocking_reasons"] + [
            r for c in result["candidates"] for r in c["blocking_reasons"]
        ]
        assert reason in all_reasons
    json.dumps(result, allow_nan=False)


def test_full_sequence_match_produces_scoped_timestamps_without_training(session):
    original = deepcopy(session)
    result = verify(session)
    assert result["status"] == "VERIFIED_EXPORT_TIMEBASE_WITH_LIMITATIONS"
    assert result["export_timebase_verified"] is True
    assert result["matching_candidate_count"] == 1
    assert result["exercise_external_id"] == "synthetic-exercise"
    assert result["timebase"]["first_sample_offset_from_api_exercise_start_us"] == 2_271_000
    assert result["timebase"]["first_sample_offset_from_api_exercise_start_ms"] == 2271
    assert result["timebase"]["first_sample_timestamp_utc"] == "2025-01-10T09:00:02.271000+00:00"
    assert len(result["timebase"]["sample_timestamps_utc"]) == 4
    assert result["binding"]["ordered_value_mismatch_count"] == 0
    assert session == original
    for flag in (
        "training_authorized",
        "numeric_prediction_authorized",
        "api_native_time_origin_verified",
        "pause_clock_semantics_verified",
        "acquisition_quality_verified",
    ):
        assert result[flag] is False
    assert result["policy"]["persists_uploaded_file"] is False
    assert result["policy"]["promotes_training_data_readiness"] is False
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("fraction_us", [0, 137000, 999999])
def test_offset_is_derived_for_each_export_at_microsecond_precision(session, fraction_us):
    start = START.replace(microsecond=fraction_us)
    result = verify(session, xml_bytes(start=start))
    assert result["export_timebase_verified"] is True
    assert result["timebase"]["first_sample_offset_from_api_exercise_start_us"] == (
        2_000_000 + fraction_us
    )


def test_decimal_api_values_equal_integer_export_values_exactly(session):
    hr(session)["values"] = [101, 103.0, 107, 111.0]
    assert verify(session)["export_timebase_verified"] is True
    hr(session)["values"][1] += 0.001
    assert_withheld(verify(session), "API_TCX_ORDERED_HR_VALUES_DIFFER")


def test_count_minimum_maximum_and_mean_do_not_replace_ordered_comparison(session):
    hr(session)["values"] = [101, 107, 103, 111]
    assert_withheld(verify(session), "API_TCX_ORDERED_HR_VALUES_DIFFER")


def test_shorter_api_vector_is_not_matched_to_export_subset(session):
    hr(session)["values"] = [103, 107, 111]
    assert_withheld(verify(session), "API_TCX_HR_COUNT_DIFFERS")


def test_missing_hr_at_edges_remains_visible_and_is_not_interpolated(session):
    result = verify(session, xml_bytes(leading=2, trailing=3))
    assert result["export_timebase_verified"] is True
    summary = result["source_import"]["activities"][0]
    assert summary["leading_points_without_hr"] == 2
    assert summary["trailing_points_without_hr"] == 3
    assert summary["internal_points_without_hr"] == 0
    assert summary["trackpoint_count"] == 9
    assert len(result["timebase"]["sample_timestamps_utc"]) == 4
    assert result["timebase"]["first_sample_offset_from_api_exercise_start_ms"] == 4271


def test_internal_missing_hr_is_not_compressed_into_regular_api_clock(session):
    result = verify(session, xml_bytes(values=[101, 103, None, 107, 111]))
    assert_withheld(result, "TCX_HR_GRID_DIFFERS_FROM_API_INTERVAL")
    assert result["source_import"]["activities"][0]["internal_points_without_hr"] == 1


def test_multiple_laps_keep_one_continuous_ordered_sequence(session):
    root = xml_tree()
    activity = root.find("t:Activities/t:Activity", module.NS)
    track = activity.find("t:Lap/t:Track", module.NS)
    second_lap = ET.SubElement(activity, N + "Lap", StartTime=START.isoformat())
    ET.SubElement(second_lap, N + "TotalTimeSeconds").text = "0"
    second_track = ET.SubElement(second_lap, N + "Track")
    for p in list(track)[2:]:
        track.remove(p)
        second_track.append(p)
    result = verify(session, xml_bytes(root))
    assert result["export_timebase_verified"] is True
    assert result["source_import"]["activities"][0]["lap_count"] == 2


@pytest.mark.parametrize("delta", [-1, 1, 86400])
def test_other_start_second_or_day_is_not_accepted_with_same_values(session, delta):
    assert_withheld(
        verify(session, xml_bytes(start=START + timedelta(seconds=delta))),
        "API_TCX_ACTIVITY_START_DOES_NOT_MATCH",
    )


def test_fractional_api_start_must_match_exactly(session):
    session["exercises"][0]["startTime"] = "2025-01-10T10:00:00.271000"
    assert verify(session)["export_timebase_verified"] is True
    session["exercises"][0]["startTime"] = "2025-01-10T10:00:00.272000"
    assert_withheld(verify(session), "API_TCX_ACTIVITY_START_DOES_NOT_MATCH")


def test_utc_api_start_and_offset_tcx_timestamp_represent_same_instant(session):
    session["exercises"][0]["startTime"] = "2025-01-10T09:00:00Z"
    session["exercises"][0]["stopTime"] = "2025-01-10T09:00:15Z"
    root = xml_tree()
    for node in root.findall(".//t:Time", module.NS) + root.findall(".//t:Id", module.NS):
        node.text = node.text.replace("09:00", "10:00").replace("+00:00", "+01:00")
    assert verify(session, xml_bytes(root))["export_timebase_verified"] is True


@pytest.mark.parametrize("offset", [None, True, "60", 1440, -1440])
def test_naive_api_clock_requires_valid_numeric_offset(session, offset):
    session["timezoneOffsetMinutes"] = offset
    assert_withheld(verify(session), "API_EXERCISE_TIME_WINDOW_UNUSABLE")


def test_grid_interval_comes_from_api_not_assumed_one_second(session):
    hr(session)["intervalMillis"] = 500
    result = verify(session, xml_bytes(interval_us=500_000))
    assert result["export_timebase_verified"] is True
    assert result["timebase"]["interval_ms"] == 500
    assert_withheld(verify(session), "TCX_HR_GRID_DIFFERS_FROM_API_INTERVAL")


@pytest.mark.parametrize("clock_change", ["duplicate", "backward", "naive", "invalid", "missing"])
def test_bad_timestamp_is_not_repaired(session, clock_change):
    root = xml_tree()
    ps = points(root)
    time = ps[1].find(N + "Time")
    if clock_change == "duplicate":
        time.text = ps[0].findtext(N + "Time")
    elif clock_change == "backward":
        time.text = START.isoformat()
    elif clock_change == "naive":
        time.text = time.text.replace("+00:00", "")
    elif clock_change == "invalid":
        time.text = "invalid"
    else:
        ps[1].remove(time)
    assert_withheld(verify(session, xml_bytes(root)))


def test_duplicate_time_field_and_duplicate_hr_field_are_withheld(session):
    root = xml_tree()
    p = points(root)[0]
    p.append(deepcopy(p.find(N + "Time")))
    assert_withheld(verify(session, xml_bytes(root)), "TCX_TRACKPOINT_TIMESTAMP_UNUSABLE")
    root = xml_tree()
    p = points(root)[0]
    p.append(deepcopy(p.find(N + "HeartRateBpm")))
    assert_withheld(verify(session, xml_bytes(root)), "TCX_HR_VALUE_INVALID")


def test_points_outside_reported_exercise_window_are_withheld(session):
    session["exercises"][0]["stopTime"] = "2025-01-10T10:00:03"
    assert_withheld(verify(session), "TCX_POINTS_OUTSIDE_API_EXERCISE_TIME_WINDOW")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "text", "1e999999"])
def test_invalid_export_hr_values_are_not_discarded_to_force_match(session, value):
    root = xml_tree()
    points(root)[0].find(N + "HeartRateBpm").find(N + "Value").text = value
    assert_withheld(verify(session, xml_bytes(root)), "TCX_HR_VALUE_INVALID")


@pytest.mark.parametrize("value", [None, True, "101", float("nan"), 0, -1])
def test_invalid_api_values_cannot_be_promoted_by_export(session, value):
    hr(session)["values"][0] = value
    assert_withheld(verify(session))


@pytest.mark.parametrize(
    "identity,count",
    [
        ("other-session", 1),
        (None, 1),
        ("synthetic-session", 0),
        ("synthetic-session", 2),
        ("synthetic-session", True),
    ],
)
def test_source_binding_is_checked_before_value_match(session, identity, count):
    assert_withheld(verify(session, identity=identity, count=count))


def test_api_exercise_duplicate_or_missing_identity_is_not_position_matched(session):
    session["exercises"].append(deepcopy(session["exercises"][0]))
    assert_withheld(verify(session), "API_EXERCISE_IDENTITY_MISSING_OR_AMBIGUOUS")
    session["exercises"].pop()
    session["exercises"][0].pop("identifier")
    assert_withheld(verify(session), "API_EXERCISE_IDENTITY_MISSING_OR_AMBIGUOUS")


def test_unique_matching_exercise_is_found_after_reordering(session):
    other = deepcopy(session["exercises"][0])
    other["identifier"]["id"] = "other-exercise"
    other["samples"]["samples"][0]["values"] = [120, 121, 122, 123]
    session["exercises"].insert(0, other)
    result = verify(session)
    assert result["export_timebase_verified"] is True
    assert result["binding"]["api_exercise_index"] == 1
    assert result["exercise_external_id"] == "synthetic-exercise"


def test_multiple_matching_exercises_require_explicit_selection(session):
    other = deepcopy(session["exercises"][0])
    other["identifier"]["id"] = "second-exercise"
    session["exercises"].append(other)
    assert_withheld(verify(session), "API_TCX_MATCH_AMBIGUOUS")
    result = verify(session, expected_exercise_external_id="second-exercise")
    assert result["export_timebase_verified"] is True
    assert result["exercise_external_id"] == "second-exercise"
    assert_withheld(
        verify(session, expected_exercise_external_id="missing"), "EXPECTED_API_EXERCISE_NOT_FOUND"
    )


def test_duplicate_matching_tcx_activities_are_ambiguous(session):
    root = xml_tree()
    container = root.find(N + "Activities")
    container.append(deepcopy(container[0]))
    assert_withheld(verify(session, xml_bytes(root)), "API_TCX_MATCH_AMBIGUOUS")


def test_gps_and_device_names_are_not_required_or_exposed(session):
    root = xml_tree()
    creator = ET.SubElement(root.find("t:Activities/t:Activity", module.NS), N + "Creator")
    ET.SubElement(creator, N + "Name").text = "PRIVATE NAME"
    position = ET.SubElement(points(root)[0], N + "Position")
    ET.SubElement(position, N + "LatitudeDegrees").text = "PRIVATE LOCATION"
    result = verify(session, xml_bytes(root))
    assert result["export_timebase_verified"] is True
    serialized = json.dumps(result)
    assert "PRIVATE NAME" not in serialized
    assert "PRIVATE LOCATION" not in serialized


def test_raw_xml_and_zip_use_same_xml_evidence_without_name_matching(session):
    xml = xml_bytes()
    raw = verify(session, xml)
    zipped = verify(session, archived(xml, names=("folder/any-name.TCX",)))
    assert zipped["export_timebase_verified"] is True
    assert raw["timebase"] == zipped["timebase"]
    assert raw["input_provenance"]["tcx_xml_sha256"] == zipped["input_provenance"]["tcx_xml_sha256"]
    assert raw["decision_hash"] != zipped["decision_hash"]
    assert zipped["source_import"]["container_kind"] == "ZIP"
    assert "any-name" not in json.dumps(zipped)


@pytest.mark.parametrize(
    "names", [("a.tcx", "b.tcx"), ("readme.txt",), ("../a.tcx",), ("/a.tcx",), ("C:\\a.tcx",)]
)
def test_ambiguous_or_unsafe_archives_are_rejected(session, names):
    assert_withheld(verify(session, archived(xml_bytes(), names=names)))


@pytest.mark.parametrize(
    "payload", [b"", b"PKnot-a-zip", b"<invalid", b"<TrainingCenterDatabase/>"]
)
def test_invalid_documents_return_structured_withheld_result(session, payload):
    assert_withheld(verify(session, payload))


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_dtd_and_entities_are_rejected_in_all_supported_encodings(session, encoding):
    xml = (
        '<?xml version="1.0" encoding="' + encoding + '"?>'
        '<!DOCTYPE TrainingCenterDatabase [<!ENTITY data "expanded">]>'
        '<TrainingCenterDatabase xmlns="' + module.TCX_NAMESPACE + '">&data;'
        "</TrainingCenterDatabase>"
    ).encode(encoding)
    assert_withheld(verify(session, xml), "TCX_DTD_NOT_ALLOWED")


@pytest.mark.parametrize(
    "limit",
    [
        "MAX_IMPORT_BYTES",
        "MAX_XML_ELEMENTS",
        "MAX_XML_DEPTH",
        "MAX_TRACKPOINTS",
        "MAX_ACTIVITIES",
        "MAX_ARCHIVE_MEMBERS",
    ],
)
def test_resource_limits_are_enforced(session, monkeypatch, limit):
    monkeypatch.setattr(module, limit, 0)
    payload = archived(xml_bytes()) if limit == "MAX_ARCHIVE_MEMBERS" else xml_bytes()
    assert_withheld(verify(session, payload))


def test_uncompressed_archive_size_is_limited(session, monkeypatch):
    xml = xml_bytes() + b" " * 20000
    payload = archived(xml)
    assert len(payload) < 2000
    monkeypatch.setattr(module, "MAX_IMPORT_BYTES", 2000)
    assert_withheld(verify(session, payload), "TCX_IMPORT_BYTE_LIMIT_EXCEEDED")


def test_corrupt_deflate_data_returns_controlled_archive_rejection(session):
    payload = bytearray(archived(xml_bytes()))
    name_length = int.from_bytes(payload[26:28], "little")
    extra_length = int.from_bytes(payload[28:30], "little")
    payload[30 + name_length + extra_length] = 255
    assert_withheld(verify(session, bytes(payload)), "TCX_ARCHIVE_INVALID")


def test_decision_hash_is_repeatable_and_binds_exact_file_bytes(session):
    xml = xml_bytes()
    first = verify(session, xml)
    assert first["decision_hash"] == verify(session, xml)["decision_hash"]
    whitespace = verify(session, xml + b"\n")
    assert whitespace["timebase"] == first["timebase"]
    assert whitespace["decision_hash"] != first["decision_hash"]
    session["exercises"][0]["durationMillis"] = 14999
    changed = verify(session, xml)
    assert changed["decision_hash"] != first["decision_hash"]
    assert "TCX_LAP_DURATION_DIFFERS_FROM_API_DECLARED_DURATION" in changed["limitations"]
