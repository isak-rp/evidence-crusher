"""init

Revision ID: 0001_init
Revises: 
Create Date: 2026-02-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ABIERTO"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("doc_type", sa.String(), nullable=False),
        sa.Column("upload_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "case_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("daily_salary", sa.Float(), nullable=True),
        sa.Column("start_date_source_doc_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_date_page", sa.Integer(), nullable=True),
        sa.Column("start_date_bbox", sa.JSON(), nullable=True),
        sa.Column("end_date_source_doc_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("end_date_page", sa.Integer(), nullable=True),
        sa.Column("end_date_bbox", sa.JSON(), nullable=True),
        sa.Column("daily_salary_source_doc_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("daily_salary_page", sa.Integer(), nullable=True),
        sa.Column("daily_salary_bbox", sa.JSON(), nullable=True),
        sa.Column("extraction_status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["start_date_source_doc_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["end_date_source_doc_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["daily_salary_source_doc_id"], ["documents.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("semantic_type", sa.String(), nullable=False, server_default="GENERAL"),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("case_metadata")
    op.drop_table("documents")
    op.drop_table("cases")
