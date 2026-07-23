from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

from app.film_config import FILM_TITLES
from app.models import GuidedAnswerRequest
from app.services.analysis import THEME_LENS_FILMS, answer_guided


BANNED_GENERIC_PHRASES = [
    "at its core",
    "profound exploration",
    "complex interplay",
    "the human condition",
    "serves as a metaphor",
    "invites the viewer",
]

SOURCE_FACING_PATTERNS = [
    r"\baccording to\b",
    r"\bretrieved\b",
    r"\bcitation\b",
    r"\bchunk\b",
    r"\bcorpus\b",
    r"\bsource\b",
]

CONCRETE_FILM_TERMS = [
    "scene",
    "image",
    "line",
    "camera",
    "cut",
    "sound",
    "music",
    "color",
    "performance",
    "prop",
    "setting",
    "structure",
    "motif",
    "mirror",
    "shot",
    "editing",
    "frame",
    "voice",
    "gesture",
    "lighting",
]


class AnswerJudgeScores(BaseModel):
    thesis_specificity: int = Field(ge=1, le=5)
    evidence_distinctness: int = Field(ge=1, le=5)
    concrete_film_detail: int = Field(ge=1, le=5)
    non_dumping: int = Field(ge=1, le=5)
    anti_plot_summary: int = Field(ge=1, le=5)
    anti_generic_language: int = Field(ge=1, le=5)
    groundedness_to_chunks: int = Field(ge=1, le=5)
    film_lens_relevance: int = Field(ge=1, le=5)
    unsupported_claim_risk: int = Field(ge=1, le=5)
    overall_reading_depth: int = Field(ge=1, le=5)
    reason: str = Field(max_length=500)
    weakest_dimension: str = Field(max_length=100)


JUDGE_INSTRUCTIONS = """
You are evaluating Motif, a film close-reading RAG app.

Score the final answer from 1 to 5 on each dimension:

5 = excellent
4 = good
3 = usable but flawed
2 = poor
1 = failure

Dimensions:
- thesis_specificity: names the film and makes a specific arguable claim.
- evidence_distinctness: the four evidence cards make distinct points.
- concrete_film_detail: cards mention visible/audible film details.
- non_dumping: answer explains evidence instead of copying retrieved text or screenplay lines.
- anti_plot_summary: answer avoids retelling the plot.
- anti_generic_language: answer avoids vague broad language and banned phrases.
- groundedness_to_chunks: claims are supported by retrieved chunks.
- film_lens_relevance: answer stays on the selected film(s) and selected theme.
- unsupported_claim_risk: high score means low risk of invented unsupported claims.
- overall_reading_depth: feels like a thoughtful close reading, not a search summary.

Return only the structured score object.
"""


