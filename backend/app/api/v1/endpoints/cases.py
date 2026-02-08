"""Case management endpoints."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Case, Document
from app.db.session import get_db
from app.schemas.cases import (
    CaseCreate,
    CaseResponse,
    DocumentResponse,
    CaseMetadataResponse,
)
from app.services.extraction import ExtractionService

router = APIRouter(tags=["cases"])

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploaded_files"))


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> CaseResponse:
    new_case = Case(title=payload.title, description=payload.description)
    db.add(new_case)
    db.commit()
    db.refresh(new_case)
    return CaseResponse.model_validate(new_case)


@router.get("/", response_model=list[CaseResponse])
def list_cases(db: Session = Depends(get_db)) -> list[CaseResponse]:
    statement = (
        select(Case)
        .options(selectinload(Case.documents), selectinload(Case.metadata_info))
        .order_by(Case.created_at.desc())
    )
    cases = db.execute(statement).scalars().all()
    return [CaseResponse.model_validate(case) for case in cases]


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: UUID, db: Session = Depends(get_db)) -> CaseResponse:
    statement = (
        select(Case)
        .where(Case.id == case_id)
        .options(selectinload(Case.documents), selectinload(Case.metadata_info))
    )
    case = db.execute(statement).scalars().first()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseResponse.model_validate(case)


@router.post(
    "/{case_id}/documents/",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    case_id: UUID,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    case = db.execute(select(Case).where(Case.id == case_id)).scalars().first()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid4()}_{file.filename}"
    destination = UPLOAD_DIR / safe_name

    try:
        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    document = Document(
        case_id=case_id,
        filename=file.filename,
        file_path=str(destination),
        doc_type=doc_type,
        upload_date=datetime.utcnow(),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return DocumentResponse.model_validate(document)


@router.post("/{case_id}/extract-metadata")
def extract_metadata_endpoint(case_id: UUID, db: Session = Depends(get_db)):
    """Analiza documentos y extrae fechas/montos automáticamente."""
    try:
        data = ExtractionService.extract_case_metadata(db, case_id)
        return {"status": "success", "data": CaseMetadataResponse.model_validate(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
