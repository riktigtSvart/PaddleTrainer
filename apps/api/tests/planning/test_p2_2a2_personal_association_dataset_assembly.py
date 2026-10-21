from dataclasses import replace
from datetime import datetime, timezone
import importlib

import pytest

assembly_module = importlib.import_module(
    "app.planning.application."
    "assemble_personal_association_datasets"
)

from app.planning.application.assemble_personal_association_datasets import (
    assemble_personal_association_datasets,
)
from app.planning.domain.common.enums import (
    KnowledgeStatus,
)
from app.planning.domain.response_evidence import (
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPredictorKey,
    PersonalResponseReferenceStatus,
    ResponseIsolationStatus,
    StimulusFeature,
    TrainingDynamicsHistoryCoverage,
    TrainingDynamicsHistoryEntry,
    build_observed_response_association,
    build_realized_training_stimulus,
    build_response_metric_observation,
    build_training_dynamics_history,
)


UTC = timezone.utc

ATHLETE = (
    "11111111-1111-4111-8111-111111111111"
)

SESSION_A = (
    "22222222-2222-4222-8222-222222222222"
)

SESSION_B = (
    "33333333-3333-4333-8333-333333333333"
)


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


def stimulus(
    *,
    session_id: str,
    day: int,
    hash_char: str,
    load_value: float,
    intensity_value: float,
):
    return build_realized_training_stimulus(
        stimulus_id=(
            "pt-training-stimulus:"
            f"session:{session_id}"
        ),
        athlete_id=ATHLETE,
        workout_session_id=session_id,
        executed_training_evidence_id=(
            "pt-executed-training-evidence:"
            f"session:{session_id}"
        ),
        executed_training_evidence_hash=(
            hash_char * 64
        ),
        exposure_observed_at=dt(
            day,
            8,
        ),
        modality_key="RUNNING",
        duration_status=KnowledgeStatus.KNOWN,
        duration_s=3600,
        features=(
            StimulusFeature(
                metric_key="intensity_score",
                knowledge_status=(
                    KnowledgeStatus.KNOWN
                ),
                value=intensity_value,
                unit="score",
            ),
            StimulusFeature(
                metric_key="training_load_index",
                knowledge_status=(
                    KnowledgeStatus.KNOWN
                ),
                value=load_value,
                unit="au",
            ),
        ),
        created_at=dt(
            day,
            9,
        ),
    )


def association(
    source_stimulus,
    *,
    response_char: str,
    day: int,
):
    observed = dt(
        day,
        14,
    )

    return build_observed_response_association(
        association_id=(
            "pt-response-association:"
            f"a2:{response_char}"
        ),
        stimulus=source_stimulus,
        response_evidence_id=(
            "pt-evidence:session-feedback:"
            f"{response_char * 64}"
        ),
        response_evidence_hash=(
            response_char * 64
        ),
        response_workout_session_id=(
            source_stimulus.workout_session_id
        ),
        response_timing=(
            TrainingResponseTiming.SAME_DAY
        ),
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),
        response_observed_at=observed,
        response_available_at=observed,
        isolation_status=(
            ResponseIsolationStatus.UNKNOWN
        ),
        intervening_stimulus_ids=(),
        created_at=observed,
    )


def observation(
    source_stimulus,
    source_association,
    *,
    metric_key: str,
    value,
    knowledge_status=KnowledgeStatus.KNOWN,
):
    return build_response_metric_observation(
        stimulus=source_stimulus,
        association=source_association,
        measurement=TrainingResponseMeasurement(
            metric_key=metric_key,
            knowledge_status=knowledge_status,
            value=value,
            unit="score_0_10",
        ),
        created_at=dt(
            23,
            21,
        ),
    )


