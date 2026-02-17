"""Pydantic schemas for case management."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CaseCreate(BaseModel):
    title: str
    description: str


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    doc_type: str
    is_classified: bool | None = None
    is_indexed: bool | None = None
    chunk_count: int | None = None
    indexed_chunk_count: int | None = None


class CaseMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_date: date | None = None
    end_date: date | None = None
    daily_salary: float | None = None
    start_date_source_doc_id: UUID | None = None
    start_date_page: int | None = None
    start_date_bbox: dict | None = None
    end_date_source_doc_id: UUID | None = None
    end_date_page: int | None = None
    end_date_bbox: dict | None = None
    daily_salary_source_doc_id: UUID | None = None
    daily_salary_page: int | None = None
    daily_salary_bbox: dict | None = None
    extraction_status: str | None = None
    is_verified: bool | None = None


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: str
    created_at: datetime
    documents: list[DocumentResponse] = []
    metadata_info: CaseMetadataResponse | None = None
