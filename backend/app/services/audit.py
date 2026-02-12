from __future__ import annotations

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, Document
from app.services.llm import LLMService


class AuditService:
    @staticmethod
    def run_case_audit(db: Session, case_id: UUID) -> dict:
        chunks = db.scalars(
            select(DocumentChunk)
            .join(Document)
            .where(Document.case_id == case_id)
            .limit(50)
        ).all()
        context = "\n\n".join([c.text_content for c in chunks])
        result = LLMService.audit_inconsistencies(context)
        return {"status": "completed", "result": result}
