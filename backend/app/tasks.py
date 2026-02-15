from __future__ import annotations

import logging
from uuid import UUID

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.ingestion import IngestionService
from app.services.embeddings import EmbeddingService
from app.services.extraction import ExtractionService
from app.services.audit import AuditService
from app.services.technical_sheet import TechnicalSheetService
from app.db.models import DocumentChunk
from sqlalchemy import select

logger = logging.getLogger(__name__)


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


@celery_app.task(name="app.tasks.extract_case_metadata", bind=True)
def extract_case_metadata(self, case_id: str):
    for db in _get_db():
        task_id = getattr(self.request, "id", None)
        logger.info("task_start name=extract_case_metadata task_id=%s case_id=%s", task_id, case_id)
        data = ExtractionService.extract_case_metadata(db, UUID(case_id), task_id=task_id)
        if TechnicalSheetService.feature_enabled():
            TechnicalSheetService.build_case_technical_sheet(db, UUID(case_id), task_id=task_id)
        logger.info("task_done name=extract_case_metadata task_id=%s case_id=%s metadata_id=%s", task_id, case_id, data.id)
        return {"status": "success", "data": str(data.id)}


@celery_app.task(name="app.tasks.audit_case", bind=True)
def audit_case(self, case_id: str):
    for db in _get_db():
        task_id = getattr(self.request, "id", None)
        logger.info("task_start name=audit_case task_id=%s case_id=%s", task_id, case_id)
        return AuditService.run_case_audit(db, UUID(case_id))


@celery_app.task(name="app.tasks.build_technical_sheet", bind=True)
def build_technical_sheet(self, case_id: str):
    for db in _get_db():
        task_id = getattr(self.request, "id", None)
        logger.info("task_start name=build_technical_sheet task_id=%s case_id=%s", task_id, case_id)
        sheet = TechnicalSheetService.build_case_technical_sheet(db, UUID(case_id), task_id=task_id)
        logger.info("task_done name=build_technical_sheet task_id=%s case_id=%s", task_id, case_id)
        return {"status": "success", "case_id": str(sheet.case_id)}
