from __future__ import annotations

from app.db.models import Document

ALIASES: dict[str, str] = {
    "NOMINA_CFDI": "RECIBO_NOMINA",
    "CFDI_NOMINA": "RECIBO_NOMINA",
    "RECIBO_SUELDO": "RECIBO_NOMINA",
    "CONTRATO_TRABAJO": "CONTRATO_INDIVIDUAL",
    "DEMANDA": "DEMANDA_INICIAL",
    "AVISO_RESCISION_PATRONAL": "AVISO_RESCISION",
    "RENUNCIA": "CARTA_RENUNCIA",
    "ACTA_ADMIN": "ACTA_ADMINISTRATIVA",
}


def canonical_doc_type(doc_type: str | None, filename: str | None = None) -> str:
    dt = (doc_type or "").strip().upper()
    if dt in ALIASES:
        return ALIASES[dt]
    if dt:
        return dt

    # Fallback por nombre de archivo cuando doc_type no es confiable.
    name = (filename or "").lower()
    if "nomina" in name or "cfdi" in name:
        return "RECIBO_NOMINA"
    if "contrato" in name:
        return "CONTRATO_INDIVIDUAL"
    if "demanda" in name:
        return "DEMANDA_INICIAL"
    if "renuncia" in name:
        return "CARTA_RENUNCIA"
    if "rescision" in name:
        return "AVISO_RESCISION"
    if "asistencia" in name:
        return "LISTA_ASISTENCIA"
    if "reglamento" in name:
        return "REGLAMENTO_INTERIOR"
    if "imss" in name:
        return "ALTA_IMSS"
    return "SIN_CLASIFICAR"


def build_docs_by_canonical_type(documents: list[Document]) -> tuple[dict[str, list[Document]], dict[str, str]]:
    docs_by_type: dict[str, list[Document]] = {}
    doc_id_to_type: dict[str, str] = {}
    for doc in documents:
        canonical = canonical_doc_type(doc.doc_type, doc.filename)
        docs_by_type.setdefault(canonical, []).append(doc)
        doc_id_to_type[str(doc.id)] = canonical
    return docs_by_type, doc_id_to_type
