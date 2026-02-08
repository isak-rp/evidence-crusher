import pdfplumber
import pytesseract
from sqlalchemy.orm import Session
from uuid import UUID
from pathlib import Path
import logging
import re

from app.db.models import Document, DocumentChunk

logger = logging.getLogger(__name__)


class IngestionService:

    @staticmethod
    def _classify_document(text: str) -> str:
        """Reglas heurísticas para detectar el tipo de documento."""
        text_lower = text.lower()[:3000]

        if any(w in text_lower for w in ["contrato individual", "tiempo indeterminado", "obra determinada"]):
            return "CONTRATO"
        if any(w in text_lower for w in ["escrito inicial", "h. junta", "tribunal laboral", "demanda", "reclamo"]):
            return "DEMANDA"
        if any(w in text_lower for w in ["sentencia", "laudo", "resolución", "acuerdo"]):
            return "SENTENCIA/AUTO"
        if any(w in text_lower for w in ["notificación", "emplazamiento", "cédula"]):
            return "NOTIFICACION"
        if any(w in text_lower for w in ["renuncia", "finiquito", "baja"]):
            return "BAJA/RENUNCIA"
        if any(w in text_lower for w in ["recibo de pago", "nómina", "cfdi"]):
            return "RECIBO_NOMINA"

        return "OTRO"

    @staticmethod
    def process_document(db: Session, document_id: UUID) -> dict:
        doc = db.get(Document, document_id)
        if not doc:
            raise ValueError("Documento no encontrado")

        file_path = Path(doc.file_path)
        if not file_path.exists():
            raise ValueError("Archivo físico no encontrado")

        strategy = "ESCANEADO"
        try:
            with pdfplumber.open(str(file_path)) as pdf:
                if len(pdf.pages) > 0 and len((pdf.pages[0].extract_text() or "").strip()) > 50:
                    strategy = "NATIVO"
        except:
            pass

        logger.info(f"Procesando {doc.filename} como {strategy}")
        chunks_created = 0
        full_first_page_text = ""

        try:
            with pdfplumber.open(str(file_path)) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_num = i + 1

                    text = ""
                    if strategy == "NATIVO":
                        text = page.extract_text() or ""
                    else:
                        pil_image = page.to_image(resolution=300).original
                        text = pytesseract.image_to_string(pil_image, lang='spa')

                    if i == 0:
                        full_first_page_text = text

                    text = text.replace("-\n", "").replace("\n", " ")
                    text = re.sub(r'\s+', ' ', text).strip()

                    chunk_size = 1000
                    overlap = 200

                    if len(text) > 0:
                        start = 0
                        while start < len(text):
                            end = start + chunk_size
                            if end < len(text):
                                while end > start and text[end] != ' ':
                                    end -= 1
                                if end == start:
                                    end = start + chunk_size

                            chunk_text = text[start:end]

                            if len(chunk_text) > 50:
                                new_chunk = DocumentChunk(
                                    document_id=document_id,
                                    page_number=page_num,
                                    chunk_index=chunks_created,
                                    text_content=chunk_text,
                                    semantic_type="GENERAL"
                                )
                                db.add(new_chunk)
                                chunks_created += 1

                            start = end - overlap
                            if start >= end:
                                start = end

            if full_first_page_text:
                detected_type = IngestionService._classify_document(full_first_page_text)
                doc.doc_type = detected_type
                db.add(doc)
            else:
                detected_type = "DESCONOCIDO"

            db.commit()
            return {"status": "success", "strategy": strategy, "chunks": chunks_created, "type": detected_type}

        except Exception as e:
            db.rollback()
            logger.error(f"Fallo ingesta: {e}")
            raise e
