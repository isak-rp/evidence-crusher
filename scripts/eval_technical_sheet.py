import json
import os
from pathlib import Path

import requests


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DATASET_ROOT = Path(__file__).parent / "datasets" / "techsheet_v1"


CRITICAL_FIELDS = {"start_date_real", "salary_sd", "termination_cause"}


def fetch_sheet(case_id: str) -> dict | None:
    res = requests.get(f"{BACKEND_URL}/api/v1/cases/{case_id}/technical-sheet", timeout=20)
    if res.status_code != 200:
        return None
    return res.json()


def index_facts_by_key(sheet: dict) -> dict[str, dict]:
    facts = sheet.get("facts") or []
    return {f.get("field_key"): f for f in facts if f.get("field_key")}


def compare_case(expected: dict, sheet: dict) -> dict:
    facts_by_key = index_facts_by_key(sheet)
    expected_fields = expected.get("expected_fields", {})

    total_fields = len(expected_fields)
    matched_fields = 0
    non_missing_fields = 0
    critical_total = 0
    critical_present = 0
    invented_facts = 0

    for key, exp in expected_fields.items():
        fact = facts_by_key.get(key)
        if not fact:
            continue
        truth_status = (fact.get("truth_status") or "").upper()
        if truth_status != "MISSING":
            non_missing_fields += 1
        if key in CRITICAL_FIELDS:
            critical_total += 1
            if truth_status != "MISSING":
                critical_present += 1
        expected_value = exp.get("value")
        actual_value = fact.get("value_raw")
        if expected_value is None:
            if truth_status == "MISSING":
                matched_fields += 1
        elif str(expected_value).strip().lower() == str(actual_value).strip().lower():
            matched_fields += 1

    for fact in sheet.get("facts", []):
        if not fact.get("source_doc_id") and not fact.get("rule_applied"):
            invented_facts += 1

    return {
        "total_fields": total_fields,
        "matched_fields": matched_fields,
        "non_missing_fields": non_missing_fields,
        "critical_total": critical_total,
        "critical_present": critical_present,
        "invented_facts": invented_facts,
    }


def main():
    if not DATASET_ROOT.exists():
        raise SystemExit(f"No existe dataset en {DATASET_ROOT}")

    case_results = []
    for case_dir in sorted(DATASET_ROOT.glob("case_*")):
        expected_file = case_dir / "expected_fields.json"
        if not expected_file.exists():
            continue
        expected = json.loads(expected_file.read_text(encoding="utf-8"))
        case_id = expected.get("case_id")
        if not case_id:
            case_results.append({"case": case_dir.name, "error": "missing_case_id"})
            continue
        sheet = fetch_sheet(case_id)
        if sheet is None:
            case_results.append({"case": case_dir.name, "error": "sheet_unavailable"})
            continue
        stats = compare_case(expected, sheet)
        stats["case"] = case_dir.name
        case_results.append(stats)

    valid_results = [r for r in case_results if "error" not in r]
    if not valid_results:
        print(json.dumps({"results": case_results, "summary": {"error": "no_valid_cases"}}, indent=2, ensure_ascii=False))
        return

    total_fields = sum(r["total_fields"] for r in valid_results)
    matched_fields = sum(r["matched_fields"] for r in valid_results)
    non_missing = sum(r["non_missing_fields"] for r in valid_results)
    critical_total = sum(r["critical_total"] for r in valid_results)
    critical_present = sum(r["critical_present"] for r in valid_results)
    invented_facts = sum(r["invented_facts"] for r in valid_results)

    coverage = (non_missing / total_fields * 100.0) if total_fields else 0.0
    accuracy = (matched_fields / total_fields * 100.0) if total_fields else 0.0
    critical_coverage = (critical_present / critical_total * 100.0) if critical_total else 0.0

    summary = {
        "coverage_pct": round(coverage, 2),
        "accuracy_pct": round(accuracy, 2),
        "critical_coverage_pct": round(critical_coverage, 2),
        "invented_facts": invented_facts,
        "gates": {
            "coverage_critical_gte_70": critical_coverage >= 70.0,
            "accuracy_gte_80": accuracy >= 80.0,
            "invented_facts_eq_0": invented_facts == 0,
        },
    }

    print(json.dumps({"results": case_results, "summary": summary}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
