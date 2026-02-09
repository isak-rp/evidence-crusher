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
        """
        Clasifica documentos según los 4 Pilares de Defensa Patronal.
        Si no cumple con los criterios, devuelve 'REVISION_REQUERIDA'.
        """
        t = text.lower()[:4000]

        # --- PILAR I: CONTRATACIÓN (BLINDAJE INICIAL) ---
        if "confidencialidad" in t and "competencia" in t:
            return "CONVENIO_NDA"
        if "teletrabajo" in t or "nom-037" in t or "nom 037" in t:
            return "CONTRATO_TELETRABAJO"
        if "aviso de privacidad" in t:
            return "AVISO_PRIVACIDAD"
        if "solicitud de empleo" in t:
            return "SOLICITUD_EMPLEO"
        if "herramientas de trabajo" in t or "carta responsiva" in t:
            return "RESPONSIVA_HERRAMIENTAS"
        if "contrato individual" in t or "tiempo indeterminado" in t or "obra determinada" in t:
            return "CONTRATO_INDIVIDUAL"

        # --- PILAR II: CONTROL OPERATIVO Y DISCIPLINARIO ---
        if "lista de asistencia" in t or "control de asistencia" in t or "reloj checador" in t:
            return "LISTA_ASISTENCIA"
        if "recibo de nómina" in t or "cfdi" in t:
            return "RECIBO_NOMINA"
        if "control de vacaciones" in t or "prima vacacional" in t:
            return "CONSTANCIA_VACACIONES"
        if "aguinaldo" in t or "ptu" in t or "participación de los trabajadores" in t:
            return "RECIBO_AGUINALDO_PTU"
        if "reglamento interior" in t:
            return "REGLAMENTO_INTERIOR"
        if "acta administrativa" in t:
            return "ACTA_ADMINISTRATIVA"
        if "amonestación" in t or "suspensión temporal" in t:
            return "SANCION_DISCIPLINARIA"

        # --- PILAR III: CUMPLIMIENTO NORMATIVO (COMPLIANCE) ---
        if "nom-035" in t or "riesgo psicosocial" in t or "ats" in t:
            return "CARPETA_NOM035"
        if "seguridad e higiene" in t or "comisión mixta" in t or "recorrido de verificación" in t:
            return "CARPETA_SEGURIDAD"
        if "plan de capacitación" in t or "dc-3" in t or "dc3" in t or "constancia de competencias" in t:
            return "CAPACITACION_DC3"
        if "repse" in t or "servicios especializados" in t:
            return "EXPEDIENTE_REPSE"
        if "protocolo" in t and ("hostigamiento" in t or "acoso" in t):
            return "PROTOCOLO_ACOSO"

        # --- PILAR IV: TERMINACIÓN Y SALIDA ---
        if "renuncia" in t and ("irrevocable" in t or "voluntaria" in t):
            return "CARTA_RENUNCIA"
        if "convenio" in t and ("terminación" in t or "mutuo consentimiento" in t):
            return "CONVENIO_TERMINACION"
        if "finiquito" in t or "liquidación" in t:
            return "RECIBO_FINIQUITO"
        if "aviso de rescisión" in t or "rescisión de la relación" in t:
            return "AVISO_RESCISION"
        if "constancia de trabajo" in t or "carta de recomendación" in t:
            return "CONSTANCIA_LABORAL"

        # --- PILAR V: DOCUMENTACIÓN PROCESAL (JUICIO) ---
        if "poder notarial" in t or "poder general" in t:
            return "PODER_NOTARIAL"
        if "contestación" in t and "demanda" in t:
            return "CONTESTACION_DEMANDA"
        if "ofrecimiento de pruebas" in t or "pruebas y alegatos" in t:
            return "OFRECIMIENTO_PRUEBAS"
        if "pliego" in t and "posiciones" in t:
            return "PLIEGO_POSICIONES"
        if "interrogatorio" in t:
            return "INTERROGATORIO_TESTIGOS"
        if "alegatos" in t:
            return "ESCRITO_ALEGATOS"
        if "amparo directo" in t or "quejoso" in t:
            return "DEMANDA_AMPARO"

        # --- REGLA DE DESCARTE/ADVERTENCIA ---
        return "⚠️ REVISION_REQUERIDA"

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
