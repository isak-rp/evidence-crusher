from __future__ import annotations

import re

from app.services.conflict_engine import detect_conflicts
from app.services.extraction import ExtractionService
from tests.fixtures.ocr_mocks import MOCK_CONTRATO_TEXT, MOCK_DEMANDA_TEXT, MOCK_NOMINA_TEXT


def _extract_sdi(text: str) -> float | None:
    m = re.search(r"SDI\):\s*\$\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not m:
        return None
    return float(m.group(1))


def test_mock_text_extraction_and_conflict_resolution():
    demanda_salary = ExtractionService._apply_regex(MOCK_DEMANDA_TEXT, "money")
    contrato_salary = ExtractionService._apply_regex(MOCK_CONTRATO_TEXT, "money")
    contrato_start = ExtractionService._apply_regex(MOCK_CONTRATO_TEXT, "date")
    nomina_salary = ExtractionService._apply_regex(MOCK_NOMINA_TEXT, "money")
    nomina_sdi = _extract_sdi(MOCK_NOMINA_TEXT)

    assert demanda_salary is not None
    assert float(demanda_salary[0]) == 800.00
    assert contrato_salary is not None
    assert float(contrato_salary[0]) == 250.00
    assert contrato_start is not None
    assert str(contrato_start[0]) == "2022-01-01"
    assert nomina_sdi == 275.50
    assert nomina_salary is not None
    assert float(nomina_salary[0]) == 250.00

    documents = [
        {"doc_type": "DEMANDA_INICIAL", "extracted_data": {"daily_salary": float(demanda_salary[0])}},
        {
            "doc_type": "CONTRATO_INDIVIDUAL",
            "extracted_data": {"daily_salary": float(contrato_salary[0]), "start_date": str(contrato_start[0])},
        },
        {"doc_type": "RECIBO_NOMINA", "extracted_data": {"daily_salary": 275.50, "salary_sdi": nomina_sdi}},
    ]

    conflicts, winner_facts = detect_conflicts(documents)
    salary_conflicts = [c for c in conflicts if c.field_key == "daily_salary"]
    assert len(salary_conflicts) > 0
    salary_winner = next(f for f in winner_facts if f.field_key == "daily_salary")
    assert salary_winner.source_doc_type == "RECIBO_NOMINA"
    assert float(salary_winner.value) == 275.50
