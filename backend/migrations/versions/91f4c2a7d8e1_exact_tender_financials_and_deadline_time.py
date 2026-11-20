"""store exact tender budgets, currencies, and deadline times

Revision ID: 91f4c2a7d8e1
Revises: b4d91e72c6a1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "91f4c2a7d8e1"
down_revision: Union[str, Sequence[str], None] = "b4d91e72c6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert budget storage to DECIMAL and add nullable source metadata."""
    op.alter_column(
        "tenders",
        "estimated_budget",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=24, scale=6),
        existing_nullable=True,
    )
    op.add_column("tenders", sa.Column("currency", sa.String(length=32), nullable=True))
    op.add_column("tenders", sa.Column("deadline_time", sa.Time(), nullable=True))
    op.add_column("tenders", sa.Column("deadline_text", sa.Text(), nullable=True))


def downgrade() -> None:
    """Restore the legacy schema; new currency/time values are discarded."""
    op.drop_column("tenders", "deadline_text")
    op.drop_column("tenders", "deadline_time")
    op.drop_column("tenders", "currency")
    op.alter_column(
        "tenders",
        "estimated_budget",
        existing_type=sa.Numeric(precision=24, scale=6),
        type_=sa.Float(),
        existing_nullable=True,
    )
