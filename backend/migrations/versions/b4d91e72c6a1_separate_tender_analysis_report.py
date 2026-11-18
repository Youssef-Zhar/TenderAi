"""separate tender descriptions from AI analysis reports

Revision ID: b4d91e72c6a1
Revises: a27bcc0acc4b
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4d91e72c6a1"
down_revision: Union[str, Sequence[str], None] = "a27bcc0acc4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Preserve legacy AI reports and replace oversized descriptions with summaries."""
    op.add_column(
        "tenders",
        sa.Column("analysis_report", sa.Text(), nullable=True),
    )

    # Existing AI reports were stored in description. Preserve long reports
    # before replacing their display description with a concise summary.
    op.execute(
        sa.text(
            """
            UPDATE tenders
            SET analysis_report = description,
                description = 'Dossier de marché analysé par TenderAI. '
                              'Consultez le rapport complet pour les détails.'
            WHERE CHAR_LENGTH(description) > 1000
            """
        )
    )


def downgrade() -> None:
    """Restore preserved reports to description before dropping the new column."""
    op.execute(
        sa.text(
            """
            UPDATE tenders
            SET description = analysis_report
            WHERE analysis_report IS NOT NULL
            """
        )
    )
    op.drop_column("tenders", "analysis_report")
