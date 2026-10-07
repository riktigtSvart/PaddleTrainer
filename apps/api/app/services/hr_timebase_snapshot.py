"""Athlete-scoped, immutable export-timebase evidence and conflict resolution."""

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy

from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.tcx_heart_rate_timebase import verify_tcx_heart_rate_timebase_evidence

SNAPSHOT_VERSION = "0.1.0"
MAX_CURRENT_SNAPSHOTS = 512
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def build_hr_timebase_snapshot(
    verification, sample_session, *, athlete_id, session_external_id, sample_session_match_count
):
    if not verify_tcx_heart_rate_timebase_evidence(
        verification,
        sample_session,
        expected_session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    ):
        raise ValueError("Export timebase evidence does not match the current API source")
    owner = _id(athlete_id)
    if owner is None:
        raise ValueError("Athlete identity is required")
    if any(
        not isinstance(verification["input_provenance"].get(key), str)
        or not _DIGEST.fullmatch(verification["input_provenance"][key])
        for key in ("source_file_sha256", "tcx_xml_sha256")
    ):
        raise ValueError("Export source digests are missing or invalid")
    result = {
        "schema_version": "0.1",
        "snapshot_version": SNAPSHOT_VERSION,
        "snapshot_kind": "VERIFIED_HR_EXPORT_TIMEBASE",
        "source_provider": "POLAR",
        "athlete_id": owner,
        "session_external_id": verification["session_external_id"],
        "exercise_external_id": verification["exercise_external_id"],
        "api_source_hash": verification["input_provenance"]["api_source_hash"],
        "verification_decision_hash": verification["decision_hash"],
        "tcx_xml_sha256": verification["input_provenance"]["tcx_xml_sha256"],
        "source_file_sha256": verification["input_provenance"]["source_file_sha256"],
        "verification": deepcopy(dict(verification)),
    }
    result["snapshot_hash"] = _hash(result)
    return result


def verify_hr_timebase_snapshot(
    snapshot,
    sample_session,
    *,
    athlete_id,
    session_external_id,
    sample_session_match_count,
    exercise_external_id=None,
):
    try:
        if not isinstance(snapshot, Mapping):
            return False
        content = dict(snapshot)
        claimed_hash = content.pop("snapshot_hash", None)
        if claimed_hash != _hash(content):
            return False
        if (
            snapshot.get("schema_version") != "0.1"
            or snapshot.get("snapshot_version") != SNAPSHOT_VERSION
            or snapshot.get("snapshot_kind") != "VERIFIED_HR_EXPORT_TIMEBASE"
            or snapshot.get("source_provider") != "POLAR"
            or snapshot.get("athlete_id") != _id(athlete_id)
            or snapshot.get("session_external_id") != _id(session_external_id)
            or _id(athlete_id) is None
        ):
            return False
        verification = snapshot["verification"]
        for key in (
            "api_source_hash",
            "verification_decision_hash",
            "tcx_xml_sha256",
            "source_file_sha256",
        ):
            if not isinstance(snapshot.get(key), str) or not _DIGEST.fullmatch(snapshot[key]):
                return False
        if (
            snapshot["verification_decision_hash"] != verification["decision_hash"]
            or snapshot["api_source_hash"] != verification["input_provenance"]["api_source_hash"]
            or snapshot["tcx_xml_sha256"] != verification["input_provenance"]["tcx_xml_sha256"]
            or snapshot["source_file_sha256"]
            != verification["input_provenance"]["source_file_sha256"]
            or snapshot["exercise_external_id"] != verification["exercise_external_id"]
        ):
            return False
        if exercise_external_id is not None and snapshot["exercise_external_id"] != _id(
            exercise_external_id
        ):
            return False
        return verify_tcx_heart_rate_timebase_evidence(
            verification,
            sample_session,
            expected_session_external_id=session_external_id,
            sample_session_match_count=sample_session_match_count,
            expected_exercise_external_id=snapshot["exercise_external_id"],
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def resolve_hr_timebase_snapshots(
    records,
    sample_session,
    *,
    athlete_id,
    session_external_id,
    sample_session_match_count,
):
    """Reject corrupt, stale or conflicting records; never choose the latest clock."""
    result = {
        "status": "NOT_PROVIDED",
        "provided_record_count": 0,
        "verified_exercise_count": 0,
        "rejected_record_count": 0,
        "blocking_reasons": [],
        "by_exercise": {},
    }
    if records is None or records == []:
        return result
    if not isinstance(records, list) or len(records) > MAX_CURRENT_SNAPSHOTS:
        result.update(
            status="WITHHELD", blocking_reasons=["SAVED_TIMEBASE_RECORD_LIMIT_OR_SHAPE_INVALID"]
        )
        return result
    result["provided_record_count"] = len(records)
    valid = []
    for record in records:
        snapshot = record.get("snapshot") if isinstance(record, Mapping) else None
        if not verify_hr_timebase_snapshot(
            snapshot,
            sample_session,
            athlete_id=athlete_id,
            session_external_id=session_external_id,
            sample_session_match_count=sample_session_match_count,
        ):
            result["rejected_record_count"] += 1
            continue
        if not _columns_match(record, snapshot):
            result["rejected_record_count"] += 1
            continue
        valid.append(record)
    if result["rejected_record_count"]:
        result.update(
            status="WITHHELD", blocking_reasons=["SAVED_TIMEBASE_RECORD_INVALID_OR_SOURCE_CHANGED"]
        )
        return result
    grouped = {}
    for record in valid:
        grouped.setdefault(record["snapshot"]["exercise_external_id"], []).append(record)
    for identity, group in grouped.items():
        hashes = {_hash(record["snapshot"]["verification"]["timebase"]) for record in group}
        if len(hashes) != 1:
            result["by_exercise"][identity] = {
                "status": "WITHHELD",
                "export_timebase_verified": False,
                "blocking_reasons": ["SAVED_TIMEBASE_CURRENT_SOURCE_CONFLICT"],
            }
            continue
        chosen = min(group, key=lambda record: record["snapshot"]["snapshot_hash"])
        result["by_exercise"][identity] = {
            "status": "VERIFIED_SAVED_EXPORT_TIMEBASE",
            "export_timebase_verified": True,
            "snapshot_id": chosen["snapshot_id"],
            "snapshot_hash": chosen["snapshot"]["snapshot_hash"],
            "verification_decision_hash": chosen["snapshot"]["verification_decision_hash"],
            "equivalent_snapshot_count": len(group),
            "timebase": deepcopy(chosen["snapshot"]["verification"]["timebase"]),
            "blocking_reasons": [],
        }
    result["verified_exercise_count"] = sum(
        e["export_timebase_verified"] for e in result["by_exercise"].values()
    )
    result["status"] = (
        "VERIFIED_WITH_LIMITATIONS" if result["verified_exercise_count"] else "WITHHELD"
    )
    return result


def current_hr_source_hash(sample_session, *, session_external_id, sample_session_match_count):
    validation = build_training_session_heart_rate_validation(
        sample_session,
        expected_session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    return None if validation["blocking_reasons"] else validation["input_provenance"]["source_hash"]


def _columns_match(record, snapshot):
    columns = record.get("column_identity")
    if not isinstance(columns, Mapping) or _id(record.get("snapshot_id")) is None:
        return False
    return all(
        columns.get(key) == snapshot[key]
        for key in (
            "athlete_id",
            "source_provider",
            "session_external_id",
            "exercise_external_id",
            "api_source_hash",
            "verification_decision_hash",
            "snapshot_hash",
        )
    )


def _id(value):
    return (
        str(value)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip()
        else None
    )


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()