def load_cases(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_cases(payload: dict, modes: list[str] | None = None) -> list[dict]:
    selected = []
    for group_name, cases in payload.items():
        if modes and group_name not in modes:
            continue
        selected.extend(cases)
    return selected


def public_answer_text(response) -> str:
    parts = [response.answer or "", response.thesis or ""]
    for card in response.evidence_cards:
        parts.extend([str(card.get("label", "")), str(card.get("title", "")), str(card.get("body", ""))])
    for card in response.theme_films:
        parts.extend([str(card.get("title", "")), str(card.get("summary", ""))])
    return "\n".join(part for part in parts if part)


def contains_wrong_film(text: str, case: dict) -> bool:
    allowed_slugs = {case.get("film_a"), case.get("film_b")}
    allowed_titles = {FILM_TITLES[slug] for slug in allowed_slugs if slug in FILM_TITLES}
    for slug, title in FILM_TITLES.items():
        if title in allowed_titles:
            continue
        if re.search(rf"\b{re.escape(title)}\b", text):
            return True
    return False


def theme_mentioned(text: str, lens: str) -> bool:
    lowered = text.lower()
    lens_lower = lens.lower()
    parts = [part.strip() for part in re.split(r"\s+vs\.?\s+|\s+and\s+", lens_lower) if len(part.strip()) >= 4]
    return lens_lower in lowered or any(part in lowered for part in parts)


def has_concrete_terms(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in CONCRETE_FILM_TERMS)


def max_source_overlap(answer_text: str, chunks: list[dict]) -> float:
    answer_words = re.findall(r"\b\w+\b", answer_text.lower())
    if not answer_words:
        return 0.0
    answer_ngrams = {" ".join(answer_words[index : index + 18]) for index in range(max(0, len(answer_words) - 17))}
    if not answer_ngrams:
        return 0.0
    max_overlap = 0.0
    for chunk in chunks:
        chunk_words = re.findall(r"\b\w+\b", chunk.get("text", "").lower())
        chunk_ngrams = {" ".join(chunk_words[index : index + 18]) for index in range(max(0, len(chunk_words) - 17))}
        if not chunk_ngrams:
            continue
        max_overlap = max(max_overlap, len(answer_ngrams & chunk_ngrams) / len(answer_ngrams))
    return round(max_overlap, 3)


def deterministic_answer_checks(case: dict, response) -> tuple[list[str], dict]:
    text = public_answer_text(response)
    lowered = text.lower()
    critical_failures = []
    metrics = {}

    if case["mode"] in {"analyze_film", "compare_films"}:
        if len(response.evidence_cards) != 4:
            critical_failures.append("fewer_than_four_evidence_cards")
        if contains_wrong_film(text, case):
            critical_failures.append("wrong_film_mentioned")
        if not theme_mentioned(text, case["lens"]):
            critical_failures.append("selected_theme_missing")
        concrete_cards = sum(1 for card in response.evidence_cards if has_concrete_terms(str(card.get("body", ""))))
        if concrete_cards < 4:
            critical_failures.append("not_every_card_has_visible_or_audible_detail")
        source_chunks = [chunk.model_dump() for chunk in response.debug_chunks]
        overlap = max_source_overlap(text, source_chunks)
        if overlap > 0.35:
            critical_failures.append("possible_raw_source_dump")
        if any(re.search(pattern, lowered) for pattern in SOURCE_FACING_PATTERNS):
            critical_failures.append("source_facing_language")
        if any(phrase in lowered for phrase in BANNED_GENERIC_PHRASES):
            critical_failures.append("generic_banned_phrase")
        if case["mode"] == "compare_films":
            film_counts = {case["film_a"]: 0, case["film_b"]: 0}
            for chunk in response.debug_chunks:
                if chunk.film_slug in film_counts:
                    film_counts[chunk.film_slug] += 1
            if min(film_counts.values()) < 4:
                critical_failures.append("comparison_retrieval_unbalanced")
            metrics["comparison_film_counts"] = film_counts
        metrics["concrete_card_count"] = concrete_cards
        metrics["max_source_overlap"] = overlap

    if case["mode"] == "explore_theme":
        allowed = set(THEME_LENS_FILMS.get(case["lens"], []))
        returned = [card.get("slug") for card in response.theme_films]
        if not returned:
            critical_failures.append("no_theme_cards")
        if any(slug not in FILM_TITLES for slug in returned):
            critical_failures.append("non_corpus_film_returned")
        if allowed and any(slug not in allowed for slug in returned):
            critical_failures.append("theme_card_outside_allowed_map")
        summaries = [str(card.get("summary", "")) for card in response.theme_films]
        if len(set(summaries)) != len(summaries):
            critical_failures.append("repeated_theme_card_summary")
        if any(len(summary.split()) > 35 for summary in summaries):
            critical_failures.append("theme_summary_too_long")
        if any(re.search(pattern, "\n".join(summaries).lower()) for pattern in SOURCE_FACING_PATTERNS):
            critical_failures.append("theme_source_facing_language")
        metrics["theme_card_count"] = len(returned)

    return critical_failures, metrics


def judge_with_llm(client, model: str, case: dict, response) -> AnswerJudgeScores:
    retrieved_chunks = [
        {
            "chunk_id": chunk.chunk_id,
            "film_slug": chunk.film_slug,
            "source_role": chunk.source_role,
            "chunk_role": chunk.chunk_role,
            "lens_tags": chunk.lens_tags,
            "text": chunk.text[:550],
        }
        for chunk in response.debug_chunks
    ]
    payload = {
        "case": case,
        "answer": {
            "thesis": response.thesis,
            "evidence_cards": response.evidence_cards,
            "theme_films": response.theme_films,
        },
        "retrieved_chunks": retrieved_chunks,
    }
    parsed = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": JUDGE_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        text_format=AnswerJudgeScores,
        max_output_tokens=1200,
    ).output_parsed
    if parsed is None:
        raise RuntimeError("OpenAI returned no parsed judge result.")
    return parsed


