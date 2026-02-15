from __future__ import annotations

from app.services.compliance_rules import check_termination_compliance
from app.services.conflict_engine import detect_conflicts
from tests.fixtures.synthetic_cases import CASE_INFLATION, CASE_MISSING_DOCS, CASE_OVERTIME


def test_salary_precedence():
    conflicts, winner_facts = detect_conflicts(CASE_INFLATION["documents"])
    salary_fact = next(f for f in winner_facts if f.field_key == "daily_salary")
    assert salary_fact.value == 210.00
    assert salary_fact.source_doc_type == "RECIBO_NOMINA"
    assert salary_fact.confidence_level == "HIGH"
    salary_conflicts = [c for c in conflicts if c.field_key == "daily_salary"]
    assert len(salary_conflicts) > 0
    assert "DEMANDA_INICIAL" in [c.source_doc_type for c in salary_conflicts]


def test_start_date_conflict():
    conflicts, winner_facts = detect_conflicts(CASE_INFLATION["documents"])
    start_date_fact = next(f for f in winner_facts if f.field_key == "start_date")
    assert "2022" in str(start_date_fact.value)
    assert start_date_fact.party_side in {"EMPRESA", "AUTORIDAD"}
    assert len(conflicts) > 0


def test_critical_compliance_failure():
    compliance_report = check_termination_compliance(CASE_MISSING_DOCS["documents"])
    assert compliance_report.missing_critical_doc == "AVISO_RESCISION"
    assert compliance_report.risk_score == 0
    assert compliance_report.recommendation == "RIESGO_ECONOMICO_TOTAL"


def test_overtime_defense():
    conflicts, winner_facts = detect_conflicts(CASE_OVERTIME["documents"])
    schedule_fact = next(f for f in winner_facts if f.field_key == "work_schedule")
    assert "18:00" in str(schedule_fact.value)
    assert schedule_fact.source_doc_type == "LISTA_ASISTENCIA"
    assert schedule_fact.legal_defense_strength == "STRONG"
    assert len(conflicts) > 0
