from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.application.assemble_training_dynamics import (
    assemble_observed_response_association,
)
from app.planning.application.project_authoritative_training_response import (
    AUTHORITATIVE_TRAINING_RESPONSE_SOURCE_SYSTEM,
)
from app.planning.application.rejoin_training_response_metrics import (
    rejoin_response_metric_observations,
)
from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_item,
)
from app.planning.domain.response_evidence import (
    TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02,
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics.history import (
    TrainingDynamicsHistoryCoverage,
    TrainingDynamicsHistoryEntry,
    build_training_dynamics_history,
)
from app.planning.domain.training_dynamics.models import (
    ResponseIsolationStatus,
    build_observed_response_association,
    build_realized_training_stimulus,
)
from app.planning.domain.training_dynamics.response_metrics import (
    RESPONSE_METRIC_OBSERVATION_SCHEMA_V01,
)
from app.planning.domain.training_state.evidence import (
    SESSION_FEEDBACK,
    SESSION_FEEDBACK_SCHEMA_V01,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"

EXECUTION_ID = (
    "pt-executed-training-evidence:"
    f"session:{SESSION}"
)

EXECUTION_HASH = "a" * 64

RESPONSE_ARTIFACT_ID = (
    "pt-training-response-evidence:c2a"
)

RESPONSE_ARTIFACT_HASH = "b" * 64


def dt(
    day: int,
    hour: int,
) -> datetime:
    return datetime(
        2026,
        10,
        day,
        hour,
        tzinfo=UTC,
    )


def stimulus():
    return build_realized_training_stimulus(
        stimulus_id=(
            "pt-training-stimulus:"
            f"session:{SESSION}"
        ),
        athlete_id=ATHLETE,
        workout_session_id=SESSION,
        executed_training_evidence_id=(
            EXECUTION_ID
        ),
        executed_training_evidence_hash=(
            EXECUTION_HASH
        ),
        exposure_observed_at=dt(19, 8),
        modality_key="RUNNING",
        duration_status=KnowledgeStatus.KNOWN,
        duration_s=3600,
        features=(),
        created_at=dt(19, 9),
    )


def response_item(
    *,
    measurements=None,
    timing="same_day",
    observed_at=None,
    available_at=None,
):
    if measurements is None:
        measurements = (
            {
                "metric_key":
                    "self_reported_fatigue_score",
                "knowledge_status": "known",
                "value": 6.0,
                "unit": None,
            },
        )

    observed = observed_at or dt(19, 14)
    available = available_at or dt(19, 15)

    return create_evidence_item(
        evidence_id=(
            "pt-evidence:session-feedback:"
            f"{RESPONSE_ARTIFACT_HASH}"
        ),
        athlete_id=ATHLETE,
        evidence_type=SESSION_FEEDBACK,
        observed_at=observed,
        available_at=available,
        created_at=available,
        source_ref=SourceRecordRef(
            source_system=(
                AUTHORITATIVE_TRAINING_RESPONSE_SOURCE_SYSTEM
            ),
            source_record_id=(
                RESPONSE_ARTIFACT_ID
            ),
            source_version=(
                TRAINING_RESPONSE_EVIDENCE_SCHEMA_V02
            ),
            source_content_hash=(
                RESPONSE_ARTIFACT_HASH
            ),
        ),
        provenance=ProvenanceKind.DERIVED,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.MODERATE,
        payload={
            "schema_version":
                SESSION_FEEDBACK_SCHEMA_V01,
            "session_id": SESSION,
            "response_timing": timing,
            "measurements": tuple(
                measurements
            ),

            "authoritative_response_evidence_id":
                RESPONSE_ARTIFACT_ID,
            "authoritative_response_evidence_hash":
                RESPONSE_ARTIFACT_HASH,

            "executed_training_evidence_id":
                EXECUTION_ID,
            "executed_training_evidence_hash":
                EXECUTION_HASH,

            "session_link_basis":
                "source_explicit_session_id",
            "session_identity_linked": True,
            "interpretation": "descriptive_only",

            "causal_attribution_established": False,
            "readiness_inference_authorized": False,
            "fatigue_diagnosis_authorized": False,
            "performance_prediction_authorized": False,
            "prescription_change_authorized": False,
        },
    )


def association(
    source_stimulus,
    evidence,
):
    return assemble_observed_response_association(
        stimulus=source_stimulus,
        response_evidence=evidence,
        intervening_stimuli=(),
        intervening_history_complete=False,
        created_at=dt(19, 16),
    )


def source_history(
    source_stimulus,
    source_association,
):
    return build_training_dynamics_history(
        history_id=(
            "pt-training-dynamics-history:"
            "c2a-test"
        ),
        athlete_id=ATHLETE,
        window_start_at=dt(18, 0),
        as_of=dt(20, 23),
        information_cutoff_at=dt(20, 23),
        stimulus_coverage=(
            TrainingDynamicsHistoryCoverage.PARTIAL
        ),
        response_coverage=(
            TrainingDynamicsHistoryCoverage.PARTIAL
        ),
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=source_stimulus,
                responses=(
                    source_association,
                ),
            ),
        ),
        source_evidence_ids=(
            evidence_id(source_association),
        ),
        created_at=dt(21, 0),
    )


