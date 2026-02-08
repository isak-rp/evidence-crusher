"""Document processing endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.ingestion import IngestionService

router = APIRouter()


@router.post("/{document_id}/process", status_code=status.HTTP_200_OK)
def process_document_content(
    document_id: UUID, db: Session = Depends(get_db)
) -> dict[str, str | int]:
    """
    Triggers OCR/reading for a specific document.
    """
    try:
        result = IngestionService.process_document(db, document_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno procesando PDF: {exc}",
        ) from exc
