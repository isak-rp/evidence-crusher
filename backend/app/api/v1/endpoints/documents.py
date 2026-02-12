"""Document processing endpoints."""

from __future__ import annotations

from uuid import UUID

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
import mimetypes
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case, Document, DocumentChunk
from app.services.embeddings import EmbeddingService
from app.services.storage import StorageService
from app.tasks import process_document as process_document_task
from app.tasks import embed_document as embed_document_task

router = APIRouter()


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

    try:
        content = file.file.read()
    finally:
        file.file.close()

    safe_name = f"{case_id}_{file.filename}"
    s3_url = StorageService.upload_bytes(
        safe_name,
        content,
        content_type=file.content_type,
    )

    document = Document(
        case_id=case_id,
        filename=file.filename,
        file_path=s3_url,
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
        task = process_document_task.delay(str(document_id))
        return {"status": "queued", "task_id": task.id}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno procesando PDF: {exc}",
        ) from exc


@router.get("/{document_id}/file", status_code=status.HTTP_200_OK)
def get_document_file(document_id: UUID, db: Session = Depends(get_db)) -> FileResponse:
    """
    Sirve el archivo físico para visualización en frontend.
    """
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if str(doc.file_path).startswith("s3://"):
        data = StorageService.download_bytes(doc.file_path)
        media_type, _ = mimetypes.guess_type(doc.filename)
        return StreamingResponse(
            iter([data]),
            media_type=media_type or "application/octet-stream",
            headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
        )

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo físico no encontrado")

    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        path=str(file_path),
        filename=doc.filename,
        media_type=media_type or "application/octet-stream",
    )


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(document_id: UUID, db: Session = Depends(get_db)) -> dict[str, str]:
    """
    Elimina un documento, sus chunks/vectores y el archivo físico si existe.
    """
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    try:
        if doc.file_path and str(doc.file_path).startswith("s3://"):
            StorageService.delete_object(doc.file_path)
        else:
            file_path = Path(doc.file_path) if doc.file_path else None
            if file_path and file_path.exists():
                file_path.unlink()
    except Exception:
        pass

    try:
        db.delete(doc)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error eliminando documento: {exc}") from exc

    return {"status": "deleted", "document_id": str(document_id)}


@router.post("/{document_id}/embed", status_code=status.HTTP_200_OK)
def create_embeddings(document_id: UUID, db: Session = Depends(get_db)) -> dict[str, str | int]:
    """
    Toma los chunks de texto existentes y genera sus vectores.
    """
    task = embed_document_task.delay(str(document_id))
    return {"status": "queued", "task_id": task.id}


class ChatQuery(BaseModel):
    question: str
    limit: int = 5


@router.post("/{document_id}/chat", status_code=status.HTTP_200_OK)
def chat_with_document(
    document_id: UUID, payload: ChatQuery, db: Session = Depends(get_db)
) -> dict[str, object]:
    """
    Chat contextual con citaciones usando command-r.
    """
    query_vector = EmbeddingService.generate_embedding(payload.question)
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.embedding.l2_distance(query_vector))
        .limit(payload.limit)
    ).all()
    context = "\n\n".join(
        [f"[p{c.page_number}] {c.text_content}" for c in chunks]
    )
    from app.services.llm import LLMService

    answer = LLMService.rag_answer(payload.question, context)
    sources = [{"page": c.page_number, "text": c.text_content[:240]} for c in chunks]
    return {"answer": answer, "sources": sources}
