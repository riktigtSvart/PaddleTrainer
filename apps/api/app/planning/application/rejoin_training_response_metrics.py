from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..domain.common.enums import KnowledgeStatus
from ..domain.common.time import to_utc
from ..domain.evidence.models import EvidenceItem
from ..domain.response_evidence import (
    TrainingResponseMeasurement,
)
from ..domain.training_dynamics.history import (
    TRAINING_DYNAMICS_HISTORY_SCHEMA_V01,
    TrainingDynamicsHistory,
)
from ..domain.training_dynamics.response_metrics import (
    ResponseMetricObservation,
    build_response_metric_observation,
)
from .assemble_training_dynamics import (
    _validated_session_feedback,
)


def _measurement_from_payload(
    raw: object,
) -> TrainingResponseMeasurement:
    if not isinstance(raw, Mapping):
        raise ValueError(
            "SESSION_FEEDBACK measurement must be a mapping."
        )

    metric_key = raw.get("metric_key")

    if (
        not isinstance(metric_key, str)
        or not metric_key.strip()
    ):
        raise ValueError(
            "Response measurement metric_key must be "
            "a non-empty string."
        )

    knowledge_raw = raw.get(
        "knowledge_status"
    )

    if not isinstance(knowledge_raw, str):
        raise ValueError(
            "Response measurement knowledge_status "
            "must be a string."
        )

    unit = raw.get("unit")

    if (
        unit is not None
        and not isinstance(unit, str)
    ):
        raise ValueError(
            "Response measurement unit must be "
            "a string or null."
        )

    return TrainingResponseMeasurement(
        metric_key=metric_key,
        knowledge_status=KnowledgeStatus(
            knowledge_raw
        ),
        value=raw.get("value"),
        unit=unit,
    )


def rejoin_response_metric_observations(
    *,
    history: TrainingDynamicsHistory,
    evidence_items: tuple[EvidenceItem, ...],
    created_at: datetime,
) -> tuple[ResponseMetricObservation, ...]:
    """Rejoin historical associations to exact durable response evidence.

    Only evidence explicitly referenced by the history is consumed.
    Extra evidence does not create additional observations.
    """

    if not history.verify_content_hash():
        raise ValueError(
            "Training-dynamics history hash does not verify."
        )

    if (
        history.schema_version
        != TRAINING_DYNAMICS_HISTORY_SCHEMA_V01
    ):
        raise ValueError(
            "Unsupported training-dynamics history schema."
        )

    if (
        history.causal_attribution_established is not False
        or history.effect_inference_authorized is not False
        or history.performance_prediction_authorized is not False
        or history.prescription_change_authorized is not False
    ):
        raise ValueError(
            "Training-dynamics history contains unsupported "
            "stronger authority."
        )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    if materialized < history.created_at:
        raise ValueError(
            "Response-metric rejoin cannot predate "
            "the source history."
        )

    by_id: dict[str, EvidenceItem] = {}

    for item in tuple(evidence_items):
        if item.evidence_id in by_id:
            raise ValueError(
                "Duplicate evidence identity supplied "
                "to response-metric rejoin."
            )

        by_id[item.evidence_id] = item

    observations = []

    for entry in history.entries:
        stimulus = entry.stimulus

        for association in entry.responses:
            evidence = by_id.get(
                association.response_evidence_id
            )

            if evidence is None:
                raise ValueError(
                    "Referenced SESSION_FEEDBACK evidence "
                    "is missing from response-metric rejoin."
                )

            if not evidence.verify_content_hash():
                raise ValueError(
                    "Referenced response evidence hash "
                    "does not verify."
                )

            if (
                evidence.content_hash
                != association.response_evidence_hash
            ):
                raise ValueError(
                    "Response evidence hash does not match "
                    "the historical association."
                )

            if evidence.athlete_id != history.athlete_id:
                raise ValueError(
                    "Response evidence belongs to another athlete."
                )

            if (
                evidence.observed_at
                != association.response_observed_at
                or evidence.available_at
                != association.response_available_at
            ):
                raise ValueError(
                    "Response evidence timestamps do not match "
                    "the historical association."
                )

            if (
                evidence.observed_at > history.as_of
                or evidence.available_at
                > history.information_cutoff_at
            ):
                raise ValueError(
                    "Response evidence is unavailable in "
                    "the history replay context."
                )

            if materialized < evidence.created_at:
                raise ValueError(
                    "Response-metric observation cannot predate "
                    "its durable response evidence."
                )

            timing, link_basis = (
                _validated_session_feedback(
                    evidence,
                    stimulus=stimulus,
                )
            )

            if timing != association.response_timing:
                raise ValueError(
                    "Response timing does not match "
                    "the historical association."
                )

            if link_basis != association.session_link_basis:
                raise ValueError(
                    "Response link basis does not match "
                    "the historical association."
                )

            payload = evidence.payload

            if not isinstance(payload, Mapping):
                raise ValueError(
                    "SESSION_FEEDBACK payload must be a mapping."
                )

            raw_measurements = payload.get(
                "measurements"
            )

            if not isinstance(
                raw_measurements,
                (tuple, list),
            ):
                raise ValueError(
                    "SESSION_FEEDBACK measurements must be "
                    "a sequence."
                )

            if not raw_measurements:
                raise ValueError(
                    "SESSION_FEEDBACK requires at least "
                    "one measurement."
                )

            measurements = tuple(
                _measurement_from_payload(raw)
                for raw in raw_measurements
            )

            metric_keys = tuple(
                measurement.metric_key
                for measurement in measurements
            )

            if (
                len(set(metric_keys))
                != len(metric_keys)
            ):
                raise ValueError(
                    "SESSION_FEEDBACK measurement keys "
                    "must be unique."
                )

            for measurement in measurements:
                observations.append(
                    build_response_metric_observation(
                        stimulus=stimulus,
                        association=association,
                        measurement=measurement,
                        created_at=materialized,
                    )
                )

    return tuple(
        sorted(
            observations,
            key=lambda observation: (
                observation.response_observed_at,
                observation.workout_session_id,
                observation.metric_key,
                observation.observation_id,
            ),
        )
    )
