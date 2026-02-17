import logging
import re
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pdfplumber
from app.db.models import CaseMetadata, Document, DocumentChunk
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService
from app.services.storage import StorageService
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

logger = logging.getLogger(__name__)


class ExtractionService:

    REGEX_MONEY = r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)"
    REGEX_MONEY_FALLBACK = r"\b(\d{2,}(?:,\d{3})*(?:\.\d{2})?)\b"
    REGEX_DATE = r"(\d{1,2})\s+(?:de\s+)?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(\d{4})|(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})"

    @staticmethod
    def extract_case_metadata(db: Session, case_id: UUID, *, task_id: str | None = None):
        """
        Llena la ficha técnica buscando semánticamente en TODO el caso.
        """
        metadata = db.scalar(select(CaseMetadata).where(CaseMetadata.case_id == case_id))
        if not metadata:
            metadata = CaseMetadata(case_id=case_id)
            db.add(metadata)

        targets = [
            {"field": "daily_salary", "query": "salario diario cuota diaria sueldo base", "type": "money"},
            {"field": "start_date", "query": "fecha de ingreso inicio de labores comenzó a trabajar", "type": "date"},
            {"field": "end_date", "query": "fecha de despido terminación de la relación laboral baja", "type": "date"},
        ]

        provider = LLMService.current_provider()
        model = LLMService.current_extract_model()
        logger.info(
            "extract_metadata_start case_id=%s task_id=%s provider=%s model=%s",
            case_id,
            task_id,
            provider,
            model,
        )

        for target in targets:
            chunk = ExtractionService._semantic_search(db, case_id, target["query"])

            if chunk:
                structured = LLMService.extract_structured(chunk.text_content)
                llm_value = structured.get(target["field"])
                match = None
                if llm_value:
                    coerced = ExtractionService._coerce_value(llm_value, target["type"])
                    if coerced is not None:
                        match = (coerced, str(llm_value))
                    else:
                        match = ExtractionService._apply_regex(chunk.text_content, target["type"])
                else:
                    match = ExtractionService._apply_regex(chunk.text_content, target["type"])
                if match:
                    value, raw_text = match
                    setattr(metadata, target["field"], value)
                    metadata.is_verified = False

                    doc_id = chunk.document_id
                    page_number = chunk.page_number
                    bbox = None
                    doc = chunk.document
                    if doc and doc.file_path and raw_text:
                        bbox = ExtractionService._find_bbox_in_pdf(
                            Path(doc.file_path),
                            page_number,
                            raw_text,
                        )

                    if target["field"] == "start_date":
                        metadata.start_date_source_doc_id = doc_id
                        metadata.start_date_page = page_number
                        metadata.start_date_bbox = bbox
                    elif target["field"] == "end_date":
                        metadata.end_date_source_doc_id = doc_id
                        metadata.end_date_page = page_number
                        metadata.end_date_bbox = bbox
                    elif target["field"] == "daily_salary":
                        metadata.daily_salary_source_doc_id = doc_id
                        metadata.daily_salary_page = page_number
                        metadata.daily_salary_bbox = bbox

                    logger.info(
                        "extract_metadata_field case_id=%s task_id=%s field=%s doc_id=%s page=%s value=%s source=%s",
                        case_id,
                        task_id,
                        target["field"],
                        doc_id,
                        page_number,
                        value,
                        "llm+coerce" if llm_value else "regex",
                    )
                else:
                    logger.warning(
                        "extract_metadata_field_not_found case_id=%s task_id=%s field=%s doc_id=%s page=%s",
                        case_id,
                        task_id,
                        target["field"],
                        chunk.document_id,
                        chunk.page_number,
                    )
            else:
                logger.warning(
                    "extract_metadata_no_chunk case_id=%s task_id=%s field=%s",
                    case_id,
                    task_id,
                    target["field"],
                )

        metadata.extraction_status = "COMPLETED"
        db.commit()
        logger.info("extract_metadata_done case_id=%s task_id=%s metadata_id=%s", case_id, task_id, metadata.id)
        return metadata

    @staticmethod
    def _semantic_search(db: Session, case_id: UUID, query: str):
        query_vec = EmbeddingService.generate_embedding(query)
        chunk = db.scalars(
            select(DocumentChunk)
            .join(Document)
            .where(Document.case_id == case_id)
            .options(selectinload(DocumentChunk.document))
            .order_by(DocumentChunk.embedding.l2_distance(query_vec))
            .limit(1)
        ).first()
        return chunk

    @staticmethod
    def _apply_regex(text: str, dtype: str):
        try:
            if dtype == "money":
                lines = (text or "").splitlines()
                salary_lines = [
                    ln for ln in lines
                    if any(k in ln.lower() for k in ("salario", "sueldo", "cuota", "sdi", "neto"))
                ]
                # 1) Prefer monto con simbolo $ en lineas de salario/sueldo.
                for line in salary_lines:
                    m = re.search(ExtractionService.REGEX_MONEY, line)
                    if m:
                        raw = m.group(1)
                        return float(raw.replace(",", "")), raw
                # 2) Luego cualquier monto con simbolo $ en el texto completo.
                m = re.search(ExtractionService.REGEX_MONEY, text or "")
                if m:
                    raw = m.group(1)
                    return float(raw.replace(",", "")), raw
                # 3) Fallback: numero monetario (2+ digitos) en lineas de salario.
                for line in salary_lines:
                    m = re.search(ExtractionService.REGEX_MONEY_FALLBACK, line)
                    if m:
                        raw = m.group(1)
                        return float(raw.replace(",", "")), raw

            elif dtype == "date":
                match = re.search(ExtractionService.REGEX_DATE, text, re.IGNORECASE)
                if match:
                    if match.group(2):
                        day, month_str, year = match.group(1), match.group(2), match.group(3)
                        month_map = {
                            "enero": 1,
                            "febrero": 2,
                            "marzo": 3,
                            "abril": 4,
                            "mayo": 5,
                            "junio": 6,
                            "julio": 7,
                            "agosto": 8,
                            "septiembre": 9,
                            "octubre": 10,
                            "noviembre": 11,
                            "diciembre": 12,
                        }
                        return datetime(int(year), month_map[month_str.lower()], int(day)).date(), match.group(0)
                    else:
                        day, month, year = match.group(4), match.group(5), match.group(6)
                        if len(year) == 2:
                            year = f"20{year}"
                        return datetime(int(year), int(month), int(day)).date(), match.group(0)
        except Exception:
            return None
        return None

    @staticmethod
    def _coerce_value(value, dtype: str):
        if value is None:
            return None
        try:
            if dtype == "money":
                if isinstance(value, (int, float)):
                    return float(value)
                raw = str(value).replace("$", "").replace(",", "").strip()
                return float(raw)
            if dtype == "date":
                if hasattr(value, "isoformat"):
                    return value
                parsed = ExtractionService._apply_regex(str(value), "date")
                if parsed:
                    return parsed[0]
        except Exception:
            return None
        return None

    @staticmethod
    def _find_bbox_in_pdf(file_path: Path, page_number: int, needle: str):
        try:
            temp_path = None
            if str(file_path).startswith("s3://"):
                temp_path = StorageService.download_to_tempfile(str(file_path))
                file_path = temp_path
            if not file_path.exists():
                return None
            with pdfplumber.open(str(file_path)) as pdf:
                page_index = max(page_number - 1, 0)
                if page_index >= len(pdf.pages):
                    return None
                page = pdf.pages[page_index]
                words = page.extract_words()
                needle_lower = needle.lower()
                for w in words:
                    if needle_lower in (w.get("text") or "").lower():
                        return {
                            "x0": w.get("x0"),
                            "y0": w.get("top"),
                            "x1": w.get("x1"),
                            "y1": w.get("bottom"),
                            "page": page_number,
                        }
        except Exception as exc:
            logger.warning("No se pudo obtener bbox: %s", exc)
        finally:
            try:
                if temp_path and temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
        return None
