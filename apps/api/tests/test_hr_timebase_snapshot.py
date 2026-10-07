import hashlib
import json
from copy import deepcopy
from datetime import timedelta

import pytest
from test_tcx_heart_rate_timebase import START, verify, xml_bytes
from test_tcx_heart_rate_timebase import session as _session_fixture

from app.services.hr_timebase_snapshot import (
    build_hr_timebase_snapshot,
    resolve_hr_timebase_snapshots,
    verify_hr_timebase_snapshot,
)
from app.services.tcx_heart_rate_timebase import verify_tcx_heart_rate_timebase_evidence

session = _session_fixture


def snapshot(source, evidence=None, owner="synthetic-athlete"):
    return build_hr_timebase_snapshot(
        verify(source) if evidence is None else evidence,
        source,
        athlete_id=owner,
        session_external_id="synthetic-session",
        sample_session_match_count=1,
    )


def record(value, identity="snapshot-1"):
    return {
        "snapshot_id": identity,
        "snapshot": value,
        "column_identity": {
            k: value[k]
            for k in (
                "athlete_id",
                "source_provider",
                "session_external_id",
                "exercise_external_id",
                "api_source_hash",
                "verification_decision_hash",
                "snapshot_hash",
            )
        },
    }


def check(value, source, **kwargs):
    return verify_hr_timebase_snapshot(
        value,
        source,
        athlete_id=kwargs.pop("owner", "synthetic-athlete"),
        session_external_id=kwargs.pop("identity", "synthetic-session"),
        sample_session_match_count=kwargs.pop("count", 1),
        **kwargs,
    )


def resolve(records, source, **kwargs):
    return resolve_hr_timebase_snapshots(
        records,
        source,
        athlete_id=kwargs.get("owner", "synthetic-athlete"),
        session_external_id="synthetic-session",
        sample_session_match_count=1,
    )


def rehash(value, key):
    content = {k: v for k, v in value.items() if k != key}
    value[key] = hashlib.sha256(
        json.dumps(
            content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def test_snapshot_round_trip_binds_owner_source_and_verification(session):
    proof = verify(session)
    before = deepcopy(proof)
    value = snapshot(session, proof)
    assert proof == before
    assert check(value, session)
    assert value == json.loads(json.dumps(value))
    resolved = resolve([record(value)], session)
    assert resolved["verified_exercise_count"] == 1
    selected = resolved["by_exercise"]["synthetic-exercise"]
    assert selected["snapshot_hash"] == value["snapshot_hash"]
    assert selected["timebase"]["first_sample_offset_from_api_exercise_start_us"] == 2271000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"owner": "another-athlete"},
        {"identity": "another-session"},
        {"count": 0},
        {"count": 2},
        {"exercise_external_id": "another-exercise"},
    ],
)
def test_snapshot_cannot_cross_identity_or_ambiguous_source_boundaries(session, kwargs):
    assert not check(snapshot(session), session, **kwargs)


@pytest.mark.parametrize("field", ["durationMillis", "startTime", "stopTime"])
def test_changed_api_metadata_invalidates_saved_proof_even_with_same_values(session, field):
    value = snapshot(session)
    e = session["exercises"][0]
    e[field] = 14999 if field == "durationMillis" else "2025-01-10T10:00:01"
    assert not check(value, session)


def test_changed_api_value_and_added_source_field_invalidate_old_snapshot(session):
    value = snapshot(session)
    session["exercises"][0]["samples"]["samples"][0]["values"][1] = 105
    assert not check(value, session)
    session["exercises"][0]["samples"]["samples"][0]["values"][1] = 103
    session["modified"] = "2025-01-11T00:00:00Z"
    assert not check(value, session)


@pytest.mark.parametrize(
    "field",
    [
        "athlete_id",
        "api_source_hash",
        "verification_decision_hash",
        "tcx_xml_sha256",
        "source_file_sha256",
        "exercise_external_id",
    ],
)
def test_tampering_and_rehashed_identity_mismatch_are_both_rejected(session, field):
    value = snapshot(session)
    value[field] = "0" * 64 if "hash" in field or "sha256" in field else "another-identity"
    assert not check(value, session)
    rehash(value, "snapshot_hash")
    assert not check(value, session)


@pytest.mark.parametrize(
    "field",
    [
        "training_authorized",
        "numeric_prediction_authorized",
        "acquisition_quality_verified",
        "api_native_time_origin_verified",
        "pause_clock_semantics_verified",
    ],
)
def test_rehashed_false_promotions_are_rejected(session, field):
    proof = verify(session)
    proof[field] = True
    rehash(proof, "decision_hash")
    assert not verify_tcx_heart_rate_timebase_evidence(
        proof,
        session,
        expected_session_external_id="synthetic-session",
        sample_session_match_count=1,
    )


@pytest.mark.parametrize(
    "field",
    [
        "sample_count",
        "interval_ms",
        "first_sample_timestamp_utc",
        "sample_grid_span_ms",
        "first_sample_offset_from_api_exercise_start_us",
    ],
)
def test_rehashed_inconsistent_timebase_is_rejected(session, field):
    proof = verify(session)
    proof["timebase"][field] = "invalid" if "timestamp" in field else 7
    rehash(proof, "decision_hash")
    assert not verify_tcx_heart_rate_timebase_evidence(
        proof,
        session,
        expected_session_external_id="synthetic-session",
        sample_session_match_count=1,
    )


def test_equivalent_snapshots_resolve_without_latest_wins_policy(session):
    first = snapshot(session)
    second = snapshot(session, verify(session, xml_bytes() + b"\n"))
    records = [record(first, "first"), record(second, "second")]
    resolved = resolve(records, session)
    assert resolved["verified_exercise_count"] == 1
    chosen = resolved["by_exercise"]["synthetic-exercise"]
    assert chosen["equivalent_snapshot_count"] == 2
    assert resolve(list(reversed(records)), session)["by_exercise"] == resolved["by_exercise"]


def test_conflicting_current_source_clocks_are_not_silently_selected(session):
    first = snapshot(session)
    second = snapshot(
        session, verify(session, xml_bytes(start=START + timedelta(microseconds=1000)))
    )
    resolved = resolve([record(first, "first"), record(second, "second")], session)
    assert resolved["verified_exercise_count"] == 0
    assert resolved["by_exercise"]["synthetic-exercise"]["blocking_reasons"] == [
        "SAVED_TIMEBASE_CURRENT_SOURCE_CONFLICT"
    ]


def test_corrupt_payload_or_database_columns_are_fail_closed(session):
    good = record(snapshot(session))
    bad = deepcopy(good)
    bad["column_identity"]["athlete_id"] = "another-athlete"
    result = resolve([good, bad], session)
    assert result["verified_exercise_count"] == 0
    assert result["rejected_record_count"] == 1
    assert result["status"] == "WITHHELD"


@pytest.mark.parametrize("records", [None, [], {}, [None], [True]])
def test_missing_or_invalid_record_collection_never_claims_verified_timebase(session, records):
    assert resolve(records, session)["verified_exercise_count"] == 0


def test_withheld_import_cannot_be_snapshotted(session):
    with pytest.raises(ValueError):
        snapshot(session, verify(session, b"<invalid"))


@pytest.mark.parametrize("key", ["source_file_sha256", "tcx_xml_sha256"])
def test_missing_or_invalid_file_digest_cannot_create_snapshot(session, key):
    proof = verify(session)
    proof["input_provenance"][key] = "invalid"
    if key == "tcx_xml_sha256":
        proof["source_import"][key] = "invalid"
    rehash(proof, "decision_hash")
    with pytest.raises(ValueError):
        snapshot(session, proof)
