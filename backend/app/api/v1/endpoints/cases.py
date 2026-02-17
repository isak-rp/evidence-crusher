"""Case management endpoints."""

from __future__ import annotations

from uuid import UUID

from app.db.models import Case, Document
from app.db.session import get_db
from app.schemas.cases import CaseCreate, CaseResponse
from app.schemas.technical_sheet import TechnicalSheetResponse
from app.services.technical_sheet import TechnicalSheetService
from app.tasks import build_technical_sheet as build_technical_sheet_task
from app.tasks import extract_case_metadata as extract_case_metadata_task
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

router = APIRouter(tags=["cases"])


def _build_case_response(case: Case) -> CaseResponse:
    documents_payload = []
    for doc in case.documents or []:
        chunks = doc.chunks or []
        chunk_count = len(chunks)
        indexed_chunk_count = sum(1 for c in chunks if c.embedding is not None)
        is_indexed = chunk_count > 0 and indexed_chunk_count == chunk_count
        is_classified = bool(
            doc.doc_type
            and doc.doc_type not in {"DETECTANDO...", "SIN_CLASIFICAR"}
        )
        documents_payload.append(
            {
                "id": doc.id,
                "filename": doc.filename,
                "doc_type": doc.doc_type,
                "is_classified": is_classified,
                "is_indexed": is_indexed,
                "chunk_count": chunk_count,
                "indexed_chunk_count": indexed_chunk_count,
            }
        )

    return CaseResponse.model_validate(
        {
            "id": case.id,
            "title": case.title,
            "status": case.status,
            "created_at": case.created_at,
            "documents": documents_payload,
            "metadata_info": case.metadata_info,
        }
    )


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> CaseResponse:
    existing_case = db.scalar(select(Case).where(Case.title == payload.title))
    if existing_case:
        raise HTTPException(
            status_code=400,
            detail=f"Ya existe un expediente con el nombre '{payload.title}'. Por favor elige otro.",
        )

    new_case = Case(title=payload.title, description=payload.description)
    db.add(new_case)
    db.commit()
    db.refresh(new_case)
    return _build_case_response(new_case)


@router.get("/", response_model=list[CaseResponse])
def list_cases(db: Session = Depends(get_db)) -> list[CaseResponse]:
    statement = (
        select(Case)
        .options(
            selectinload(Case.documents).selectinload(Document.chunks),
            selectinload(Case.metadata_info),
        )
        .order_by(Case.created_at.desc())
    )
    cases = db.execute(statement).scalars().all()
    return [_build_case_response(case) for case in cases]


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: UUID, db: Session = Depends(get_db)) -> CaseResponse:
    statement = (
        select(Case)
        .where(Case.id == case_id)
        .options(
            selectinload(Case.documents).selectinload(Document.chunks),
            selectinload(Case.metadata_info),
        )
    )
    case = db.execute(statement).scalars().first()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return _build_case_response(case)


@router.delete("/{case_id}", status_code=status.HTTP_200_OK)
def delete_case(case_id: UUID, db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    db.delete(case)
    db.commit()
    return {"status": "deleted", "id": str(case_id)}


@router.post("/{case_id}/extract-metadata")
def extract_metadata_endpoint(case_id: UUID, db: Session = Depends(get_db)):
    try:
        task = extract_case_metadata_task.delay(str(case_id))
        return {"status": "queued", "task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/build-technical-sheet")
def build_technical_sheet_endpoint(case_id: UUID, db: Session = Depends(get_db)):
    if not TechnicalSheetService.feature_enabled():
        raise HTTPException(status_code=404, detail="Technical sheet v2 disabled")
    try:
        task = build_technical_sheet_task.delay(str(case_id))
        return {"status": "queued", "task_id": task.id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{case_id}/technical-sheet", response_model=TechnicalSheetResponse)
def get_technical_sheet_endpoint(case_id: UUID, db: Session = Depends(get_db)) -> TechnicalSheetResponse:
    if not TechnicalSheetService.feature_enabled():
        raise HTTPException(status_code=404, detail="Technical sheet v2 disabled")
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    return TechnicalSheetService.get_case_technical_sheet(db, case_id)
