import re
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID
import logging

from app.db.models import Case, CaseMetadata, Document, DocumentChunk
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class ExtractionService:

    REGEX_MONEY = r"\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)"
    REGEX_DATE = r"(\d{1,2})\s+(?:de\s+)?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(\d{4})|(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})"

    @staticmethod
    def extract_case_metadata(db: Session, case_id: UUID):
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

        for target in targets:
            chunk = ExtractionService._semantic_search(db, case_id, target["query"])

            if chunk:
                val = ExtractionService._apply_regex(chunk.text_content, target["type"])
                if val:
                    setattr(metadata, target["field"], val)
                    metadata.is_verified = False

        metadata.extraction_status = "COMPLETED"
        db.commit()
        return metadata

    @staticmethod
    def _semantic_search(db: Session, case_id: UUID, query: str):
        query_vec = EmbeddingService.generate_embedding(query)
        chunk = db.scalars(
            select(DocumentChunk)
            .join(Document)
            .where(Document.case_id == case_id)
            .order_by(DocumentChunk.embedding.l2_distance(query_vec))
            .limit(1)
        ).first()
        return chunk

    @staticmethod
    def _apply_regex(text: str, dtype: str):
        try:
            if dtype == "money":
                matches = re.findall(ExtractionService.REGEX_MONEY, text)
                if matches:
                    return float(matches[0].replace(",", ""))

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
                        return datetime(int(year), month_map[month_str.lower()], int(day)).date()
                    else:
                        day, month, year = match.group(4), match.group(5), match.group(6)
                        if len(year) == 2:
                            year = f"20{year}"
                        return datetime(int(year), int(month), int(day)).date()
        except:
            return None
        return None
