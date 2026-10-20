from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from ..domain.common.time import to_utc
from ..domain.evidence.models import (
    EvidenceItem,
    EvidenceQuality,
)
from ..domain.executed_training import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
)
from ..domain.training_dynamics import (
    RealizedTrainingStimulus,
    ResponseIsolationStatus,
    build_realized_training_stimulus,
)
from ..domain.training_dynamics.history import (
    TrainingDynamicsHistory,
    TrainingDynamicsHistoryCoverage,
    TrainingDynamicsHistoryEntry,
    build_training_dynamics_history,
)
from ..domain.training_state.evidence import (
    EXECUTED_TRAINING_SESSION,
    EXECUTED_TRAINING_SESSION_SCHEMA_V02,
    SESSION_FEEDBACK,
    SESSION_FEEDBACK_SCHEMA_V01,
)
from ..ports.evidence import AsyncEvidenceRepository
from .assemble_training_dynamics import (
    assemble_observed_response_association,
)
from .collect_evidence import (
    collect_available_evidence_async,
)
from .project_authoritative_executed_training import (
    AUTHORITATIVE_EXECUTED_TRAINING_SOURCE_SYSTEM,
)


def _payload(
    evidence: EvidenceItem,
) -> Mapping[str, object]:
    payload = evidence.payload

    if not isinstance(payload, Mapping):
        raise ValueError(
            "Evidence payload must be a mapping."
        )

    return payload


def _string(
    value: object,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )

    return value


def _bool(
    value: object,
    *,
    field_name: str,
) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be boolean."
        )

    return value


def _assemble_stimulus_from_evidence(
    evidence: EvidenceItem,
    *,
    created_at: datetime,
) -> RealizedTrainingStimulus:
    if not evidence.verify_content_hash():
        raise ValueError(
            "Executed-training evidence hash does not verify."
        )

    if evidence.evidence_type != EXECUTED_TRAINING_SESSION:
        raise ValueError(
            "Expected EXECUTED_TRAINING_SESSION evidence."
        )

    if evidence.provenance != ProvenanceKind.DERIVED:
        raise ValueError(
            "P2.1B requires authoritative derived "
            "executed-training evidence."
        )

    if evidence.knowledge_status != KnowledgeStatus.KNOWN:
        raise ValueError(
            "Executed-training session identity must be KNOWN."
        )

    if evidence.quality != EvidenceQuality.HIGH:
        raise ValueError(
            "Unexpected executed-training evidence quality."
        )

    payload = _payload(evidence)

    schema = _string(
        payload.get("schema_version"),
        field_name="payload.schema_version",
    )

    if schema != EXECUTED_TRAINING_SESSION_SCHEMA_V02:
        raise ValueError(
            "P2.1B requires authoritative executed-training "
            "evidence schema v0.2."
        )

    session_id = _string(
        payload.get("session_id"),
        field_name="payload.session_id",
    )

    modality_key = _string(
        payload.get("modality_key"),
        field_name="payload.modality_key",
    )

    duration_status = KnowledgeStatus(
        _string(
            payload.get("duration_status"),
            field_name="payload.duration_status",
        )
    )

    duration_s = payload.get("duration_s")

    authoritative_id = _string(
        payload.get("authoritative_execution_evidence_id"),
        field_name=(
            "payload.authoritative_execution_evidence_id"
        ),
    )

    authoritative_hash = _string(
        payload.get("authoritative_execution_evidence_hash"),
        field_name=(
            "payload.authoritative_execution_evidence_hash"
        ),
    )

    if (
        evidence.source_ref.source_system
        != AUTHORITATIVE_EXECUTED_TRAINING_SOURCE_SYSTEM
        or evidence.source_ref.source_record_id
        != authoritative_id
        or evidence.source_ref.source_version
        != AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
        or evidence.source_ref.source_content_hash
        != authoritative_hash
    ):
        raise ValueError(
            "Executed-training source reference does not match "
            "its authoritative provenance."
        )

    if (
        _bool(
            payload.get("plan_identity_linked"),
            field_name="payload.plan_identity_linked",
        )
        is not True
    ):
        raise ValueError(
            "Executed-training evidence must preserve plan identity."
        )

    if (
        _string(
            payload.get("plan_content_at_execution_status"),
            field_name=(
                "payload.plan_content_at_execution_status"
            ),
        )
        != "unverified"
    ):
        raise ValueError(
            "Executed-training evidence contains unsupported "
            "historical plan-content authority."
        )

    for field_name in (
        "occurrence_alignment_verified",
        "phase_alignment_verified",
        "provider_event_verified",
        "clock_alignment_verified",
        "actual_boundary_verified",
        "temporal_match_used",
    ):
        if (
            _bool(
                payload.get(field_name),
                field_name=f"payload.{field_name}",
            )
            is not False
        ):
            raise ValueError(
                f"{field_name} must remain false."
            )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    if materialized < evidence.available_at:
        raise ValueError(
            "Realized stimulus cannot predate source availability."
        )

    return build_realized_training_stimulus(
        stimulus_id=(
            "pt-training-stimulus:"
            f"session:{session_id}"
        ),
        athlete_id=evidence.athlete_id,
        workout_session_id=session_id,
        executed_training_evidence_id=authoritative_id,
        executed_training_evidence_hash=authoritative_hash,
        exposure_observed_at=evidence.observed_at,
        modality_key=modality_key,
        duration_status=duration_status,
        duration_s=duration_s,
        features=(),
        created_at=materialized,
    )


