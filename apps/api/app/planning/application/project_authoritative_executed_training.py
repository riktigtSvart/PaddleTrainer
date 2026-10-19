from __future__ import annotations

from datetime import datetime

from ..domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from ..domain.common.time import to_utc
from ..domain.evidence.models import (
    EvidenceItem,
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_item,
)
from ..domain.executed_training import (
    AuthoritativeExecutedTrainingEvidence,
)
from ..domain.training_state.evidence import (
    EXECUTED_TRAINING_SESSION,
    EXECUTED_TRAINING_SESSION_SCHEMA_V02,
)


AUTHORITATIVE_EXECUTED_TRAINING_SOURCE_SYSTEM = (
    "planning_authoritative_executed_training"
)


def project_authoritative_executed_training_evidence(
    source: AuthoritativeExecutedTrainingEvidence,
    *,
    created_at: datetime,
) -> EvidenceItem:
    """Project authoritative execution evidence into training exposure.

    The projection exposes only descriptive session exposure to the
    CurrentTrainingState resolver. Planning/execution authority remains
    metadata and must not become readiness, fatigue, performance, or
    prescription evidence.
    """

    if not source.verify_content_hash():
        raise ValueError(
            "Authoritative executed-training evidence hash "
            "does not verify."
        )

    projected_created_at = to_utc(
        created_at,
        field_name="created_at",
    )
    source_created_at = to_utc(
        source.created_at,
        field_name="source.created_at",
    )

    if projected_created_at < source_created_at:
        raise ValueError(
            "Projected evidence cannot predate its "
            "authoritative source artifact."
        )

    if source.plan_identity_linked is not True:
        raise ValueError(
            "Authoritative executed-training source must "
            "establish plan identity."
        )

    if (
        source.plan_content_at_execution_status
        != "unverified"
    ):
        raise ValueError(
            "Unexpected stronger historical plan-content claim."
        )

    for field_name in (
        "occurrence_alignment_verified",
        "phase_alignment_verified",
        "provider_event_verified",
        "clock_alignment_verified",
        "actual_boundary_verified",
        "temporal_match_used",
    ):
        if getattr(source, field_name) is not False:
            raise ValueError(
                f"{field_name} must remain false."
            )

    associations = tuple(
        source.occurrence_associations
    )

    if associations:
        for association in associations:
            if (
                association.occurrence_alignment_status
                != "user_confirmed_candidate_segment"
            ):
                raise ValueError(
                    "Unsupported occurrence association status."
                )

            for field_name in (
                "provider_event_verified",
                "clock_alignment_verified",
                "actual_boundary_verified",
                "temporal_match_used",
            ):
                if (
                    getattr(association, field_name)
                    is not False
                ):
                    raise ValueError(
                        "Occurrence association contains "
                        "an unsupported stronger claim."
                    )

        occurrence_alignment_status = (
            "user_confirmed_candidate_segment"
        )
    else:
        occurrence_alignment_status = "none"

    payload = {
        "schema_version":
            EXECUTED_TRAINING_SESSION_SCHEMA_V02,

        # Training-exposure projection.
        "session_id": source.workout_session_id,
        "modality_key": source.modality_key,
        "duration_status": source.duration_status.value,
        "duration_s": source.duration_s,

        # Authority / audit metadata. These fields are not load,
        # readiness, fatigue, or prescription variables.
        "authoritative_execution_evidence_id":
            source.artifact_id,
        "authoritative_execution_evidence_hash":
            source.content_hash,
        "plan_execution_link_id":
            source.plan_execution_link_id,
        "plan_identity_linked": True,

        "occurrence_association_count":
            len(associations),
        "occurrence_alignment_status":
            occurrence_alignment_status,

        "plan_content_at_execution_status":
            source.plan_content_at_execution_status,

        # P1.7C must not silently promote P1.6/P1.6C authority.
        "occurrence_alignment_verified": False,
        "phase_alignment_verified": False,
        "provider_event_verified": False,
        "clock_alignment_verified": False,
        "actual_boundary_verified": False,
        "temporal_match_used": False,
    }

    return create_evidence_item(
        evidence_id=(
            "pt-evidence:executed-training:"
            f"{source.content_hash}"
        ),
        athlete_id=source.athlete_id,
        evidence_type=EXECUTED_TRAINING_SESSION,

        # When the training occurred.
        observed_at=source.observed_at,

        # When authoritative execution evidence became available
        # to the planner. This preserves cutoff semantics.
        available_at=source_created_at,

        created_at=projected_created_at,
        source_ref=SourceRecordRef(
            source_system=(
                AUTHORITATIVE_EXECUTED_TRAINING_SOURCE_SYSTEM
            ),
            source_record_id=source.artifact_id,
            source_version=source.schema_version,
            source_content_hash=source.content_hash,
        ),

        # This EvidenceItem is a deterministic projection of an
        # already-established authority artifact, not a raw source row.
        provenance=ProvenanceKind.DERIVED,

        # The executed session itself is known. Duration uncertainty
        # remains explicit in payload.duration_status.
        knowledge_status=KnowledgeStatus.KNOWN,

        # High refers to the session/exposure identity carried through
        # the hash-verified authoritative artifact. It does not upgrade
        # occurrence/phase/boundary claims.
        quality=EvidenceQuality.HIGH,

        payload=payload,
    )