def evidence_id(source_association):
    return source_association.response_evidence_id


def rejoin(
    history,
    *items,
):
    return rejoin_response_metric_observations(
        history=history,
        evidence_items=tuple(items),
        created_at=dt(21, 1),
    )


def test_rejoins_exact_response_measurement_with_context():
    s = stimulus()

    item = response_item(
        measurements=(
            {
                "metric_key":
                    "self_reported_energy_score",
                "knowledge_status": "known",
                "value": 0.0,
                "unit": None,
            },
            {
                "metric_key":
                    "self_reported_fatigue_score",
                "knowledge_status": "known",
                "value": 6.0,
                "unit": "score_0_10",
            },
        )
    )

    a = association(s, item)
    history = source_history(s, a)

    observations = rejoin(
        history,
        item,
    )

    assert len(observations) == 2

    by_key = {
        observation.metric_key: observation
        for observation in observations
    }

    energy = by_key[
        "self_reported_energy_score"
    ]

    assert energy.value == 0.0
    assert energy.knowledge_status == KnowledgeStatus.KNOWN

    fatigue = by_key[
        "self_reported_fatigue_score"
    ]

    assert fatigue.value == 6.0
    assert fatigue.unit == "score_0_10"

    assert (
        fatigue.schema_version
        == RESPONSE_METRIC_OBSERVATION_SCHEMA_V01
    )

    assert fatigue.athlete_id == ATHLETE
    assert fatigue.workout_session_id == SESSION
    assert fatigue.stimulus_id == s.stimulus_id
    assert fatigue.stimulus_modality_key == "RUNNING"

    assert fatigue.association_id == a.association_id
    assert (
        fatigue.association_content_hash
        == a.content_hash
    )

    assert (
        fatigue.response_evidence_id
        == item.evidence_id
    )
    assert (
        fatigue.response_evidence_hash
        == item.content_hash
    )

    assert (
        fatigue.response_timing
        == TrainingResponseTiming.SAME_DAY
    )

    assert (
        fatigue.isolation_status
        == ResponseIsolationStatus.UNKNOWN
    )

    assert fatigue.verify_content_hash()


def test_unknown_measurement_remains_null_not_zero():
    s = stimulus()

    item = response_item(
        measurements=(
            {
                "metric_key":
                    "self_reported_fatigue_score",
                "knowledge_status": "unknown",
                "value": None,
                "unit": "score_0_10",
            },
        )
    )

    a = association(s, item)
    history = source_history(s, a)

    observation = rejoin(
        history,
        item,
    )[0]

    assert (
        observation.knowledge_status
        == KnowledgeStatus.UNKNOWN
    )
    assert observation.value is None


def test_c2a_preserves_non_numeric_scalar_measurements():
    s = stimulus()

    item = response_item(
        measurements=(
            {
                "metric_key": "completed",
                "knowledge_status": "known",
                "value": True,
                "unit": None,
            },
            {
                "metric_key": "subjective_label",
                "knowledge_status": "known",
                "value": "controlled",
                "unit": None,
            },
        )
    )

    a = association(s, item)
    history = source_history(s, a)

    observations = rejoin(
        history,
        item,
    )

    values = {
        observation.metric_key:
            observation.value
        for observation in observations
    }

    assert values == {
        "completed": True,
        "subjective_label": "controlled",
    }


def test_missing_referenced_response_evidence_fails_closed():
    s = stimulus()
    item = response_item()
    a = association(s, item)
    history = source_history(s, a)

    with pytest.raises(
        ValueError,
        match="missing",
    ):
        rejoin(history)


