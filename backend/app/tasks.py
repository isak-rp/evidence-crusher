from __future__ import annotations

from uuid import UUID

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.ingestion import IngestionService
from app.services.embeddings import EmbeddingService
from app.services.extraction import ExtractionService
from app.services.audit import AuditService
from app.db.models import DocumentChunk
from sqlalchemy import select


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@celery_app.task(name="app.tasks.process_document")
def process_document(document_id: str):
    for db in _get_db():
        return IngestionService.process_document(db, UUID(document_id))


@celery_app.task(
    name="app.tasks.embed_document",
    soft_time_limit=120,
    time_limit=150,
)
def embed_document(document_id: str):
    for db in _get_db():
        try:
            stmt = select(DocumentChunk).where(DocumentChunk.document_id == UUID(document_id))
            chunks = db.execute(stmt).scalars().all()
            count = 0
            for chunk in chunks:
                if chunk.embedding is None:
                    chunk.embedding = EmbeddingService.generate_embedding(chunk.text_content)
                    count += 1
            db.commit()
            return {"status": "indexed", "chunks_embedded": count}
        except Exception:
            db.rollback()
            raise


@celery_app.task(name="app.tasks.extract_case_metadata")
def extract_case_metadata(case_id: str):
    for db in _get_db():
        data = ExtractionService.extract_case_metadata(db, UUID(case_id))
        return {"status": "success", "data": str(data.id)}


@celery_app.task(name="app.tasks.audit_case")
def audit_case(case_id: str):
    for db in _get_db():
        return AuditService.run_case_audit(db, UUID(case_id))
