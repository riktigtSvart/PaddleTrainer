from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


JSON_DOCUMENT = JSON().with_variant(postgresql.JSONB(), "postgresql")


class PlanningLogicalPlanRow(Base):
    __tablename__ = "planning_logical_plans"
    __table_args__ = (
        UniqueConstraint(
            "source_workout_id",
            name="uq_planning_logical_plans_source_workout_id",
        ),
        CheckConstraint(
            "(current_revision_id IS NULL AND current_revision_number = 0 "
            "AND authority_established_at IS NULL) OR "
            "(current_revision_id IS NOT NULL AND current_revision_number >= 1 "
            "AND authority_established_at IS NOT NULL)",
            name="ck_planning_logical_plan_pointer_state",
        ),
    )

    logical_plan_id: Mapped[str] = mapped_column(Text, primary_key=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    source_workout_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("planned_workouts.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Planning-owned revision IDs use the pt-plan-rev:* namespace and are
    # therefore stored as text rather than PostgreSQL UUID values.
    current_revision_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "planning_plan_revisions.revision_id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_planning_logical_plans_current_revision_id",
        ),
        nullable=True,
    )
    current_revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    authority_established_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlanningPlanRevisionRow(Base):
    __tablename__ = "planning_plan_revisions"
    __table_args__ = (
        UniqueConstraint(
            "logical_plan_id",
            "revision_number",
            name="uq_planning_plan_revision_number",
        ),
        CheckConstraint(
            "revision_number >= 1",
            name="ck_planning_plan_revision_number_positive",
        ),
        CheckConstraint(
            "origin IN ('adopted_current_state', 'planner_created', 'external_reconciled')",
            name="ck_planning_plan_revision_origin",
        ),
        CheckConstraint(
            "history_claim IN ('current_state_baseline_only', 'verified_from_authority_start')",
            name="ck_planning_plan_revision_history_claim",
        ),
        CheckConstraint(
            "origin <> 'adopted_current_state' OR "
            "(revision_number = 1 AND previous_revision_id IS NULL "
            "AND history_claim = 'current_state_baseline_only' "
            "AND source_capture_id IS NOT NULL "
            "AND source_capture_hash IS NOT NULL "
            "AND source_read_content_hash IS NOT NULL "
            "AND source_content_sha256 IS NOT NULL "
            "AND source_external_contract_plan_id IS NOT NULL "
            "AND source_external_contract_plan_revision IS NOT NULL "
            "AND context_hash IS NULL AND decision_hash IS NULL "
            "AND rationale_hash IS NULL AND instruction_hash IS NULL)",
            name="ck_planning_adoption_revision_semantics",
        ),
        CheckConstraint(
            "origin <> 'planner_created' OR "
            "(history_claim = 'verified_from_authority_start' "
            "AND source_capture_id IS NULL AND source_capture_hash IS NULL "
            "AND source_read_content_hash IS NULL AND source_content_sha256 IS NULL "
            "AND source_external_contract_plan_id IS NULL "
            "AND source_external_contract_plan_revision IS NULL "
            "AND context_hash IS NOT NULL AND decision_hash IS NOT NULL "
            "AND rationale_hash IS NOT NULL AND instruction_hash IS NOT NULL)",
            name="ck_planning_planner_revision_semantics",
        ),
    )

    revision_id: Mapped[str] = mapped_column(Text, primary_key=True)
    logical_plan_id: Mapped[str] = mapped_column(
        ForeignKey("planning_logical_plans.logical_plan_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("planning_plan_revisions.revision_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    history_claim: Mapped[str] = mapped_column(Text, nullable=False)
    authority_established_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    contract_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_contract_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    contract_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    revision_content_hash: Mapped[str] = mapped_column(Text, nullable=False)

    source_capture_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_capture_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_read_content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_content_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_external_contract_plan_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_external_contract_plan_revision: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    context_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction_hash: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlanningPlanOccurrenceIdentityRow(Base):
    __tablename__ = "planning_plan_occurrence_identities"

    occurrence_id: Mapped[str] = mapped_column(Text, primary_key=True)
    logical_plan_id: Mapped[str] = mapped_column(
        ForeignKey("planning_logical_plans.logical_plan_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    first_revision_id: Mapped[str] = mapped_column(
        ForeignKey("planning_plan_revisions.revision_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlanningPlanRevisionOccurrenceRow(Base):
    __tablename__ = "planning_plan_revision_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "ordinal",
            name="uq_planning_plan_revision_occurrence_ordinal",
        ),
        CheckConstraint(
            "ordinal >= 0",
            name="ck_planning_plan_revision_occurrence_ordinal_nonnegative",
        ),
        CheckConstraint(
            "lineage_kind IN ('new', 'preserved')",
            name="ck_planning_plan_revision_occurrence_lineage_kind",
        ),
    )

    revision_id: Mapped[str] = mapped_column(
        ForeignKey("planning_plan_revisions.revision_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    occurrence_id: Mapped[str] = mapped_column(
        ForeignKey("planning_plan_occurrence_identities.occurrence_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    lineage_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_capture_occurrence_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlanningPlanRevisionReconciliationAuditRow(Base):
    __tablename__ = "planning_plan_revision_reconciliation_audits"
    __table_args__ = (
        CheckConstraint(
            "reconciliation_status = 'sync_projection_match'",
            name="ck_planning_polar_reconciliation_audit_status",
        ),
        CheckConstraint(
            "length(reconciliation_content_hash) = 64",
            name="ck_planning_polar_reconciliation_content_hash_length",
        ),
        CheckConstraint(
            "length(source_content_sha256) = 64",
            name="ck_planning_polar_reconciliation_source_hash_length",
        ),
        CheckConstraint(
            "length(source_read_content_hash) = 64",
            name="ck_planning_polar_reconciliation_source_read_hash_length",
        ),
        CheckConstraint(
            "length(audit_content_hash) = 64",
            name="ck_planning_polar_reconciliation_audit_hash_length",
        ),
    )

    revision_id: Mapped[str] = mapped_column(
        ForeignKey("planning_plan_revisions.revision_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    audit_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    logical_plan_id: Mapped[str] = mapped_column(
        ForeignKey("planning_logical_plans.logical_plan_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_workout_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("planned_workouts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    capture_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    reconciliation_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_rules_version: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_content_hash_algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_artifact_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    reconciliation_captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source_read_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    timezone_context_name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone_context_source: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    audit_content_hash_algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    audit_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
