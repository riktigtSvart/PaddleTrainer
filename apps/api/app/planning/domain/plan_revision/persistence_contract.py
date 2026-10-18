from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import json

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
    compute_content_hash,
)
from ..common.time import to_utc


PLAN_IDENTITY_HASH_EXCLUDE_FIELDS = frozenset({'content_hash'})
PLAN_REVISION_HASH_EXCLUDE_FIELDS = frozenset({'content_hash'})
ADOPTION_BINDING_HASH_EXCLUDE_FIELDS = frozenset({'content_hash'})


class PlanRevisionOrigin(StrEnum):
    ADOPTED_CURRENT_STATE = 'adopted_current_state'
    PLANNER_CREATED = 'planner_created'
    EXTERNAL_RECONCILED = 'external_reconciled'


class PlanHistoryClaim(StrEnum):
    CURRENT_STATE_BASELINE_ONLY = 'current_state_baseline_only'
    VERIFIED_FROM_AUTHORITY_START = 'verified_from_authority_start'


class OccurrenceLineageKind(StrEnum):
    NEW = 'new'
    PRESERVED = 'preserved'


class AuthoritativePlanConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthoritativePlanIdentity:
    logical_plan_id: str
    athlete_id: str
    source_workout_id: str | None
    current_revision_id: str | None
    current_revision_number: int
    authority_established_at: datetime | None
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return compute_content_hash(
            self,
            exclude_fields=PLAN_IDENTITY_HASH_EXCLUDE_FIELDS,
        ) == self.content_hash


def finalize_authoritative_plan_identity(
    *,
    logical_plan_id: str,
    athlete_id: str,
    source_workout_id: str | None,
    current_revision_id: str | None,
    current_revision_number: int,
    authority_established_at: datetime | None,
) -> AuthoritativePlanIdentity:
    if not logical_plan_id.strip():
        raise ValueError('logical_plan_id must be non-empty.')
    if not athlete_id.strip():
        raise ValueError('athlete_id must be non-empty.')
    if source_workout_id is not None and not source_workout_id.strip():
        raise ValueError('source_workout_id must be non-empty when present.')
    if current_revision_number < 0:
        raise ValueError('current_revision_number must be >= 0.')
    if current_revision_id is None:
        if current_revision_number != 0:
            raise ValueError('No current revision requires revision number 0.')
        if authority_established_at is not None:
            raise ValueError('Unadopted plan cannot have authority_established_at.')
        established = None
    else:
        if not current_revision_id.strip():
            raise ValueError('current_revision_id must be non-empty when present.')
        if current_revision_number < 1:
            raise ValueError('Current revision requires revision number >= 1.')
        if authority_established_at is None:
            raise ValueError('Current revision requires authority_established_at.')
        established = to_utc(
            authority_established_at,
            field_name='authority_established_at',
        )

    provisional = AuthoritativePlanIdentity(
        logical_plan_id=logical_plan_id,
        athlete_id=athlete_id,
        source_workout_id=source_workout_id,
        current_revision_id=current_revision_id,
        current_revision_number=current_revision_number,
        authority_established_at=established,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash='',
    )
    return AuthoritativePlanIdentity(
        **{
            **provisional.__dict__,
            'content_hash': compute_content_hash(
                provisional,
                exclude_fields=PLAN_IDENTITY_HASH_EXCLUDE_FIELDS,
            ),
        }
    )


@dataclass(frozen=True)
class RevisionOccurrence:
    occurrence_id: str
    ordinal: int
    lineage_kind: OccurrenceLineageKind
    source_capture_occurrence_id: str | None = None

    def __post_init__(self) -> None:
        if not self.occurrence_id.startswith('pt-occ:'):
            raise ValueError(
                'occurrence_id must use planning-owned pt-occ: namespace.'
            )
        if self.ordinal < 0:
            raise ValueError('ordinal must be >= 0.')
        if (
            self.source_capture_occurrence_id is not None
            and not self.source_capture_occurrence_id.strip()
        ):
            raise ValueError(
                'source_capture_occurrence_id must be non-empty when present.'
            )


@dataclass(frozen=True)
class RevisionDecisionLineage:
    context_hash: str
    decision_hash: str
    rationale_hash: str
    instruction_hash: str

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if not value.strip():
                raise ValueError(f'{field_name} must be non-empty.')


@dataclass(frozen=True)
class AdoptionSourceRef:
    capture_id: str
    capture_content_hash: str
    source_read_content_hash: str
    source_content_sha256: str
    external_contract_plan_id: str
    external_contract_plan_revision: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ('capture_id', self.capture_id),
            ('capture_content_hash', self.capture_content_hash),
            ('source_read_content_hash', self.source_read_content_hash),
            ('source_content_sha256', self.source_content_sha256),
            ('external_contract_plan_id', self.external_contract_plan_id),
        ):
            if not value.strip():
                raise ValueError(f'{field_name} must be non-empty.')
        if self.external_contract_plan_revision < 1:
            raise ValueError('external_contract_plan_revision must be >= 1.')


