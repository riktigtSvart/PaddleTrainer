from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.planning.application.project_authoritative_executed_training import (
    AUTHORITATIVE_EXECUTED_TRAINING_SOURCE_SYSTEM,
    project_authoritative_executed_training_evidence,
)
from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_bundle,
    create_evidence_item,
)
from app.planning.domain.training_state.evidence import (
    EXECUTED_TRAINING_SESSION,
    EXECUTED_TRAINING_SESSION_SCHEMA_V01,
    EXECUTED_TRAINING_SESSION_SCHEMA_V02,
    training_exposure_from_evidence,
)
from app.planning.domain.training_state.models import (
    EvidenceCoverage,
    LoadAnchorStatus,
    ObservationWindow,
)
from app.planning.domain.training_state.resolver import (
    build_current_training_state,
)


UTC = timezone.utc

ATHLETE_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"

OBSERVED_AT = datetime(
    2026, 10, 19, 12, 0, tzinfo=UTC
)
AVAILABLE_AT = datetime(
    2026, 10, 19, 13, 0, tzinfo=UTC
)
PROJECTED_AT = datetime(
    2026, 10, 19, 13, 5, tzinfo=UTC
)


def artifact(
    *,
    duration_status=KnowledgeStatus.KNOWN,
    duration_s=3600,
    associations=(),
    valid_hash=True,
    occurrence_alignment_verified=False,
    phase_alignment_verified=False,
    provider_event_verified=False,
    clock_alignment_verified=False,
    actual_boundary_verified=False,
    temporal_match_used=False,
):
    return SimpleNamespace(
        artifact_id="pt-executed-training-evidence:p1-7c",
        schema_version=(
            "authoritative-executed-training-evidence-v0.1"
        ),
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
        observed_at=OBSERVED_AT,
        modality_key="RUNNING",
        duration_status=duration_status,
        duration_s=duration_s,
        plan_execution_link_id="pt-exec-link:p1-7c",
        plan_identity_linked=True,
        plan_content_at_execution_status="unverified",
        occurrence_associations=tuple(associations),
        occurrence_alignment_verified=(
            occurrence_alignment_verified
        ),
        phase_alignment_verified=phase_alignment_verified,
        provider_event_verified=provider_event_verified,
        clock_alignment_verified=clock_alignment_verified,
        actual_boundary_verified=actual_boundary_verified,
        temporal_match_used=temporal_match_used,
        created_at=AVAILABLE_AT,
        content_hash="a" * 64,
        verify_content_hash=lambda: valid_hash,
    )


def association(
    *,
    status="user_confirmed_candidate_segment",
    provider_event_verified=False,
):
    return SimpleNamespace(
        occurrence_alignment_status=status,
        provider_event_verified=provider_event_verified,
        clock_alignment_verified=False,
        actual_boundary_verified=False,
        temporal_match_used=False,
    )


def project(source=None):
    return project_authoritative_executed_training_evidence(
        source or artifact(),
        created_at=PROJECTED_AT,
    )


def test_projection_creates_v02_derived_evidence():
    item = project()

    assert item.evidence_type == EXECUTED_TRAINING_SESSION
    assert item.provenance == ProvenanceKind.DERIVED
    assert item.knowledge_status == KnowledgeStatus.KNOWN
    assert item.quality == EvidenceQuality.HIGH

    assert item.observed_at == OBSERVED_AT
    assert item.available_at == AVAILABLE_AT
    assert item.created_at == PROJECTED_AT

    assert item.source_ref == SourceRecordRef(
        source_system=(
            AUTHORITATIVE_EXECUTED_TRAINING_SOURCE_SYSTEM
        ),
        source_record_id=(
            "pt-executed-training-evidence:p1-7c"
        ),
        source_version=(
            "authoritative-executed-training-evidence-v0.1"
        ),
        source_content_hash="a" * 64,
    )

    payload = item.payload
    assert payload["schema_version"] == (
        EXECUTED_TRAINING_SESSION_SCHEMA_V02
    )
    assert payload["session_id"] == SESSION_ID
    assert payload["modality_key"] == "RUNNING"
    assert payload["duration_status"] == "known"
    assert payload["duration_s"] == 3600

    assert payload["plan_identity_linked"] is True
    assert payload["occurrence_association_count"] == 0
    assert payload["occurrence_alignment_status"] == "none"

    assert payload["occurrence_alignment_verified"] is False
    assert payload["phase_alignment_verified"] is False
    assert payload["provider_event_verified"] is False
    assert payload["clock_alignment_verified"] is False
    assert payload["actual_boundary_verified"] is False
    assert payload["temporal_match_used"] is False

    assert item.verify_content_hash() is True


def test_unknown_duration_survives_projection_as_unknown_not_zero():
    item = project(
        artifact(
            duration_status=KnowledgeStatus.UNKNOWN,
            duration_s=None,
        )
    )

    observation = training_exposure_from_evidence(item)

    assert observation is not None
    assert observation.duration_status == KnowledgeStatus.UNKNOWN
    assert observation.duration_s is None


def test_user_confirmed_occurrence_remains_metadata_not_verified_alignment():
    item = project(
        artifact(
            associations=(association(),),
        )
    )

    assert item.payload["occurrence_association_count"] == 1
    assert item.payload["occurrence_alignment_status"] == (
        "user_confirmed_candidate_segment"
    )

    assert item.payload["occurrence_alignment_verified"] is False
    assert item.payload["phase_alignment_verified"] is False


