"""Capture complete current-source inputs, not reconstructed legacy hash preimages."""

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime

from app.services.environment_evidence_persistence import build_environment_persistence_plan
from app.services.hydrology_relation_decision_snapshot import (
    verify_hydrology_relation_decision_snapshot,
)
from app.services.hydrology_trust_decision_snapshot import verify_hydrology_trust_decision_snapshot
from app.services.polar_training_samples import normalize_polar_training_samples
from app.services.route_hydrology_source_resolution_snapshot import (
    verify_route_hydrology_source_resolution_snapshot,
)
from app.services.route_response_dataset import build_route_response_dataset
from app.services.route_water_environment_identity_snapshot import (
    verify_route_water_environment_identity_snapshot,
)
from app.services.trusted_environment_context_snapshot import (
    build_trusted_route_environment_context_snapshot,
    verify_trusted_environment_context_snapshot,
)

SCHEMA_VERSION = "0.1"
MAX_CAPTURE_BYTES = 64 * 1024 * 1024
LINEAGE = {
    "water_identity": ("identity_hash", verify_route_water_environment_identity_snapshot),
    "hydrology_resolution": ("resolution_hash", verify_route_hydrology_source_resolution_snapshot),
    "hydrology_trust": ("decision_hash", verify_hydrology_trust_decision_snapshot),
    "hydrology_relation": ("relation_decision_hash", verify_hydrology_relation_decision_snapshot),
    "trusted_projection": ("projection_hash", verify_trusted_environment_context_snapshot),
}


def canonical_json(value):
    def default(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError("Noncanonical replay input")

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=default
    )


