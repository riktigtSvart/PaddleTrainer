from datetime import datetime
import json

from ..common.enums import (
    ConfidenceLevel,
    DecisionPurpose,
    DecisionRelevance,
    Freshness,
    PlanningScope,
    SnapshotStatus,
)
from ..common.refs import SourceSnapshotRef, VersionRef
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
)
from ..common.snapshot import (
    ImmutableDomainSnapshot,
    create_domain_snapshot,
)
from ..context.models import (
    AthletePlanningContextAggregate,
    CriticalUnknown,
    CurrentStateContextProjection,
    DomainFreshness,
    EntryGateContextProjection,
    EvidenceConflict,
    PlanningAssumption,
    RuntimePlanningProjection,
    StimulusGateContextProjection,
    TrainingSpaceProjection,
    TrainingSpaceStatus,
    UnresolvedPlanningDimension,
    WorkoutFamilySpaceItem,
    create_planning_context,
)
from ..entry_gate.models import EntryMode, GlobalEntryGate, StimulusGateStatus
from ..training_state.models import EvidenceCoverage, LoadAnchorStatus
from ..workout_family.models import FamilyEntryGateStatus
from .models import SnapshotKind, SnapshotRecord


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def encode_domain_snapshot(
    snapshot: ImmutableDomainSnapshot,
) -> SnapshotRecord:
    if not snapshot.verify_content_hash():
        raise ValueError("Domain snapshot content hash is invalid.")
    return SnapshotRecord(
        snapshot_kind=SnapshotKind.DOMAIN_SNAPSHOT,
        snapshot_id=snapshot.snapshot_id,
        athlete_id=snapshot.athlete_id,
        schema_version=snapshot.schema_version,
        as_of=snapshot.as_of,
        information_cutoff_at=snapshot.information_cutoff_at,
        created_at=snapshot.created_at,
        content_hash_algorithm=snapshot.content_hash_algorithm,
        content_hash=snapshot.content_hash,
        contract_json=canonical_json(snapshot),
    )


def decode_domain_snapshot(
    record: SnapshotRecord,
) -> ImmutableDomainSnapshot:
    if record.snapshot_kind != SnapshotKind.DOMAIN_SNAPSHOT:
        raise ValueError("SnapshotRecord is not a domain snapshot.")
    data = json.loads(record.contract_json)
    if data["content_hash_algorithm"] != CONTENT_HASH_ALGORITHM:
        raise ValueError("Unsupported content hash algorithm.")
    restored = create_domain_snapshot(
        snapshot_id=data["snapshot_id"],
        athlete_id=data["athlete_id"],
        domain_type=data["domain_type"],
        schema_version=data["schema_version"],
        as_of=_dt(data["as_of"]),
        information_cutoff_at=_dt(data["information_cutoff_at"]),
        created_at=_dt(data["created_at"]),
        payload=data["payload"],
        status=SnapshotStatus(data["status"]),
    )
    if restored.content_hash != record.content_hash:
        raise ValueError("Stored domain snapshot hash does not verify.")
    return restored



def _runtime_projection(data: dict | None) -> RuntimePlanningProjection | None:
    if data is None:
        return None

    current = data["current_state"]
    gate = data["entry_gate"]
    space = data["training_space"]

    return RuntimePlanningProjection(
        current_state=CurrentStateContextProjection(
            current_training_state_hash=current[
                "current_training_state_hash"
            ],
            load_anchor_status=LoadAnchorStatus(
                current["load_anchor_status"]
            ),
            recent_source_coverage=EvidenceCoverage(
                current["recent_source_coverage"]
            ),
            recent_observed_session_count=current[
                "recent_observed_session_count"
            ],
            recent_known_duration_s=current[
                "recent_known_duration_s"
            ],
            recent_complete_window_duration_s=current[
                "recent_complete_window_duration_s"
            ],
            latest_training_observed_at=(
                _dt(current["latest_training_observed_at"])
                if current["latest_training_observed_at"] is not None
                else None
            ),
        ),
        entry_gate=EntryGateContextProjection(
            entry_gate_decision_hash=gate[
                "entry_gate_decision_hash"
            ],
            global_gate=GlobalEntryGate(gate["global_gate"]),
            entry_mode=EntryMode(gate["entry_mode"]),
            reason_codes=tuple(gate["reason_codes"]),
            stimulus_gates=tuple(
                StimulusGateContextProjection(
                    stimulus_key=item["stimulus_key"],
                    status=StimulusGateStatus(item["status"]),
                    reason_codes=tuple(item["reason_codes"]),
                )
                for item in gate["stimulus_gates"]
            ),
        ),
        workout_family_registry_version=data[
            "workout_family_registry_version"
        ],
        workout_family_registry_hash=data[
            "workout_family_registry_hash"
        ],
        training_space=TrainingSpaceProjection(
            projection_scope=space["projection_scope"],
            status=TrainingSpaceStatus(space["status"]),
            families=tuple(
                WorkoutFamilySpaceItem(
                    family_key=item["family_key"],
                    family_version=item["family_version"],
                    modality_key=item["modality_key"],
                    sport_key=item["sport_key"],
                    entry_gate_status=FamilyEntryGateStatus(
                        item["entry_gate_status"]
                    ),
                    build_authorized_by_entry_gate=item[
                        "build_authorized_by_entry_gate"
                    ],
                    dose_reduction_required=item[
                        "dose_reduction_required"
                    ],
                    reason_codes=tuple(item["reason_codes"]),
                )
                for item in space["families"]
            ),
            unresolved_dimensions=tuple(
                UnresolvedPlanningDimension(item)
                for item in space["unresolved_dimensions"]
            ),
            final_authorization=space["final_authorization"],
        ),
    )

