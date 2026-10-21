from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy import Float
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

class PlanningAuditArtifactRow(Base):
    __tablename__ = "planning_audit_artifacts"
    __table_args__ = (
        Index(
            "ix_planning_audit_athlete_kind_created",
            "athlete_id",
            "artifact_kind",
            "created_at",
        ),
    )

    artifact_kind: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )
    artifact_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    persisted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    content_hash_algorithm: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    contract_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )


class PlanningPlanExecutionLinkRow(Base):
    __tablename__ = "planning_plan_execution_links"
    __table_args__ = (
        UniqueConstraint(
            "workout_session_id",
            name="uq_planning_plan_execution_link_session",
        ),
        CheckConstraint(
            "link_basis IN "
            "('exact_provider_id', 'manual_confirmed')",
            name="ck_planning_plan_execution_link_basis",
        ),
        CheckConstraint(
            "plan_content_at_execution_status = 'unverified'",
            name="ck_planning_plan_execution_content_status",
        ),
        CheckConstraint(
            "temporal_match_used = false",
            name="ck_planning_plan_execution_no_temporal_match",
        ),
        CheckConstraint(
            "(link_basis = 'exact_provider_id' "
            "AND provider_target_id IS NOT NULL) OR "
            "(link_basis = 'manual_confirmed' "
            "AND provider_target_id IS NULL)",
            name="ck_planning_plan_execution_provider_proof",
        ),
        CheckConstraint(
            "length(source_workout_content_hash) = 64",
            name="ck_planning_plan_execution_source_hash_length",
        ),
        CheckConstraint(
            "length(session_source_content_hash) = 64",
            name="ck_planning_plan_execution_session_hash_length",
        ),
        CheckConstraint(
            "length(observed_revision_content_hash) = 64",
            name="ck_planning_plan_execution_revision_hash_length",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_planning_plan_execution_hash_length",
        ),
    )

    link_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )
    schema_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    logical_plan_id: Mapped[str] = mapped_column(
        ForeignKey(
            "planning_logical_plans.logical_plan_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    observed_revision_id: Mapped[str] = mapped_column(
        ForeignKey(
            "planning_plan_revisions.revision_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    workout_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_workout_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("planned_workouts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    link_basis: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    provider_target_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    source_workout_content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    session_source_content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    observed_revision_content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    plan_content_at_execution_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    temporal_match_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    content_hash_algorithm: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

class PlanningOccurrenceExecutionLinkRow(Base):
    __tablename__ = "planning_occurrence_execution_links"
    __table_args__ = (
        UniqueConstraint(
            "plan_execution_link_id",
            "authoritative_occurrence_id",
            name="uq_planning_occ_exec_authoritative_occurrence",
        ),
        UniqueConstraint(
            "plan_execution_link_id",
            "phase_reconciliation_artifact_id",
            "stable_source_occurrence_id",
            name="uq_planning_occ_exec_source_candidate",
        ),
        UniqueConstraint(
            "confirmation_id",
            name="uq_planning_occ_exec_confirmation",
        ),
        CheckConstraint(
            "link_basis = 'user_confirmed_candidate_segment'",
            name="ck_planning_occ_exec_basis",
        ),
        CheckConstraint(
            "occurrence_alignment_status = "
            "'user_confirmed_candidate_segment'",
            name="ck_planning_occ_exec_alignment_status",
        ),
        CheckConstraint(
            "plan_content_at_execution_status = 'unverified'",
            name="ck_planning_occ_exec_plan_content_status",
        ),
        CheckConstraint(
            "provider_event_verified = false",
            name="ck_planning_occ_exec_no_provider_event",
        ),
        CheckConstraint(
            "clock_alignment_verified = false",
            name="ck_planning_occ_exec_no_clock_alignment",
        ),
        CheckConstraint(
            "actual_boundary_verified = false",
            name="ck_planning_occ_exec_no_actual_boundary",
        ),
        CheckConstraint(
            "temporal_match_used = false",
            name="ck_planning_occ_exec_no_temporal_match",
        ),
        CheckConstraint(
            "candidate_start_min_s >= 0 "
            "AND candidate_start_max_s >= candidate_start_min_s",
            name="ck_planning_occ_exec_start_window",
        ),
        CheckConstraint(
            "candidate_completion_min_s >= 0 "
            "AND candidate_completion_max_s "
            ">= candidate_completion_min_s",
            name="ck_planning_occ_exec_completion_window",
        ),
        CheckConstraint(
            "length(session_source_content_hash) = 64",
            name="ck_planning_occ_exec_session_hash_length",
        ),
        CheckConstraint(
            "length(plan_source_content_hash) = 64",
            name="ck_planning_occ_exec_plan_hash_length",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_planning_occ_exec_hash_length",
        ),
    )

    link_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )
    schema_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    plan_execution_link_id: Mapped[str] = mapped_column(
        ForeignKey(
            "planning_plan_execution_links.link_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    logical_plan_id: Mapped[str] = mapped_column(
        ForeignKey(
            "planning_logical_plans.logical_plan_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    observed_revision_id: Mapped[str] = mapped_column(
        ForeignKey(
            "planning_plan_revisions.revision_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    authoritative_occurrence_id: Mapped[str] = mapped_column(
        ForeignKey(
            "planning_plan_occurrence_identities.occurrence_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    workout_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    link_basis: Mapped[str] = mapped_column(Text, nullable=False)

    phase_reconciliation_artifact_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    phase_reconciliation_rules_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    session_source_content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    plan_source_content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    stable_source_occurrence_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    captured_contract_occurrence_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    hypothesis_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    candidate_start_min_s: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    candidate_start_max_s: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    candidate_completion_min_s: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    candidate_completion_max_s: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    clock_domain: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    confirmation_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    confirmation_submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    occurrence_alignment_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    plan_content_at_execution_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    provider_event_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    clock_alignment_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    actual_boundary_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    temporal_match_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    content_hash_algorithm: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )


class PlanningEvidenceItemRow(Base):
    __tablename__ = "planning_evidence_items"
    __table_args__ = (
        CheckConstraint(
            "available_at >= observed_at",
            name="ck_planning_evidence_available_after_observed",
        ),
        CheckConstraint(
            "source_content_hash IS NULL "
            "OR length(source_content_hash) = 64",
            name="ck_planning_evidence_source_hash_length",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_planning_evidence_hash_length",
        ),
        CheckConstraint(
            "provenance IN "
            "('source', 'derived', 'policy_resolved', 'inferred')",
            name="ck_planning_evidence_provenance",
        ),
        CheckConstraint(
            "knowledge_status IN "
            "('known', 'unknown', 'not_applicable', "
            "'not_measured', 'not_asked')",
            name="ck_planning_evidence_knowledge_status",
        ),
        CheckConstraint(
            "quality IN ('high', 'moderate', 'low', 'unknown')",
            name="ck_planning_evidence_quality",
        ),
        Index(
            "ix_planning_evidence_athlete_available",
            "athlete_id",
            "available_at",
            "evidence_id",
        ),
    )

    evidence_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    athlete_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    evidence_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    source_system: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source_record_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source_version: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_content_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    provenance: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    knowledge_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    quality: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    payload_json: Mapped[dict] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
    )

    content_hash_algorithm: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