def build_training_dynamics_history_from_evidence(
    *,
    items: tuple[EvidenceItem, ...],
    history_id: str,
    athlete_id: str,
    window_start_at: datetime,
    as_of: datetime,
    information_cutoff_at: datetime,
    stimulus_coverage: TrainingDynamicsHistoryCoverage,
    response_coverage: TrainingDynamicsHistoryCoverage,
    created_at: datetime,
) -> TrainingDynamicsHistory:
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

    materialized = to_utc(
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

    evidence_items = tuple(items)

    for item in evidence_items:
        if item.athlete_id != athlete_id:
            raise ValueError(
                "Evidence collection contains another athlete."
            )

        if not item.verify_content_hash():
            raise ValueError(
                "Evidence item content hash does not verify."
            )

        if (
            item.observed_at > cutoff
            or item.available_at > cutoff
        ):
            raise ValueError(
                "Evidence item is unavailable at "
                "the information cutoff."
            )

    executed_items = []

    for item in evidence_items:
        if item.evidence_type != EXECUTED_TRAINING_SESSION:
            continue

        payload = _payload(item)

        # Legacy v0.1 training exposure remains valid for P1 state, but
        # P2 dynamics requires the authoritative v0.2 provenance chain.
        if (
            payload.get("schema_version")
            != EXECUTED_TRAINING_SESSION_SCHEMA_V02
        ):
            continue

        executed_items.append(item)

    all_stimuli: list[tuple[RealizedTrainingStimulus, EvidenceItem]] = []
    stimulus_by_session: dict[
        str,
        tuple[RealizedTrainingStimulus, EvidenceItem],
    ] = {}

    for item in executed_items:
        stimulus = _assemble_stimulus_from_evidence(
            item,
            created_at=materialized,
        )

        if stimulus.workout_session_id in stimulus_by_session:
            raise ValueError(
                "Duplicate authoritative stimulus session identity."
            )

        stimulus_by_session[
            stimulus.workout_session_id
        ] = (
            stimulus,
            item,
        )

        all_stimuli.append(
            (
                stimulus,
                item,
            )
        )

    target_stimuli = tuple(
        (
            stimulus,
            source_item,
        )
        for stimulus, source_item in all_stimuli
        if (
            start
            <= stimulus.exposure_observed_at
            <= state_as_of
        )
    )

    target_sessions = {
        stimulus.workout_session_id
        for stimulus, _ in target_stimuli
    }

    responses_by_session: dict[
        str,
        list[EvidenceItem],
    ] = {
        session_id: []
        for session_id in target_sessions
    }

    for item in evidence_items:
        if item.evidence_type != SESSION_FEEDBACK:
            continue

        payload = _payload(item)

        if (
            payload.get("schema_version")
            != SESSION_FEEDBACK_SCHEMA_V01
        ):
            raise ValueError(
                "Unsupported SESSION_FEEDBACK evidence schema."
            )

        session_id = _string(
            payload.get("session_id"),
            field_name="payload.session_id",
        )

        # The history window is stimulus-based. A response to a stimulus
        # outside this window is intentionally not pulled into the history.
        if session_id not in target_sessions:
            continue

        responses_by_session[
            session_id
        ].append(item)

    entries = []
    source_evidence_ids: set[str] = set()

    stimulus_coverage_value = (
        TrainingDynamicsHistoryCoverage(
            stimulus_coverage
        )
    )

    for stimulus, stimulus_item in target_stimuli:
        source_evidence_ids.add(
            stimulus_item.evidence_id
        )

        response_items = tuple(
            sorted(
                responses_by_session[
                    stimulus.workout_session_id
                ],
                key=lambda item: (
                    item.observed_at,
                    item.evidence_id,
                ),
            )
        )

        associations = []

        for response_item in response_items:
            intervening = tuple(
                candidate
                for candidate, _ in all_stimuli
                if (
                    stimulus.exposure_observed_at
                    < candidate.exposure_observed_at
                    < response_item.observed_at
                    and candidate.stimulus_id
                    != stimulus.stimulus_id
                )
            )

            association = (
                assemble_observed_response_association(
                    stimulus=stimulus,
                    response_evidence=response_item,
                    intervening_stimuli=intervening,
                    intervening_history_complete=(
                        stimulus_coverage_value
                        == TrainingDynamicsHistoryCoverage.COMPLETE
                    ),
                    created_at=materialized,
                )
            )

            associations.append(
                association
            )

            source_evidence_ids.add(
                response_item.evidence_id
            )

            for candidate, candidate_item in all_stimuli:
                if candidate.stimulus_id in (
                    association.intervening_stimulus_ids
                ):
                    source_evidence_ids.add(
                        candidate_item.evidence_id
                    )

        entries.append(
            TrainingDynamicsHistoryEntry(
                stimulus=stimulus,
                responses=tuple(associations),
            )
        )

    return build_training_dynamics_history(
        history_id=history_id,
        athlete_id=athlete_id,
        window_start_at=start,
        as_of=state_as_of,
        information_cutoff_at=cutoff,
        stimulus_coverage=stimulus_coverage_value,
        response_coverage=response_coverage,
        entries=tuple(entries),
        source_evidence_ids=tuple(
            source_evidence_ids
        ),
        created_at=materialized,
    )


async def build_training_dynamics_history_from_repository(
    *,
    repository: AsyncEvidenceRepository,
    bundle_id: str,
    history_id: str,
    athlete_id: str,
    window_start_at: datetime,
    as_of: datetime,
    information_cutoff_at: datetime,
    stimulus_coverage: TrainingDynamicsHistoryCoverage,
    response_coverage: TrainingDynamicsHistoryCoverage,
    created_at: datetime,
) -> TrainingDynamicsHistory:
    """Build cutoff-safe P2 history from durable generic evidence."""

    bundle = await collect_available_evidence_async(
        repository=repository,
        bundle_id=bundle_id,
        athlete_id=athlete_id,
        as_of=as_of,
        information_cutoff_at=information_cutoff_at,
        created_at=created_at,
    )

    return build_training_dynamics_history_from_evidence(
        items=bundle.items,
        history_id=history_id,
        athlete_id=athlete_id,
        window_start_at=window_start_at,
        as_of=as_of,
        information_cutoff_at=information_cutoff_at,
        stimulus_coverage=stimulus_coverage,
        response_coverage=response_coverage,
        created_at=created_at,
    )
