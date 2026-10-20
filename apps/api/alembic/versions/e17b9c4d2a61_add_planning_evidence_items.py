"""Add durable immutable planning evidence items.

Revision ID: e17b9c4d2a61
Revises: c84d7e1a6f32
Create Date: 2026-10-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e17b9c4d2a61"
down_revision = "c84d7e1a6f32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planning_evidence_items",
        sa.Column(
            "evidence_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "athlete_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "evidence_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "source_system",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "source_record_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "source_version",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_content_hash",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "provenance",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "knowledge_status",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "quality",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "payload_json",
            sa.JSON().with_variant(
                postgresql.JSONB(),
                "postgresql",
            ),
            nullable=False,
        ),
        sa.Column(
            "content_hash_algorithm",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "content_hash",
            sa.Text(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "available_at >= observed_at",
            name="ck_planning_evidence_available_after_observed",
        ),
        sa.CheckConstraint(
            "source_content_hash IS NULL "
            "OR length(source_content_hash) = 64",
            name="ck_planning_evidence_source_hash_length",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_planning_evidence_hash_length",
        ),
        sa.CheckConstraint(
            "provenance IN "
            "('source', 'derived', 'policy_resolved', 'inferred')",
            name="ck_planning_evidence_provenance",
        ),
        sa.CheckConstraint(
            "knowledge_status IN "
            "('known', 'unknown', 'not_applicable', "
            "'not_measured', 'not_asked')",
            name="ck_planning_evidence_knowledge_status",
        ),
        sa.CheckConstraint(
            "quality IN ('high', 'moderate', 'low', 'unknown')",
            name="ck_planning_evidence_quality",
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("evidence_id"),
    )

    op.create_index(
        "ix_planning_evidence_athlete_available",
        "planning_evidence_items",
        [
            "athlete_id",
            "available_at",
            "evidence_id",
        ],
        unique=False,
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION
            planning_reject_immutable_evidence_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'planning evidence history is immutable';
            END;
            $$;
            """
        )

        # planning_audit_artifacts already has immutable repository
        # semantics. P1.7D closes the database-level mutation gap too.
        op.execute(
            """
            CREATE TRIGGER
            trg_planning_audit_artifacts_immutable
            BEFORE UPDATE OR DELETE
            ON planning_audit_artifacts
            FOR EACH ROW
            EXECUTE FUNCTION
            planning_reject_immutable_evidence_mutation();
            """
        )

        op.execute(
            """
            CREATE TRIGGER
            trg_planning_evidence_items_immutable
            BEFORE UPDATE OR DELETE
            ON planning_evidence_items
            FOR EACH ROW
            EXECUTE FUNCTION
            planning_reject_immutable_evidence_mutation();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DROP TRIGGER IF EXISTS
            trg_planning_evidence_items_immutable
            ON planning_evidence_items;
            """
        )

        op.execute(
            """
            DROP TRIGGER IF EXISTS
            trg_planning_audit_artifacts_immutable
            ON planning_audit_artifacts;
            """
        )

        op.execute(
            """
            DROP FUNCTION IF EXISTS
            planning_reject_immutable_evidence_mutation();
            """
        )

    op.drop_index(
        "ix_planning_evidence_athlete_available",
        table_name="planning_evidence_items",
    )

    op.drop_table("planning_evidence_items")
