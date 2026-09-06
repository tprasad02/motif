"""Judgment-backed RAG retrieval metrics for Motif.

Unlike the heuristic checks in ``test_retrieval_quality.py``, this module
measures rankings against independently assigned relevance judgments.  A
judgment is graded from 0 (not useful) to 3 (essential evidence).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import mean
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.retrieval import retrieve_chunks
from evals.test_retrieval_quality import flatten_cases, load_cases, query_for_case


RELEVANT_GRADE = 1
MAX_GRADE = 3


def load_judgments(path: Path) -> dict[str, dict[str, int]]:
    """Load ``case_id,chunk_id,relevance`` judgments, rejecting bad grades."""
    if not path.exists():
        raise FileNotFoundError(f"Judgments file not found: {path}")
    judgments: dict[str, dict[str, int]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            case_id = (row.get("case_id") or "").strip()
            chunk_id = (row.get("chunk_id") or "").strip()
            value = (row.get("relevance") or "").strip()
            if not case_id or not chunk_id or not value:
                continue
            try:
                grade = int(value)
            except ValueError as error:
                raise ValueError(f"Invalid relevance for {case_id}/{chunk_id}: {value}") from error
            if not 0 <= grade <= MAX_GRADE:
                raise ValueError(f"Relevance must be 0–{MAX_GRADE}, got {grade} for {case_id}/{chunk_id}")
            judgments.setdefault(case_id, {})[chunk_id] = grade
    return judgments


def ranking_metrics(retrieved_ids: list[str], judgments: dict[str, int], k: int) -> dict[str, float | int]:
    """Compute standard IR metrics; unjudged results are reported separately.

    Precision is deliberately calculated only over judged ranks.  Treating an
    unjudged result as irrelevant makes a sparse assessment pool look worse
    than the system; silently excluding it makes it look better.  ``judged_at_k``
    exposes the coverage needed to interpret each score.
    """
    ranked = retrieved_ids[:k]
    grades = [judgments.get(chunk_id) for chunk_id in ranked]
    judged = [grade for grade in grades if grade is not None]
    relevant_total = sum(grade >= RELEVANT_GRADE for grade in judgments.values())
    relevant_retrieved = sum((grade or 0) >= RELEVANT_GRADE for grade in grades)
    first_relevant = next((index for index, grade in enumerate(grades, start=1) if (grade or 0) >= RELEVANT_GRADE), None)

    dcg = sum(((2 ** (grade or 0)) - 1) / math.log2(index + 1) for index, grade in enumerate(grades, start=1))
    ideal_grades = sorted(judgments.values(), reverse=True)[:k]
    idcg = sum(((2**grade) - 1) / math.log2(index + 1) for index, grade in enumerate(ideal_grades, start=1))
    return {
        "precision_at_k": round(relevant_retrieved / len(judged), 4) if judged else 0.0,
        "recall_at_k": round(relevant_retrieved / relevant_total, 4) if relevant_total else 0.0,
        "mrr": round(1 / first_relevant, 4) if first_relevant else 0.0,
        "ndcg_at_k": round(dcg / idcg, 4) if idcg else 0.0,
        "judged_at_k": len(judged),
        "unjudged_at_k": len(ranked) - len(judged),
        "relevant_retrieved_at_k": relevant_retrieved,
        "relevant_judgments": relevant_total,
    }


def retrieve_for_case(case: dict[str, Any], top_k: int) -> list[str]:
    film_slugs = []
    if case["mode"] == "analyze_film":
        film_slugs = [case["film_a"]]
    elif case["mode"] == "compare_films":
        film_slugs = [case["film_a"], case["film_b"]]
    return [
        chunk.chunk_id
        for chunk in retrieve_chunks(query_for_case(case), film_slugs, [], top_k, lens_tags=[case["lens"]])
    ]


def write_annotation_pool(cases: list[dict[str, Any]], output: Path, pool_k: int) -> None:
    """Write candidates for human annotation without overwriting judgments."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "chunk_id", "rank", "relevance", "notes"])
        writer.writeheader()
        for case in cases:
            for rank, chunk_id in enumerate(retrieve_for_case(case, pool_k), start=1):
                writer.writerow({"case_id": case["id"], "chunk_id": chunk_id, "rank": rank, "relevance": "", "notes": ""})


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval with graded relevance judgments.")
    parser.add_argument("--cases", default="evals/benchmark_cases.json")
    parser.add_argument("--judgments", default="evals/relevance_judgments.csv")
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--output", default="evals/Reports/rag_ranking_metrics.json")
    parser.add_argument("--csv-output", default="evals/Reports/rag_ranking_metrics.csv")
    parser.add_argument("--write-annotation-pool", default="", help="Write a blank candidate pool and exit.")
    parser.add_argument("--pool-k", type=int, default=30)
    args = parser.parse_args()

    cases = flatten_cases(load_cases(Path(args.cases)))
    if args.write_annotation_pool:
        write_annotation_pool(cases, Path(args.write_annotation_pool), args.pool_k)
        print(f"annotation_pool={args.write_annotation_pool}")
        return

    judgments = load_judgments(Path(args.judgments))
    missing = [case["id"] for case in cases if case["id"] not in judgments]
    if missing:
        raise SystemExit(f"Missing judgments for {len(missing)} benchmark cases (for example: {missing[0]}).")

    rows = []
    for case in cases:
        metrics = ranking_metrics(retrieve_for_case(case, args.top_k), judgments[case["id"]], args.top_k)
        rows.append({"id": case["id"], "mode": case["mode"], "lens": case["lens"], **metrics})

    aggregate = {
        "cases": len(rows),
        "top_k": args.top_k,
        "precision_at_k": round(mean(row["precision_at_k"] for row in rows), 4),
        "recall_at_k": round(mean(row["recall_at_k"] for row in rows), 4),
        "mrr": round(mean(row["mrr"] for row in rows), 4),
        "ndcg_at_k": round(mean(row["ndcg_at_k"] for row in rows), 4),
        "judgment_coverage_at_k": round(mean(row["judged_at_k"] / args.top_k for row in rows), 4),
    }
    Path(args.output).write_text(json.dumps({"summary": aggregate, "cases": rows}, indent=2), encoding="utf-8")
    with Path(args.csv_output).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