def build_context(
    *,
    energy_known=True,
):
    s1 = stimulus(
        session_id=SESSION_A,
        day=19,
        hash_char="a",
        load_value=100.0,
        intensity_value=4.0,
    )

    s2 = stimulus(
        session_id=SESSION_B,
        day=21,
        hash_char="b",
        load_value=200.0,
        intensity_value=7.0,
    )

    a1 = association(
        s1,
        response_char="d",
        day=19,
    )

    a2 = association(
        s2,
        response_char="e",
        day=21,
    )

    observations = [
        observation(
            s1,
            a1,
            metric_key=(
                "self_reported_fatigue_score"
            ),
            value=6.0,
        ),
        observation(
            s2,
            a2,
            metric_key=(
                "self_reported_fatigue_score"
            ),
            value=8.0,
        ),
    ]

    if energy_known:
        observations.extend(
            [
                observation(
                    s1,
                    a1,
                    metric_key=(
                        "self_reported_energy_score"
                    ),
                    value=5.0,
                ),
                observation(
                    s2,
                    a2,
                    metric_key=(
                        "self_reported_energy_score"
                    ),
                    value=3.0,
                ),
            ]
        )

    else:
        observations.extend(
            [
                observation(
                    s1,
                    a1,
                    metric_key=(
                        "self_reported_energy_score"
                    ),
                    value=None,
                    knowledge_status=(
                        KnowledgeStatus.UNKNOWN
                    ),
                ),
                observation(
                    s2,
                    a2,
                    metric_key=(
                        "self_reported_energy_score"
                    ),
                    value=None,
                    knowledge_status=(
                        KnowledgeStatus.UNKNOWN
                    ),
                ),
            ]
        )

    history = build_training_dynamics_history(
        history_id=(
            "pt-training-dynamics-history:"
            "p2-2a2"
        ),
        athlete_id=ATHLETE,
        window_start_at=dt(
            18,
            0,
        ),
        as_of=dt(
            23,
            20,
        ),
        information_cutoff_at=dt(
            23,
            20,
        ),
        stimulus_coverage=(
            TrainingDynamicsHistoryCoverage.COMPLETE
        ),
        response_coverage=(
            TrainingDynamicsHistoryCoverage.COMPLETE
        ),
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=s1,
                responses=(a1,),
            ),
            TrainingDynamicsHistoryEntry(
                stimulus=s2,
                responses=(a2,),
            ),
        ),
        source_evidence_ids=(
            a1.response_evidence_id,
            a2.response_evidence_id,
        ),
        created_at=dt(
            23,
            21,
        ),
    )

    return (
        history,
        tuple(observations),
    )


def predictor_keys():
    return (
        PersonalAssociationPredictorKey(
            metric_key="training_load_index",
            unit="au",
        ),
        PersonalAssociationPredictorKey(
            metric_key="intensity_score",
            unit="score",
        ),
    )


def patch_rejoin(
    monkeypatch,
    observations,
):
    calls = []

    def fake_rejoin(
        *,
        history,
        evidence_items,
        created_at,
    ):
        calls.append(
            (
                history.history_id,
                tuple(evidence_items),
                created_at,
            )
        )

        return tuple(
            observations
        )

    monkeypatch.setattr(
        assembly_module,
        "rejoin_response_metric_observations",
        fake_rejoin,
    )

    return calls


def test_assembles_all_response_context_predictor_combinations(
    monkeypatch,
):
    history, observations = build_context()

    patch_rejoin(
        monkeypatch,
        observations,
    )

    result = assemble_personal_association_datasets(
        history=history,
        response_evidence_items=(),
        predictor_keys=predictor_keys(),
        created_at=dt(
            24,
            2,
        ),
    )

    assert len(
        result.response_observations
    ) == 4

    assert len(
        result.response_references
    ) == 2

    assert len(
        result.reference_sufficiency
    ) == 2

    assert len(
        result.personal_references
    ) == 2

    # Two exact response contexts ? two explicit predictors.
    assert len(
        result.datasets
    ) == 4

    assert {
        (
            dataset.response_key.metric_key,
            dataset.predictor_key.metric_key,
        )
        for dataset in result.datasets
    } == {
        (
            "self_reported_energy_score",
            "intensity_score",
        ),
        (
            "self_reported_energy_score",
            "training_load_index",
        ),
        (
            "self_reported_fatigue_score",
            "intensity_score",
        ),
        (
            "self_reported_fatigue_score",
            "training_load_index",
        ),
    }

    assert all(
        dataset.observed_pair_count == 2
        for dataset in result.datasets
    )


def test_rejoin_service_is_the_only_observation_source(
    monkeypatch,
):
    history, observations = build_context()

    calls = patch_rejoin(
        monkeypatch,
        observations,
    )

    result = assemble_personal_association_datasets(
        history=history,
        response_evidence_items=(),
        predictor_keys=(
            PersonalAssociationPredictorKey(
                metric_key=(
                    "training_load_index"
                ),
                unit="au",
            ),
        ),
        created_at=dt(
            24,
            2,
        ),
    )

    assert len(calls) == 1
    assert calls[0][0] == history.history_id
    assert calls[0][1] == ()
    assert calls[0][2] == dt(
        24,
        2,
    )

    assert (
        result.response_observations
        == observations
    )


