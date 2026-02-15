from __future__ import annotations

from typing import Any


DIMENSION_MAP = {
    "IDENTIDAD": "documental",
    "ECONOMICA": "economico",
    "CONFLICTO": "documental",
    "COMPLIANCE": "compliance",
}


def _level_for(score: int) -> str:
    if score >= 80:
        return "LOW"
    if score >= 50:
        return "MEDIUM"
    return "HIGH"


def compute_dimension_scores(facts: list[Any], alerts: list[Any]) -> dict[str, dict[str, Any]]:
    penalty = {"economico": 0, "documental": 0, "compliance": 0}

    for fact in facts:
        dim = DIMENSION_MAP.get((getattr(fact, "pillar", "") or "").upper(), "documental")
        risk = (getattr(fact, "risk_level", "") or "").upper()
        truth = (getattr(fact, "truth_status", "") or "").upper()
        confidence = float(getattr(fact, "confidence", 0.0) or 0.0)
        if risk == "CRITICAL":
            penalty[dim] += 35
        elif risk == "HIGH":
            penalty[dim] += 20
        elif risk == "MEDIUM":
            penalty[dim] += 10
        if truth == "CONFLICT":
            penalty[dim] += 20
        if truth == "MISSING":
            penalty[dim] += 15
        if confidence < 0.4:
            penalty[dim] += 5

    for alert in alerts:
        sev = (getattr(alert, "severity", "") or "").upper()
        dim = (getattr(alert, "dimension", "") or "").lower()
        if dim not in penalty:
            dim = "documental"
        if sev == "CRITICAL":
            penalty[dim] += 30
        elif sev == "HIGH":
            penalty[dim] += 15

    out: dict[str, dict[str, Any]] = {}
    for dim in ("economico", "documental", "compliance"):
        score = max(0, min(100, 100 - penalty[dim]))
        out[dim] = {"score": score, "level": _level_for(score)}
    return out