def encode_planning_context(
    context: AthletePlanningContextAggregate,
) -> SnapshotRecord:
    if not context.verify_content_hash():
        raise ValueError("Planning context content hash is invalid.")
    return SnapshotRecord(
        snapshot_kind=SnapshotKind.PLANNING_CONTEXT,
        snapshot_id=context.context_id,
        athlete_id=context.athlete_id,
        schema_version=context.schema_version,
        as_of=context.as_of,
        information_cutoff_at=context.information_cutoff_at,
        created_at=context.created_at,
        content_hash_algorithm=context.content_hash_algorithm,
        content_hash=context.content_hash,
        contract_json=canonical_json(context),
    )


def _source_ref(data: dict) -> SourceSnapshotRef:
    return SourceSnapshotRef(
        domain=data["domain"],
        object_id=data["object_id"],
        object_version=data["object_version"],
        as_of=_dt(data["as_of"]),
        information_cutoff_at=_dt(data["information_cutoff_at"]),
        available_at=_dt(data["available_at"]),
        content_hash=data["content_hash"],
    )


def _version_ref(data: dict) -> VersionRef:
    return VersionRef(
        namespace=data["namespace"],
        version=data["version"],
    )


def decode_planning_context(
    record: SnapshotRecord,
) -> AthletePlanningContextAggregate:
    if record.snapshot_kind != SnapshotKind.PLANNING_CONTEXT:
        raise ValueError("SnapshotRecord is not a planning context.")
    data = json.loads(record.contract_json)
    if data["content_hash_algorithm"] != CONTENT_HASH_ALGORITHM:
        raise ValueError("Unsupported content hash algorithm.")
    restored = create_planning_context(
        context_id=data["context_id"],
        athlete_id=data["athlete_id"],
        schema_version=data["schema_version"],
        as_of=_dt(data["as_of"]),
        information_cutoff_at=_dt(data["information_cutoff_at"]),
        created_at=_dt(data["created_at"]),
        planning_scope=PlanningScope(data["planning_scope"]),
        decision_purpose=DecisionPurpose(data["decision_purpose"]),
        source_snapshot_refs=tuple(
            _source_ref(item) for item in data["source_snapshot_refs"]
        ),
        engine_version=_version_ref(data["engine_version"]),
        rules_version=_version_ref(data["rules_version"]),
        evidence_pack_version=_version_ref(data["evidence_pack_version"]),
        sport_profile_versions=tuple(
            _version_ref(item) for item in data["sport_profile_versions"]
        ),
        policy_versions=tuple(
            _version_ref(item) for item in data["policy_versions"]
        ),
        critical_unknowns=tuple(
            CriticalUnknown(
                domain=item["domain"],
                question=item["question"],
                decision_relevance=DecisionRelevance(
                    item["decision_relevance"]
                ),
                fallback_policy=item["fallback_policy"],
            )
            for item in data["critical_unknowns"]
        ),
        evidence_conflicts=tuple(
            EvidenceConflict(
                domain=item["domain"],
                description=item["description"],
                decision_impact=DecisionRelevance(
                    item["decision_impact"]
                ),
            )
            for item in data["evidence_conflicts"]
        ),
        assumptions=tuple(
            PlanningAssumption(
                statement=item["statement"],
                impact_if_wrong=DecisionRelevance(
                    item["impact_if_wrong"]
                ),
                review_trigger=item["review_trigger"],
            )
            for item in data["assumptions"]
        ),
        domain_freshness=tuple(
            DomainFreshness(
                domain=item["domain"],
                freshness=Freshness(item["freshness"]),
                confidence=ConfidenceLevel(item["confidence"]),
            )
            for item in data["domain_freshness"]
        ),
        runtime_projection=_runtime_projection(
            data.get("runtime_projection")
        ),
    )
    if restored.content_hash != record.content_hash:
        raise ValueError("Stored planning context hash does not verify.")
    return restored