def test_unestablished_response_context_is_retained(
    monkeypatch,
):
    history, observations = build_context(
        energy_known=False,
    )

    patch_rejoin(
        monkeypatch,
        observations,
    )

    result = assemble_personal_association_datasets(
        history=history,
        response_evidence_items=(),
        predictor_keys=(
            PersonalAssociationPredictorKey(
                metric_key=(
                    "training_load_index"
                ),
                unit="au",
            ),
        ),
        created_at=dt(
            24,
            2,
        ),
    )

    assert len(
        result.response_references
    ) == 2

    assert len(
        result.datasets
    ) == 2

    personal_by_metric = {
        item.key.metric_key: item
        for item in result.personal_references
    }

    assert (
        personal_by_metric[
            "self_reported_energy_score"
        ].status
        == PersonalResponseReferenceStatus
        .UNESTABLISHED
    )

    dataset_by_metric = {
        item.response_key.metric_key: item
        for item in result.datasets
    }

    energy_dataset = dataset_by_metric[
        "self_reported_energy_score"
    ]

    assert (
        energy_dataset.observed_pair_count
        == 2
    )

    assert (
        energy_dataset.eligible_numeric_pair_count
        == 0
    )


def test_duplicate_predictor_keys_fail_closed(
    monkeypatch,
):
    history, observations = build_context()

    patch_rejoin(
        monkeypatch,
        observations,
    )

    with pytest.raises(
        ValueError,
        match="must be unique",
    ):
        assemble_personal_association_datasets(
            history=history,
            response_evidence_items=(),
            predictor_keys=(
                PersonalAssociationPredictorKey(
                    metric_key=(
                        "training_load_index"
                    ),
                    unit="au",
                ),
                PersonalAssociationPredictorKey(
                    metric_key=(
                        " training_load_index "
                    ),
                    unit="au",
                ),
            ),
            created_at=dt(
                24,
                2,
            ),
        )


def test_tampered_rejoined_observation_fails_closed(
    monkeypatch,
):
    history, observations = build_context()

    tampered = (
        replace(
            observations[0],
            value=999.0,
        ),
        *observations[1:],
    )

    patch_rejoin(
        monkeypatch,
        tampered,
    )

    with pytest.raises(
        ValueError,
        match="hash does not verify",
    ):
        assemble_personal_association_datasets(
            history=history,
            response_evidence_items=(),
            predictor_keys=(
                PersonalAssociationPredictorKey(
                    metric_key=(
                        "training_load_index"
                    ),
                    unit="au",
                ),
            ),
            created_at=dt(
                24,
                2,
            ),
        )


def test_assembly_is_deterministic_and_never_claims_association(
    monkeypatch,
):
    history, observations = build_context()

    patch_rejoin(
        monkeypatch,
        observations,
    )

    first = assemble_personal_association_datasets(
        history=history,
        response_evidence_items=(),
        predictor_keys=predictor_keys(),
        created_at=dt(
            24,
            2,
        ),
    )

    patch_rejoin(
        monkeypatch,
        tuple(
            reversed(
                observations
            )
        ),
    )

    second = assemble_personal_association_datasets(
        history=history,
        response_evidence_items=(),
        predictor_keys=tuple(
            reversed(
                predictor_keys()
            )
        ),
        created_at=dt(
            24,
            3,
        ),
    )

    assert (
        first.predictor_keys
        == second.predictor_keys
    )

    assert tuple(
        dataset.dataset_id
        for dataset in first.datasets
    ) == tuple(
        dataset.dataset_id
        for dataset in second.datasets
    )

    assert (
        first.evidence_level_ceiling
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert first.association_supported is False
    assert (
        first.prospective_validation_established
        is False
    )
    assert (
        first.causal_attribution_established
        is False
    )
    assert (
        first.effect_inference_authorized
        is False
    )
    assert (
        first.readiness_inference_authorized
        is False
    )
    assert (
        first.performance_prediction_authorized
        is False
    )
    assert (
        first.prescription_change_authorized
        is False
    )
    assert first.planning_authorized is False

    assert all(
        (
            dataset.evidence_level_ceiling
            == EffectEvidenceLevel.DESCRIPTIVE
        )
        and dataset.association_supported is False
        and dataset.planning_authorized is False
        for dataset in first.datasets
    )
