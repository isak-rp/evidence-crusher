from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Any


@dataclass(frozen=True)
class FieldSpec:
    pillar: str
    field_key: str
    queries: tuple[str, ...]
    preferred_doc_types: tuple[str, ...]
    is_critical: bool
    parser: Callable[[str], tuple[str | None, dict | None]]
    evidence_hint: str


MONEY_PATTERN = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")
DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+(?:de\s+)?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(\d{4})|(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",
    re.IGNORECASE,
)


def parse_money(text: str) -> tuple[str | None, dict | None]:
    match = MONEY_PATTERN.search(text or "")
    if not match:
        return None, None
    raw = match.group(1)
    try:
        amount = float(raw.replace(",", ""))
    except Exception:
        return None, None
    return raw, {"amount": amount, "currency": "MXN"}


def parse_date(text: str) -> tuple[str | None, dict | None]:
    match = DATE_PATTERN.search(text or "")
    if not match:
        return None, None
    raw = match.group(0)
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
        dt = datetime(int(year), month_map[month_str.lower()], int(day)).date()
        return raw, {"iso_date": str(dt)}
    day, month, year = match.group(4), match.group(5), match.group(6)
    if len(year) == 2:
        year = f"20{year}"
    dt = datetime(int(year), int(month), int(day)).date()
    return raw, {"iso_date": str(dt)}


def parse_contract_type(text: str) -> tuple[str | None, dict | None]:
    content = (text or "").lower()
    if "indeterminado" in content:
        return "indeterminado", {"contract_type": "INDETERMINADO"}
    if "determinado" in content:
        return "determinado", {"contract_type": "DETERMINADO"}
    if "periodo de prueba" in content or "prueba" in content:
        return "prueba", {"contract_type": "PRUEBA"}
    return None, None


def parse_position(text: str) -> tuple[str | None, dict | None]:
    content = (text or "").strip()
    if not content:
        return None, None
    # Heurística simple: primera línea útil.
    line = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
    if not line:
        return None, None
    return line[:120], {"position_excerpt": line[:120]}


FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec(
        pillar="IDENTIDAD",
        field_key="start_date_real",
        queries=("fecha de ingreso", "inicio de labores", "comenzo a trabajar"),
        preferred_doc_types=("CONTRATO_INDIVIDUAL", "ALTA_IMSS", "CONSTANCIA_LABORAL", "DEMANDA_INICIAL"),
        is_critical=True,
        parser=parse_date,
        evidence_hint="Agregar CONTRATO_INDIVIDUAL o ALTA_IMSS con fecha de ingreso visible.",
    ),
    FieldSpec(
        pillar="IDENTIDAD",
        field_key="contract_type",
        queries=("tipo de contrato", "duracion del contrato", "periodo de prueba"),
        preferred_doc_types=("CONTRATO_INDIVIDUAL",),
        is_critical=False,
        parser=parse_contract_type,
        evidence_hint="Agregar CONTRATO_INDIVIDUAL o CONVENIO_MODIFICATORIO.",
    ),
    FieldSpec(
        pillar="IDENTIDAD",
        field_key="position",
        queries=("puesto", "categoria", "funciones"),
        preferred_doc_types=("CONTRATO_INDIVIDUAL", "CONSTANCIA_LABORAL"),
        is_critical=False,
        parser=parse_position,
        evidence_hint="Agregar documento con puesto/categoria (contrato o constancia).",
    ),
    FieldSpec(
        pillar="ECONOMICA",
        field_key="salary_sd",
        queries=("salario diario", "cuota diaria", "sueldo base"),
        preferred_doc_types=("RECIBO_NOMINA", "CONTRATO_INDIVIDUAL"),
        is_critical=True,
        parser=parse_money,
        evidence_hint="Agregar RECIBO_NOMINA (CFDI) o contrato con salario diario.",
    ),
    FieldSpec(
        pillar="ECONOMICA",
        field_key="salary_sdi",
        queries=("salario diario integrado", "sdi"),
        preferred_doc_types=("RECIBO_NOMINA", "CONTRATO_INDIVIDUAL"),
        is_critical=False,
        parser=parse_money,
        evidence_hint="Agregar recibo o anexo con SDI.",
    ),
    FieldSpec(
        pillar="CONFLICTO",
        field_key="claimed_amount",
        queries=("monto reclamado", "prestaciones reclamadas", "cantidad reclamada"),
        preferred_doc_types=("DEMANDA_INICIAL",),
        is_critical=False,
        parser=parse_money,
        evidence_hint="Agregar DEMANDA_INICIAL con monto reclamado.",
    ),
    FieldSpec(
        pillar="CONFLICTO",
        field_key="closure_offer",
        queries=("finiquito", "oferta de pago", "liquidacion ofrecida"),
        preferred_doc_types=("RECIBO_FINIQUITO",),
        is_critical=False,
        parser=parse_money,
        evidence_hint="Agregar RECIBO_FINIQUITO o documento de oferta.",
    ),
)


def doc_type_priority(doc_type: str, preferred_doc_types: tuple[str, ...]) -> int:
    if doc_type in preferred_doc_types:
        return 100 - preferred_doc_types.index(doc_type)
    if doc_type == "DEMANDA_INICIAL":
        return 10
    return 30


def parser_validity_score(parsed: tuple[str | None, dict | None]) -> int:
    raw, normalized = parsed
    if raw and normalized:
        return 20
    return 0


def build_missing_message(field_key: str, doc_type: str) -> str:
    return f"FALTA_EVIDENCIA:{field_key}:{doc_type}"
