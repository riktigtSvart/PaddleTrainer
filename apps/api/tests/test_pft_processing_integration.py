"""Executable without a web server/database: real recording and input contract."""
from copy import deepcopy
from pathlib import Path
import json
import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError
from app.schemas.pft import PftMeasurementContext
from app.services.pft_processing import (
    PftInputError, canonical_hash, parse_recording, process_recording, recording_hash,
)

FIXTURE = Path(__file__).parent / "fixtures/pft/synthetic_pft_run_v01.TCX"
CONTEXT = {
    "profile_id": "PFT_RUN_GRITX_380_460_550_V01",
    "target_power_w": {"p0": 380, "p1": 460, "p2": 550},
    "sensor_model": "Grit X", "sensor_modality": "WRIST_OPTICAL",
    "power_origin": "POLAR_RUNNING_POWER_ESTIMATE", "recovery_mode": "PASSIVE",
    "targets_prespecified": False,
}


def context(**changes):
    return PftMeasurementContext.model_validate_json(json.dumps({**CONTEXT, **changes}))


@pytest.fixture(scope="module")
def processed():
    return process_recording(FIXTURE.read_bytes(), context())


def test_actual_first_pft_preserves_the_eleven_core_features(processed):
    whole, selected, manifest, result = processed
    values = {f["name"]: f["value"] for f in result["processing_output"]["features"]}
    assert values == {
        "HR_PRE_MEDIAN": 69.0, "HR_P1_MEDIAN": 147.0, "HR_P2_MEDIAN": 163.0,
        "DELTA_HR30_P1": 7.0, "DELTA_HR60_P1": 12.0,
        "DELTA_HR30_P2": 1.0, "DELTA_HR60_P2": 11.0,
        "HRR30": 28.0, "HRR60": 57.0, "HRR90": 65.0, "HRR120": 67.0,
    }
    assert len(whole.samples) == len(selected.samples) == 787
    assert result["state_estimation_authorized"] is False
    assert result["provenance"]["sensor_identity_verified"] is False
    assert result["processing_output"]["algorithm_lineage"]["rhri_sig"] == "rhri_sig_v0.2"


def test_actual_sigmoid_maximum_and_end_window_are_preserved(processed):
    result = processed[-1]
    sig = {s["stage"]: s for s in result["processing_output"]["experimental"]["rhri_sig"]}
    assert sig["p1"]["value_bpm_per_s"] == pytest.approx(0.2685863, abs=1e-5)
    assert sig["p1"]["midpoint_slope_bpm_per_s"] == pytest.approx(0.2188960, abs=1e-5)
    assert sig["p2"]["value_bpm_per_s"] == pytest.approx(0.2641125, abs=1e-5)
    p2 = next(s for s in result["observed_context"]["stages"] if s["stage"] == "p2")
    assert p2["end_windows"]["60"]["hr_mean_bpm"] == pytest.approx(163.15)
    assert p2["end_windows"]["60"]["power_mean_w"] == pytest.approx(535.333333)


@pytest.mark.parametrize("field,value", [
    ("user_id", "another-owner"), ("athlete_id", "other"),
    ("state_estimation_authorized", True), ("sensor_identity_verified", True),
    ("training_plan_modification_authorized", True),
])
def test_client_cannot_supply_owner_or_authority(field, value):
    with pytest.raises(ValidationError):
        context(**{field: value})


@pytest.mark.parametrize("target", [True, 0, -1, float("inf"), "550"])
def test_invalid_target_is_rejected(target):
    with pytest.raises(ValidationError):
        context(target_power_w={"p0": 380, "p1": 460, "p2": target})


def test_byte_different_identical_recordings_are_deduplicated():
    original = FIXTURE.read_bytes()
    changed = original + b"\n "
    assert original != changed
    assert recording_hash(parse_recording(original)) == recording_hash(parse_recording(changed))


def test_power_target_order_must_match_the_step_protocol():
    with pytest.raises(ValidationError, match="must increase"):
        context(target_power_w={"p0": 550, "p1": 460, "p2": 380})


@pytest.mark.parametrize("replacement,expected", [
    (b"<Value>nan</Value>", "TCX_METRIC_NOT_FINITE"),
])
def test_nonfinite_metric_is_rejected(replacement, expected):
    root = ET.fromstring(FIXTURE.read_bytes())
    value = root.find(".//{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}HeartRateBpm/{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Value")
    value.text = "nan"
    with pytest.raises(PftInputError, match=expected):
        parse_recording(ET.tostring(root))


def test_naive_and_nonmonotonic_clock_are_rejected():
    raw = FIXTURE.read_bytes()
    root = ET.fromstring(raw)
    points = root.findall(".//{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Trackpoint")
    tag = "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Time"
    points[1].find(tag).text = points[0].find(tag).text
    with pytest.raises(PftInputError, match="STRICTLY_INCREASING"):
        parse_recording(ET.tostring(root))
    root = ET.fromstring(raw)
    t = root.find(".//"+tag)
    t.text = t.text.replace("Z", "")
    with pytest.raises(PftInputError, match="TIMEZONE_REQUIRED"):
        parse_recording(ET.tostring(root))


def test_dtd_and_multiple_activities_are_rejected():
    with pytest.raises(PftInputError, match="DTD"):
        parse_recording(b'<!DOCTYPE x [<!ENTITY y "z">]><x/>')
    root = ET.fromstring(FIXTURE.read_bytes())
    container = root.find("{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Activities")
    container.append(deepcopy(container[0]))
    with pytest.raises(PftInputError, match="ONE_RUNNING_ACTIVITY"):
        parse_recording(ET.tostring(root))


def test_offset_outside_recording_cannot_produce_a_measurement():
    with pytest.raises(PftInputError, match="SELECTED_SAMPLE"):
        process_recording(FIXTURE.read_bytes(), context(pft_start_offset_s=1000))


def test_context_correction_changes_processing_key_without_new_recording(processed):
    whole, _, first_manifest, _ = processed
    other = process_recording(FIXTURE.read_bytes(), context(hydration_note="Context correction"))
    assert recording_hash(whole) == recording_hash(other[0])
    assert canonical_hash(first_manifest) != canonical_hash(other[2])