@dataclass(frozen=True)
class AuthoritativePlanRevision:
    revision_id: str
    logical_plan_id: str
    athlete_id: str
    revision_number: int
    previous_revision_id: str | None
    origin: PlanRevisionOrigin
    history_claim: PlanHistoryClaim
    authority_established_at: datetime
    effective_from: datetime
    created_at: datetime

    contract_schema_version: str
    canonical_contract_json: str
    contract_content_hash: str
    occurrences: tuple[RevisionOccurrence, ...]

    adoption_source: AdoptionSourceRef | None
    decision_lineage: RevisionDecisionLineage | None

    content_hash_algorithm: str
    content_hash: str

    def verify_contract_hash(self) -> bool:
        parsed = json.loads(self.canonical_contract_json)
        return compute_content_hash(
            parsed,
            exclude_fields=frozenset(),
        ) == self.contract_content_hash

    def verify_content_hash(self) -> bool:
        return compute_content_hash(
            self,
            exclude_fields=PLAN_REVISION_HASH_EXCLUDE_FIELDS,
        ) == self.content_hash


def finalize_authoritative_plan_revision(
    *,
    revision_id: str,
    logical_plan_id: str,
    athlete_id: str,
    revision_number: int,
    previous_revision_id: str | None,
    origin: PlanRevisionOrigin,
    history_claim: PlanHistoryClaim,
    authority_established_at: datetime,
    effective_from: datetime,
    created_at: datetime,
    contract_schema_version: str,
    contract_json: str,
    occurrences: tuple[RevisionOccurrence, ...],
    adoption_source: AdoptionSourceRef | None,
    decision_lineage: RevisionDecisionLineage | None,
) -> AuthoritativePlanRevision:
    for field_name, value in (
        ('revision_id', revision_id),
        ('logical_plan_id', logical_plan_id),
        ('athlete_id', athlete_id),
        ('contract_schema_version', contract_schema_version),
    ):
        if not value.strip():
            raise ValueError(f'{field_name} must be non-empty.')
    if not revision_id.startswith('pt-plan-rev:'):
        raise ValueError('revision_id must use planning-owned pt-plan-rev: namespace.')
    if revision_number < 1:
        raise ValueError('revision_number must be >= 1.')

    authority_at = to_utc(
        authority_established_at,
        field_name='authority_established_at',
    )
    effective = to_utc(effective_from, field_name='effective_from')
    created = to_utc(created_at, field_name='created_at')
    if created < authority_at:
        raise ValueError('created_at must not precede authority_established_at.')

    if revision_number == 1:
        if previous_revision_id is not None:
            raise ValueError('Revision 1 must not have previous_revision_id.')
    else:
        if previous_revision_id is None or not previous_revision_id.strip():
            raise ValueError('Revision > 1 requires previous_revision_id.')

    if origin == PlanRevisionOrigin.ADOPTED_CURRENT_STATE:
        if revision_number != 1:
            raise ValueError('Adopted current state must be revision 1.')
        if history_claim != PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY:
            raise ValueError(
                'Adopted current state cannot claim verified pre-adoption history.'
            )
        if adoption_source is None:
            raise ValueError('Adopted current state requires adoption_source.')
        if decision_lineage is not None:
            raise ValueError('Adoption baseline must not invent decision lineage.')
    elif origin == PlanRevisionOrigin.PLANNER_CREATED:
        if adoption_source is not None:
            raise ValueError('Planner-created revision must not carry adoption_source.')
        if decision_lineage is None:
            raise ValueError('Planner-created revision requires decision_lineage.')
        if history_claim != PlanHistoryClaim.VERIFIED_FROM_AUTHORITY_START:
            raise ValueError(
                'Planner-created revision must preserve authority-window history claim.'
            )
    else:
        # External reconciliation is reserved for a later implementation phase.
        if decision_lineage is None:
            raise ValueError(
                'External reconciliation requires explicit decision lineage in P1.1.'
            )

    if not occurrences:
        raise ValueError('At least one occurrence is required in P1.1.')
    occurrence_ids = tuple(item.occurrence_id for item in occurrences)
    ordinals = tuple(item.ordinal for item in occurrences)
    if len(occurrence_ids) != len(set(occurrence_ids)):
        raise ValueError('occurrence IDs must be unique within a revision.')
    if len(ordinals) != len(set(ordinals)):
        raise ValueError('occurrence ordinals must be unique within a revision.')
    if tuple(sorted(ordinals)) != tuple(range(len(ordinals))):
        raise ValueError('occurrence ordinals must be contiguous from zero.')

    if origin == PlanRevisionOrigin.ADOPTED_CURRENT_STATE:
        if any(
            item.lineage_kind != OccurrenceLineageKind.NEW
            for item in occurrences
        ):
            raise ValueError('Adoption baseline occurrences must all be NEW.')
        if any(
            item.source_capture_occurrence_id is None
            for item in occurrences
        ):
            raise ValueError(
                'Adoption baseline must retain capture occurrence provenance.'
            )
    else:
        if any(
            item.source_capture_occurrence_id is not None
            for item in occurrences
        ):
            raise ValueError(
                'Only adoption baseline may bind capture-scoped occurrence IDs.'
            )

    parsed = json.loads(contract_json)
    canonical_contract = canonical_json(parsed)
    contract_hash = compute_content_hash(
        parsed,
        exclude_fields=frozenset(),
    )

    provisional = AuthoritativePlanRevision(
        revision_id=revision_id,
        logical_plan_id=logical_plan_id,
        athlete_id=athlete_id,
        revision_number=revision_number,
        previous_revision_id=previous_revision_id,
        origin=origin,
        history_claim=history_claim,
        authority_established_at=authority_at,
        effective_from=effective,
        created_at=created,
        contract_schema_version=contract_schema_version,
        canonical_contract_json=canonical_contract,
        contract_content_hash=contract_hash,
        occurrences=tuple(sorted(occurrences, key=lambda item: item.ordinal)),
        adoption_source=adoption_source,
        decision_lineage=decision_lineage,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash='',
    )
    return AuthoritativePlanRevision(
        **{
            **provisional.__dict__,
            'content_hash': compute_content_hash(
                provisional,
                exclude_fields=PLAN_REVISION_HASH_EXCLUDE_FIELDS,
            ),
        }
    )


