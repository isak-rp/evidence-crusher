from __future__ import annotations


CASE_INFLATION = {
    "case_id": "SYNTH-001",
    "documents": [
        {
            "doc_type": "CONTRATO_INDIVIDUAL",
            "extracted_data": {
                "start_date": "2022-01-01",
                "daily_salary": 200.00,
                "contract_signed": True,
            },
        },
        {
            "doc_type": "DEMANDA_INICIAL",
            "extracted_data": {
                "start_date": "2020-01-01",
                "daily_salary": 500.00,
                "end_date": "2026-02-10",
            },
        },
        {
            "doc_type": "RECIBO_NOMINA",
            "extracted_data": {
                "daily_salary": 210.00,
                "period_start": "2026-01-01",
                "period_end": "2026-01-15",
            },
        },
        {
            "doc_type": "ALTA_IMSS",
            "extracted_data": {
                "start_date": "2022-01-05",
                "base_salary": 210.00,
            },
        },
    ],
}

CASE_MISSING_DOCS = {
    "case_id": "SYNTH-002",
    "documents": [
        {
            "doc_type": "DEMANDA_INICIAL",
            "extracted_data": {
                "termination_cause": "DESPIDO_INJUSTIFICADO",
                "end_date": "2026-02-14",
            },
        },
        {
            "doc_type": "ACTA_ADMINISTRATIVA",
            "extracted_data": {
                "date": "2026-02-10",
                "reason": "Faltas injustificadas",
            },
        },
    ],
}

CASE_OVERTIME = {
    "case_id": "SYNTH-003",
    "documents": [
        {
            "doc_type": "DEMANDA_INICIAL",
            "extracted_data": {
                "work_schedule": "08:00 - 22:00",
            },
        },
        {
            "doc_type": "LISTA_ASISTENCIA",
            "extracted_data": {
                "work_schedule": "09:00 - 18:00",
                "employee_signature": True,
            },
        },
    ],
}