def test_wrong_response_evidence_hash_fails_closed():
    s = stimulus()
    item = response_item()
    a = association(s, item)

    wrong = response_item(
        measurements=(
            {
                "metric_key":
                    "self_reported_fatigue_score",
                "knowledge_status": "known",
                "value": 9.0,
                "unit": None,
            },
        )
    )

    # Same durable evidence ID, different semantic content/hash.
    assert wrong.evidence_id == item.evidence_id
    assert wrong.content_hash != item.content_hash

    history = source_history(s, a)

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        rejoin(
            history,
            wrong,
        )


def test_response_timing_mismatch_fails_closed():
    s = stimulus()
    item = response_item(
        timing="same_day"
    )

    a = build_observed_response_association(
        association_id=(
            "pt-response-association:"
            f"timing:{item.content_hash}"
        ),
        stimulus=s,
        response_evidence_id=(
            item.evidence_id
        ),
        response_evidence_hash=(
            item.content_hash
        ),
        response_workout_session_id=SESSION,
        response_timing=(
            TrainingResponseTiming.NEXT_MORNING
        ),
        session_link_basis=(
            "source_explicit_session_id"
        ),
        response_observed_at=item.observed_at,
        response_available_at=item.available_at,
        isolation_status=(
            ResponseIsolationStatus.UNKNOWN
        ),
        created_at=dt(19, 16),
    )

    history = source_history(s, a)

    with pytest.raises(
        ValueError,
        match="timing",
    ):
        rejoin(
            history,
            item,
        )


def test_malformed_non_known_value_fails_closed():
    s = stimulus()

    item = response_item(
        measurements=(
            {
                "metric_key":
                    "self_reported_fatigue_score",
                "knowledge_status": "unknown",
                "value": 0,
                "unit": None,
            },
        )
    )

    a = association(s, item)
    history = source_history(s, a)

    with pytest.raises(
        ValueError,
        match="requires value=None",
    ):
        rejoin(
            history,
            item,
        )


def test_duplicate_metric_keys_in_generic_payload_fail_closed():
    s = stimulus()

    item = response_item(
        measurements=(
            {
                "metric_key": "duplicate_metric",
                "knowledge_status": "known",
                "value": 1.0,
                "unit": "score",
            },
            {
                "metric_key": "duplicate_metric",
                "knowledge_status": "known",
                "value": 2.0,
                "unit": "score",
            },
        )
    )

    a = association(s, item)
    history = source_history(s, a)

    with pytest.raises(
        ValueError,
        match="must be unique",
    ):
        rejoin(
            history,
            item,
        )


def test_extra_unreferenced_evidence_does_not_create_observations():
    s = stimulus()
    item = response_item()
    a = association(s, item)
    history = source_history(s, a)

    other = create_evidence_item(
        evidence_id="unrelated:evidence",
        athlete_id=ATHLETE,
        evidence_type="MEASUREMENT_OBSERVATION",
        observed_at=dt(19, 12),
        available_at=dt(19, 12),
        created_at=dt(19, 12),
        source_ref=SourceRecordRef(
            source_system="test",
            source_record_id="unrelated",
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.LOW,
        payload={
            "value": 999,
        },
    )

    observations = rejoin(
        history,
        other,
        item,
    )

    assert len(observations) == 1
    assert (
        observations[0].response_evidence_id
        == item.evidence_id
    )


def test_rejoin_is_deterministic_across_input_order_and_created_at():
    s = stimulus()
    item = response_item()
    a = association(s, item)
    history = source_history(s, a)

    first = rejoin_response_metric_observations(
        history=history,
        evidence_items=(item,),
        created_at=dt(21, 1),
    )

    second = rejoin_response_metric_observations(
        history=history,
        evidence_items=(item,),
        created_at=dt(21, 2),
    )

    assert len(first) == 1
    assert len(second) == 1

    assert (
        first[0].observation_id
        == second[0].observation_id
    )

    assert (
        first[0].content_hash
        == second[0].content_hash
    )

    assert (
        first[0].created_at
        != second[0].created_at
    )

    assert first[0].causal_attribution_established is False
    assert first[0].effect_inference_authorized is False
    assert first[0].readiness_inference_authorized is False
    assert first[0].performance_prediction_authorized is False
    assert first[0].prescription_change_authorized is False
