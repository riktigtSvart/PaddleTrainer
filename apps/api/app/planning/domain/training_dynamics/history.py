from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from .models import (
    ObservedResponseAssociation,
    RealizedTrainingStimulus,
)


TRAINING_DYNAMICS_HISTORY_SCHEMA_V01 = (
    "training-dynamics-history-v0.1"
)

TRAINING_DYNAMICS_HISTORY_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "history_id",
        "created_at",
        "content_hash",
    }
)


class TrainingDynamicsHistoryCoverage(StrEnum):
    """Scientific/source coverage, not database-query completeness."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrainingDynamicsHistoryEntry:
    stimulus: RealizedTrainingStimulus
    responses: tuple[
        ObservedResponseAssociation,
        ...,
    ]


@dataclass(frozen=True)
class TrainingDynamicsHistory:
    """Cutoff-safe descriptive stimulus/response history.

    This is historical evidence organization only. It does not estimate
    fatigue, adaptation, causality, performance, retention or prescription.
    """

    history_id: str
    schema_version: str

    athlete_id: str

    window_start_at: datetime
    as_of: datetime
    information_cutoff_at: datetime

    stimulus_coverage: TrainingDynamicsHistoryCoverage
    response_coverage: TrainingDynamicsHistoryCoverage

    entries: tuple[
        TrainingDynamicsHistoryEntry,
        ...,
    ]

    source_evidence_ids: tuple[str, ...]

    effect_inference_authorized: bool
    causal_attribution_established: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    TRAINING_DYNAMICS_HISTORY_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _canonical_uuid(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty UUID string."
        )

    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ValueError(
            f"{field_name} must be a canonical UUID."
        ) from None

    canonical = str(parsed)

    if canonical != value:
        raise ValueError(
            f"{field_name} must be a canonical UUID."
        )

    return canonical


def _ordered_unique_strings(
    values,
    *,
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(values)

    for value in normalized:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{field_name} must contain non-empty strings."
            )

    if len(set(normalized)) != len(normalized):
        raise ValueError(
            f"{field_name} must not contain duplicates."
        )

    return tuple(sorted(normalized))


def build_training_dynamics_history(
    *,
    history_id: str,
    athlete_id: str,
    window_start_at: datetime,
    as_of: datetime,
    information_cutoff_at: datetime,
    stimulus_coverage: TrainingDynamicsHistoryCoverage,
    response_coverage: TrainingDynamicsHistoryCoverage,
    entries: tuple[
        TrainingDynamicsHistoryEntry,
        ...,
    ],
    source_evidence_ids: tuple[str, ...],
    created_at: datetime,
) -> TrainingDynamicsHistory:
    if (
        not isinstance(history_id, str)
        or not history_id.strip()
    ):
        raise ValueError(
            "history_id must be non-empty."
        )

    if not history_id.startswith(
        "pt-training-dynamics-history:"
    ):
        raise ValueError(
            "history_id must use "
            "pt-training-dynamics-history: namespace."
        )

    canonical_athlete = _canonical_uuid(
        athlete_id,
        field_name="athlete_id",
    )

    start = to_utc(
        window_start_at,
        field_name="window_start_at",
    )

    state_as_of = to_utc(
        as_of,
        field_name="as_of",
    )

    cutoff = to_utc(
        information_cutoff_at,
        field_name="information_cutoff_at",
    )

    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if start > state_as_of:
        raise ValueError(
            "window_start_at must not be after as_of."
        )

    if cutoff > state_as_of:
        raise ValueError(
            "information_cutoff_at must not be after as_of."
        )

    if created < state_as_of:
        raise ValueError(
            "Training-dynamics history cannot be created "
            "before as_of."
        )

    stimulus_coverage_value = (
        TrainingDynamicsHistoryCoverage(
            stimulus_coverage
        )
    )

    response_coverage_value = (
        TrainingDynamicsHistoryCoverage(
            response_coverage
        )
    )

    raw_entries = tuple(entries)

    stimulus_ids: set[str] = set()
    response_ids: set[str] = set()

    normalized_entries = []

    for entry in raw_entries:
        stimulus = entry.stimulus

        if not stimulus.verify_content_hash():
            raise ValueError(
                "History stimulus hash does not verify."
            )

        if stimulus.athlete_id != canonical_athlete:
            raise ValueError(
                "History stimulus belongs to another athlete."
            )

        if not (
            start
            <= stimulus.exposure_observed_at
            <= state_as_of
        ):
            raise ValueError(
                "History stimulus lies outside the history window."
            )

        if stimulus.stimulus_id in stimulus_ids:
            raise ValueError(
                "Duplicate history stimulus identity."
            )

        stimulus_ids.add(
            stimulus.stimulus_id
        )

        ordered_responses = tuple(
            sorted(
                tuple(entry.responses),
                key=lambda response: (
                    response.response_observed_at,
                    response.association_id,
                ),
            )
        )

        for response in ordered_responses:
            if not response.verify_content_hash():
                raise ValueError(
                    "History response-association hash "
                    "does not verify."
                )

            if response.athlete_id != canonical_athlete:
                raise ValueError(
                    "History response belongs to another athlete."
                )

            if (
                response.stimulus_id
                != stimulus.stimulus_id
                or response.stimulus_content_hash
                != stimulus.content_hash
            ):
                raise ValueError(
                    "History response does not belong to "
                    "its entry stimulus."
                )

            if response.response_observed_at > state_as_of:
                raise ValueError(
                    "History response is observed after as_of."
                )

            if response.response_available_at > cutoff:
                raise ValueError(
                    "History response is unavailable at "
                    "the information cutoff."
                )

            if response.association_id in response_ids:
                raise ValueError(
                    "Duplicate history response identity."
                )

            response_ids.add(
                response.association_id
            )

            if (
                response.causal_attribution_established
                is not False
                or response.effect_inference_authorized
                is not False
                or response.planning_authorized
                is not False
            ):
                raise ValueError(
                    "History response contains unsupported "
                    "stronger authority."
                )

        normalized_entries.append(
            TrainingDynamicsHistoryEntry(
                stimulus=stimulus,
                responses=ordered_responses,
            )
        )

    ordered_entries = tuple(
        sorted(
            normalized_entries,
            key=lambda entry: (
                entry.stimulus.exposure_observed_at,
                entry.stimulus.stimulus_id,
            ),
        )
    )

    source_ids = _ordered_unique_strings(
        source_evidence_ids,
        field_name="source_evidence_ids",
    )

    provisional = TrainingDynamicsHistory(
        history_id=history_id,
        schema_version=(
            TRAINING_DYNAMICS_HISTORY_SCHEMA_V01
        ),
        athlete_id=canonical_athlete,
        window_start_at=start,
        as_of=state_as_of,
        information_cutoff_at=cutoff,
        stimulus_coverage=stimulus_coverage_value,
        response_coverage=response_coverage_value,
        entries=ordered_entries,
        source_evidence_ids=source_ids,

        # P2.1B is descriptive organization only.
        effect_inference_authorized=False,
        causal_attribution_established=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,

        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            TRAINING_DYNAMICS_HISTORY_HASH_EXCLUDE_FIELDS
        ),
    )

    return TrainingDynamicsHistory(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )
