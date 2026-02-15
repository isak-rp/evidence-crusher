"""technical sheet explainability fields

Revision ID: a4f21f2bb5d4
Revises: 5f0e4f7b9e3a
Create Date: 2026-02-12 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a4f21f2bb5d4"
down_revision = "5f0e4f7b9e3a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("technical_facts", sa.Column("why_critical", sa.Text(), nullable=True))
    op.add_column("technical_facts", sa.Column("evidence_hint", sa.Text(), nullable=True))
    op.add_column("technical_alerts", sa.Column("required_doc_type", sa.String(), nullable=True))
    op.add_column("technical_alerts", sa.Column("field_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("technical_alerts", "field_key")
    op.drop_column("technical_alerts", "required_doc_type")
    op.drop_column("technical_facts", "evidence_hint")
    op.drop_column("technical_facts", "why_critical")
