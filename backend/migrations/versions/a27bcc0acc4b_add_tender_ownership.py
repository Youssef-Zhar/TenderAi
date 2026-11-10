"""add tender ownership

Revision ID: a27bcc0acc4b
Revises: 6c68b6be204a
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a27bcc0acc4b"
down_revision: Union[str, Sequence[str], None] = "6c68b6be204a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional ownership to existing tenders."""

    op.add_column(
        "tenders",
        sa.Column("owner_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_tenders_owner_id",
        "tenders",
        ["owner_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_tenders_owner_id_users",
        "tenders",
        "users",
        ["owner_id"],
        ["id"],
    )


def downgrade() -> None:
    """Remove tender ownership."""

    op.drop_constraint(
        "fk_tenders_owner_id_users",
        "tenders",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_tenders_owner_id",
        table_name="tenders",
    )

    op.drop_column("tenders", "owner_id")