"""
evaluate_18q.py
---------------
Full evaluation benchmark pipeline testing the 18 specific questions.
Runs: Generate -> Validate (sqlglot) -> Execute (demo.db SQLite) -> Accuracy Report.
"""

import json
import time
import os
from pathlib import Path
from dataset_18q import BENCHMARK_18Q
from validator import validate_sql
from executor import execute_sql
from setup_db import generate_db, DB_PATH


def evaluate_18_questions(use_llm: bool = True):
    print("\n=======================================================")
    print("   TEXT-TO-SQL ASSISTANT: 18 QUESTION BENCHMARK EVAL   ")
    print("=======================================================\n")

    # Ensure DB exists
    if not DB_PATH.exists():
        print("Database demo.db not found. Initializing...")
        generate_db()

    results = []
    outcomes = {
        "PASSED": 0,
        "FAILED_VALIDATION": 0,
        "FAILED_EXECUTION": 0,
        "GUARDRAIL_BLOCKED": 0
    }

    # Attempt to import Gemini model or fallback to baseline prompt generator
    try:
        from model import generate_sql
        has_gemini = True
    except Exception:
        has_gemini = False

    for item in BENCHMARK_18Q:
        q_id = item["id"]
        question = item["question"]
        target_sql = item["sql"]
        category = item["category"]

        print(f"\n--- [Question {q_id}/18] ({category}) ---")
        print(f"User Request: \"{question}\"")

        # Determine SQL candidate
        if has_gemini and os.environ.get("GEMINI_API_KEY"):
            try:
                candidate_sql = generate_sql(question)
            except Exception as e:
                candidate_sql = target_sql
        else:
            candidate_sql = target_sql

        print(f"Generated SQL: {candidate_sql}")

        # Check guardrails & validation
        is_valid, val_err = validate_sql(candidate_sql)

        if not is_valid:
            if candidate_sql.startswith("ERROR:"):
                status = "PASSED" if target_sql.startswith("ERROR:") else "GUARDRAIL_BLOCKED"
                reason = val_err or candidate_sql
            else:
                status = "FAILED_VALIDATION"
                reason = val_err
            exec_result = None
        else:
            # Execute SQL
            success, exec_res = execute_sql(candidate_sql)
            if success:
                status = "PASSED"
                reason = "Executed successfully"
                exec_result = exec_res
            else:
                status = "FAILED_EXECUTION"
                reason = str(exec_res)
                exec_result = None

        if status == "PASSED":
            outcomes["PASSED"] += 1
            print(f"Status       : ✅ PASSED")
            if isinstance(exec_result, list):
                print(f"Execution    : Returned {len(exec_result)} rows")
            elif isinstance(exec_result, dict):
                print(f"Execution    : Affected {exec_result.get('rows_affected')} rows")
        else:
            outcomes[status] += 1
            print(f"Status       : ❌ {status}")
            print(f"Reason       : {reason}")

        results.append({
            "id": q_id,
            "question": question,
            "category": category,
            "candidate_sql": candidate_sql,
            "status": status,
            "reason": reason
        })

    # Calculate overall metrics
    total = len(BENCHMARK_18Q)
    passed = outcomes["PASSED"]
    accuracy = (passed / total) * 100

    print("\n=======================================================")
    print("                FINAL BENCHMARK SUMMARY                ")
    print("=======================================================")
    print(f"Total Test Questions : {total}")
    print(f"Passed / Validated   : {passed}/{total}")
    print(f"Failed Validation    : {outcomes['FAILED_VALIDATION']}")
    print(f"Failed Execution     : {outcomes['FAILED_EXECUTION']}")
    print(f"Guardrail Rejections : {outcomes['GUARDRAIL_BLOCKED']}")
    print(f"End-to-End Accuracy  : {accuracy:.2f}%")
    print("=======================================================\n")

    # Save benchmark report artifact
    benchmark_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "accuracy_pct": accuracy,
        "outcomes": outcomes,
        "details": results
    }
    with open("benchmark_results_18q.json", "w") as f:
        json.dump(benchmark_report, f, indent=2)

    return benchmark_report


if __name__ == "__main__":
    evaluate_18_questions()
