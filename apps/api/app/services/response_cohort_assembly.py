"""Verify selected real sources sequentially, then commit a compact cohort index."""

import asyncio
from collections import Counter
from datetime import date, timedelta
from time import monotonic
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.integrations.polar.client import PolarAPIError, PolarClient
from app.models.entities import ExternalConnection, RouteEnvironmentEvidenceSet, WorkoutSession
from app.models.environment_replay_snapshot import EnvironmentReplaySnapshot
from app.schemas.response_cohort import ResponseCohortManifest
from app.services.environment_replay_persistence import load_environment_replay_snapshot
from app.services.environment_replay_snapshot import (
    MAX_CAPTURE_BYTES,
    canonical_hash,
    replay_environment_dataset,
)
from app.services.hr_acquisition_persistence import load_current_hr_acquisition_declarations
from app.services.hr_timebase_persistence import load_current_hr_timebase_snapshots
from app.services.polar_tokens import get_valid_access_token
from app.services.response_cohort_temporal import (
    MAX_TEMPORAL_EXERCISES,
    audit_cohort_temporal_metadata,
    build_session_temporal_evidence,
)
from app.services.response_dataset_integrity import (
    MAX_DATASET_BYTES,
    MAX_HR_SLOTS,
    MAX_OBSERVATIONS,
    MAX_ROUTES,
    check_response_dataset_integrity,
    require_json_size,
)
from app.services.response_dataset_split import resolve_dataset_split

MAX_EXECUTION_MEMBERS = 20
MAX_ASSEMBLY_SECONDS = 120
MAX_CURRENT_SESSION_BYTES = 16 * 1024 * 1024
MAX_INDEX_BYTES = 1024 * 1024
VERIFIED_REPLAY_SCOPE = "VERIFIED_SAVED_ENVIRONMENT_WITH_CURRENT_POLAR_SOURCE_AND_PINNED_HR_PROOFS"

# Only fixed codes from trusted verifiers may enter a public diagnostic.
UPSTREAM_CODES = frozenset(
    {
        "REPLAY_CURRENT_POLAR_SOURCE_CHANGED",
        "REPLAY_HR_PROOF_STATE_CHANGED",
        "REPLAY_DATASET_IMPLEMENTATION_OR_INPUT_CHANGED",
        "REPLAY_SNAPSHOT_INTEGRITY_FAILED",
        "REPLAY_STORED_SNAPSHOT_BINDING_FAILED",
        "REPLAY_DATABASE_OWNER_OR_SESSION_MISMATCH",
        "REPLAY_DATABASE_EVIDENCE_HASH_MISMATCH",
        "REPLAY_DATABASE_EVIDENCE_METADATA_MISMATCH",
        "REPLAY_DATABASE_MEASUREMENT_SET_MISMATCH",
        "REPLAY_DATABASE_MEASUREMENT_VALUE_MISMATCH",
        "REPLAY_DATABASE_ROUTE_SET_MISMATCH",
        "REPLAY_DATABASE_ROUTE_METADATA_MISMATCH",
        "REPLAY_DATABASE_SEGMENT_SET_MISMATCH",
        "REPLAY_DATABASE_SEGMENT_VALUE_MISMATCH",
        "REPLAY_DATABASE_SEGMENT_ROUTE_LINK_MISMATCH",
        "REPLAY_DATABASE_MEASUREMENT_LINK_MISMATCH",
        "REPLAY_DATABASE_LINEAGE_MISSING_OR_CHANGED",
        "REPLAY_LINEAGE_INTEGRITY_FAILED",
        "DATASET_FULL_PAYLOAD_REQUIRED",
        "DATASET_VERSION_UNSUPPORTED",
        "DATASET_PAYLOAD_HASH_MISMATCH",
        "DATASET_INTERNAL_REFERENCES_INVALID",
        "DATASET_UNEXPECTED_AUTHORIZATION",
        "DATASET_UNEXPECTED_TRANSFORMATION",
        "DATASET_EXECUTION_SIZE_LIMIT",
    }
)


