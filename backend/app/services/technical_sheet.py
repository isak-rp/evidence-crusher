from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Case, Document, DocumentChunk, TechnicalAlert, TechnicalFact, TechnicalSnapshot
from app.schemas.technical_sheet import (
    ExecutiveSummaryResponse,
    TechnicalAlertResponse,
    TechnicalFactResponse,
    TechnicalSheetResponse,
)
from app.services.doc_type_mapping import build_docs_by_canonical_type
from app.services.embeddings import EmbeddingService
from app.services.field_extractors import (
    FIELD_SPECS,
    build_missing_message,
    doc_type_priority,
    parser_validity_score,
)


class TechnicalSheetService:
    DOC_TYPES_REQUIRED = {
        "CONTRATO_INDIVIDUAL",
        "ALTA_IMSS",
        "CONSTANCIA_LABORAL",
        "RECIBO_NOMINA",
        "DEMANDA_INICIAL",
        "AVISO_RESCISION",
    }
    PILLAR_TITLES = {
        "IDENTIDAD": "A. IDENTIDAD Y VINCULO",
        "ECONOMICA": "B. INGENIERIA ECONOMICA",
        "CONFLICTO": "C. EL CONFLICTO",
        "COMPLIANCE": "D. BLINDAJE Y COMPLIANCE",
    }
    TOP_K_CHUNKS = 3

    @staticmethod
    def feature_enabled() -> bool:
        return os.getenv("TECH_SHEET_V2_ENABLED", "true").lower() == "true"

    @staticmethod
    def build_case_technical_sheet(db: Session, case_id: UUID, *, task_id: str | None = None) -> TechnicalSheetResponse:
        case = db.scalar(
            select(Case)
            .where(Case.id == case_id)
            .options(selectinload(Case.documents).selectinload(Document.chunks))
        )
        if case is None:
            raise ValueError("Case not found")

        docs = case.documents or []
        docs_by_type, doc_id_to_type = build_docs_by_canonical_type(docs)

        db.execute(delete(TechnicalFact).where(TechnicalFact.case_id == case_id))
        db.execute(delete(TechnicalAlert).where(TechnicalAlert.case_id == case_id))
        facts: list[TechnicalFact] = []
        alerts: list[TechnicalAlert] = []

        def add_fact(
            *,
            pillar: str,
            field_key: str,
            value_raw: str | None,
            value_normalized: dict | None,
            source_doc: Document | None,
            source_page: int | None,
            source_bbox: dict | None,
            source_text_excerpt: str | None,
            risk_level: str,
            confidence: float,
            truth_status: str,
            rule_applied: str,
            why_critical: str | None = None,
            evidence_hint: str | None = None,
        ) -> TechnicalFact:
            fact = TechnicalFact(
                case_id=case_id,
                pillar=pillar,
                field_key=field_key,
                value_raw=value_raw,
                value_normalized=value_normalized,
                source_doc_id=source_doc.id if source_doc else None,
                source_page=source_page,
                source_bbox=source_bbox,
                source_text_excerpt=source_text_excerpt,
                source_doc_type=(doc_id_to_type.get(str(source_doc.id)) if source_doc else None),
                risk_level=risk_level,
                confidence=confidence,
                truth_status=truth_status,
                rule_applied=rule_applied,
                why_critical=why_critical,
                evidence_hint=evidence_hint,
            )
            facts.append(fact)
            return fact

        # Alerts por documento requerido faltante.
        missing_doc_types = sorted([dt for dt in TechnicalSheetService.DOC_TYPES_REQUIRED if not docs_by_type.get(dt)])
        for missing_doc_type in missing_doc_types:
            alerts.append(
                TechnicalAlert(
                    case_id=case_id,
                    severity="CRITICAL",
                    code=f"MISSING_{missing_doc_type}",
                    message=build_missing_message("required_document", missing_doc_type),
                    required_doc_type=missing_doc_type,
                    field_key="required_document",
                    evidence_fact_ids=[],
                )
            )

        # Extracción robusta por catálogo de campos.
        for spec in FIELD_SPECS:
            candidate = TechnicalSheetService._pick_best_candidate(
                db,
                case_id,
                spec.queries,
                spec.preferred_doc_types,
                doc_id_to_type,
                spec.parser,
            )
            if candidate is None:
                missing_fact = add_fact(
                    pillar=spec.pillar,
                    field_key=spec.field_key,
                    value_raw=None,
                    value_normalized=None,
                    source_doc=None,
                    source_page=None,
                    source_bbox=None,
                    source_text_excerpt=None,
                    risk_level="CRITICAL" if spec.is_critical else "HIGH",
                    confidence=0.0,
                    truth_status="MISSING",
                    rule_applied="missing_required_doc" if spec.is_critical else "missing_evidence",
                    why_critical=(f"No se encontro evidencia valida para {spec.field_key}." if spec.is_critical else None),
                    evidence_hint=spec.evidence_hint,
                )
                if spec.is_critical:
                    alerts.append(
                        TechnicalAlert(
                            case_id=case_id,
                            severity="CRITICAL",
                            code=f"MISSING_{spec.field_key.upper()}",
                            message=build_missing_message(spec.field_key, spec.preferred_doc_types[0]),
                            required_doc_type=spec.preferred_doc_types[0],
                            field_key=spec.field_key,
                            evidence_fact_ids=[str(missing_fact.id)] if missing_fact.id else [],
                        )
                    )
                continue

            chunk, canonical_type, distance = candidate
            raw, normalized = spec.parser(chunk.text_content or "")
            if raw is None or normalized is None:
                missing_fact = add_fact(
                    pillar=spec.pillar,
                    field_key=spec.field_key,
                    value_raw=None,
                    value_normalized=None,
                    source_doc=chunk.document,
                    source_page=chunk.page_number,
                    source_bbox=None,
                    source_text_excerpt=(chunk.text_content or "")[:220],
                    risk_level="CRITICAL" if spec.is_critical else "HIGH",
                    confidence=0.0,
                    truth_status="MISSING",
                    rule_applied="parser_invalid_value",
                    why_critical=(f"Se encontro documento pero el valor no pudo normalizarse para {spec.field_key}." if spec.is_critical else None),
                    evidence_hint=spec.evidence_hint,
                )
                if spec.is_critical:
                    alerts.append(
                        TechnicalAlert(
                            case_id=case_id,
                            severity="CRITICAL",
                            code=f"MISSING_{spec.field_key.upper()}",
                            message=build_missing_message(spec.field_key, spec.preferred_doc_types[0]),
                            required_doc_type=spec.preferred_doc_types[0],
                            field_key=spec.field_key,
                            evidence_fact_ids=[str(missing_fact.id)] if missing_fact.id else [],
                        )
                    )
                continue

            truth_status = "CLAIM" if canonical_type == "DEMANDA_INICIAL" else "FACT"
            risk_level = "MEDIUM" if truth_status == "CLAIM" else "LOW"
            rule = "demanda_es_pretension" if truth_status == "CLAIM" else "canonical_doc_type_mapping"
            confidence = max(0.1, min(1.0, 1.0 - distance))
            add_fact(
                pillar=spec.pillar,
                field_key=spec.field_key,
                value_raw=raw,
                value_normalized=normalized,
                source_doc=chunk.document,
                source_page=chunk.page_number,
                source_bbox=None,
                source_text_excerpt=(chunk.text_content or "")[:220],
                risk_level=risk_level,
                confidence=confidence,
                truth_status=truth_status,
                rule_applied=rule,
                evidence_hint=spec.evidence_hint,
            )

        # Reglas jerárquicas explícitas.
        salary_contract = TechnicalSheetService._get_fact_amount(facts, "salary_sd", source_type="CONTRATO_INDIVIDUAL")
        salary_payroll = TechnicalSheetService._get_fact_amount(facts, "salary_sd", source_type="RECIBO_NOMINA")
        if salary_contract is not None and salary_payroll is not None and abs(salary_contract - salary_payroll) > 0.01:
            conflict = add_fact(
                pillar="ECONOMICA",
                field_key="salary_conflict_contract_vs_nomina",
                value_raw=f"Contrato={salary_contract}, Nomina={salary_payroll}",
                value_normalized={"contract_amount": salary_contract, "payroll_amount": salary_payroll, "winner": "RECIBO_NOMINA"},
                source_doc=None,
                source_page=None,
                source_bbox=None,
                source_text_excerpt=None,
                risk_level="HIGH",
                confidence=1.0,
                truth_status="CONFLICT",
                rule_applied="recibo_nomina_manda_dinero",
                evidence_hint="Usar recibo CFDI de nomina como fuente de verdad economica.",
            )
            alerts.append(
                TechnicalAlert(
                    case_id=case_id,
                    severity="HIGH",
                    code="SALARY_CONFLICT",
                    message="Conflicto salario contrato vs nomina.",
                    required_doc_type="RECIBO_NOMINA",
                    field_key="salary_sd",
                    evidence_fact_ids=[str(conflict.id)] if conflict.id else [],
                )
            )

        termination_from_docs = TechnicalSheetService._derive_termination_cause(docs_by_type)
        if termination_from_docs is not None:
            cause, truth_status, rule, source_doc = termination_from_docs
            add_fact(
                pillar="CONFLICTO",
                field_key="termination_cause",
                value_raw=cause,
                value_normalized={"cause": cause},
                source_doc=source_doc,
                source_page=1,
                source_bbox=None,
                source_text_excerpt=None,
                risk_level="MEDIUM" if truth_status == "CLAIM" else "LOW",
                confidence=0.9 if truth_status == "FACT" else 0.6,
                truth_status=truth_status,
                rule_applied=rule,
                evidence_hint="Agregar aviso de rescision o carta renuncia firmada.",
            )
        else:
            missing_cause = add_fact(
                pillar="CONFLICTO",
                field_key="termination_cause",
                value_raw=None,
                value_normalized=None,
                source_doc=None,
                source_page=None,
                source_bbox=None,
                source_text_excerpt=None,
                risk_level="CRITICAL",
                confidence=0.0,
                truth_status="MISSING",
                rule_applied="missing_required_doc",
                why_critical="No hay evidencia para determinar causa de terminacion.",
                evidence_hint="Agregar AVISO_RESCISION o CARTA_RENUNCIA.",
            )
            alerts.append(
                TechnicalAlert(
                    case_id=case_id,
                    severity="CRITICAL",
                    code="MISSING_TERMINATION_CAUSE",
                    message=build_missing_message("termination_cause", "AVISO_RESCISION"),
                    required_doc_type="AVISO_RESCISION",
                    field_key="termination_cause",
                    evidence_fact_ids=[str(missing_cause.id)] if missing_cause.id else [],
                )
            )

        # Coverage incremental compliance.
        for optional_doc, label in (
            ("EXPEDIENTE_REPSE", "repse"),
            ("CARPETA_NOM035", "nom035"),
            ("CONVENIO_NDA", "nda"),
        ):
            present = bool(docs_by_type.get(optional_doc))
            add_fact(
                pillar="COMPLIANCE",
                field_key=f"{label}_coverage",
                value_raw="PRESENTE" if present else "SIN_COBERTURA",
                value_normalized={"present": present},
                source_doc=docs_by_type[optional_doc][0] if present else None,
                source_page=1 if present else None,
                source_bbox=None,
                source_text_excerpt=None,
                risk_level="LOW" if present else "MEDIUM",
                confidence=1.0 if present else 0.0,
                truth_status="FACT" if present else "MISSING",
                rule_applied="mapeo_incremental_taxonomia",
                evidence_hint=f"Agregar evidencia de {optional_doc}.",
            )

        db.add_all(facts)
        db.add_all(alerts)
        db.flush()

        high_impact_alerts = [a.message for a in alerts if a.severity in {"CRITICAL", "HIGH"}]
        overall_status = TechnicalSheetService._resolve_overall_status(facts, alerts)
        cause_for_summary = TechnicalSheetService._extract_text_fact(facts, "termination_cause") or "INDETERMINADA"
        claimed_amount = TechnicalSheetService._extract_amount_fact(facts, "claimed_amount")
        closure_offer = TechnicalSheetService._extract_amount_fact(facts, "closure_offer")
        gap = (claimed_amount - closure_offer) if (claimed_amount is not None and closure_offer is not None) else None
        litis_narrative = (
            f"Se identifica {cause_for_summary} con brecha economica estimada de "
            f"{gap if gap is not None else 'N/D'} MXN. "
            f"Riesgos criticos: {', '.join(high_impact_alerts) if high_impact_alerts else 'Ninguno'}."
        )

        snapshot = db.get(TechnicalSnapshot, case_id)
        if snapshot is None:
            snapshot = TechnicalSnapshot(case_id=case_id)
            db.add(snapshot)
        snapshot.overall_status = overall_status
        snapshot.litis_narrative = litis_narrative
        snapshot.high_impact_alerts = high_impact_alerts
        snapshot.updated_at = datetime.now(timezone.utc)

        db.commit()
        return TechnicalSheetService.get_case_technical_sheet(db, case_id)

    @staticmethod
    def get_case_technical_sheet(db: Session, case_id: UUID) -> TechnicalSheetResponse:
        snapshot = db.get(TechnicalSnapshot, case_id)
        facts = db.scalars(
            select(TechnicalFact)
            .where(TechnicalFact.case_id == case_id)
            .order_by(TechnicalFact.pillar.asc(), TechnicalFact.field_key.asc())
        ).all()
        alerts = db.scalars(
            select(TechnicalAlert)
            .where(TechnicalAlert.case_id == case_id)
            .order_by(TechnicalAlert.created_at.desc())
        ).all()

        facts_resp = [TechnicalFactResponse.model_validate(f) for f in facts]
        alerts_resp = [TechnicalAlertResponse.model_validate(a) for a in alerts]
        pillars: dict[str, list[TechnicalFactResponse]] = {label: [] for label in TechnicalSheetService.PILLAR_TITLES.values()}
        for fact in facts_resp:
            label = TechnicalSheetService.PILLAR_TITLES.get(fact.pillar, fact.pillar)
            pillars.setdefault(label, []).append(fact)

        conflicts = [f for f in facts_resp if f.truth_status == "CONFLICT"]
        missing_required_docs = [a for a in alerts_resp if (a.code or "").startswith("MISSING_")]
        executive = ExecutiveSummaryResponse(
            overall_status=(snapshot.overall_status if snapshot else "YELLOW"),
            litis_narrative=(snapshot.litis_narrative if snapshot else "Ficha tecnica aun no generada."),
            high_impact_alerts=(snapshot.high_impact_alerts if snapshot and snapshot.high_impact_alerts else []),
        )
        generated_at = snapshot.updated_at if snapshot else datetime.now(timezone.utc)
        return TechnicalSheetResponse(
            case_id=case_id,
            executive_summary=executive,
            pillars=pillars,
            facts=facts_resp,
            conflicts=conflicts,
            missing_required_docs=missing_required_docs,
            alerts=alerts_resp,
            generated_at=generated_at,
        )

    @staticmethod
    def _pick_best_candidate(
        db: Session,
        case_id: UUID,
        queries: tuple[str, ...],
        preferred_doc_types: tuple[str, ...],
        doc_id_to_type: dict[str, str],
        parser,
    ) -> tuple[DocumentChunk, str, float] | None:
        best: tuple[DocumentChunk, str, float, int] | None = None
        for query in queries:
            try:
                vec = EmbeddingService.generate_embedding(query)
            except Exception:
                continue
            chunks = db.scalars(
                select(DocumentChunk)
                .join(Document)
                .where(Document.case_id == case_id, DocumentChunk.embedding.is_not(None))
                .options(selectinload(DocumentChunk.document))
                .order_by(DocumentChunk.embedding.l2_distance(vec))
                .limit(TechnicalSheetService.TOP_K_CHUNKS)
            ).all()
            for rank, chunk in enumerate(chunks):
                canonical = doc_id_to_type.get(str(chunk.document_id), "SIN_CLASIFICAR")
                parsed = parser(chunk.text_content or "")
                score = doc_type_priority(canonical, preferred_doc_types) + parser_validity_score(parsed) - (rank * 5)
                distance = float(rank + 1) / 10.0
                current = (chunk, canonical, distance, score)
                if best is None or current[3] > best[3]:
                    best = current
        if best is None:
            return None
        return best[0], best[1], best[2]

    @staticmethod
    def _resolve_overall_status(facts: list[TechnicalFact], alerts: list[TechnicalAlert]) -> str:
        if any(a.severity == "CRITICAL" for a in alerts) or any(f.risk_level == "CRITICAL" for f in facts):
            return "RED"
        if any(a.severity == "HIGH" for a in alerts) or any(f.risk_level in {"HIGH", "MEDIUM"} for f in facts):
            return "YELLOW"
        return "GREEN"

    @staticmethod
    def _get_fact_amount(facts: list[TechnicalFact], field_key: str, *, source_type: str | None = None) -> float | None:
        for fact in facts:
            if fact.field_key != field_key:
                continue
            if source_type and fact.source_doc_type != source_type:
                continue
            data = fact.value_normalized or {}
            amount = data.get("amount")
            if amount is None:
                continue
            try:
                return float(amount)
            except Exception:
                continue
        return None

    @staticmethod
    def _extract_amount_fact(facts: list[TechnicalFact], field_key: str) -> float | None:
        return TechnicalSheetService._get_fact_amount(facts, field_key)

    @staticmethod
    def _extract_text_fact(facts: list[TechnicalFact], field_key: str) -> str | None:
        for fact in facts:
            if fact.field_key == field_key and fact.value_raw:
                return fact.value_raw
        return None

    @staticmethod
    def _derive_termination_cause(docs_by_type: dict[str, list[Document]]) -> tuple[str, str, str, Document] | None:
        if docs_by_type.get("AVISO_RESCISION"):
            return "RESCISION_PATRONAL", "FACT", "aviso_rescision_presente", docs_by_type["AVISO_RESCISION"][0]
        if docs_by_type.get("CARTA_RENUNCIA"):
            return "RENUNCIA_VOLUNTARIA", "FACT", "carta_renuncia_presente", docs_by_type["CARTA_RENUNCIA"][0]
        if docs_by_type.get("DEMANDA_INICIAL"):
            return "DESPIDO_INJUSTIFICADO", "CLAIM", "demanda_es_pretension", docs_by_type["DEMANDA_INICIAL"][0]
        return None
