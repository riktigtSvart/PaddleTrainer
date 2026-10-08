"""Explicit session-level split assignments; no automatic partition or storage."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any

SPLITS = ("TRAIN", "VALIDATION", "TEST")
MAX_ASSIGNMENTS = 10000


def session_group_key(athlete_id: str, session_external_id: str) -> str:
    return _hash(["POLAR", athlete_id, session_external_id])


def validate_split_manifest(manifest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if manifest is None:
        return None
    if not isinstance(manifest, Mapping) or set(manifest) != {
        "schema_version",
        "manifest_id",
        "assignments",
    }:
        raise ValueError("Split manifest requires schema_version, manifest_id and assignments only")
    if manifest["schema_version"] != "0.1":
        raise ValueError("Unsupported split manifest schema_version")
    _text(manifest["manifest_id"], "manifest_id")
    entries = manifest["assignments"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ASSIGNMENTS:
        raise ValueError(f"assignments must contain 1 to {MAX_ASSIGNMENTS} whole sessions")
    normalized, groups = [], set()
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "provider",
            "athlete_id",
            "session_external_id",
            "split",
        }:
            raise ValueError("Split assignments must select whole athlete/provider sessions only")
        if entry["provider"] != "POLAR" or entry["split"] not in SPLITS:
            raise ValueError("Split assignment requires POLAR and TRAIN, VALIDATION or TEST")
        owner = _text(entry["athlete_id"], "athlete_id")
        session = _text(entry["session_external_id"], "session_external_id")
        group = session_group_key(owner, session)
        if group in groups:
            raise ValueError("Duplicate or conflicting assignment for one session group")
        groups.add(group)
        normalized.append(dict(entry))
    normalized.sort(key=lambda entry: (entry["athlete_id"], entry["session_external_id"]))
    return {
        "schema_version": "0.1",
        "manifest_id": manifest["manifest_id"],
        "assignments": normalized,
    }


def resolve_dataset_split(
    manifest: Mapping[str, Any] | None,
    *,
    athlete_id: str | None,
    session_external_id: str | None,
) -> dict[str, Any]:
    normalized = validate_split_manifest(manifest)
    assignment = (
        next(
            (
                entry
                for entry in normalized["assignments"]
                if entry["athlete_id"] == athlete_id
                and entry["session_external_id"] == session_external_id
            ),
            None,
        )
        if normalized
        else None
    )
    group = (
        session_group_key(athlete_id, session_external_id)
        if athlete_id and session_external_id
        else None
    )
    return {
        "schema_version": "0.1",
        "grouping_unit": "ATHLETE_PROVIDER_SESSION",
        "session_group_key": group,
        "status": "ASSIGNED" if assignment else "UNASSIGNED",
        "split": assignment["split"] if assignment else None,
        "manifest_id": normalized["manifest_id"] if normalized else None,
        "manifest_hash": _hash(normalized) if normalized else None,
        "assignment_source": "EXPLICIT_REQUEST_MANIFEST" if assignment else None,
        "assignment_persisted": False,
        "all_routes_exercises_history_and_labels_share_assignment": True,
        "verified_scope": "THIS_SESSION_WITHIN_PROVIDED_MANIFEST",
        "chronological_cohort_order_verified": False,
        "independence_between_sessions_verified": False,
        "unseen_athlete_generalization_verified": False,
        "preprocessing_fitted": False,
        "preprocessing_fit_scope_required": "TRAIN_ONLY",
        "training_authorized": False,
        "blocking_reasons": [] if assignment else ["DATASET_SPLIT_NOT_ASSIGNED"],
    }


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or value != value.strip():
        raise ValueError(f"{field} must be a nonempty, trimmed string of at most 200 characters")
    return value


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
