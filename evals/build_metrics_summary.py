from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.film_config import FILM_TITLES
from app.models import GuidedAnswerRequest
from app.services.analysis import answer_guided
from evals.test_retrieval_quality import evaluate_retrieval_case, flatten_cases, load_cases


REPORTS_DIR = Path("evals/Reports")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _latest_report(pattern: str) -> Path | None:
    matches = sorted(REPORTS_DIR.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _load_answer_quality(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        failures = row.get("critical_failures") or {}
        failure_count = 0
        if isinstance(failures, dict):
            failure_count = sum(len(value or []) for value in failures.values())
        by_id[row["id"]] = {
            "answer_passed": bool(row.get("passed")),
            "answer_quality_score": row.get("answer_quality_score"),
            "answer_coverage_level": row.get("coverage_level", ""),
            "answer_coverage_score": row.get("coverage_score"),
            "answer_retry_used": bool(row.get("retry_used")),
            "answer_failure_count": failure_count,
            "answer_judge_available": row.get("answer_quality_score") is not None,
            "answer_judge_gate_passed": row.get("judge_gate_passed"),
            "answer_first_passed": row.get("first_passed"),
            "answer_faithfulness": (row.get("judge_scores") or {}).get("faithfulness"),
            "answer_relevance": (row.get("judge_scores") or {}).get("answer_relevance"),
        }
    return by_id


def _load_rag_ranking_metrics(path: Path | None) -> dict[str, Any] | None:
    """Load the judgment-backed retrieval report when a full suite produced it."""
    if not path or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else None


def _response_latency(case: dict[str, Any]) -> tuple[float | None, bool, str]:
    request = GuidedAnswerRequest(
        mode=case["mode"],
        film_a=case.get("film_a"),
        film_b=case.get("film_b"),
        lens=case["lens"],
        top_k=12,
        include_debug=True,
    )
    start = time.perf_counter()
    response = answer_guided(request)
    elapsed = time.perf_counter() - start
    generated = not response.refused and (case["mode"] == "explore_lens" or len(response.evidence_cards) == 4)
    return elapsed, generated, ""


def _average(values: list[float]) -> float | None:
    return round(mean(values), 3) if values else None


def _percent(values: list[bool]) -> float | None:
    return round((sum(1 for value in values if value) / len(values)) * 100, 1) if values else None


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _clean_retrieval_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "mode": row["mode"],
        "film_a": row.get("film_a", ""),
        "film_b": row.get("film_b", ""),
        "lens": row["lens"],
        "chunk_count": row["chunk_count"],
        "retrieval_failed_gates": "|".join(row.get("failed_gates", [])),
        "retrieval_guardrails_passed": row["overall"] == "pass",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _case_summary(case: dict[str, Any], rows: list[dict[str, Any]], answer_metrics: dict[str, Any]) -> dict[str, Any]:
    latency_values = [
        _number(row["response_latency_seconds"])
        for row in rows
        if row.get("response_latency_seconds") not in (None, "") and row.get("latency_generated")
    ]
    return {
        "id": case["id"],
        "mode": case["mode"],
        "film_a": case.get("film_a", ""),
        "film_b": case.get("film_b", ""),
        "lens": case["lens"],
        "trials": len(rows),
        "retrieval_guardrails_pass_rate": _percent([bool(row["retrieval_guardrails_passed"]) for row in rows]),
        "avg_response_latency_seconds": _average(latency_values) if latency_values else "",
        **answer_metrics,
    }


def _build_overall_summary(
    cases: list[dict[str, Any]],
    trial_rows: list[dict[str, Any]],
    case_rows: list[dict[str, Any]],
    answer_report: Path | None,
    rag_ranking_report: Path | None,
    trials: int,
) -> dict[str, Any]:
    chunks = _load_jsonl(Path("backend/app/corpus/chunks.jsonl"))
    sources = _load_jsonl(Path("backend/app/corpus/sources.jsonl"))
    film_rows = {row.get("film_slug") for row in chunks if row.get("film_slug")}
    latency_values = [
        _number(row["response_latency_seconds"])
        for row in trial_rows
        if row.get("response_latency_seconds") not in (None, "") and row.get("latency_generated")
    ]
    answer_rows = [row for row in case_rows if row.get("answer_judge_available")]
    answer_first_pass_rows = [row for row in case_rows if row.get("answer_first_passed") not in (None, "")]
    answer_judge_gate_rows = [row for row in case_rows if row.get("answer_judge_gate_passed") is not None]
    unscored_answer_case_ids = [
        row["id"] for row in case_rows if row.get("answer_first_passed") not in (None, "") and not row.get("answer_judge_available")
    ]
    summary = {
        "films": len(film_rows or set(FILM_TITLES)),
        "documents": len(sources),
        "chunks": len(chunks),
        "eval_cases": len(cases),
        "trials_per_retrieval_case": trials,
        "retrieval_trials": len(trial_rows),
        "generated_latency_trials": len(latency_values),
        "retrieval_guardrails_pass_rate": _percent([bool(row["retrieval_guardrails_passed"]) for row in trial_rows]),
        "answer_checked_cases": len(answer_first_pass_rows),
        "answer_llm_judged_cases": len(answer_rows),
        "answer_unscored_case_ids": unscored_answer_case_ids,
        "answer_validity_pass_rate": _percent([bool(row.get("answer_first_passed")) for row in answer_first_pass_rows]),
        "answer_quality_pass_rate": _percent([bool(row.get("answer_judge_gate_passed")) for row in answer_judge_gate_rows]),
        "average_faithfulness": _average([_number(row["answer_faithfulness"]) for row in answer_rows]),
        "average_answer_relevance": _average([_number(row["answer_relevance"]) for row in answer_rows]),
        "average_response_latency_seconds": _average(latency_values),
        "answer_quality_source_report": str(answer_report) if answer_report else None,
    }
    rag_metrics = _load_rag_ranking_metrics(rag_ranking_report)
    summary["judgment_backed_retrieval"] = rag_metrics
    summary["judgment_backed_retrieval_source_report"] = str(rag_ranking_report) if rag_metrics else None
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build clean Motif metrics artifacts from benchmark cases.")
    parser.add_argument("--cases", default="evals/benchmark_cases.json")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--answer-quality-report", default="")
    parser.add_argument(
        "--rag-ranking-report",
        default="evals/Reports/rag_ranking_metrics.json",
        help="Judgment-backed ranking report produced by evals.rag_metrics.",
    )
    parser.add_argument("--skip-response-latency", action="store_true")
    parser.add_argument("--latency-case-limit", type=int, default=5)
    parser.add_argument("--summary-output", default="evals/final_metrics/metrics_summary.json")
    parser.add_argument("--trial-output", default="evals/final_metrics/metrics_trials.csv")
    parser.add_argument("--case-output", default="evals/final_metrics/metrics_case_summary.csv")
    args = parser.parse_args()

    load_dotenv(Path(".env"))
    payload = load_cases(Path(args.cases))
    cases = flatten_cases(payload)
    answer_report = Path(args.answer_quality_report) if args.answer_quality_report else _latest_report("answer_quality_results_*.json")
    rag_ranking_report = Path(args.rag_ranking_report) if args.rag_ranking_report else None
    answer_quality = _load_answer_quality(answer_report)
    latency_case_ids = {case["id"] for case in cases[: args.latency_case_limit]} if args.latency_case_limit else {case["id"] for case in cases}

    trial_rows: list[dict[str, Any]] = []
    for trial in range(1, args.trials + 1):
        for case in cases:
            row = _clean_retrieval_row(evaluate_retrieval_case(case, args.top_k))
            row["trial"] = trial
            row.update(
                {
                    "response_latency_seconds": "",
                    "latency_generated": "",
                    "latency_error": "",
                    **answer_quality.get(case["id"], {}),
                }
            )
            if not args.skip_response_latency and case["id"] in latency_case_ids:
                try:
                    latency, generated, latency_error = _response_latency(case)
                    row["response_latency_seconds"] = round(latency, 3) if latency is not None else ""
                    row["latency_generated"] = generated
                    row["latency_error"] = latency_error
                except Exception as error:
                    row["latency_generated"] = False
                    row["latency_error"] = type(error).__name__
            trial_rows.append(row)
            print(f"trial={trial} case={case['id']}", flush=True)

    rows_by_case = {case["id"]: [row for row in trial_rows if row["id"] == case["id"]] for case in cases}
    case_rows = [_case_summary(case, rows_by_case[case["id"]], answer_quality.get(case["id"], {})) for case in cases]
    summary = _build_overall_summary(cases, trial_rows, case_rows, answer_report, rag_ranking_report, args.trials)

    trial_fields = [
        "trial",
        "id",
        "mode",
        "film_a",
        "film_b",
        "lens",
        "chunk_count",
        "retrieval_failed_gates",
        "retrieval_guardrails_passed",
        "answer_passed",
        "answer_quality_score",
        "answer_faithfulness",
        "answer_relevance",
        "answer_coverage_level",
        "answer_coverage_score",
        "answer_retry_used",
        "answer_failure_count",
        "answer_judge_available",
        "answer_judge_gate_passed",
        "answer_first_passed",
        "response_latency_seconds",
        "latency_generated",
        "latency_error",
    ]
    case_fields = [
        "id",
        "mode",
        "film_a",
        "film_b",
        "lens",
        "trials",
        "retrieval_guardrails_pass_rate",
        "answer_faithfulness",
        "answer_relevance",
        "answer_coverage_level",
        "answer_coverage_score",
        "answer_retry_used",
        "answer_failure_count",
        "answer_judge_available",
        "answer_judge_gate_passed",
        "answer_first_passed",
        "avg_response_latency_seconds",
    ]

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "artifacts": {
                    "trial_rows": args.trial_output,
                    "case_summary_rows": args.case_output,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_csv(Path(args.trial_output), trial_rows, trial_fields)
    _write_csv(Path(args.case_output), case_rows, case_fields)

    print(json.dumps(summary, indent=2))
    print(f"summary={summary_path}")
    print(f"trials={args.trial_output}")
    print(f"cases={args.case_output}")


if __name__ == "__main__":
    main()
