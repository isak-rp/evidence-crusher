from __future__ import annotations

import re
from typing import Any

from app.services.llm import LLMService


MONEY_OR_NUMBER_RE = re.compile(r"\$?\s?\d+(?:[.,]\d+)?")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{2,4}")


def build_deterministic_narrative(
    *,
    cause: str,
    gap: float | None,
    high_impact_alerts: list[str],
) -> str:
    return (
        f"Se identifica {cause} con brecha economica estimada de "
        f"{gap if gap is not None else 'N/D'} MXN. "
        f"Riesgos criticos: {', '.join(high_impact_alerts) if high_impact_alerts else 'Ninguno'}."
    )


def _facts_allowed_tokens(facts: list[Any]) -> set[str]:
    tokens: set[str] = set()
    for fact in facts:
        raw = getattr(fact, "value_raw", None)
        if raw is None:
            continue
        text = str(raw)
        tokens.update([m.group(0).replace(" ", "") for m in MONEY_OR_NUMBER_RE.finditer(text)])
        tokens.update([m.group(0) for m in DATE_RE.finditer(text)])
    return tokens


def _is_traceable_narrative(text: str, facts: list[Any]) -> bool:
    if not text.strip():
        return False
    allowed = _facts_allowed_tokens(facts)
    numbers = [m.group(0).replace(" ", "") for m in MONEY_OR_NUMBER_RE.finditer(text)]
    dates = [m.group(0) for m in DATE_RE.finditer(text)]
    for token in numbers + dates:
        if token not in allowed:
            return False
    return True


def build_hybrid_narrative(
    *,
    deterministic_narrative: str,
    facts: list[Any],
    alerts: list[Any],
) -> tuple[str, str]:
    mode = "DETERMINISTIC"
    provider = (LLMService.current_provider() or "").lower()
    if provider != "groq":
        return deterministic_narrative, mode

    facts_context = []
    for fact in facts:
        facts_context.append(
            f"{getattr(fact, 'field_key', '-')}: {getattr(fact, 'value_raw', None)} "
            f"[{getattr(fact, 'truth_status', '-')}/{getattr(fact, 'risk_level', '-')}]"
        )
    alerts_context = [str(getattr(a, "message", "")) for a in alerts]
    prompt = (
        "Resume la litis en espanol juridico claro en maximo 70 palabras.\n"
        "No inventes cifras ni fechas; solo usa evidencias provistas.\n\n"
        f"Narrativa base:\n{deterministic_narrative}\n\n"
        f"Facts:\n- " + "\n- ".join(facts_context[:30]) + "\n\n"
        f"Alerts:\n- " + "\n- ".join(alerts_context[:20]) + "\n\n"
        "Resumen:"
    )
    try:
        llm_text = LLMService.rag_answer("Genera el resumen ejecutivo", prompt)
        if _is_traceable_narrative(llm_text, facts):
            return llm_text.strip(), "HYBRID_LLM"
        return deterministic_narrative, "DETERMINISTIC"
    except Exception:
        return deterministic_narrative, mode
