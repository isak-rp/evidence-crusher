"""phase2 conflict scoring fields

Revision ID: b9d4c2f14a11
Revises: a4f21f2bb5d4
Create Date: 2026-02-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b9d4c2f14a11"
down_revision = "a4f21f2bb5d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("technical_facts", sa.Column("party_side", sa.String(), nullable=True))
    op.add_column("technical_facts", sa.Column("conflict_group_id", sa.String(), nullable=True))
    op.add_column("technical_facts", sa.Column("evidence_weight", sa.Float(), nullable=True))
    op.add_column("technical_facts", sa.Column("precedence_rank", sa.Integer(), nullable=True))
    op.add_column("technical_facts", sa.Column("legal_defense_strength", sa.String(), nullable=True))

    op.add_column("technical_alerts", sa.Column("dimension", sa.String(), nullable=True))
    op.add_column("technical_alerts", sa.Column("why_flagged", sa.Text(), nullable=True))

    op.add_column(
        "technical_snapshot",
        sa.Column("narrative_mode", sa.String(), nullable=False, server_default="DETERMINISTIC"),
    )
    op.add_column("technical_snapshot", sa.Column("dimension_scores", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("technical_snapshot", "dimension_scores")
    op.drop_column("technical_snapshot", "narrative_mode")

    op.drop_column("technical_alerts", "why_flagged")
    op.drop_column("technical_alerts", "dimension")

    op.drop_column("technical_facts", "legal_defense_strength")
    op.drop_column("technical_facts", "precedence_rank")
    op.drop_column("technical_facts", "evidence_weight")
    op.drop_column("technical_facts", "conflict_group_id")
    op.drop_column("technical_facts", "party_side")