class CohortVerificationError(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise CohortVerificationError(code)


def _deadline(start):
    _require(monotonic() - start < MAX_ASSEMBLY_SECONDS, "COHORT_EXECUTION_TIME_LIMIT")


async def _selected_metadata(db, user_id, member):
    """All owner/session joins and pins are checked before any Polar calls."""
    row = (
        await db.execute(
            select(
                EnvironmentReplaySnapshot.id,
                EnvironmentReplaySnapshot.snapshot_hash,
                EnvironmentReplaySnapshot.snapshot_schema_version,
                EnvironmentReplaySnapshot.evidence_set_id,
                RouteEnvironmentEvidenceSet.evidence_hash,
            )
            .join(WorkoutSession, WorkoutSession.id == EnvironmentReplaySnapshot.workout_session_id)
            .join(
                RouteEnvironmentEvidenceSet,
                RouteEnvironmentEvidenceSet.id == EnvironmentReplaySnapshot.evidence_set_id,
            )
            .where(
                EnvironmentReplaySnapshot.id == UUID(member.replay_snapshot_id),
                EnvironmentReplaySnapshot.user_id == user_id,
                WorkoutSession.user_id == user_id,
                WorkoutSession.external_provider == member.provider,
                WorkoutSession.external_id == member.session_external_id,
                RouteEnvironmentEvidenceSet.user_id == user_id,
                RouteEnvironmentEvidenceSet.workout_session_id == WorkoutSession.id,
                RouteEnvironmentEvidenceSet.provider == member.provider,
                RouteEnvironmentEvidenceSet.session_external_id == member.session_external_id,
            )
        )
    ).one_or_none()
    _require(row is not None, "COHORT_SNAPSHOT_NOT_FOUND_OR_NOT_OWNED")
    _require(row.snapshot_hash == member.expected_snapshot_hash, "COHORT_SNAPSHOT_PIN_MISMATCH")
    _require(
        row.snapshot_schema_version == member.expected_snapshot_schema_version,
        "COHORT_SNAPSHOT_VERSION_MISMATCH",
    )
    _require(
        str(row.evidence_set_id) == member.expected_evidence_set_id
        and row.evidence_hash == member.expected_evidence_hash,
        "COHORT_ENVIRONMENT_PIN_MISMATCH",
    )


async def _current_session(client, token, member, feature):
    day = date.fromisoformat(member.route_date)
    result = await client.list_training_sessions(
        token, day, day + timedelta(days=1), features=[feature]
    )
    _require(
        isinstance(result, dict) and isinstance(result.get("trainingSessions"), list),
        "COHORT_CURRENT_SOURCE_PAYLOAD_INVALID",
    )
    matches = [
        item
        for item in result["trainingSessions"]
        if isinstance(item, dict)
        and isinstance(item.get("identifier"), dict)
        and str(item["identifier"].get("id")) == member.session_external_id
    ]
    _require(bool(matches), "COHORT_CURRENT_SOURCE_SESSION_MISSING")
    _require(len(matches) == 1, "COHORT_CURRENT_SOURCE_SESSION_AMBIGUOUS")
    require_json_size(matches[0], MAX_CURRENT_SESSION_BYTES, "COHORT_CURRENT_SOURCE_SIZE_LIMIT")
    return matches[0]


async def _member_index(
    db, user_id, member, split_manifest, client, token, start, *, verify_chronology=False
):
    saved = await load_environment_replay_snapshot(
        db,
        user_id=user_id,
        session_external_id=member.session_external_id,
        snapshot_id=member.replay_snapshot_id,
    )
    _require(saved is not None, "COHORT_SNAPSHOT_NOT_FOUND_OR_NOT_OWNED")
    await _selected_metadata(db, user_id, member)  # Recheck pins after preflight.
    snapshot = saved.snapshot_json
    require_json_size(snapshot, MAX_CAPTURE_BYTES, "COHORT_SNAPSHOT_SIZE_LIMIT")
    _deadline(start)
    route = await _current_session(client, token, member, "routes")
    sample = await _current_session(client, token, member, "samples")
    kwargs = {
        "athlete_id": str(user_id),
        "session_external_id": member.session_external_id,
        "sample_session_match_count": 1,
    }
    clocks = await load_current_hr_timebase_snapshots(db, sample, **kwargs)
    declarations = await load_current_hr_acquisition_declarations(db, sample, **kwargs)
    _deadline(start)
    dataset = replay_environment_dataset(
        snapshot,
        snapshot_id=saved.id,
        athlete_id=user_id,
        session_external_id=member.session_external_id,
        route_session=route,
        sample_session=sample,
        clocks=clocks,
        declarations=declarations,
        split_manifest=None,
    )
    # As in V24.9, promotion follows the actual DB verifier, never a JSON claim.
    dataset["input_provenance"].update(
        database_environment_replay_verified=True, scope=VERIFIED_REPLAY_SCOPE
    )
    dataset["package_hash"] = canonical_hash(
        {key: value for key, value in dataset.items() if key != "package_hash"}
    )
    _require(
        dataset["dataset_version"] == member.expected_dataset_version,
        "COHORT_DATASET_VERSION_MISMATCH",
    )
    _require(
        dataset["athlete_id"] == str(user_id)
        and dataset["session_external_id"] == member.session_external_id,
        "COHORT_DATASET_OWNER_OR_SESSION_MISMATCH",
    )
    _require(
        dataset["status"] == "OBSERVATION_PACKAGE_WITH_LIMITATIONS"
        and not dataset["blocking_reasons"],
        "COHORT_DATASET_WITHHELD",
    )
    _require(
        dataset["split_assignment"]["status"] == "UNASSIGNED"
        and dataset["split_assignment"]["split"] is None,
        "COHORT_UNASSIGNED_BASE_REQUIRED",
    )
    integrity = check_response_dataset_integrity(dataset)
    _require(
        dataset["package_hash"] == member.expected_unassigned_replay_package_hash,
        "COHORT_REPLAY_PACKAGE_PIN_MISMATCH",
    )
    _deadline(start)
    sequences = [s for r in dataset["routes"] for s in r["sequences"]]
    result = {
        "status": "SOURCE_VERIFIED_WITH_LIMITATIONS",
        "provider": member.provider,
        "athlete_id": str(user_id),
        "session_external_id": member.session_external_id,
        "session_group_key": dataset["session_group_key"],
        "replay_snapshot_id": str(saved.id),
        "snapshot_hash": snapshot["snapshot_hash"],
        "snapshot_schema_version": snapshot["snapshot_schema_version"],
        "evidence_set_id": snapshot["evidence_set_id"],
        "evidence_hash": snapshot["evidence_hash"],
        "dataset_version": dataset["dataset_version"],
        "unassigned_replay_package_hash": dataset["package_hash"],
        "source_commitments": {
            field: snapshot[field]
            for field in ("route_source_hash", "sample_source_hash", "hr_proof_state_hash")
        },
        "source_evidence_verified": True,
        "database_environment_evidence_verified": True,
        "current_polar_source_verified": True,
        "pinned_hr_proof_state_verified": True,
        "payload_integrity_verified": True,
        "internal_references_verified": True,
        "full_member_payload_in_index": False,
        "base_split_status": "UNASSIGNED",
        "requested_split": resolve_dataset_split(
            split_manifest, athlete_id=str(user_id), session_external_id=member.session_external_id
        ),
        "counts": {
            field: dataset[field]
            for field in (
                "observation_count",
                "source_observation_count",
                "route_count",
                "hr_stream_count",
                "hr_slot_count",
                "complete_hr_window_count",
                "preparation_candidate_count",
                "excluded_observation_count",
            )
        },
        "feature_status_counts": dataset["feature_status_counts"],
        "hr_window_status_counts": integrity["hr_window_status_counts"],
        "history_summary": {
            "sequence_count": len(sequences),
            "supported_workload_observation_count": sum(
                r["supported_workload_observation_count"] for r in dataset["routes"]
            ),
            "unknown_initial_state_sequence_count": len(sequences),
            "pre_observation_censored_sequence_count": len(sequences),
            "post_observation_censored_sequence_count": len(sequences),
        },
        "temporal_evidence": {
            "session_interval_status": "NOT_EVALUATED_IN_V24_10_B",
            "route_exercise_starts_utc": [
                {
                    "route_index": r["route_index"],
                    "exercise_index": r["exercise_index"],
                    "exercise_start_utc": r["exercise_start_utc"],
                }
                for r in dataset["routes"]
            ],
            "route_date_used_as_chronological_evidence": False,
        },
        "training_blocking_reasons": dataset["training_blocking_reasons"],
    }
    if verify_chronology:
        result["temporal_evidence"] = build_session_temporal_evidence(route, sample)
        result["temporal_evidence"]["binding_scope"] = (
            "ACTUALLY_VERIFIED_CURRENT_POLAR_SOURCES_AND_PINNED_UNASSIGNED_REPLAY"
        )
        result["temporal_evidence"]["temporal_evidence_hash"] = canonical_hash(
            {k: v for k, v in result["temporal_evidence"].items() if k != "temporal_evidence_hash"}
        )
    # Only small references and counts escape this scope; full arrays remain in the member package.
    return result


def _base(manifest):
    return {
        "schema_version": "0.1",
        "assembly_version": "0.1.0",
        "task": manifest.task,
        "manifest_id": manifest.manifest_id,
        "request_manifest_hash": manifest.request_manifest_hash(),
        "requested_member_count": len(manifest.members),
        "chronological_cohort_order_verified": False,
        "split_assignment_persisted": False,
        "independence_between_sessions_verified": False,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "pre_exercise_prediction_authorized": False,
        "causal_prediction_authorized": False,
        "environmental_provider_calls": 0,
        "science_storage_writes": 0,
        "policy": {
            "members_processed_sequentially": True,
            "full_member_payloads_copied": False,
            "failed_members_silently_omitted": False,
            "snapshot_fallback_performed": False,
            "fixed_hr_shift_applied": False,
            "physiological_lag_ms": None,
            "feature_fit_performed": False,
            "feature_missing_values_imputed": False,
            "source_checks_are_per_member_during_assembly": True,
            "sensor_identity_or_acquisition_quality_promoted": False,
        },
        "execution_limits": {
            "max_members": MAX_EXECUTION_MEMBERS,
            "max_assembly_seconds": MAX_ASSEMBLY_SECONDS,
            "max_snapshot_bytes": MAX_CAPTURE_BYTES,
            "max_current_session_bytes": MAX_CURRENT_SESSION_BYTES,
            "max_dataset_bytes": MAX_DATASET_BYTES,
            "max_observations_per_member": MAX_OBSERVATIONS,
            "max_hr_slots_per_member": MAX_HR_SLOTS,
            "max_routes_per_member": MAX_ROUTES,
            "max_index_bytes": MAX_INDEX_BYTES,
        },
    }


async def assemble_response_cohort(db, manifest, *, user_id, verify_chronology=False):
    """user_id is supplied by trusted server/local auth, never selected by the manifest.

    No environmental provider calls or scientific writes. The existing Polar
    credential service may refresh and persist the owner's authentication token.
    """
    manifest = ResponseCohortManifest.model_validate(
        manifest.model_dump(mode="json")
        if isinstance(manifest, ResponseCohortManifest)
        else manifest
    )
    base = _base(manifest)
    if verify_chronology:
        base.update(assembly_version="0.2.0", chronological_split_verified=False)
        base["execution_limits"]["max_temporal_exercises_per_member"] = MAX_TEMPORAL_EXERCISES
        base["policy"]["declared_whole_session_chronology_evaluated"] = True
    started = monotonic()
    failing_member = None
    try:
        _require(len(manifest.members) <= MAX_EXECUTION_MEMBERS, "COHORT_MEMBER_EXECUTION_LIMIT")
        user_id = UUID(str(user_id))
        _require(
            all(m.athlete_id == str(user_id) for m in manifest.members), "COHORT_OWNER_MISMATCH"
        )
        async with asyncio.timeout(MAX_ASSEMBLY_SECONDS):
            connection = (
                await db.execute(
                    select(ExternalConnection).where(
                        ExternalConnection.user_id == user_id,
                        ExternalConnection.provider == "POLAR",
                    )
                )
            ).scalar_one_or_none()
            _require(connection is not None, "COHORT_POLAR_CONNECTION_REQUIRED")
            _require(
                "training_sessions:read" in (connection.scopes or []), "COHORT_POLAR_SCOPE_REQUIRED"
            )
            normalized = manifest.canonical_payload()
            members = [type(manifest.members[0]).model_validate(m) for m in normalized["members"]]
            for position, member in enumerate(members):
                failing_member = position
                await _selected_metadata(db, user_id, member)
                _deadline(started)
            failing_member = None
            token = await get_valid_access_token(db, connection)
            _require(
                "training_sessions:read" in (connection.scopes or []), "COHORT_POLAR_SCOPE_REQUIRED"
            )
            client = PolarClient()
            verified = []
            for position, member in enumerate(members):
                failing_member = position
                verified.append(
                    await _member_index(
                        db,
                        user_id,
                        member,
                        normalized["split_manifest"],
                        client,
                        token,
                        started,
                        verify_chronology=verify_chronology,
                    )
                )
                _deadline(started)
            result = {
                **base,
                "status": "SOURCE_VERIFIED_COHORT_INDEX_WITH_LIMITATIONS",
                "claim_scope": "SELECTED_MEMBER_SOURCE_BINDING_AND_PAYLOAD_INTEGRITY_ONLY",
                "source_evidence_verified": True,
                "verified_member_count": len(verified),
                "member_order": "CANONICAL_SESSION_IDENTITY_NOT_CHRONOLOGICAL",
                "members": verified,
                "totals": {
                    key: sum(m["counts"][key] for m in verified) for key in verified[0]["counts"]
                },
                "requested_split_counts": dict(
                    sorted(
                        Counter(
                            m["requested_split"]["split"] or "UNASSIGNED" for m in verified
                        ).items()
                    )
                ),
                "blocking_reasons": [],
                "training_blocking_reasons": [
                    "COHORT_CHRONOLOGY_NOT_EVALUATED",
                    "COHORT_EVALUATION_SPLIT_NOT_VERIFIED",
                    "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED",
                    "RESPONSE_MODEL_NOT_CONFIGURED",
                ],
            }
            if verify_chronology:
                temporal = audit_cohort_temporal_metadata(verified)
                # The pure audit cannot promote source proof. This point is reached
                # only after every member passed the actual owner/DB/provider checks.
                result["temporal_audit"] = temporal
                result["chronological_cohort_order_verified"] = temporal[
                    "chronological_order_supported"
                ]
                result["chronological_split_verified"] = temporal["chronological_split_supported"]
                result["chronology_claim_scope"] = (
                    "ACTUALLY_SOURCE_BOUND_DECLARED_WALL_CLOCK_METADATA_ONLY"
                )
                result["training_blocking_reasons"] = list(
                    dict.fromkeys(
                        temporal["split_blocking_reasons"]
                        + [
                            "HR_ACQUISITION_QUALITY_NOT_ESTABLISHED",
                            "RESPONSE_MODEL_NOT_CONFIGURED",
                        ]
                    )
                )
            _deadline(started)
            result["cohort_index_hash"] = canonical_hash(result)
            require_json_size(result, MAX_INDEX_BYTES, "COHORT_INDEX_SIZE_LIMIT")
            return result
    except CohortVerificationError as exc:
        reason, upstream = str(exc), None
    except TimeoutError:
        reason, upstream = "COHORT_EXECUTION_TIME_LIMIT", None
    except (PolarAPIError, httpx.RequestError):
        reason, upstream = "COHORT_POLAR_SOURCE_REQUEST_FAILED", None
    except ValueError as exc:
        limits = {
            "COHORT_CURRENT_SOURCE_SIZE_LIMIT",
            "COHORT_SNAPSHOT_SIZE_LIMIT",
            "COHORT_INDEX_SIZE_LIMIT",
        }
        reason, upstream = (
            (str(exc), None)
            if str(exc) in limits
            else (
                "COHORT_MEMBER_EVIDENCE_VERIFICATION_FAILED",
                str(exc) if str(exc) in UPSTREAM_CODES else None,
            )
        )
    except (SQLAlchemyError, RuntimeError, OSError, KeyError, TypeError, AttributeError):
        # Do not echo DB URLs, raw payloads or secret-bearing provider exceptions.
        reason, upstream = "COHORT_DEPENDENCY_FAILURE", None
    failed = {
        **base,
        "status": "WITHHELD",
        "claim_scope": "NO_COHORT_SOURCE_PROOF_ISSUED",
        "source_evidence_verified": False,
        "verified_member_count": 0,
        "members": [],
        "totals": None,
        "cohort_index_hash": None,
        "blocking_reasons": [reason],
        "upstream_reason": upstream,
        "failed_member_canonical_index": failing_member,
    }
    if verify_chronology:
        failed["temporal_audit"] = None
    return failed


def verify_cohort_index_integrity(index):
    """Hash/internal consistency only; a caller's JSON is never source proof."""
    try:
        return (
            index["status"] == "SOURCE_VERIFIED_COHORT_INDEX_WITH_LIMITATIONS"
            and index["cohort_index_hash"]
            == canonical_hash({k: v for k, v in index.items() if k != "cohort_index_hash"})
            and len(index["members"])
            == index["verified_member_count"]
            == index["requested_member_count"]
            and all(
                index["totals"][key] == sum(m["counts"][key] for m in index["members"])
                for key in index["totals"]
            )
        )
    except (KeyError, TypeError, ValueError):
        return False
