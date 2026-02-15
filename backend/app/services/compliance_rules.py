from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})|(\d{2}[/-]\d{2}[/-]\d{2,4})")


@dataclass
class ComplianceCheckResult:
    field_key: str
    status: str
    risk_level: str
    why_flagged: str
    evidence_hint: str
    required_doc_type: str | None = None
    source_doc_type: str | None = None


@dataclass
class TerminationComplianceReport:
    missing_critical_doc: str | None
    risk_score: int
    recommendation: str


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _extract_valid_until(text: str | None) -> datetime | None:
    if not text:
        return None
    matches = DATE_RE.findall(text)
    values = [m[0] or m[1] for m in matches]
    parsed = [_parse_date(v) for v in values]
    parsed = [p for p in parsed if p is not None]
    if not parsed:
        return None
    return max(parsed)


def evaluate_compliance_docs(
    docs_by_type: dict[str, list[Any]],
    *,
    now: datetime | None = None,
) -> list[ComplianceCheckResult]:
    now = now or datetime.now(timezone.utc)
    out: list[ComplianceCheckResult] = []

    # REPSE con vigencia temporal.
    repse_docs = docs_by_type.get("EXPEDIENTE_REPSE") or []
    if not repse_docs:
        out.append(
            ComplianceCheckResult(
                field_key="repse_status",
                status="AUSENTE",
                risk_level="HIGH",
                why_flagged="No existe expediente REPSE.",
                evidence_hint="Agregar constancia vigente REPSE.",
                required_doc_type="EXPEDIENTE_REPSE",
            )
        )
    else:
        repse_text = " ".join([(getattr(d, "filename", "") or "") for d in repse_docs])
        valid_until = _extract_valid_until(repse_text)
        if valid_until and valid_until < now:
            out.append(
                ComplianceCheckResult(
                    field_key="repse_status",
                    status="VENCIDO",
                    risk_level="HIGH",
                    why_flagged=f"REPSE vencido desde {valid_until.date().isoformat()}.",
                    evidence_hint="Actualizar constancia REPSE vigente.",
                    required_doc_type="EXPEDIENTE_REPSE",
                    source_doc_type="EXPEDIENTE_REPSE",
                )
            )
        elif valid_until is None:
            out.append(
                ComplianceCheckResult(
                    field_key="repse_status",
                    status="INSUFICIENTE",
                    risk_level="MEDIUM",
                    why_flagged="REPSE presente pero sin fecha verificable de vigencia.",
                    evidence_hint="Agregar constancia REPSE con fecha de vigencia legible.",
                    required_doc_type="EXPEDIENTE_REPSE",
                    source_doc_type="EXPEDIENTE_REPSE",
                )
            )
        else:
            out.append(
                ComplianceCheckResult(
                    field_key="repse_status",
                    status="PRESENTE",
                    risk_level="LOW",
                    why_flagged="REPSE presente.",
                    evidence_hint="Mantener evidencia de vigencia.",
                    required_doc_type="EXPEDIENTE_REPSE",
                    source_doc_type="EXPEDIENTE_REPSE",
                )
            )

    for doc_type, field_key, hint in (
        ("CARPETA_NOM035", "nom035_status", "Agregar carpeta NOM-035 y evidencias de aplicación."),
        ("REGLAMENTO_INTERIOR", "reglamento_status", "Agregar reglamento interior depositado/vigente."),
        ("COMISION_MIXTA", "comisiones_mixtas_status", "Agregar actas/comisiones mixtas."),
        ("CONVENIO_NDA", "nda_status", "Agregar convenio de confidencialidad firmado."),
        ("LISTA_ASISTENCIA", "attendance_control", "Agregar listas de asistencia firmadas."),
        ("ALTA_IMSS", "imss_registration", "Agregar alta/reporte IMSS."),
    ):
        present = bool(docs_by_type.get(doc_type))
        out.append(
            ComplianceCheckResult(
                field_key=field_key,
                status="PRESENTE" if present else "AUSENTE",
                risk_level="LOW" if present else "HIGH",
                why_flagged=f"{doc_type} {'presente' if present else 'ausente'}.",
                evidence_hint=hint,
                required_doc_type=doc_type,
                source_doc_type=doc_type if present else None,
            )
        )

    return out


def check_termination_compliance(documents: list[dict[str, Any]]) -> TerminationComplianceReport:
    doc_types = {(d.get("doc_type") or "").upper() for d in documents}
    alleges_termination = "DEMANDA_INICIAL" in doc_types or "ACTA_ADMINISTRATIVA" in doc_types
    has_notice = "AVISO_RESCISION" in doc_types
    if alleges_termination and not has_notice:
        return TerminationComplianceReport(
            missing_critical_doc="AVISO_RESCISION",
            risk_score=0,
            recommendation="RIESGO_ECONOMICO_TOTAL",
        )
    return TerminationComplianceReport(
        missing_critical_doc=None,
        risk_score=100,
        recommendation="CUMPLIMIENTO_MINIMO_OK",
    )
