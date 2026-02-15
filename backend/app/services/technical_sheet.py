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
from app.services.compliance_rules import evaluate_compliance_docs
from app.services.conflict_engine import make_conflict_group_id, resolve_precedence
from app.services.doc_type_mapping import build_docs_by_canonical_type
from app.services.embeddings import EmbeddingService
from app.services.field_extractors import FIELD_SPECS, build_missing_message, doc_type_priority, parser_validity_score
from app.services.narrative_builder import build_deterministic_narrative, build_hybrid_narrative
from app.services.scoring_engine import compute_dimension_scores


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
    def phase2_enabled() -> bool:
        return os.getenv("TECH_SHEET_PHASE2_ENABLED", "true").lower() == "true"

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
        contract_signed = TechnicalSheetService._infer_contract_signed(docs_by_type)

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
            party_side: str | None = None,
            conflict_group_id: str | None = None,
            evidence_weight: float | None = None,
            precedence_rank: int | None = None,
            legal_defense_strength: str | None = None,
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
                party_side=party_side,
                conflict_group_id=conflict_group_id,
                evidence_weight=evidence_weight,
                precedence_rank=precedence_rank,
                legal_defense_strength=legal_defense_strength,
                why_critical=why_critical,
                evidence_hint=evidence_hint,
            )
            facts.append(fact)
            return fact

        missing_doc_types = sorted([dt for dt in TechnicalSheetService.DOC_TYPES_REQUIRED if not docs_by_type.get(dt)])
        for missing_doc_type in missing_doc_types:
            alerts.append(
                TechnicalAlert(
                    case_id=case_id,
                    severity="CRITICAL",
                    code=f"MISSING_{missing_doc_type}",
                    message=build_missing_message("required_document", missing_doc_type),
                    dimension="DOCUMENTAL",
                    why_flagged=f"Documento obligatorio ausente: {missing_doc_type}.",
                    required_doc_type=missing_doc_type,
                    field_key="required_document",
                    evidence_fact_ids=[],
                )
            )

        for spec in FIELD_SPECS:
            candidates = TechnicalSheetService._collect_candidates(
                db,
                case_id,
                spec.queries,
                spec.preferred_doc_types,
                doc_id_to_type,
                spec.parser,
            )
            winner = resolve_precedence(candidates, spec.field_key, contract_signed=contract_signed) if candidates else None
            if winner is None:
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
                    party_side="NEUTRO",
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
                            dimension="DOCUMENTAL",
                            why_flagged=f"Campo critico sin evidencia: {spec.field_key}.",
                            required_doc_type=spec.preferred_doc_types[0],
                            field_key=spec.field_key,
                            evidence_fact_ids=[str(missing_fact.id)] if missing_fact.id else [],
                        )
                    )
                continue

            truth_status = "CLAIM" if winner.get("source_doc_type") == "DEMANDA_INICIAL" else "FACT"
            risk_level = "MEDIUM" if truth_status == "CLAIM" else "LOW"
            rule = "demanda_es_pretension" if truth_status == "CLAIM" else "precedencia_deterministica"
            add_fact(
                pillar=spec.pillar,
                field_key=spec.field_key,
                value_raw=winner.get("value_raw"),
                value_normalized=winner.get("value_normalized"),
                source_doc=winner.get("source_doc"),
                source_page=winner.get("source_page"),
                source_bbox=None,
                source_text_excerpt=winner.get("source_text_excerpt"),
                risk_level=risk_level,
                confidence=float(winner.get("confidence") or 0.5),
                truth_status=truth_status,
                rule_applied=rule,
                party_side=winner.get("party_side"),
                evidence_weight=float(winner.get("confidence") or 0.5),
                precedence_rank=int(winner.get("precedence_rank") or 0),
                evidence_hint=spec.evidence_hint,
            )

            distinct_values = {str(c.get("value_raw")).strip().lower() for c in candidates if c.get("value_raw") is not None}
            if len(distinct_values) > 1:
                conflict_id = make_conflict_group_id(str(case_id), spec.field_key)
                add_fact(
                    pillar=spec.pillar,
                    field_key=f"{spec.field_key}_conflict",
                    value_raw=f"Conflicto detectado en {spec.field_key}",
                    value_normalized={"values": sorted(list(distinct_values)), "winner": winner.get("value_raw")},
                    source_doc=None,
                    source_page=None,
                    source_bbox=None,
                    source_text_excerpt=None,
                    risk_level="HIGH",
                    confidence=1.0,
                    truth_status="CONFLICT",
                    rule_applied="conflict_engine_multi_document",
                    party_side="NEUTRO",
                    conflict_group_id=conflict_id,
                    evidence_hint=f"Validar {spec.field_key} con documentos de mayor jerarquia.",
                )
                alerts.append(
                    TechnicalAlert(
                        case_id=case_id,
                        severity="HIGH",
                        code=f"CONFLICT_{spec.field_key.upper()}",
                        message=f"Conflicto detectado en campo {spec.field_key}.",
                        dimension="DOCUMENTAL",
                        why_flagged="Existen fuentes validas con valores distintos.",
                        required_doc_type=spec.preferred_doc_types[0] if spec.preferred_doc_types else None,
                        field_key=spec.field_key,
                        evidence_fact_ids=[],
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
                party_side=TechnicalSheetService._party_for_doc_type(docs_by_type, source_doc),
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
                party_side="NEUTRO",
                why_critical="No hay evidencia para determinar causa de terminacion.",
                evidence_hint="Agregar AVISO_RESCISION o CARTA_RENUNCIA.",
            )
            alerts.append(
                TechnicalAlert(
                    case_id=case_id,
                    severity="CRITICAL",
                    code="MISSING_TERMINATION_CAUSE",
                    message=build_missing_message("termination_cause", "AVISO_RESCISION"),
                    dimension="DOCUMENTAL",
                    why_flagged="No existe evidencia juridica para causa de terminacion.",
                    required_doc_type="AVISO_RESCISION",
                    field_key="termination_cause",
                    evidence_fact_ids=[str(missing_cause.id)] if missing_cause.id else [],
                )
            )

        compliance_checks = evaluate_compliance_docs(docs_by_type)
        for chk in compliance_checks:
            src_doc = (docs_by_type.get(chk.source_doc_type) or [None])[0] if chk.source_doc_type else None
            add_fact(
                pillar="COMPLIANCE",
                field_key=chk.field_key,
                value_raw=chk.status,
                value_normalized={"status": chk.status},
                source_doc=src_doc,
                source_page=1 if src_doc else None,
                source_bbox=None,
                source_text_excerpt=None,
                risk_level=chk.risk_level,
                confidence=1.0 if chk.status == "PRESENTE" else 0.3,
                truth_status="FACT" if chk.status == "PRESENTE" else "MISSING",
                rule_applied="compliance_rules_vigencia",
                party_side="AUTORIDAD" if chk.field_key in {"repse_status", "imss_registration"} else "EMPRESA",
                evidence_hint=chk.evidence_hint,
                why_critical=(chk.why_flagged if chk.risk_level in {"HIGH", "CRITICAL"} else None),
            )
            if chk.risk_level in {"HIGH", "CRITICAL"}:
                alerts.append(
                    TechnicalAlert(
                        case_id=case_id,
                        severity=chk.risk_level,
                        code=f"COMPLIANCE_{chk.field_key.upper()}",
                        message=build_missing_message(chk.field_key, chk.required_doc_type or "N/A"),
                        dimension="COMPLIANCE",
                        why_flagged=chk.why_flagged,
                        required_doc_type=chk.required_doc_type,
                        field_key=chk.field_key,
                        evidence_fact_ids=[],
                    )
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
        deterministic = build_deterministic_narrative(
            cause=cause_for_summary,
            gap=gap,
            high_impact_alerts=high_impact_alerts,
        )
        narrative_mode = "DETERMINISTIC"
        litis_narrative = deterministic
        if TechnicalSheetService.phase2_enabled() and os.getenv("TECH_SHEET_NARRATIVE_MODE", "HYBRID").upper() == "HYBRID":
            litis_narrative, narrative_mode = build_hybrid_narrative(
                deterministic_narrative=deterministic,
                facts=facts,
                alerts=alerts,
            )

        dimension_scores = compute_dimension_scores(facts, alerts)
        snapshot = db.get(TechnicalSnapshot, case_id)
        if snapshot is None:
            snapshot = TechnicalSnapshot(case_id=case_id)
            db.add(snapshot)
        snapshot.overall_status = overall_status
        snapshot.litis_narrative = litis_narrative
        snapshot.narrative_mode = narrative_mode
        snapshot.dimension_scores = dimension_scores
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

        conflicts = [f for f in facts_resp if f.truth_status == "CONFLICT" or (f.conflict_group_id is not None)]
        missing_required_docs = [a for a in alerts_resp if (a.code or "").startswith("MISSING_")]
        executive = ExecutiveSummaryResponse(
            overall_status=(snapshot.overall_status if snapshot else "YELLOW"),
            litis_narrative=(snapshot.litis_narrative if snapshot else "Ficha tecnica aun no generada."),
            high_impact_alerts=(snapshot.high_impact_alerts if snapshot and snapshot.high_impact_alerts else []),
            dimension_scores=(snapshot.dimension_scores if snapshot and snapshot.dimension_scores else {}),
            narrative_mode=(snapshot.narrative_mode if snapshot else "DETERMINISTIC"),
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
    def _collect_candidates(
        db: Session,
        case_id: UUID,
        queries: tuple[str, ...],
        preferred_doc_types: tuple[str, ...],
        doc_id_to_type: dict[str, str],
        parser,
    ) -> list[dict]:
        candidates: list[dict] = []
        seen: set[str] = set()
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
                if str(chunk.id) in seen:
                    continue
                seen.add(str(chunk.id))
                canonical = doc_id_to_type.get(str(chunk.document_id), "SIN_CLASIFICAR")
                raw, normalized = parser(chunk.text_content or "")
                if raw is None or normalized is None:
                    continue
                score = doc_type_priority(canonical, preferred_doc_types) + parser_validity_score((raw, normalized)) - (rank * 5)
                candidates.append(
                    {
                        "source_doc": chunk.document,
                        "source_doc_type": canonical,
                        "source_page": chunk.page_number,
                        "source_text_excerpt": (chunk.text_content or "")[:220],
                        "value_raw": raw,
                        "value_normalized": normalized,
                        "confidence": max(0.1, min(1.0, float(score) / 120.0)),
                        "party_side": TechnicalSheetService._party_from_type(canonical),
                        "precedence_rank": score,
                    }
                )
        return candidates

    @staticmethod
    def _resolve_overall_status(facts: list[TechnicalFact], alerts: list[TechnicalAlert]) -> str:
        if any(a.severity == "CRITICAL" for a in alerts) or any(f.risk_level == "CRITICAL" for f in facts):
            return "RED"
        if any(a.severity == "HIGH" for a in alerts) or any(f.risk_level in {"HIGH", "MEDIUM"} for f in facts):
            return "YELLOW"
        return "GREEN"

    @staticmethod
    def _infer_contract_signed(docs_by_type: dict[str, list[Document]]) -> bool:
        contrato_docs = docs_by_type.get("CONTRATO_INDIVIDUAL") or []
        if not contrato_docs:
            return False
        for doc in contrato_docs:
            text_blob = " ".join([(c.text_content or "") for c in (doc.chunks or [])[:20]]).lower()
            if "firma" in text_blob or "huella" in text_blob:
                return True
            if "firmado" in (doc.filename or "").lower():
                return True
        return True

    @staticmethod
    def _get_fact_amount(facts: list[TechnicalFact], field_key: str) -> float | None:
        for fact in facts:
            if fact.field_key != field_key:
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

    @staticmethod
    def _party_from_type(doc_type: str | None) -> str:
        t = (doc_type or "").upper()
        if t in {"DEMANDA_INICIAL", "CARTA_RENUNCIA"}:
            return "TRABAJADOR"
        if t in {"ALTA_IMSS", "IDSE", "SUA"}:
            return "AUTORIDAD"
        if t in {"CONTRATO_INDIVIDUAL", "RECIBO_NOMINA", "LISTA_ASISTENCIA", "ACTA_ADMINISTRATIVA"}:
            return "EMPRESA"
        return "NEUTRO"

    @staticmethod
    def _party_for_doc_type(docs_by_type: dict[str, list[Document]], source_doc: Document | None) -> str:
        if source_doc is None:
            return "NEUTRO"
        for doc_type, docs in docs_by_type.items():
            if source_doc in docs:
                return TechnicalSheetService._party_from_type(doc_type)
        return "NEUTRO"
