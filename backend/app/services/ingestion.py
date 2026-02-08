"""Deterministic PDF ingestion pipeline (no AI)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

import pdfplumber
import pytesseract
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk

logger = logging.getLogger(__name__)


class IngestionService:
    @staticmethod
    def detect_pdf_type(file_path: str) -> str:
        """
        Reads the first page. If selectable text exists, it's NATIVE.
        Otherwise, treat as SCANNED (image-based).
        """
        try:
            with pdfplumber.open(file_path) as pdf:
                if pdf.pages:
                    first_page_text = pdf.pages[0].extract_text() or ""
                    if len(first_page_text.strip()) > 50:
                        return "NATIVO"
        except Exception as exc:
            logger.error("Error detectando tipo PDF: %s", exc)

        return "ESCANEADO"

    @staticmethod
    def process_document(db: Session, document_id: UUID) -> dict[str, Any]:
        """
        Orchestrates reading and chunk persistence.
        """
        doc = db.get(Document, document_id)
        if not doc:
            raise ValueError("Documento no encontrado")

        file_path = Path(doc.file_path)
        if not file_path.exists():
            raise ValueError("Archivo físico no encontrado")

        strategy = IngestionService.detect_pdf_type(str(file_path))
        logger.info("Procesando doc %s como %s", doc.filename, strategy)

        chunks_created = 0

        try:
            with pdfplumber.open(str(file_path)) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_num = i + 1
                    if strategy == "NATIVO":
                        text = page.extract_text() or ""
                    else:
                        pil_image = page.to_image(resolution=300).original
                        text = pytesseract.image_to_string(pil_image, lang="spa")

                    text = text.replace("-\n", "").replace("\n", " ")
                    raw_chunks = [c.strip() for c in text.split(". ") if len(c.strip()) > 20]

                    for idx, chunk_text in enumerate(raw_chunks):
                        new_chunk = DocumentChunk(
                            document_id=document_id,
                            page_number=page_num,
                            chunk_index=idx,
                            text_content=chunk_text,
                            semantic_type="GENERAL",
                        )
                        db.add(new_chunk)
                        chunks_created += 1

            db.commit()
            return {"status": "success", "strategy": strategy, "chunks": chunks_created}
        except Exception as exc:
            db.rollback()
            logger.error("Fallo en ingesta: %s", exc)
            raise