def score_average(scores: AnswerJudgeScores | None) -> float | None:
    if scores is None:
        return None
    values = [
        scores.thesis_specificity,
        scores.evidence_distinctness,
        scores.concrete_film_detail,
        scores.non_dumping,
        scores.anti_plot_summary,
        scores.anti_generic_language,
        scores.groundedness_to_chunks,
        scores.film_lens_relevance,
        scores.unsupported_claim_risk,
        scores.overall_reading_depth,
    ]
    return round(sum(values) / len(values), 2)


def format_theme_cards(theme_films: list[dict]) -> tuple[str, str]:
    titles = []
    summaries = []
    for card in theme_films:
        title = str(card.get("title", ""))
        summary = str(card.get("summary", ""))
        if title:
            titles.append(title)
        if title or summary:
            summaries.append(f"{title}: {summary}".strip(": "))
    return " | ".join(titles), " | ".join(summaries)


def run_case(case: dict, client: OpenAI | None, model: str | None) -> dict:
    print(f"Evaluating {case['id']}...", flush=True)
    request = GuidedAnswerRequest(
        mode=case["mode"],
        film_a=case.get("film_a"),
        film_b=case.get("film_b"),
        lens=case["lens"],
        top_k=12,
        include_debug=True,
    )
    response = answer_guided(request)
    critical_failures, deterministic_metrics = deterministic_answer_checks(case, response)
    judge = None
    judge_error = ""
    if client and model and case["mode"] != "explore_theme":
        try:
            judge = judge_with_llm(client, model, case, response)
        except Exception as error:
            judge_error = str(error)

    answer_quality_score = score_average(judge)
    passed = not critical_failures and (answer_quality_score is None or answer_quality_score >= 4.0)
    theme_titles, theme_summaries = format_theme_cards(response.theme_films)
    row = {
        "id": case["id"],
        "mode": case["mode"],
        "film_a": case.get("film_a", ""),
        "film_b": case.get("film_b", ""),
        "lens": case["lens"],
        "coverage_level": response.coverage_level,
        "coverage_score": response.coverage_score,
        "critical_failures": critical_failures,
        "deterministic_metrics": deterministic_metrics,
        "answer_quality_score": answer_quality_score,
        "passed": passed,
        "judge_error": judge_error,
        "theme_card_titles": theme_titles,
        "theme_card_summaries": theme_summaries,
        "response": {
            "thesis": response.thesis,
            "evidence_cards": response.evidence_cards,
            "theme_films": response.theme_films,
        },
        "judge_scores": judge.model_dump() if judge else None,
    }
    return row


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Evaluate final Motif answer quality.")
    parser.add_argument("--cases", default="evals/benchmark_cases.json")
    parser.add_argument("--modes", nargs="*", choices=["analyze", "compare", "theme"], default=None)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-llm", action="store_true", help="Run deterministic answer checks without LLM judging.")
    parser.add_argument("--output", default="evals/Reports/answer_quality_results.json")
    parser.add_argument("--csv-output", default="evals/Reports/answer_quality_results.csv")
    args = parser.parse_args()

    client = None
    if not args.skip_llm:
        try:
            from openai import OpenAI
        except ModuleNotFoundError as error:
            raise SystemExit("The `openai` package is missing. Install it or run with --skip-llm.") from error
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY is missing. Add it to .env or run with --skip-llm.")
        client = OpenAI(api_key=api_key, timeout=45.0, max_retries=1)

    cases = flatten_cases(load_cases(Path(args.cases)), args.modes)
    if args.limit is not None:
        cases = cases[: args.limit]
    rows = [run_case(case, client, args.model) for case in cases]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    csv_path = Path(args.csv_output)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "mode",
        "film_a",
        "film_b",
        "lens",
        "coverage_level",
        "coverage_score",
        "answer_quality_score",
        "passed",
        "critical_failures",
        "judge_error",
        "theme_card_titles",
        "theme_card_summaries",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(row[field]) if isinstance(row[field], list) else row[field] for field in fieldnames})

    for row in rows:
        score = "N/A" if row["answer_quality_score"] is None else f"{row['answer_quality_score']:.2f}"
        failures = ",".join(row["critical_failures"]) or "none"
        print(f"{'PASS' if row['passed'] else 'FAIL'} {row['id']}: score={score} failures={failures}")
    print(f"passed={sum(row['passed'] for row in rows)}/{len(rows)}")
    print(f"json={output_path}")
    print(f"csv={csv_path}")


if __name__ == "__main__":
    main()
