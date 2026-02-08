"""Document processing endpoints."""

from __future__ import annotations

from uuid import UUID

from datetime import datetime
from pathlib import Path
import os
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case, Document, DocumentChunk
from app.services.embeddings import EmbeddingService
from app.services.ingestion import IngestionService

router = APIRouter()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploaded_files"))


@router.post("/", status_code=status.HTTP_200_OK)
def upload_document(
    case_id: UUID = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    case = db.execute(select(Case).where(Case.id == case_id)).scalars().first()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{case_id}_{file.filename}"
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
    return {"status": "created", "document_id": str(document.id)}


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


@router.post("/{document_id}/embed", status_code=status.HTTP_200_OK)
def create_embeddings(document_id: UUID, db: Session = Depends(get_db)) -> dict[str, str | int]:
    """
    Toma los chunks de texto existentes y genera sus vectores.
    """
    stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    chunks = db.execute(stmt).scalars().all()

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No hay chunks procesados para este documento. Ejecuta /process primero.",
        )

    count = 0
    for chunk in chunks:
        if chunk.embedding is None:
            vector = EmbeddingService.generate_embedding(chunk.text_content)
            chunk.embedding = vector
            count += 1

    db.commit()
    return {"status": "indexed", "chunks_embedded": count}


class SearchQuery(BaseModel):
    query: str
    limit: int = 5


@router.post("/{document_id}/search", status_code=status.HTTP_200_OK)
def search_document(
    document_id: UUID, search: SearchQuery, db: Session = Depends(get_db)
) -> list[dict[str, str | int]]:
    """
    Busca los fragmentos más relevantes dentro de un documento usando similitud semántica.
    """
    query_vector = EmbeddingService.generate_embedding(search.query)

    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.embedding.l2_distance(query_vector))
        .limit(search.limit)
    ).all()

    results: list[dict[str, str | int]] = []
    for chunk in chunks:
        results.append(
            {
                "text": chunk.text_content,
                "page": chunk.page_number,
                "type": chunk.semantic_type,
            }
        )

    return results