def canonical_hash(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def ordered_proofs(records):
    return sorted(deepcopy(records or []), key=canonical_hash)


def proof_state_hash(clocks, declarations):
    return canonical_hash(
        {"clocks": ordered_proofs(clocks), "declarations": ordered_proofs(declarations)}
    )


def build_environment_replay_snapshot(
    *,
    athlete_id,
    session_external_id,
    evidence_set_id,
    evidence_hash,
    evidence_record,
    expected_response_input,
    trusted_environment,
    provider_selection,
    weather_source,
    route_session,
    sample_session,
    sample_session_match_count,
    hr_timebase_snapshots,
    hr_acquisition_declarations,
    lineage,
):
    if set(lineage) != set(LINEAGE) or lineage["trusted_projection"] is None:
        raise ValueError("REPLAY_FULL_PROJECTION_LINEAGE_REQUIRED")
    for route in (trusted_environment or {}).get("routes", []):
        for segment in route.get("segments", []):
            if (
                segment.get("water_identity", {}).get("available") is True
                and lineage["water_identity"] is None
            ):
                raise ValueError("REPLAY_WATER_IDENTITY_LINEAGE_REQUIRED")
            if (
                segment.get("hydrology", {}).get("available") is True
                and lineage["hydrology_trust"] is None
                and lineage["hydrology_relation"] is None
            ):
                raise ValueError("REPLAY_HYDROLOGY_TRUST_LINEAGE_REQUIRED")
    plan = build_environment_persistence_plan(evidence_record)
    if (
        plan["evidence_hash"] != evidence_hash
        or plan["provider"] != "POLAR"
        or plan["session_external_id"] != session_external_id
    ):
        raise ValueError("REPLAY_ENVIRONMENT_EVIDENCE_BINDING_MISMATCH")
    for name, (field, verifier) in LINEAGE.items():
        value = lineage[name]
        if value is not None and not verifier(value):
            raise ValueError("REPLAY_INVALID_LINEAGE_" + name.upper())
        if (
            value is not None
            and name in ("hydrology_trust", "hydrology_relation", "trusted_projection")
            and (
                value["environment_evidence_set_id"] != str(evidence_set_id)
                or value["environment_evidence_hash"] != evidence_hash
            )
        ):
            raise ValueError("REPLAY_LINEAGE_EVIDENCE_BINDING_MISMATCH")
    expected_projection = build_trusted_route_environment_context_snapshot(
        environment_evidence_set_id=str(evidence_set_id),
        environment_evidence_hash=evidence_hash,
        route_water_environment_identity_snapshot=lineage["water_identity"],
        hydrology_trust_decision_snapshot=lineage["hydrology_trust"],
        hydrology_relation_decision_snapshot=lineage["hydrology_relation"],
        trusted_route_environment_context=trusted_environment,
    )
    if expected_projection != lineage["trusted_projection"]:
        raise ValueError("REPLAY_PROJECTION_PAYLOAD_MISMATCH")
    for name, plan_field in (
        ("water_identity", "water_environment_identity_hash"),
        ("hydrology_resolution", "hydrology_source_resolution_hash"),
    ):
        value = lineage[name]
        field = LINEAGE[name][0]
        if plan.get(plan_field) != (value[field] if value else None):
            raise ValueError("REPLAY_UPSTREAM_HASH_MISMATCH")
    resolution = lineage["hydrology_resolution"]
    for name in ("hydrology_trust", "hydrology_relation"):
        value = lineage[name]
        if value and value.get("hydrology_source_resolution_hash") != (
            resolution["resolution_hash"] if resolution else None
        ):
            raise ValueError("REPLAY_HYDROLOGY_RESOLUTION_LINEAGE_MISMATCH")
    for source in (route_session, sample_session):
        if (
            not isinstance(source, dict)
            or source.get("identifier", {}).get("id") != session_external_id
        ):
            raise ValueError("REPLAY_API_SESSION_BINDING_MISMATCH")
    if sample_session_match_count != 1:
        raise ValueError("REPLAY_API_SESSION_AMBIGUOUS")
    inputs = {
        "expected_response_input": deepcopy(expected_response_input),
        "trusted_environment": deepcopy(trusted_environment),
        "provider_selection": deepcopy(provider_selection),
        "weather_source": deepcopy(weather_source),
    }
    dataset = dataset_from_inputs(
        inputs,
        route_session=route_session,
        sample_session=sample_session,
        athlete_id=str(athlete_id),
        session_external_id=session_external_id,
        clocks=hr_timebase_snapshots,
        declarations=hr_acquisition_declarations,
    )
    if dataset["status"] != "OBSERVATION_PACKAGE_WITH_LIMITATIONS" or dataset["blocking_reasons"]:
        raise ValueError("REPLAY_DATASET_SOURCE_BINDING_UNVERIFIED")
    payload = {
        "snapshot_schema_version": SCHEMA_VERSION,
        "athlete_id": str(athlete_id),
        "session_external_id": session_external_id,
        "evidence_set_id": str(evidence_set_id),
        "evidence_hash": evidence_hash,
        "route_source_hash": canonical_hash(route_session),
        "sample_source_hash": canonical_hash(sample_session),
        "hr_proof_state_hash": proof_state_hash(hr_timebase_snapshots, hr_acquisition_declarations),
        "unassigned_dataset_package_hash": dataset["package_hash"],
        "evidence_record": deepcopy(evidence_record),
        "inputs": inputs,
        "lineage": deepcopy(lineage),
        "scope": {
            "domain": "PINNED_ENVIRONMENT_REPLAY_WITH_CURRENT_POLAR_SOURCE_CHECK",
            "stores_full_environment_inputs": True,
            "stores_raw_polar_hr_or_route_payload": False,
            "environmental_provider_refetch_required_for_replay": False,
            "current_polar_source_check_required": True,
            "training_authorized": False,
        },
    }
    encoded = canonical_json(payload)
    if len(encoded.encode()) > MAX_CAPTURE_BYTES:
        raise ValueError("REPLAY_CAPTURE_SIZE_LIMIT_EXCEEDED")
    # Freeze through JSON so the persisted bytes and reconstructed values agree.
    payload = json.loads(encoded)
    payload["snapshot_hash"] = canonical_hash(payload)
    return payload


def verify_environment_replay_snapshot(snapshot):
    try:
        required = {
            "snapshot_schema_version",
            "athlete_id",
            "session_external_id",
            "evidence_set_id",
            "evidence_hash",
            "route_source_hash",
            "sample_source_hash",
            "hr_proof_state_hash",
            "unassigned_dataset_package_hash",
            "evidence_record",
            "inputs",
            "lineage",
            "scope",
            "snapshot_hash",
        }
        return (
            isinstance(snapshot, dict)
            and set(snapshot) == required
            and set(snapshot["lineage"]) == set(LINEAGE)
            and set(snapshot["inputs"])
            == {
                "expected_response_input",
                "trusted_environment",
                "provider_selection",
                "weather_source",
            }
            and snapshot.get("snapshot_schema_version") == SCHEMA_VERSION
            and snapshot.get("snapshot_hash")
            == canonical_hash({k: v for k, v in snapshot.items() if k != "snapshot_hash"})
        )
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def dataset_from_inputs(
    inputs,
    *,
    route_session,
    sample_session,
    athlete_id,
    session_external_id,
    clocks,
    declarations,
    split_manifest=None,
):
    return build_route_response_dataset(
        inputs["expected_response_input"],
        normalize_polar_training_samples({"exerciseSamples": sample_session["exercises"]}),
        athlete_id=athlete_id,
        session_external_id=session_external_id,
        route_session=route_session,
        sample_session=sample_session,
        sample_session_match_count=1,
        hr_timebase_snapshots=ordered_proofs(clocks),
        hr_acquisition_declarations=ordered_proofs(declarations),
        trusted_environment=inputs["trusted_environment"],
        provider_selection=inputs["provider_selection"],
        weather_source=inputs["weather_source"],
        split_manifest=split_manifest,
    )


def replay_environment_dataset(
    snapshot,
    *,
    snapshot_id,
    athlete_id,
    session_external_id,
    route_session,
    sample_session,
    clocks,
    declarations,
    split_manifest=None,
):
    if not verify_environment_replay_snapshot(snapshot):
        raise ValueError("REPLAY_SNAPSHOT_INTEGRITY_FAILED")
    if (
        snapshot["athlete_id"] != str(athlete_id)
        or snapshot["session_external_id"] != session_external_id
    ):
        raise ValueError("REPLAY_OWNER_OR_SESSION_MISMATCH")
    if snapshot["route_source_hash"] != canonical_hash(route_session) or snapshot[
        "sample_source_hash"
    ] != canonical_hash(sample_session):
        raise ValueError("REPLAY_CURRENT_POLAR_SOURCE_CHANGED")
    if snapshot["hr_proof_state_hash"] != proof_state_hash(clocks, declarations):
        raise ValueError("REPLAY_HR_PROOF_STATE_CHANGED")
    kwargs = {
        "route_session": route_session,
        "sample_session": sample_session,
        "athlete_id": str(athlete_id),
        "session_external_id": session_external_id,
        "clocks": clocks,
        "declarations": declarations,
    }
    unassigned = dataset_from_inputs(snapshot["inputs"], **kwargs)
    if unassigned["package_hash"] != snapshot["unassigned_dataset_package_hash"]:
        raise ValueError("REPLAY_DATASET_IMPLEMENTATION_OR_INPUT_CHANGED")
    dataset = (
        dataset_from_inputs(snapshot["inputs"], split_manifest=split_manifest, **kwargs)
        if split_manifest
        else unassigned
    )
    dataset["input_provenance"].update(
        scope="VERIFIED_SNAPSHOT_PAYLOAD_WITH_CURRENT_POLAR_SOURCE_AND_PINNED_HR_PROOFS",
        database_environment_replay_verified=False,
    )
    dataset["replay_evidence"] = {
        "status": "VERIFIED_SAVED_ENVIRONMENT_REPLAY",
        "snapshot_id": str(snapshot_id),
        "snapshot_hash": snapshot["snapshot_hash"],
        "evidence_set_id": snapshot["evidence_set_id"],
        "evidence_hash": snapshot["evidence_hash"],
        "projection_hash": snapshot["lineage"]["trusted_projection"]["projection_hash"],
        "captured_unassigned_package_hash": snapshot["unassigned_dataset_package_hash"],
        "current_polar_source_verified": True,
        "pinned_hr_proof_state_verified": True,
        "environmental_provider_calls": 0,
        "replay_storage_writes": 0,
    }
    dataset["policy"].update(
        environment_inputs_replayed_from_saved_snapshot=True,
        replay_snapshot_selected_explicitly=True,
    )
    dataset["package_hash"] = canonical_hash(
        {k: v for k, v in dataset.items() if k != "package_hash"}
    )
    return dataset
