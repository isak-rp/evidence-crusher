from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TechnicalFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pillar: str
    field_key: str
    value_raw: str | None = None
    value_normalized: dict | None = None
    source_doc_id: UUID | None = None
    source_page: int | None = None
    source_bbox: dict | None = None
    source_text_excerpt: str | None = None
    source_doc_type: str | None = None
    risk_level: str
    confidence: float
    truth_status: str
    rule_applied: str | None = None
    party_side: str | None = None
    conflict_group_id: str | None = None
    evidence_weight: float | None = None
    precedence_rank: int | None = None
    legal_defense_strength: str | None = None
    why_critical: str | None = None
    evidence_hint: str | None = None
    updated_at: datetime


class TechnicalAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    severity: str
    code: str
    message: str
    dimension: str | None = None
    why_flagged: str | None = None
    required_doc_type: str | None = None
    field_key: str | None = None
    evidence_fact_ids: list[str] | None = None
    created_at: datetime


class ExecutiveSummaryResponse(BaseModel):
    overall_status: str
    litis_narrative: str
    high_impact_alerts: list[str] = []
    dimension_scores: dict[str, dict] = {}
    narrative_mode: str = "DETERMINISTIC"


class TechnicalSheetResponse(BaseModel):
    case_id: UUID
    executive_summary: ExecutiveSummaryResponse
    pillars: dict[str, list[TechnicalFactResponse]]
    facts: list[TechnicalFactResponse]
    conflicts: list[TechnicalFactResponse]
    missing_required_docs: list[TechnicalAlertResponse]
    alerts: list[TechnicalAlertResponse]
    generated_at: datetime
