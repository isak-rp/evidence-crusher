"""technical sheet v2

Revision ID: 5f0e4f7b9e3a
Revises: 04832691e35f
Create Date: 2026-02-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "5f0e4f7b9e3a"
down_revision = "04832691e35f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "technical_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pillar", sa.String(), nullable=False),
        sa.Column("field_key", sa.String(), nullable=False),
        sa.Column("value_raw", sa.Text(), nullable=True),
        sa.Column("value_normalized", sa.JSON(), nullable=True),
        sa.Column("source_doc_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_bbox", sa.JSON(), nullable=True),
        sa.Column("source_text_excerpt", sa.Text(), nullable=True),
        sa.Column("source_doc_type", sa.String(), nullable=True),
        sa.Column("risk_level", sa.String(), nullable=False, server_default="LOW"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("truth_status", sa.String(), nullable=False, server_default="FACT"),
        sa.Column("rule_applied", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_doc_id"], ["documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_technical_facts_case_id", "technical_facts", ["case_id"], unique=False)
    op.create_index("ix_technical_facts_case_field", "technical_facts", ["case_id", "field_key"], unique=False)

    op.create_table(
        "technical_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence_fact_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_technical_alerts_case_id", "technical_alerts", ["case_id"], unique=False)

    op.create_table(
        "technical_snapshot",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("overall_status", sa.String(), nullable=False, server_default="YELLOW"),
        sa.Column("litis_narrative", sa.Text(), nullable=False, server_default=""),
        sa.Column("high_impact_alerts", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("technical_snapshot")
    op.drop_index("ix_technical_alerts_case_id", table_name="technical_alerts")
    op.drop_table("technical_alerts")
    op.drop_index("ix_technical_facts_case_field", table_name="technical_facts")
    op.drop_index("ix_technical_facts_case_id", table_name="technical_facts")
    op.drop_table("technical_facts")