def validate_revision_transition(
    *,
    previous: AuthoritativePlanRevision,
    candidate: AuthoritativePlanRevision,
) -> None:
    if not previous.verify_content_hash():
        raise ValueError('Previous revision hash does not verify.')
    if not candidate.verify_content_hash():
        raise ValueError('Candidate revision hash does not verify.')
    if previous.logical_plan_id != candidate.logical_plan_id:
        raise ValueError('logical_plan_id cannot change across revisions.')
    if previous.athlete_id != candidate.athlete_id:
        raise ValueError('athlete_id cannot change across revisions.')
    if candidate.revision_number != previous.revision_number + 1:
        raise ValueError('revision_number must increase exactly by one.')
    if candidate.previous_revision_id != previous.revision_id:
        raise ValueError('previous_revision_id must reference current revision.')
    if candidate.authority_established_at != previous.authority_established_at:
        raise ValueError('authority_established_at is immutable for a logical plan.')

    previous_ids = {item.occurrence_id for item in previous.occurrences}
    for item in candidate.occurrences:
        if item.lineage_kind == OccurrenceLineageKind.PRESERVED:
            if item.occurrence_id not in previous_ids:
                raise ValueError(
                    'PRESERVED occurrence must exist in previous revision.'
                )
        elif item.lineage_kind == OccurrenceLineageKind.NEW:
            if item.occurrence_id in previous_ids:
                raise ValueError(
                    'NEW occurrence must not reuse a previous occurrence ID.'
                )


@dataclass(frozen=True)
class CurrentStateAdoptionBinding:
    logical_plan_id: str
    source_workout_id: str
    expected_source_content_sha256: str
    adopted_revision_id: str
    authority_established_at: datetime
    history_claim: PlanHistoryClaim
    external_plan_id_promoted: bool
    external_occurrence_ids_promoted: bool
    source_workout_mutated: bool
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return compute_content_hash(
            self,
            exclude_fields=ADOPTION_BINDING_HASH_EXCLUDE_FIELDS,
        ) == self.content_hash


def finalize_current_state_adoption_binding(
    *,
    logical_plan_id: str,
    source_workout_id: str,
    expected_source_content_sha256: str,
    adopted_revision_id: str,
    authority_established_at: datetime,
) -> CurrentStateAdoptionBinding:
    for field_name, value in (
        ('logical_plan_id', logical_plan_id),
        ('source_workout_id', source_workout_id),
        ('expected_source_content_sha256', expected_source_content_sha256),
        ('adopted_revision_id', adopted_revision_id),
    ):
        if not value.strip():
            raise ValueError(f'{field_name} must be non-empty.')
    established = to_utc(
        authority_established_at,
        field_name='authority_established_at',
    )
    provisional = CurrentStateAdoptionBinding(
        logical_plan_id=logical_plan_id,
        source_workout_id=source_workout_id,
        expected_source_content_sha256=expected_source_content_sha256,
        adopted_revision_id=adopted_revision_id,
        authority_established_at=established,
        history_claim=PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY,
        external_plan_id_promoted=False,
        external_occurrence_ids_promoted=False,
        source_workout_mutated=False,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash='',
    )
    return CurrentStateAdoptionBinding(
        **{
            **provisional.__dict__,
            'content_hash': compute_content_hash(
                provisional,
                exclude_fields=ADOPTION_BINDING_HASH_EXCLUDE_FIELDS,
            ),
        }
    )
