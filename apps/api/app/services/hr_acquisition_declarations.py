"""Resolve source-bound user statements without certifying sensor accuracy.

Recording-device metadata and user-declared HR acquisition are distinct sources.
Only explicit predecessor IDs retire statements; timestamps never choose a winner.
"""

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from uuid import UUID

from app.schemas.hr_acquisition import HRAcquisitionDeclarationCreate
from app.services.hr_timebase_snapshot import current_hr_source_hash

DECLARATION_VERSION = "0.1.0"
MAX_DECLARATIONS = 512
QUALITY_LIMITATIONS = [
    "HR_SENSOR_IDENTITY_NOT_ESTABLISHED",
    "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED",
]


class HRAcquisitionDeclarationError(ValueError):
    """A stable public code, without database or upstream credential details."""


def build_hr_acquisition_declaration(
    payload, sample_session, *, athlete_id, session_external_id, sample_session_match_count
):
    request = HRAcquisitionDeclarationCreate.model_validate(payload)
    owner, identity = _id(athlete_id), _id(session_external_id)
    source_hash = current_hr_source_hash(
        sample_session,
        session_external_id=identity,
        sample_session_match_count=sample_session_match_count,
    )
    if owner is None or identity is None or source_hash is None:
        raise HRAcquisitionDeclarationError("HR_ACQUISITION_SOURCE_BINDING_UNVERIFIABLE")
    exercises = sample_session.get("exercises", [])
    if sum(_exercise_id(e) == request.exercise_external_id for e in exercises) != 1:
        raise HRAcquisitionDeclarationError("HR_ACQUISITION_EXERCISE_MISSING_OR_AMBIGUOUS")
    statement = request.model_dump(mode="json")
    statement.pop("exercise_external_id")
    predecessors = statement.pop("supersedes_declaration_ids")
    result = {
        "schema_version": "0.1",
        "declaration_version": DECLARATION_VERSION,
        "declaration_kind": "HR_SENSOR_USER_DECLARATION",
        "source_provider": "POLAR",
        "source_kind": "USER_DECLARATION",
        "athlete_id": owner,
        "session_external_id": identity,
        "exercise_external_id": request.exercise_external_id,
        "api_source_hash": source_hash,
        "statement": statement,
        "supersedes_declaration_ids": predecessors,
        "sensor_identity_verified": False,
        "acquisition_quality_verified": False,
        "training_authorized": False,
        "numeric_prediction_authorized": False,
    }
    result["declaration_hash"] = _hash(result)
    return result


