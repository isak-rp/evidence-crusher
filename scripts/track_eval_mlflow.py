from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import mlflow
import requests


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DATASET_ROOT = Path(__file__).parent / "datasets" / "techsheet_v1"
CRITICAL_FIELDS = {"start_date_real", "salary_sd", "termination_cause"}


def fetch_sheet(case_id: str) -> tuple[dict | None, float]:
    started = time.perf_counter()
    res = requests.get(f"{BACKEND_URL}/api/v1/cases/{case_id}/technical-sheet", timeout=25)
    latency_ms = (time.perf_counter() - started) * 1000.0
    if res.status_code != 200:
        return None, latency_ms
    return res.json(), latency_ms


def trigger_build(case_id: str) -> str | None:
    res = requests.post(f"{BACKEND_URL}/api/v1/cases/{case_id}/build-technical-sheet", timeout=25)
    if res.status_code != 200:
        return None
    payload = res.json()
    return payload.get("task_id")


def wait_task(task_id: str, timeout_sec: int = 180) -> tuple[str, float]:
    started = time.perf_counter()
    while True:
        status_res = requests.get(f"{BACKEND_URL}/api/v1/tasks/{task_id}", timeout=20)
        if status_res.status_code != 200:
            return "ERROR", (time.perf_counter() - started)
        payload = status_res.json()
        status = payload.get("status", "UNKNOWN")
        if status in {"SUCCESS", "FAILURE", "REVOKED", "ERROR"}:
            return status, (time.perf_counter() - started)
        if (time.perf_counter() - started) > timeout_sec:
            return "TIMEOUT", (time.perf_counter() - started)
        time.sleep(2)


def index_facts_by_key(sheet: dict) -> dict[str, dict]:
    facts = sheet.get("facts") or []
    return {f.get("field_key"): f for f in facts if f.get("field_key")}


def compare_case(expected: dict, sheet: dict) -> dict[str, Any]:
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


def summarize(valid_results: list[dict[str, Any]]) -> dict[str, float]:
    total_fields = sum(r["total_fields"] for r in valid_results)
    matched_fields = sum(r["matched_fields"] for r in valid_results)
    non_missing = sum(r["non_missing_fields"] for r in valid_results)
    critical_total = sum(r["critical_total"] for r in valid_results)
    critical_present = sum(r["critical_present"] for r in valid_results)
    invented_facts = sum(r["invented_facts"] for r in valid_results)

    coverage = (non_missing / total_fields * 100.0) if total_fields else 0.0
    accuracy = (matched_fields / total_fields * 100.0) if total_fields else 0.0
    critical_coverage = (critical_present / critical_total * 100.0) if critical_total else 0.0

    return {
        "coverage_pct": round(coverage, 4),
        "accuracy_pct": round(accuracy, 4),
        "critical_coverage_pct": round(critical_coverage, 4),
        "invented_facts": float(invented_facts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Track technical sheet eval runs in MLflow.")
    parser.add_argument("--experiment-name", default="evidence-crusher-techsheet")
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--dataset-root", default=str(DATASET_ROOT))
    parser.add_argument("--build-before-eval", action="store_true")
    parser.add_argument("--model-name", default=os.getenv("GROQ_EXTRACT_MODEL", "unknown"))
    parser.add_argument("--provider", default=os.getenv("AI_PROVIDER", "unknown"))
    parser.add_argument("--token-count", type=float, default=0.0, help="Optional total tokens for TPS.")
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root)
    if not dataset_root.exists():
        raise SystemExit(f"No existe dataset en {dataset_root}")

    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment(args.experiment_name)

    case_results = []
    latencies_ms: list[float] = []
    build_latencies_sec: list[float] = []
    started_eval = time.perf_counter()

    with mlflow.start_run(run_name=args.run_name):
        mlflow.log_param("provider", args.provider)
        mlflow.log_param("model_name", args.model_name)
        mlflow.log_param("dataset_root", str(dataset_root))
        mlflow.log_param("build_before_eval", bool(args.build_before_eval))

        for case_dir in sorted(dataset_root.glob("case_*")):
            expected_file = case_dir / "expected_fields.json"
            if not expected_file.exists():
                continue
            expected = json.loads(expected_file.read_text(encoding="utf-8"))
            case_id = expected.get("case_id")
            if not case_id:
                case_results.append({"case": case_dir.name, "error": "missing_case_id"})
                continue

            if args.build_before_eval:
                task_id = trigger_build(case_id)
                if task_id is None:
                    case_results.append({"case": case_dir.name, "error": "build_enqueue_failed"})
                    continue
                status, build_latency = wait_task(task_id)
                build_latencies_sec.append(build_latency)
                if status != "SUCCESS":
                    case_results.append({"case": case_dir.name, "error": f"build_{status.lower()}"})
                    continue

            sheet, latency_ms = fetch_sheet(case_id)
            latencies_ms.append(latency_ms)
            if sheet is None:
                case_results.append({"case": case_dir.name, "error": "sheet_unavailable"})
                continue
            stats = compare_case(expected, sheet)
            stats["case"] = case_dir.name
            case_results.append(stats)

        valid_results = [r for r in case_results if "error" not in r]
        if not valid_results:
            mlflow.log_param("result", "no_valid_cases")
            print(json.dumps({"results": case_results, "summary": {"error": "no_valid_cases"}}, indent=2, ensure_ascii=False))
            return

        summary = summarize(valid_results)
        eval_time_sec = max(1e-9, (time.perf_counter() - started_eval))
        avg_latency_ms = (sum(latencies_ms) / len(latencies_ms)) if latencies_ms else 0.0
        avg_build_latency_sec = (sum(build_latencies_sec) / len(build_latencies_sec)) if build_latencies_sec else 0.0
        tokens_per_second = (args.token_count / eval_time_sec) if args.token_count > 0 else 0.0

        mlflow.log_metric("accuracy_pct", summary["accuracy_pct"])
        mlflow.log_metric("coverage_pct", summary["coverage_pct"])
        mlflow.log_metric("critical_coverage_pct", summary["critical_coverage_pct"])
        mlflow.log_metric("invented_facts", summary["invented_facts"])
        mlflow.log_metric("avg_api_latency_ms", round(avg_latency_ms, 4))
        mlflow.log_metric("avg_build_latency_sec", round(avg_build_latency_sec, 4))
        mlflow.log_metric("eval_total_time_sec", round(eval_time_sec, 4))
        mlflow.log_metric("tokens_per_second", round(tokens_per_second, 4))

        mlflow.log_text(json.dumps(case_results, ensure_ascii=False, indent=2), "case_results.json")

        output = {
            "results": case_results,
            "summary": {
                **summary,
                "avg_api_latency_ms": round(avg_latency_ms, 2),
                "avg_build_latency_sec": round(avg_build_latency_sec, 2),
                "eval_total_time_sec": round(eval_time_sec, 2),
                "tokens_per_second": round(tokens_per_second, 4),
            },
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