@pytest.mark.parametrize(
    "field_name",
    [
        "occurrence_alignment_verified",
        "phase_alignment_verified",
        "provider_event_verified",
        "clock_alignment_verified",
        "actual_boundary_verified",
        "temporal_match_used",
    ],
)
def test_projection_rejects_stronger_session_claims(
    field_name,
):
    kwargs = {field_name: True}

    with pytest.raises(
        ValueError,
        match="must remain false",
    ):
        project(artifact(**kwargs))


def test_projection_rejects_stronger_occurrence_claim():
    with pytest.raises(
        ValueError,
        match="stronger claim",
    ):
        project(
            artifact(
                associations=(
                    association(
                        provider_event_verified=True
                    ),
                )
            )
        )


def test_projection_rejects_invalid_authoritative_hash():
    with pytest.raises(
        ValueError,
        match="hash does not verify",
    ):
        project(
            artifact(valid_hash=False)
        )


def test_projection_cannot_predate_authoritative_availability():
    with pytest.raises(
        ValueError,
        match="cannot predate",
    ):
        project_authoritative_executed_training_evidence(
            artifact(),
            created_at=datetime(
                2026, 10, 19, 12, 59, tzinfo=UTC
            ),
        )


def test_v01_contract_remains_supported():
    item = create_evidence_item(
        evidence_id="legacy-v01",
        athlete_id=ATHLETE_ID,
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=OBSERVED_AT,
        available_at=OBSERVED_AT,
        created_at=PROJECTED_AT,
        source_ref=SourceRecordRef(
            source_system="legacy-test",
            source_record_id=SESSION_ID,
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload={
            "schema_version":
                EXECUTED_TRAINING_SESSION_SCHEMA_V01,
            "session_id": SESSION_ID,
            "modality_key": "RUNNING",
            "duration_status": "known",
            "duration_s": 3600,
        },
    )

    observation = training_exposure_from_evidence(item)

    assert observation is not None
    assert observation.session_id == SESSION_ID
    assert observation.duration_s == 3600


def test_v02_parser_rejects_silent_authority_upgrade():
    item = project()

    payload = dict(item.payload)
    payload["phase_alignment_verified"] = True

    malformed = create_evidence_item(
        evidence_id="malformed-v02",
        athlete_id=item.athlete_id,
        evidence_type=item.evidence_type,
        observed_at=item.observed_at,
        available_at=item.available_at,
        created_at=item.created_at,
        source_ref=item.source_ref,
        provenance=item.provenance,
        knowledge_status=item.knowledge_status,
        quality=item.quality,
        payload=payload,
    )

    with pytest.raises(
        ValueError,
        match="phase_alignment_verified",
    ):
        training_exposure_from_evidence(malformed)


def _state(item, *, state_id):
    bundle = create_evidence_bundle(
        bundle_id=f"bundle:{state_id}",
        athlete_id=ATHLETE_ID,
        as_of=datetime(
            2026, 10, 19, 14, 0, tzinfo=UTC
        ),
        information_cutoff_at=datetime(
            2026, 10, 19, 14, 0, tzinfo=UTC
        ),
        created_at=datetime(
            2026, 10, 19, 14, 5, tzinfo=UTC
        ),
        items=(item,),
    )

    return build_current_training_state(
        bundle=bundle,
        state_id=state_id,
        schema_version="cts_v0.1",
        created_at=datetime(
            2026, 10, 19, 14, 10, tzinfo=UTC
        ),
        recent_window=ObservationWindow(
            datetime(
                2026, 10, 18, 0, 0, tzinfo=UTC
            ),
            datetime(
                2026, 10, 19, 14, 0, tzinfo=UTC
            ),
        ),
        load_anchor_window=ObservationWindow(
            datetime(
                2026, 10, 18, 0, 0, tzinfo=UTC
            ),
            datetime(
                2026, 10, 19, 14, 0, tzinfo=UTC
            ),
        ),
        recent_training_coverage=(
            EvidenceCoverage.COMPLETE
        ),
        load_anchor_training_coverage=(
            EvidenceCoverage.COMPLETE
        ),
        domain_coverage=(),
    )


def test_v02_authority_metadata_does_not_change_exposure_semantics():
    legacy = create_evidence_item(
        evidence_id="legacy-exposure",
        athlete_id=ATHLETE_ID,
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=OBSERVED_AT,
        available_at=AVAILABLE_AT,
        created_at=PROJECTED_AT,
        source_ref=SourceRecordRef(
            source_system="legacy-test",
            source_record_id=SESSION_ID,
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.HIGH,
        payload={
            "schema_version":
                EXECUTED_TRAINING_SESSION_SCHEMA_V01,
            "session_id": SESSION_ID,
            "modality_key": "RUNNING",
            "duration_status": "known",
            "duration_s": 3600,
        },
    )

    authoritative = project()

    legacy_state = _state(
        legacy,
        state_id="state-v01",
    )
    authoritative_state = _state(
        authoritative,
        state_id="state-v02",
    )

    assert (
        legacy_state.recent_exposure.observed_session_count
        == authoritative_state
        .recent_exposure.observed_session_count
        == 1
    )

    assert (
        legacy_state.recent_exposure.observed_known_duration_s
        == authoritative_state
        .recent_exposure.observed_known_duration_s
        == 3600
    )

    assert (
        legacy_state.load_anchor.status
        == authoritative_state.load_anchor.status
        == LoadAnchorStatus.VERIFIED_EXPOSURE
    )

    assert (
        legacy_state
        .load_anchor.exposure
        .complete_window_total_duration_s
        == authoritative_state
        .load_anchor.exposure
        .complete_window_total_duration_s
        == 3600
    )
