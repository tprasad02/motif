"""Run Motif's complete, reproducible evaluation suite.

The suite deliberately reports distinct layers together: corpus coverage,
retrieval guardrails, judgment-backed ranking quality, answer quality, and an
aggregate artifact. A failed layer stops the run because a later score should
not conceal an earlier failure.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_module(module: str, *arguments: str) -> None:
    subprocess.run([sys.executable, "-m", module, *arguments], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all Motif evaluation layers and publish one metrics summary.")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--chunk-limit", type=int, default=200, help="Representative chunk sample to judge.")
    parser.add_argument("--latency-case-limit", type=int, default=5)
    parser.add_argument("--skip-answer-judge", action="store_true", help="Offline-only: omit the LLM answer judge.")
    parser.add_argument("--skip-chunk-judge", action="store_true", help="Offline-only: use deterministic chunk checks only.")
    parser.add_argument("--skip-response-latency", action="store_true")
    args = parser.parse_args()

    reports = Path("evals/Reports")
    final_metrics = Path("evals/final_metrics")
    reports.mkdir(parents=True, exist_ok=True)
    final_metrics.mkdir(parents=True, exist_ok=True)
    retrieval_csv = reports / "retrieval_quality_results.csv"
    retrieval_json = reports / "retrieval_quality_results.json"
    answer_json = reports / "answer_quality_results.json"
    answer_csv = reports / "answer_quality_results.csv"
    rag_json = reports / "rag_ranking_metrics.json"
    rag_csv = reports / "rag_ranking_metrics.csv"

    chunk_args = ["backend/app/corpus/chunks.jsonl", "--limit", str(args.chunk_limit), "--model", args.model, "--output", "chunk_evaluation_results.json"]
    if args.skip_chunk_judge:
        chunk_args.append("--skip-llm")
    run_module("evals.chunk_eval", *chunk_args)
    chunk_reports = sorted(reports.glob("chunk_evaluation_results*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    chunk_report = str(chunk_reports[0]) if chunk_reports else ""
    run_module("evals.verify_corpus", "--sources", "data/manual_sources.csv", "--min-per-film", "4", "--output", str(reports / "corpus_coverage.csv"))
    run_module("evals.test_retrieval_quality", "--top-k", str(args.top_k), "--output", str(retrieval_csv), "--json-output", str(retrieval_json))
    run_module("evals.test_supported_retrieval_sweep", "--scope", "primary", "--top-k", str(args.top_k), "--output", str(reports / "supported_retrieval_sweep_primary.csv"), "--json-output", str(reports / "supported_retrieval_sweep_primary.json"))
    run_module("evals.test_supported_retrieval_sweep", "--scope", "secondary", "--top-k", str(args.top_k), "--output", str(reports / "supported_retrieval_sweep_secondary.csv"), "--json-output", str(reports / "supported_retrieval_sweep_secondary.json"))
    run_module("evals.rag_metrics", "--top-k", str(args.top_k), "--output", str(rag_json), "--csv-output", str(rag_csv))

    answer_args = ["--model", args.model, "--output", str(answer_json), "--csv-output", str(answer_csv)]
    if args.skip_answer_judge:
        answer_args.append("--skip-llm")
    run_module("evals.test_answer_quality", *answer_args)

    summary_args = [
        "--trials", str(args.trials),
        "--top-k", str(args.top_k),
        "--latency-case-limit", str(args.latency_case_limit),
        "--answer-quality-report", str(answer_json),
        "--rag-ranking-report", str(rag_json),
    ]
    if args.skip_response_latency:
        summary_args.append("--skip-response-latency")
    run_module("evals.build_metrics_summary", *summary_args)

    manifest = {
        "suite": "Motif evaluation",
        "trials": args.trials,
        "top_k": args.top_k,
        "chunk_limit": args.chunk_limit,
        "chunk_judge_skipped": args.skip_chunk_judge,
        "answer_judge_skipped": args.skip_answer_judge,
        "response_latency_skipped": args.skip_response_latency,
        "artifacts": {
            "corpus_coverage": str(reports / "corpus_coverage.csv"),
            "chunk_quality": chunk_report,
            "retrieval_guardrails": str(retrieval_json),
            "supported_primary_sweep": str(reports / "supported_retrieval_sweep_primary.json"),
            "supported_secondary_sweep": str(reports / "supported_retrieval_sweep_secondary.json"),
            "ranking_metrics": str(rag_json),
            "answer_quality": str(answer_json),
            "aggregate_summary": "evals/final_metrics/metrics_summary.json",
        },
    }
    (final_metrics / "evaluation_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest={final_metrics / 'evaluation_manifest.json'}")


if __name__ == "__main__":
    main()
