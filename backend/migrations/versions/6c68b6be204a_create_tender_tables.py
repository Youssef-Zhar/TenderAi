
"""create_tender_tables

Revision ID: 6c68b6be204a
Revises: 0b3739630d1a
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6c68b6be204a"
down_revision: Union[str, Sequence[str], None] = "0b3739630d1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create tender-related tables."""

    op.create_table(
        "tenders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("estimated_budget", sa.Float(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenders_id", "tenders", ["id"], unique=False)

    op.create_table(
        "tender_conditions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tender_id", sa.Integer(), nullable=False),
        sa.Column("condition_type", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tender_conditions_id",
        "tender_conditions",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_tender_conditions_tender_id",
        "tender_conditions",
        ["tender_id"],
        unique=False,
    )

    op.create_table(
        "tender_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tender_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tender_documents_id",
        "tender_documents",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_tender_documents_tender_id",
        "tender_documents",
        ["tender_id"],
        unique=False,
    )

    op.create_table(
        "tender_criteria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tender_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tender_criteria_id",
        "tender_criteria",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_tender_criteria_tender_id",
        "tender_criteria",
        ["tender_id"],
        unique=False,
    )

    op.create_table(
        "tender_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tender_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("extracted_value", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tender_evidence_id",
        "tender_evidence",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_tender_evidence_tender_id",
        "tender_evidence",
        ["tender_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop tender-related tables."""

    op.drop_index("ix_tender_evidence_tender_id", table_name="tender_evidence")
    op.drop_index("ix_tender_evidence_id", table_name="tender_evidence")
    op.drop_table("tender_evidence")

    op.drop_index("ix_tender_criteria_tender_id", table_name="tender_criteria")
    op.drop_index("ix_tender_criteria_id", table_name="tender_criteria")
    op.drop_table("tender_criteria")

    op.drop_index("ix_tender_documents_tender_id", table_name="tender_documents")
    op.drop_index("ix_tender_documents_id", table_name="tender_documents")
    op.drop_table("tender_documents")

    op.drop_index("ix_tender_conditions_tender_id", table_name="tender_conditions")
    op.drop_index("ix_tender_conditions_id", table_name="tender_conditions")
    op.drop_table("tender_conditions")

    op.drop_index("ix_tenders_id", table_name="tenders")
    op.drop_table("tenders")
