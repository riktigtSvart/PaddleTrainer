from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningOccurrenceExecutionLinkRow,
)


API_ROOT = Path(__file__).resolve().parents[2]


def test_p1_6c_occurrence_execution_model_columns():
    columns = set(
        PlanningOccurrenceExecutionLinkRow
        .__table__.columns.keys()
    )

    assert {
        "link_id",
        "schema_version",
        "athlete_id",
        "plan_execution_link_id",
        "logical_plan_id",
        "observed_revision_id",
        "authoritative_occurrence_id",
        "workout_session_id",
        "link_basis",
        "phase_reconciliation_artifact_id",
        "phase_reconciliation_rules_version",
        "session_source_content_hash",
        "plan_source_content_hash",
        "stable_source_occurrence_id",
        "captured_contract_occurrence_id",
        "hypothesis_id",
        "candidate_start_min_s",
        "candidate_start_max_s",
        "candidate_completion_min_s",
        "candidate_completion_max_s",
        "clock_domain",
        "confirmation_id",
        "confirmation_submitted_at",
        "occurrence_alignment_status",
        "plan_content_at_execution_status",
        "provider_event_verified",
        "clock_alignment_verified",
        "actual_boundary_verified",
        "temporal_match_used",
        "created_at",
        "content_hash_algorithm",
        "content_hash",
    } == columns


def test_p1_6c_occurrence_execution_unique_guards():
    constraints = {
        constraint.name
        for constraint
        in PlanningOccurrenceExecutionLinkRow
        .__table__.constraints
        if constraint.name
    }

    assert (
        "uq_planning_occ_exec_authoritative_occurrence"
        in constraints
    )
    assert (
        "uq_planning_occ_exec_source_candidate"
        in constraints
    )
    assert (
        "uq_planning_occ_exec_confirmation"
        in constraints
    )


def test_p1_6c_occurrence_execution_foreign_keys():
    targets = {
        fk.target_fullname
        for fk
        in PlanningOccurrenceExecutionLinkRow
        .__table__.foreign_keys
    }

    assert "users.id" in targets
    assert "planning_plan_execution_links.link_id" in targets
    assert "planning_logical_plans.logical_plan_id" in targets
    assert "planning_plan_revisions.revision_id" in targets
    assert (
        "planning_plan_occurrence_identities.occurrence_id"
        in targets
    )
    assert "workout_sessions.id" in targets


def test_p1_6c_migration_is_new_head():
    scripts = ScriptDirectory.from_config(
        Config(str(API_ROOT / "alembic.ini"))
    )
    assert scripts.get_heads() == ["e17b9c4d2a61"]

    current = scripts.get_revision("c84d7e1a6f32")
    assert current is not None
    assert current.down_revision == "a91f6c3d7b20"


def test_p1_6c_migration_has_postgres_immutability_guard():
    migration = (
        API_ROOT
        / "alembic"
        / "versions"
        / (
            "c84d7e1a6f32_"
            "add_authoritative_occurrence_execution_links.py"
        )
    ).read_text(encoding="utf-8")

    assert (
        "BEFORE UPDATE OR DELETE"
        in migration
    )
    assert (
        "planning_occurrence_execution_links_immutable_guard"
        in migration
    )
