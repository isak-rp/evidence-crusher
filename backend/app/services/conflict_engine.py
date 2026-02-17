from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

DOC_TYPE_PRECEDENCE = {
    "ECONOMICA": ("RECIBO_NOMINA", "CONTRATO_INDIVIDUAL", "DEMANDA_INICIAL"),
    "IDENTIDAD": ("ALTA_IMSS", "CONTRATO_INDIVIDUAL", "DEMANDA_INICIAL"),
    "CONDICIONES": ("CONTRATO_INDIVIDUAL", "LISTA_ASISTENCIA", "DEMANDA_INICIAL"),
}


def _party_for_doc_type(doc_type: str) -> str:
    t = (doc_type or "").upper()
    if t in {"DEMANDA_INICIAL", "CARTA_RENUNCIA"}:
        return "TRABAJADOR"
    if t in {"ALTA_IMSS", "IDSE", "SUA"}:
        return "AUTORIDAD"
    if t in {"CONTRATO_INDIVIDUAL", "RECIBO_NOMINA", "LISTA_ASISTENCIA", "ACTA_ADMINISTRATIVA"}:
        return "EMPRESA"
    return "NEUTRO"


def _field_domain(field_key: str) -> str:
    f = (field_key or "").lower()
    if f in {"daily_salary", "salary_sd", "salary_sdi", "claimed_amount", "closure_offer"}:
        return "ECONOMICA"
    if f in {"start_date", "start_date_real"}:
        return "IDENTIDAD"
    return "CONDICIONES"


@dataclass
class ConflictItem:
    field_key: str
    source_doc_type: str
    value: Any
    message: str


@dataclass
class WinnerFact:
    field_key: str
    value: Any
    source_doc_type: str
    party_side: str
    confidence_level: str
    legal_defense_strength: str | None = None


def _precedence_rank(doc_type: str, field_key: str, contract_signed: bool) -> int:
    domain = _field_domain(field_key)
    order = DOC_TYPE_PRECEDENCE.get(domain, ())
    dt = (doc_type or "").upper()
    if not contract_signed and dt == "DEMANDA_INICIAL":
        # Carga dinamica de la prueba cuando no hay contrato firmado.
        return 85
    if dt in order:
        return 100 - (order.index(dt) * 10)
    if dt == "DEMANDA_INICIAL":
        return 20
    return 40


def detect_conflicts(documents: list[dict[str, Any]], contract_signed: bool = True) -> tuple[list[ConflictItem], list[WinnerFact]]:
    """
    Utility for synthetic tests and deterministic legal precedence checks.
    """
    by_field: dict[str, list[dict[str, Any]]] = {}
    for doc in documents:
        doc_type = (doc.get("doc_type") or "").upper()
        data = doc.get("extracted_data") or {}
        for field_key, value in data.items():
            by_field.setdefault(field_key, []).append(
                {
                    "field_key": field_key,
                    "value": value,
                    "doc_type": doc_type,
                    "party_side": _party_for_doc_type(doc_type),
                    "rank": _precedence_rank(doc_type, field_key, contract_signed),
                }
            )

    conflicts: list[ConflictItem] = []
    winners: list[WinnerFact] = []

    for field_key, entries in by_field.items():
        if not entries:
            continue
        sorted_entries = sorted(entries, key=lambda e: e["rank"], reverse=True)
        winner = sorted_entries[0]
        winner_value = str(winner["value"]).strip().lower()
        for contender in sorted_entries[1:]:
            contender_value = str(contender["value"]).strip().lower()
            if contender_value != winner_value:
                conflicts.append(
                    ConflictItem(
                        field_key=field_key,
                        source_doc_type=contender["doc_type"],
                        value=contender["value"],
                        message=f"{field_key} contradice ganador {winner['doc_type']}.",
                    )
                )

        defense = None
        if field_key in {"work_schedule", "check_out", "check_in"} and winner["doc_type"] == "LISTA_ASISTENCIA":
            defense = "STRONG"

        winners.append(
            WinnerFact(
                field_key=field_key,
                value=winner["value"],
                source_doc_type=winner["doc_type"],
                party_side=winner["party_side"],
                confidence_level="HIGH" if winner["rank"] >= 80 else "MEDIUM",
                legal_defense_strength=defense,
            )
        )
    return conflicts, winners


def resolve_precedence(candidates: list[dict[str, Any]], field_key: str, contract_signed: bool = True) -> dict[str, Any] | None:
    """
    Resolve precedence for candidates already normalized by technical sheet.
    candidate keys: source_doc_type, value_raw, value_normalized, confidence, party_side.
    """
    if not candidates:
        return None
    ranked = []
    for c in candidates:
        doc_type = (c.get("source_doc_type") or "").upper()
        base = _precedence_rank(doc_type, field_key, contract_signed)
        conf = float(c.get("confidence") or 0.0)
        score = base + int(conf * 10)
        ranked.append((score, c))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


def make_conflict_group_id(case_id: str, field_key: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{case_id}:{field_key}:{ts}"
