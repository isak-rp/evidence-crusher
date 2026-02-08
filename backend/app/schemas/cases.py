"""Pydantic schemas for case management."""

from __future__ import annotations

from datetime import datetime, date
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


class CaseMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_date: date | None = None
    end_date: date | None = None
    daily_salary: float | None = None
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
