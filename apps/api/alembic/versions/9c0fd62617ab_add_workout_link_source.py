"""add workout link source

Revision ID: 9c0fd62617ab
Revises: 7b4747788e15
Create Date: 2026-09-29 13:39:12.637464
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9c0fd62617ab"
down_revision: Union[str, Sequence[str], None] = "7b4747788e15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


workout_link_source_enum = postgresql.ENUM(
    "PROVIDER_EXACT",
    "MANUAL_CONFIRMED",
    "AUTO_MATCHED",
    name="workout_link_source_enum",
    create_type=False,
)


def upgrade() -> None:
    workout_link_source_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    op.add_column(
        "workout_sessions",
        sa.Column(
            "planned_workout_link_source",
            workout_link_source_enum,
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "workout_sessions",
        "planned_workout_link_source",
    )

    workout_link_source_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )