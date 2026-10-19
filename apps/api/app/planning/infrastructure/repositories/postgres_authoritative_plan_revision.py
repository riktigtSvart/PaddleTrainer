from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...domain.common.serialization import canonical_json
from ...domain.plan_revision.persistence_contract import (
    AdoptionSourceRef,
    AuthoritativePlanConflictError,
    AuthoritativePlanIdentity,
    AuthoritativePlanRevision,
    CurrentStateAdoptionBinding,
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionDecisionLineage,
    RevisionOccurrence,
    finalize_authoritative_plan_identity,
    finalize_authoritative_plan_revision,
    validate_revision_transition,
)
from ..adapters.locked_plan_source import (
    CurrentAppLockedPlanSourceHashProvider,
    LockedPlanSourceHashProvider,
)
from ..persistence.sqlalchemy_models import (
    PlanningLogicalPlanRow,
    PlanningPlanOccurrenceIdentityRow,
    PlanningPlanRevisionOccurrenceRow,
    PlanningPlanRevisionRow,
)


def _db_utc(value: datetime) -> datetime:
    # asyncpg returns aware values for timestamptz. SQLite-based contract tests
    # may return naive values; in that test-only case the stored value is UTC.
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _uuid(value: str, *, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a UUID string.") from exc


class SqlAlchemyAuthoritativePlanRevisionRepository:
    """Async SQLAlchemy implementation of the P1.1 persistence port.

    Methods flush but never commit. The caller owns the surrounding transaction.
    Adoption additionally locks and re-hashes the mutable source workout inside
    the same session before authoritative revision 1 is inserted.
    """

    repository_version = "authoritative-plan-repository-v0.1"

    def __init__(
        self,
        session,
        *,
        source_hash_provider: LockedPlanSourceHashProvider | None = None,
    ) -> None:
        self._session = session
        self._source_hash_provider = source_hash_provider

    async def get_plan(
        self,
        *,
        logical_plan_id: str,
    ) -> AuthoritativePlanIdentity | None:
        result = await self._session.execute(
            select(PlanningLogicalPlanRow).where(
                PlanningLogicalPlanRow.logical_plan_id == logical_plan_id
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else self._identity_from_row(row)

    async def get_plan_for_update(
        self,
        *,
        logical_plan_id: str,
    ) -> AuthoritativePlanIdentity | None:
        result = await self._session.execute(
            select(PlanningLogicalPlanRow)
            .where(
                PlanningLogicalPlanRow.logical_plan_id
                == logical_plan_id
            )
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        return (
            None
            if row is None
            else self._identity_from_row(row)
        )

    async def get_revision(
        self,
        *,
        revision_id: str,
    ) -> AuthoritativePlanRevision | None:
        return await self._load_revision(revision_id=revision_id, for_update=False)

    async def get_current_revision(
        self,
        *,
        logical_plan_id: str,
    ) -> AuthoritativePlanRevision | None:
        plan = await self.get_plan(logical_plan_id=logical_plan_id)
        if plan is None or plan.current_revision_id is None:
            return None
        return await self.get_revision(revision_id=plan.current_revision_id)

    async def adopt_current_state(
        self,
        *,
        binding: CurrentStateAdoptionBinding,
        revision: AuthoritativePlanRevision,
    ) -> AuthoritativePlanIdentity:
        self._validate_adoption_input(binding=binding, revision=revision)
        if self._source_hash_provider is None:
            raise RuntimeError(
                "Adoption requires a LockedPlanSourceHashProvider. "
                "Use build_production_authoritative_plan_revision_repository() "
                "or inject an equivalent provider."
            )

        actual_source_hash = await self._source_hash_provider.lock_and_hash(
            self._session,
            source_workout_id=binding.source_workout_id,
            athlete_id=revision.athlete_id,
        )
        if actual_source_hash != binding.expected_source_content_sha256:
            raise AuthoritativePlanConflictError(
                "Source workout changed after the adoption capture."
            )

        plan_result = await self._session.execute(
            select(PlanningLogicalPlanRow)
            .where(
                PlanningLogicalPlanRow.logical_plan_id == binding.logical_plan_id
            )
            .with_for_update()
        )
        plan_row = plan_result.scalar_one_or_none()

        source_uuid = _uuid(binding.source_workout_id, field_name="source_workout_id")
        athlete_uuid = _uuid(revision.athlete_id, field_name="athlete_id")

        other_binding_result = await self._session.execute(
            select(PlanningLogicalPlanRow).where(
                PlanningLogicalPlanRow.source_workout_id == source_uuid,
                PlanningLogicalPlanRow.logical_plan_id != binding.logical_plan_id,
            )
        )
        if other_binding_result.scalar_one_or_none() is not None:
            raise AuthoritativePlanConflictError(
                "source_workout_id is already bound to another logical plan."
            )

        if plan_row is None:
            plan_row = PlanningLogicalPlanRow(
                logical_plan_id=binding.logical_plan_id,
                athlete_id=athlete_uuid,
                source_workout_id=source_uuid,
                current_revision_id=None,
                current_revision_number=0,
                authority_established_at=None,
                created_at=revision.created_at,
                updated_at=revision.created_at,
            )
            self._session.add(plan_row)
            await self._flush_conflict("logical plan adoption conflict")
        else:
            if str(plan_row.athlete_id) != revision.athlete_id:
                raise AuthoritativePlanConflictError("Logical plan athlete binding changed.")
            if (
                plan_row.source_workout_id is not None
                and str(plan_row.source_workout_id) != binding.source_workout_id
            ):
                raise AuthoritativePlanConflictError("Logical plan source binding changed.")
            if plan_row.current_revision_id is not None:
                raise AuthoritativePlanConflictError("Logical plan is already adopted.")
            plan_row.source_workout_id = source_uuid

        await self._insert_revision(revision)
        await self._insert_occurrence_identities(revision)
        await self._insert_revision_occurrences(revision)

        plan_row.current_revision_id = revision.revision_id
        plan_row.current_revision_number = revision.revision_number
        plan_row.authority_established_at = revision.authority_established_at
        plan_row.updated_at = revision.created_at
        await self._flush_conflict("authoritative plan adoption conflict")
        return self._identity_from_row(plan_row)

    async def append_revision(
        self,
        *,
        expected_current_revision_id: str,
        revision: AuthoritativePlanRevision,
    ) -> AuthoritativePlanIdentity:
        if not expected_current_revision_id.strip():
            raise ValueError("expected_current_revision_id must be non-empty.")
        if not revision.verify_content_hash() or not revision.verify_contract_hash():
            raise ValueError("Revision hash does not verify.")

        plan_result = await self._session.execute(
            select(PlanningLogicalPlanRow)
            .where(
                PlanningLogicalPlanRow.logical_plan_id == revision.logical_plan_id
            )
            .with_for_update()
        )
        plan_row = plan_result.scalar_one_or_none()
        if plan_row is None:
            raise AuthoritativePlanConflictError("Logical plan does not exist.")
        if plan_row.current_revision_id != expected_current_revision_id:
            raise AuthoritativePlanConflictError(
                "Current revision changed before append."
            )
        if str(plan_row.athlete_id) != revision.athlete_id:
            raise AuthoritativePlanConflictError("Logical plan athlete binding changed.")

        previous = await self._load_revision(
            revision_id=expected_current_revision_id,
            for_update=False,
        )
        if previous is None:
            raise AuthoritativePlanConflictError(
                "Current revision pointer does not resolve."
            )
        validate_revision_transition(previous=previous, candidate=revision)

        await self._validate_occurrence_identity_transition(revision)
        await self._insert_revision(revision)
        await self._insert_occurrence_identities(revision)
        await self._insert_revision_occurrences(revision)

        plan_row.current_revision_id = revision.revision_id
        plan_row.current_revision_number = revision.revision_number
        plan_row.updated_at = revision.created_at
        await self._flush_conflict("authoritative plan append conflict")
        return self._identity_from_row(plan_row)

    def _validate_adoption_input(
        self,
        *,
        binding: CurrentStateAdoptionBinding,
        revision: AuthoritativePlanRevision,
    ) -> None:
        if not binding.verify_content_hash():
            raise ValueError("Adoption binding hash does not verify.")
        if not revision.verify_content_hash() or not revision.verify_contract_hash():
            raise ValueError("Revision hash does not verify.")
        if revision.origin != PlanRevisionOrigin.ADOPTED_CURRENT_STATE:
            raise ValueError("Adoption requires ADOPTED_CURRENT_STATE revision.")
        if revision.revision_id != binding.adopted_revision_id:
            raise ValueError("Adoption binding/revision ID mismatch.")
        if revision.logical_plan_id != binding.logical_plan_id:
            raise ValueError("Adoption logical_plan_id mismatch.")
        if revision.authority_established_at != binding.authority_established_at:
            raise ValueError("Adoption authority time mismatch.")
        if revision.adoption_source is None:
            raise ValueError("Adoption revision requires adoption_source.")
        if (
            revision.adoption_source.source_content_sha256
            != binding.expected_source_content_sha256
        ):
            raise ValueError("Adoption source hash mismatch.")
        if binding.logical_plan_id != f"planned-workout:{binding.source_workout_id}":
            raise ValueError(
                "Current application adoption must use planned-workout:<source UUID> logical ID."
            )

    async def _load_revision(
        self,
        *,
        revision_id: str,
        for_update: bool,
    ) -> AuthoritativePlanRevision | None:
        statement = select(PlanningPlanRevisionRow).where(
            PlanningPlanRevisionRow.revision_id == revision_id
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        membership_result = await self._session.execute(
            select(PlanningPlanRevisionOccurrenceRow)
            .where(
                PlanningPlanRevisionOccurrenceRow.revision_id == revision_id
            )
            .order_by(PlanningPlanRevisionOccurrenceRow.ordinal)
        )
        memberships = tuple(membership_result.scalars())
        return self._revision_from_rows(row=row, memberships=memberships)

    def _revision_from_rows(
        self,
        *,
        row: PlanningPlanRevisionRow,
        memberships: tuple[PlanningPlanRevisionOccurrenceRow, ...],
    ) -> AuthoritativePlanRevision:
        adoption_source = None
        if row.source_capture_id is not None:
            adoption_source = AdoptionSourceRef(
                capture_id=row.source_capture_id,
                capture_content_hash=row.source_capture_hash,
                source_read_content_hash=row.source_read_content_hash,
                source_content_sha256=row.source_content_sha256,
                external_contract_plan_id=row.source_external_contract_plan_id,
                external_contract_plan_revision=row.source_external_contract_plan_revision,
            )

        decision_lineage = None
        if row.context_hash is not None:
            decision_lineage = RevisionDecisionLineage(
                context_hash=row.context_hash,
                decision_hash=row.decision_hash,
                rationale_hash=row.rationale_hash,
                instruction_hash=row.instruction_hash,
            )

        revision = finalize_authoritative_plan_revision(
            revision_id=row.revision_id,
            logical_plan_id=row.logical_plan_id,
            athlete_id=str(row.athlete_id),
            revision_number=row.revision_number,
            previous_revision_id=row.previous_revision_id,
            origin=PlanRevisionOrigin(row.origin),
            history_claim=PlanHistoryClaim(row.history_claim),
            authority_established_at=_db_utc(row.authority_established_at),
            effective_from=_db_utc(row.effective_from),
            created_at=_db_utc(row.created_at),
            contract_schema_version=row.contract_schema_version,
            contract_json=canonical_json(row.canonical_contract_json),
            occurrences=tuple(
                RevisionOccurrence(
                    occurrence_id=item.occurrence_id,
                    ordinal=item.ordinal,
                    lineage_kind=OccurrenceLineageKind(item.lineage_kind),
                    source_capture_occurrence_id=item.source_capture_occurrence_id,
                )
                for item in memberships
            ),
            adoption_source=adoption_source,
            decision_lineage=decision_lineage,
        )
        if revision.content_hash != row.revision_content_hash:
            raise ValueError("Stored authoritative revision round-trip hash mismatch.")
        return revision

    def _identity_from_row(
        self,
        row: PlanningLogicalPlanRow,
    ) -> AuthoritativePlanIdentity:
        return finalize_authoritative_plan_identity(
            logical_plan_id=row.logical_plan_id,
            athlete_id=str(row.athlete_id),
            source_workout_id=(
                None if row.source_workout_id is None else str(row.source_workout_id)
            ),
            current_revision_id=row.current_revision_id,
            current_revision_number=row.current_revision_number,
            authority_established_at=(
                None
                if row.authority_established_at is None
                else _db_utc(row.authority_established_at)
            ),
        )

    async def _validate_occurrence_identity_transition(
        self,
        revision: AuthoritativePlanRevision,
    ) -> None:
        for occurrence in revision.occurrences:
            result = await self._session.execute(
                select(PlanningPlanOccurrenceIdentityRow).where(
                    PlanningPlanOccurrenceIdentityRow.occurrence_id
                    == occurrence.occurrence_id
                )
            )
            existing = result.scalar_one_or_none()
            if occurrence.lineage_kind == OccurrenceLineageKind.PRESERVED:
                if existing is None:
                    raise AuthoritativePlanConflictError(
                        "Preserved occurrence identity is missing from persistence."
                    )
                if existing.logical_plan_id != revision.logical_plan_id:
                    raise AuthoritativePlanConflictError(
                        "Occurrence identity belongs to another logical plan."
                    )
            else:
                if existing is not None:
                    raise AuthoritativePlanConflictError(
                        "New occurrence identity already exists."
                    )

    async def _insert_revision(self, revision: AuthoritativePlanRevision) -> None:
        source = revision.adoption_source
        lineage = revision.decision_lineage
        self._session.add(
            PlanningPlanRevisionRow(
                revision_id=revision.revision_id,
                logical_plan_id=revision.logical_plan_id,
                athlete_id=_uuid(revision.athlete_id, field_name="athlete_id"),
                revision_number=revision.revision_number,
                previous_revision_id=revision.previous_revision_id,
                origin=revision.origin.value,
                history_claim=revision.history_claim.value,
                authority_established_at=revision.authority_established_at,
                effective_from=revision.effective_from,
                created_at=revision.created_at,
                contract_schema_version=revision.contract_schema_version,
                canonical_contract_json=json.loads(revision.canonical_contract_json),
                contract_content_hash=revision.contract_content_hash,
                revision_content_hash=revision.content_hash,
                source_capture_id=None if source is None else source.capture_id,
                source_capture_hash=None if source is None else source.capture_content_hash,
                source_read_content_hash=None if source is None else source.source_read_content_hash,
                source_content_sha256=None if source is None else source.source_content_sha256,
                source_external_contract_plan_id=(
                    None if source is None else source.external_contract_plan_id
                ),
                source_external_contract_plan_revision=(
                    None if source is None else source.external_contract_plan_revision
                ),
                context_hash=None if lineage is None else lineage.context_hash,
                decision_hash=None if lineage is None else lineage.decision_hash,
                rationale_hash=None if lineage is None else lineage.rationale_hash,
                instruction_hash=None if lineage is None else lineage.instruction_hash,
            )
        )
        await self._flush_conflict("immutable revision insert conflict")

    async def _insert_occurrence_identities(
        self,
        revision: AuthoritativePlanRevision,
    ) -> None:
        for occurrence in revision.occurrences:
            if occurrence.lineage_kind != OccurrenceLineageKind.NEW:
                continue
            self._session.add(
                PlanningPlanOccurrenceIdentityRow(
                    occurrence_id=occurrence.occurrence_id,
                    logical_plan_id=revision.logical_plan_id,
                    first_revision_id=revision.revision_id,
                    created_at=revision.created_at,
                )
            )
        await self._flush_conflict("occurrence identity insert conflict")

    async def _insert_revision_occurrences(
        self,
        revision: AuthoritativePlanRevision,
    ) -> None:
        for occurrence in revision.occurrences:
            self._session.add(
                PlanningPlanRevisionOccurrenceRow(
                    revision_id=revision.revision_id,
                    occurrence_id=occurrence.occurrence_id,
                    ordinal=occurrence.ordinal,
                    lineage_kind=occurrence.lineage_kind.value,
                    source_capture_occurrence_id=occurrence.source_capture_occurrence_id,
                )
            )
        await self._flush_conflict("revision occurrence insert conflict")

    async def _flush_conflict(self, message: str) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise AuthoritativePlanConflictError(message) from exc


def build_production_authoritative_plan_revision_repository(session):
    return SqlAlchemyAuthoritativePlanRevisionRepository(
        session,
        source_hash_provider=CurrentAppLockedPlanSourceHashProvider(),
    )
