from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.planning.domain.persistence.audit import (
    AuditArtifactKind,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningEvidenceItemRow,
)


API_ROOT = Path(__file__).resolve().parents[2]


def test_p1_7d_evidence_model_columns():
    columns = set(
        PlanningEvidenceItemRow.__table__.columns.keys()
    )

    assert {
        "evidence_id",
        "athlete_id",
        "evidence_type",
        "observed_at",
        "available_at",
        "created_at",
        "source_system",
        "source_record_id",
        "source_version",
        "source_content_hash",
        "provenance",
        "knowledge_status",
        "quality",
        "payload_json",
        "content_hash_algorithm",
        "content_hash",
    } == columns


def test_p1_7d_evidence_model_owner_foreign_key():
    targets = {
        fk.target_fullname
        for fk
        in PlanningEvidenceItemRow.__table__.foreign_keys
    }

    assert targets == {"users.id"}


def test_p1_7d_evidence_model_constraints():
    constraints = {
        constraint.name
        for constraint
        in PlanningEvidenceItemRow.__table__.constraints
        if constraint.name is not None
    }

    assert {
        "ck_planning_evidence_available_after_observed",
        "ck_planning_evidence_source_hash_length",
        "ck_planning_evidence_hash_length",
        "ck_planning_evidence_provenance",
        "ck_planning_evidence_knowledge_status",
        "ck_planning_evidence_quality",
    }.issubset(constraints)


def test_p1_7d_evidence_model_cutoff_index():
    indexes = {
        index.name: tuple(
            column.name
            for column in index.columns
        )
        for index
        in PlanningEvidenceItemRow.__table__.indexes
    }

    assert indexes[
        "ix_planning_evidence_athlete_available"
    ] == (
        "athlete_id",
        "available_at",
        "evidence_id",
    )


def test_authoritative_executed_training_has_audit_kind():
    assert (
        AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING.value
        == "authoritative_executed_training"
    )


def test_p1_7d_migration_is_new_head():
    scripts = ScriptDirectory.from_config(
        Config(str(API_ROOT / "alembic.ini"))
    )

    assert scripts.get_heads() == [
        "e17b9c4d2a61"
    ]

    current = scripts.get_revision(
        "e17b9c4d2a61"
    )

    assert current.down_revision == "c84d7e1a6f32"


def test_p1_7d_migration_has_database_immutability_guards():
    path = (
        API_ROOT
        / "alembic/versions/"
        "e17b9c4d2a61_add_planning_evidence_items.py"
    )

    source = path.read_text(encoding="utf-8")

    assert "planning_evidence_items" in source

    assert (
        "trg_planning_evidence_items_immutable"
        in source
    )

    assert (
        "trg_planning_audit_artifacts_immutable"
        in source
    )

    assert source.count(
        "BEFORE UPDATE OR DELETE"
    ) == 2

    assert (
        "planning_reject_immutable_evidence_mutation"
        in source
    )
