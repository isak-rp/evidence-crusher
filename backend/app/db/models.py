"""SQLAlchemy models for Evidence Crusher case management."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector

# --- MODIFICACIÓN: Agregamos Integer y Text a los imports ---
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for declarative SQLAlchemy models."""


class Case(Base):
    """Case (expediente) model."""

    __tablename__ = "cases"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ABIERTO")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    metadata_info: Mapped["CaseMetadata | None"] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        uselist=False,
    )
    technical_facts: Mapped[list["TechnicalFact"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    technical_alerts: Mapped[list["TechnicalAlert"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    technical_snapshot: Mapped["TechnicalSnapshot | None"] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Document(Base):
    """Document model linked to a case."""

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    upload_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    case: Mapped[Case] = relationship(back_populates="documents")
    
    # --- MODIFICACIÓN SPRINT 2: Relación con los chunks ---
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", 
        cascade="all, delete-orphan"
    )


# --- MODIFICACIÓN SPRINT 2: Nueva tabla para guardar texto extraído ---
class DocumentChunk(Base):
    """Stores extracted text chunks from documents."""

    __tablename__ = "document_chunks"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Metadatos físicos
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # El contenido real
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Clasificación simple (HECHO, CLAUSULA, FECHA, GENERAL)
    semantic_type: Mapped[str] = mapped_column(String, nullable=False, default="GENERAL")

    # Vector de embeddings (modelo local 384 dims)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")


class CaseMetadata(Base):
    """Technical sheet extracted from case documents."""

    __tablename__ = "case_metadata"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    start_date: Mapped[date | None] = mapped_column(nullable=True)
    end_date: Mapped[date | None] = mapped_column(nullable=True)
    daily_salary: Mapped[float | None] = mapped_column(nullable=True)
    start_date_source_doc_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    start_date_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date_bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    end_date_source_doc_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    end_date_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_date_bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    daily_salary_source_doc_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    daily_salary_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_salary_bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extraction_status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")
    is_verified: Mapped[bool] = mapped_column(nullable=False, default=False)

    case: Mapped[Case] = relationship(back_populates="metadata_info")


class TechnicalFact(Base):
    """Smart field persisted for technical sheet traceability."""

    __tablename__ = "technical_facts"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    pillar: Mapped[str] = mapped_column(String, nullable=False)
    field_key: Mapped[str] = mapped_column(String, nullable=False)
    value_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_normalized: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_doc_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_doc_type: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_level: Mapped[str] = mapped_column(String, nullable=False, default="LOW")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    truth_status: Mapped[str] = mapped_column(String, nullable=False, default="FACT")
    rule_applied: Mapped[str | None] = mapped_column(String, nullable=True)
    party_side: Mapped[str | None] = mapped_column(String, nullable=True)
    conflict_group_id: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    precedence_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    legal_defense_strength: Mapped[str | None] = mapped_column(String, nullable=True)
    why_critical: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    case: Mapped[Case] = relationship(back_populates="technical_facts")
    source_document: Mapped["Document | None"] = relationship()


class TechnicalAlert(Base):
    """Aggregated legal/compliance alerts for technical sheet."""

    __tablename__ = "technical_alerts"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[str | None] = mapped_column(String, nullable=True)
    why_flagged: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_doc_type: Mapped[str | None] = mapped_column(String, nullable=True)
    field_key: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_fact_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    case: Mapped[Case] = relationship(back_populates="technical_alerts")


class TechnicalSnapshot(Base):
    """Executive summary snapshot for technical sheet."""

    __tablename__ = "technical_snapshot"

    case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    overall_status: Mapped[str] = mapped_column(String, nullable=False, default="YELLOW")
    litis_narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    narrative_mode: Mapped[str] = mapped_column(String, nullable=False, default="DETERMINISTIC")
    dimension_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    high_impact_alerts: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    case: Mapped[Case] = relationship(back_populates="technical_snapshot")