def verify_hr_acquisition_declaration(
    declaration, sample_session, *, athlete_id, session_external_id, sample_session_match_count
):
    try:
        if not isinstance(declaration, Mapping):
            return False
        payload = {
            **declaration["statement"],
            "exercise_external_id": declaration["exercise_external_id"],
            "supersedes_declaration_ids": declaration["supersedes_declaration_ids"],
        }
        return dict(declaration) == build_hr_acquisition_declaration(
            payload,
            sample_session,
            athlete_id=athlete_id,
            session_external_id=session_external_id,
            sample_session_match_count=sample_session_match_count,
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def resolve_hr_acquisition_declarations(
    records, sample_session, *, athlete_id, session_external_id, sample_session_match_count
):
    source_hash = current_hr_source_hash(
        sample_session,
        session_external_id=session_external_id,
        sample_session_match_count=sample_session_match_count,
    )
    product = sample_session.get("product", {}) if isinstance(sample_session, Mapping) else {}
    product = product.get("modelName") if isinstance(product, Mapping) else None
    exercises = sample_session.get("exercises", []) if isinstance(sample_session, Mapping) else []
    exercises = exercises if isinstance(exercises, list) else []
    ids = list(dict.fromkeys(_exercise_id(e) for e in exercises if _exercise_id(e) is not None))
    result = {
        "schema_version": "0.1",
        "acquisition_context_version": DECLARATION_VERSION,
        "status": "NOT_DECLARED",
        "source_binding_verified": source_hash is not None and _id(athlete_id) is not None,
        "current_api_source_hash": source_hash,
        "recording_product_model_name": product if isinstance(product, str) else None,
        "recording_product_source": "PROVIDER_RECORDING_DEVICE_METADATA",
        "provided_record_count": len(records) if isinstance(records, list) else 0,
        "declared_exercise_count": 0,
        "review_required_exercise_count": 0,
        "rejected_record_count": 0,
        "sensor_identity_verified": False,
        "acquisition_quality_verified": False,
        "training_authorized": False,
        "numeric_prediction_authorized": False,
        "blocking_reasons": [],
        "limitations": list(QUALITY_LIMITATIONS),
        "policy": {
            "scope": "ATHLETE_PROVIDER_SESSION_EXERCISE_CURRENT_API_SOURCE",
            "recording_product_infers_hr_sensor": False,
            "user_statement_certifies_measurement_accuracy": False,
            "latest_record_wins": False,
            "explicit_correction_preserves_prior_statements": True,
            "reported_issues_require_preparation_review": True,
            "missing_issue_reports_certify_signal_quality": False,
            "modifies_raw_samples_or_export_timebase": False,
        },
        "by_exercise": {identity: _empty_context(identity) for identity in ids},
    }
    if not result["source_binding_verified"]:
        return _finish(result, "WITHHELD", "HR_ACQUISITION_SOURCE_BINDING_UNVERIFIABLE")
    if records is None:
        records = []
    if not isinstance(records, list) or len(records) > MAX_DECLARATIONS:
        return _finish(result, "WITHHELD", "HR_ACQUISITION_RECORD_LIMIT_OR_SHAPE_INVALID")
    valid = []
    seen = set()
    for record in records:
        declaration = record.get("declaration") if isinstance(record, Mapping) else None
        identity = record.get("declaration_id") if isinstance(record, Mapping) else None
        if (
            _uuid(identity) is None
            or identity in seen
            or not verify_hr_acquisition_declaration(
                declaration,
                sample_session,
                athlete_id=athlete_id,
                session_external_id=session_external_id,
                sample_session_match_count=sample_session_match_count,
            )
            or not _columns_match(record, declaration)
        ):
            result["rejected_record_count"] += 1
        else:
            seen.add(identity)
            valid.append(record)
    if result["rejected_record_count"]:
        return _finish(result, "WITHHELD", "HR_ACQUISITION_RECORD_INVALID_OR_SOURCE_CHANGED")
    grouped = {}
    for record in valid:
        grouped.setdefault(record["declaration"]["exercise_external_id"], []).append(record)
    for identity, group in grouped.items():
        context = result["by_exercise"][identity]
        nodes = {record["declaration_id"]: record for record in group}
        graph = {
            key: record["declaration"]["supersedes_declaration_ids"]
            for key, record in nodes.items()
        }
        if not _valid_graph(graph):
            context.update(
                status="REVIEW_REQUIRED",
                blocking_reasons=["HR_ACQUISITION_CORRECTION_LINEAGE_INVALID"],
            )
            result["review_required_exercise_count"] += 1
            continue
        retired = {parent for parents in graph.values() for parent in parents}
        active = sorted(set(nodes) - retired)
        context["active_declaration_ids"] = active
        statements = {_hash(nodes[key]["declaration"]["statement"]) for key in active}
        if len(statements) != 1:
            context.update(
                status="REVIEW_REQUIRED",
                blocking_reasons=["HR_ACQUISITION_CONFLICTING_USER_DECLARATIONS"],
            )
            result["review_required_exercise_count"] += 1
            continue
        chosen = nodes[active[0]]["declaration"]
        statement = deepcopy(chosen["statement"])
        issues = statement.pop("reported_issue_codes")
        context.update(
            status="USER_DECLARED_WITH_LIMITATIONS",
            source_binding_verified=True,
            declaration_source="USER_DECLARATION",
            declared_sensor=statement,
            reported_issue_codes=issues,
            declaration_hashes=[nodes[key]["declaration"]["declaration_hash"] for key in active],
            limitations=[
                *QUALITY_LIMITATIONS,
                "HR_SENSOR_DETAILS_USER_DECLARED_NOT_PROVIDER_VERIFIED",
            ],
        )
        if issues:
            context["blocking_reasons"] = ["HR_USER_REPORTED_ACQUISITION_ISSUES_REQUIRE_REVIEW"]
            context["limitations"].append(
                "HR_USER_REPORTED_ISSUES_ARE_NOT_VALIDATED_ARTIFACT_DETECTION"
            )
            result["review_required_exercise_count"] += 1
        result["declared_exercise_count"] += 1
    status = (
        "REVIEW_REQUIRED"
        if result["review_required_exercise_count"]
        else "USER_DECLARED_WITH_LIMITATIONS"
        if result["declared_exercise_count"]
        else "NOT_DECLARED"
    )
    return _finish(result, status)


def acquisition_declaration_history(records):
    """Return user statements and lineage, never raw provider samples or GPS."""
    return [
        {
            "declaration_id": record["declaration_id"],
            "recorded_at_utc": record.get("recorded_at_utc"),
            "exercise_external_id": record["declaration"]["exercise_external_id"],
            "declaration_hash": record["declaration"]["declaration_hash"],
            "source_kind": record["declaration"]["source_kind"],
            "statement": deepcopy(record["declaration"]["statement"]),
            "supersedes_declaration_ids": record["declaration"]["supersedes_declaration_ids"],
        }
        for record in records
    ]


def _empty_context(identity):
    return {
        "exercise_external_id": identity,
        "status": "NOT_DECLARED",
        "source_binding_verified": False,
        "declaration_source": None,
        "declared_sensor": None,
        "active_declaration_ids": [],
        "declaration_hashes": [],
        "reported_issue_codes": [],
        "sensor_identity_verified": False,
        "acquisition_quality_verified": False,
        "blocking_reasons": [],
        "limitations": list(QUALITY_LIMITATIONS),
    }


def _finish(result, status, reason=None):
    result["status"] = status
    if reason:
        result["blocking_reasons"] = [reason]
        for context in result["by_exercise"].values():
            context.update(status="WITHHELD", blocking_reasons=[reason])
    result["exercises"] = list(result["by_exercise"].values())
    result["decision_hash"] = _hash(result)
    return result


def _valid_graph(graph):
    if any(parent not in graph for parents in graph.values() for parent in parents):
        return False
    dependencies = {key: len(parents) for key, parents in graph.items()}
    children = {key: [] for key in graph}
    for key, parents in graph.items():
        for parent in parents:
            children[parent].append(key)
    ready = [key for key, count in dependencies.items() if count == 0]
    processed = 0
    while ready:
        parent = ready.pop()
        processed += 1
        for child in children[parent]:
            dependencies[child] -= 1
            if dependencies[child] == 0:
                ready.append(child)
    return processed == len(graph)


def _columns_match(record, declaration):
    return record.get("column_identity") == {
        key: declaration[key]
        for key in (
            "athlete_id",
            "source_provider",
            "session_external_id",
            "exercise_external_id",
            "api_source_hash",
            "declaration_hash",
        )
    }


def _uuid(value):
    try:
        return str(UUID(value)) if isinstance(value, str) and str(UUID(value)) == value else None
    except (ValueError, TypeError, AttributeError):
        return None


def _id(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    value = str(value).strip()
    return value if value and len(value) <= 200 else None


def _exercise_id(exercise):
    identifier = exercise.get("identifier") if isinstance(exercise, Mapping) else None
    return _id(identifier.get("id")) if isinstance(identifier, Mapping) else None


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
