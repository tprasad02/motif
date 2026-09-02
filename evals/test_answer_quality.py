from __future__ import annotations
from datetime import datetime
import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.film_config import FILM_TITLES
from app.models import GuidedAnswerRequest
from app.services.analysis import answer_guided
from.utilities import get_current_time_string 

BANNED_GENERIC_PHRASES = [
    "at its core",
    "profound exploration",
    "complex interplay",
    "the human condition",
    "serves as a metaphor",
    "invites the viewer",
    "matters because",
    "not only",
    "but also",
    "not just",
    "serves as",
    "underscores",
    "illustrating how",
]

SOURCE_FACING_PATTERNS = [
    r"\baccording to\b",
    r"\bretrieved\b",
    r"\bcitation\b",
    r"\bchunk\b",
    r"\bcorpus\b",
    r"\b(?:retrieved|cited)\s+sources?\b",
    r"\bsource\s+(?:title|type|role|material|chunk|document)\b",
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

CARDS = ["Scene", "Character", "Pattern", "Counterreading"]

class AnswerJudgeScores(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    answer_relevance: int = Field(ge=1, le=5)
    reason: str = Field(max_length=500)
    weakest_dimension: str = Field(max_length=100)


class FaithfulnessJudgeScore(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    reason: str = Field(max_length=300)


class RelevanceJudgeScore(BaseModel):
    answer_relevance: int = Field(ge=1, le=5)
    reason: str = Field(max_length=300)


FAITHFULNESS_JUDGE_INSTRUCTIONS = """
You are evaluating Motif, a film close-reading RAG app.

Score faithfulness from 1 to 5:

5 = excellent
4 = good
3 = usable but flawed
2 = poor
1 = failure


Assess the thesis and every evidence-card claim only against the supplied
retrieved-chunk excerpts. Do not supply outside film knowledge. A score of 5
means every substantive claim is entailed or directly supported; 4 allows one
minor interpretive extension; 3 means a material claim lacks support; 1-2
means unsupported claims substantially change the reading. The card `chunk_ids`
identify intended support and should be prioritized.

Return only the structured score object.
"""


RELEVANCE_JUDGE_INSTRUCTIONS = """
You are evaluating whether a Motif film close-reading answer responds to its request.

Score answer_relevance from 1 to 5. You receive only the benchmark request and
public answer, never retrieval evidence. A score of 5 directly answers the
selected film(s) and lens with specific, useful close reading; 4 has a minor
focus or specificity issue; 3 is partially on-topic but generic or plot-led;
1-2 substantially misses the requested film(s) or lens.

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


def has_detail_signal(text: str) -> bool:
    words = re.findall(r"\b[\w'-]+\b", text)
    if len(words) < 45:
        return False
    lowered = text.lower()
    concrete_term_count = sum(1 for term in CONCRETE_FILM_TERMS if re.search(rf"\b{re.escape(term)}\b", lowered))
    proper_names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", text)
    quoted_or_specific = bool(re.search(r"[\"“”]", text) or re.search(r"\b(?:when|after|as|during|in the scene|sequence)\b", lowered))
    return concrete_term_count >= 1 or len(proper_names) >= 2 or quoted_or_specific


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


def max_verbatim_run(answer_text: str, chunks: list[dict]) -> int:
    """Longest copied word run shared with any retrieved chunk.

    Proportional n-gram overlap can miss a short pasted quotation inside a long
    answer.  This companion check catches that failure mode directly.
    """
    answer_words = re.findall(r"\b\w+\b", answer_text.lower())
    longest = 0
    for chunk in chunks:
        source_words = re.findall(r"\b\w+\b", chunk.get("text", "").lower())
        runs: dict[tuple[int, int], int] = {}
        positions: dict[str, list[int]] = {}
        for index, word in enumerate(source_words):
            positions.setdefault(word, []).append(index)
        for answer_index, word in enumerate(answer_words):
            for source_index in positions.get(word, []):
                previous = runs.get((answer_index - 1, source_index - 1), 0)
                current = previous + 1
                runs[(answer_index, source_index)] = current
                longest = max(longest, current)
    return longest


def card_similarity(left: str, right: str) -> float:
    left_words = set(re.findall(r"\b[a-z]{4,}\b", left.lower()))
    right_words = set(re.findall(r"\b[a-z]{4,}\b", right.lower()))
    union = left_words | right_words
    return len(left_words & right_words) / len(union) if union else 0.0


def card_failure_reasons(card: dict) -> list[str]:
    reasons = []
    label = str(card.get("label", ""))
    body = str(card.get("body", ""))
    lowered = body.lower()
    if label not in CARDS:
        reasons.append("unexpected_card_label")
    if len(body.split()) < 45:
        reasons.append("card_too_short")
    if any(re.search(pattern, lowered) for pattern in SOURCE_FACING_PATTERNS):
        reasons.append("source_facing_language")
    if not has_detail_signal(body):
        reasons.append("card_too_generic")
    return reasons


def card_chunk_ids(card: dict) -> list[str]:
    raw_ids = card.get("chunk_ids") or []
    if isinstance(raw_ids, str):
        try:
            raw_ids = json.loads(raw_ids)
        except json.JSONDecodeError:
            raw_ids = [raw_ids]
    return [str(chunk_id) for chunk_id in raw_ids if str(chunk_id).strip()]


def deterministic_answer_checks(case: dict, response) -> tuple[dict, dict]:
    text = public_answer_text(response)
    lowered = text.lower()
    critical_failures = {"overall":[], **{card:[] for card in CARDS}}
    metrics = {}
    mode = case["mode"]

    if mode in {"analyze_film", "compare_films"}:
        # Overall Error              
        if len(response.evidence_cards) != 4:
            critical_failures["overall"].append("fewer_than_four_evidence_cards")
        if contains_wrong_film(text, case):
            critical_failures["overall"].append("wrong_film_mentioned")
        if not theme_mentioned(text, case["lens"]):
            critical_failures["overall"].append("selected_theme_missing")

        # Card-dependent checks. These are less strict than exact
        # keyword restrictions because good film evidence can be named many ways.
        specific_cards = 0
        for card in response.evidence_cards:
            label = str(card.get("label", ""))
            label_bucket = label if label in critical_failures else "overall"
            reasons = card_failure_reasons(card)
            critical_failures[label_bucket].extend(reasons)
            if not reasons:
                specific_cards += 1
        source_chunks = [chunk.model_dump() for chunk in response.debug_chunks]
        retrieved_chunk_ids = {chunk["chunk_id"] for chunk in source_chunks}
        cards_with_valid_chunk_ids = 0
        for card in response.evidence_cards:
            label = str(card.get("label", ""))
            label_bucket = label if label in critical_failures else "overall"
            chunk_ids = card_chunk_ids(card)
            if not chunk_ids:
                critical_failures[label_bucket].append("missing_supporting_chunk_ids")
            elif retrieved_chunk_ids and not set(chunk_ids).issubset(retrieved_chunk_ids):
                critical_failures[label_bucket].append("unknown_supporting_chunk_id")
            else:
                cards_with_valid_chunk_ids += 1
        overlap = max_source_overlap(text, source_chunks)
        if overlap > 0.35:
            critical_failures["overall"].append("possible_raw_source_dump")
        verbatim_run = max_verbatim_run(text, source_chunks)
        if verbatim_run >= 25:
            critical_failures["overall"].append("long_verbatim_source_run")
        if any(re.search(pattern, lowered) for pattern in SOURCE_FACING_PATTERNS):
            critical_failures["overall"].append("source_facing_language")
        metrics["banned_generic_phrase_count"] = sum(1 for phrase in BANNED_GENERIC_PHRASES if phrase in lowered)
        if case["mode"] == "compare_films":
            film_counts = {case["film_a"]: 0, case["film_b"]: 0}
            for chunk in response.debug_chunks:
                if chunk.film_slug in film_counts:
                    film_counts[chunk.film_slug] += 1
            if min(film_counts.values()) < 4:
                critical_failures["overall"].append("comparison_retrieval_unbalanced")
            metrics["comparison_film_counts"] = film_counts
            film_a_title = FILM_TITLES.get(case["film_a"], case["film_a"])
            film_b_title = FILM_TITLES.get(case["film_b"], case["film_b"])
            cards_with_both_films = 0
            for card in response.evidence_cards:
                label = str(card.get("label", ""))
                label_bucket = label if label in critical_failures else "overall"
                card_text = f"{card.get('title', '')} {card.get('body', '')}"
                has_a = bool(re.search(rf"\b{re.escape(film_a_title)}\b", card_text))
                has_b = bool(re.search(rf"\b{re.escape(film_b_title)}\b", card_text))
                if has_a and has_b:
                    cards_with_both_films += 1
                else:
                    if not has_a:
                        critical_failures[label_bucket].append("comparison_card_missing_film_a")
                    if not has_b:
                        critical_failures[label_bucket].append("comparison_card_missing_film_b")
            if cards_with_both_films < 4:
                critical_failures["overall"].append("comparison_cards_not_integrated")
            metrics["comparison_cards_with_both_films"] = cards_with_both_films
        metrics["specific_card_count"] = specific_cards
        metrics["cards_with_valid_chunk_ids"] = cards_with_valid_chunk_ids
        metrics["max_source_overlap"] = overlap
        metrics["max_verbatim_source_run_words"] = verbatim_run
        card_bodies = [str(card.get("body", "")) for card in response.evidence_cards]
        max_card_similarity = max(
            (card_similarity(left, right) for index, left in enumerate(card_bodies) for right in card_bodies[index + 1 :]),
            default=0.0,
        )
        if max_card_similarity > 0.75:
            critical_failures["overall"].append("evidence_cards_are_lexically_redundant")
        metrics["max_card_lexical_similarity"] = round(max_card_similarity, 3)

    if mode == "explore_theme":
        returned = [card.get("slug") for card in response.theme_films]
        if not returned:
            critical_failures["overall"].append("no_theme_cards")
        if any(slug not in FILM_TITLES for slug in returned):
            critical_failures["overall"].append("non_corpus_film_returned")
        summaries = [str(card.get("summary", "")) for card in response.theme_films]
        if len(set(summaries)) != len(summaries):
            critical_failures["overall"].append("repeated_theme_card_summary")
        if any(len(summary.split()) > 35 for summary in summaries):
            critical_failures["overall"].append("theme_summary_too_long")
        if len(returned) < 4:
            critical_failures["overall"].append("too_few_theme_cards")
        if len(set(returned)) != len(returned):
            critical_failures["overall"].append("repeated_theme_film")
        if len({slug for slug in returned if slug}) < 4:
            critical_failures["overall"].append("theme_results_not_diverse")
        if any(len(summary.split()) < 8 for summary in summaries):
            critical_failures["overall"].append("theme_summary_too_thin")
        if any(re.search(pattern, "\n".join(summaries).lower()) for pattern in SOURCE_FACING_PATTERNS):
            critical_failures["overall"].append("theme_source_facing_language")
        metrics["theme_card_count"] = len(returned)

    return critical_failures, metrics


def has_card_failures(failures: dict) -> bool:
    return any(failures.get(card) for card in CARDS)


def has_any_failure(failures: dict) -> bool:
    return any(bool(value) for value in failures.values())


def summarize_failures(failures: dict) -> str:
    parts = []
    for bucket, reasons in failures.items():
        if reasons:
            parts.append(f"{bucket}: {';'.join(reasons)}")
    return " | ".join(parts) or "none"


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
    answer = {
        "answer": response.answer,
        "thesis": response.thesis,
        "evidence_cards": response.evidence_cards,
        "theme_films": response.theme_films,
    }
    public_answer = {
        "answer": response.answer,
        "thesis": response.thesis,
        "evidence_cards": [
            {key: card.get(key, "") for key in ("label", "title", "body")}
            for card in response.evidence_cards
        ],
        "theme_films": response.theme_films,
    }
    faithfulness_payload = {
        "case": case,
        "answer": answer,
        "retrieved_chunks": retrieved_chunks,
    }
    faithfulness = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": FAITHFULNESS_JUDGE_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(faithfulness_payload, ensure_ascii=False)},
        ],
        text_format=FaithfulnessJudgeScore,
        max_output_tokens=500,
    ).output_parsed
    relevance = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": RELEVANCE_JUDGE_INSTRUCTIONS},
            {"role": "user", "content": json.dumps({"case": case, "answer": public_answer}, ensure_ascii=False)},
        ],
        text_format=RelevanceJudgeScore,
        max_output_tokens=500,
    ).output_parsed
    if faithfulness is None or relevance is None:
        raise RuntimeError("OpenAI returned no parsed judge result.")
    weakest = "faithfulness" if faithfulness.faithfulness <= relevance.answer_relevance else "answer_relevance"
    return AnswerJudgeScores(
        faithfulness=faithfulness.faithfulness,
        answer_relevance=relevance.answer_relevance,
        weakest_dimension=weakest,
        reason=f"Faithfulness: {faithfulness.reason} Relevance: {relevance.reason}"[:500],
    )


def score_average(scores: AnswerJudgeScores | None) -> float | None:
    if scores is None:
        return None
    values = [scores.faithfulness, scores.answer_relevance]
    return round(sum(values) / len(values), 2)


def judge_passes_gate(scores: AnswerJudgeScores | None) -> bool | None:
    """Neither canonical RAG answer-quality dimension may be weak."""
    if scores is None:
        return None
    return scores.faithfulness >= 4 and scores.answer_relevance >= 4


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


def run_case(case: dict, client: OpenAI | None, model: str | None, retry_card_failures: bool = False) -> dict:
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
    retry_used = False
    first_attempt_failures = critical_failures
    if retry_card_failures and case["mode"] != "explore_theme" and has_card_failures(critical_failures):
        retry_used = True
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
    judge_gate_passed = judge_passes_gate(judge)
    # First-pass success is the production quality metric. Optional retry data
    # is retained for diagnosis, never allowed to inflate the headline result.
    passed = not has_any_failure(first_attempt_failures) and (judge_gate_passed is not False)
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
        "first_attempt_failures": first_attempt_failures,
        "retry_used": retry_used,
        "deterministic_metrics": deterministic_metrics,
        "answer_quality_score": answer_quality_score,
        "judge_gate_passed": judge_gate_passed,
        "first_passed": not has_any_failure(first_attempt_failures),
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

def build_csv(csv_path: Path, rows) -> None:
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
        "judge_gate_passed",
        "first_passed",
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
            csv_row = {}

            for field in fieldnames:
                value = row.get(field)

                if field == "critical_failures" and isinstance(value, dict):
                    flattened_failures = [
                        f"{label}: {failure}"
                        for label, label_failures in value.items()
                        for failure in label_failures
                    ]

                    value = ", ".join(flattened_failures) or "none"

                elif isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)

                csv_row[field] = value

            writer.writerow(csv_row)

def build_output(rows: dict = None) -> None:
    
    passed_count = 0

    for row in rows:
        passed = row["passed"]
        passed_count += passed

        score = row["answer_quality_score"]
        score_text = "N/A" if score is None else f"{score:.2f}"

        non_empty_failures = {
            label: failures
            for label, failures in row["critical_failures"].items()
            if failures
        }
        status = "PASS" if passed else "FAIL"

        print(
            f"{status} {row['id']}: "
            f"score={score_text} failures={non_empty_failures}"
        )

    print(f"passed={passed_count}/{len(rows)}, passing rate: {(100 * (passed_count/len(rows))):.2f} %")
    
    

def main() -> None:
    load_dotenv()
    timestamp = get_current_time_string()
    parser = argparse.ArgumentParser(description="Evaluate final Motif answer quality.")
    parser.add_argument("--cases", default="evals/benchmark_cases.json")
    parser.add_argument("--modes", nargs="*", choices=["analyze", "compare", "theme"], default=None)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-llm", action="store_true", help="Run deterministic answer checks without LLM judging.")
    parser.add_argument(
        "--retry-card-failures",
        action="store_true",
        help="Run one diagnostic retry after a card failure; retries do not affect first-pass results.",
    )
    parser.add_argument("--output", default=f"evals/Reports/answer_quality_results_{timestamp}.json")
    parser.add_argument("--csv-output", default=f"evals/Reports/answer_quality_results_{timestamp}.csv")
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
    rows = [run_case(case, client, args.model, args.retry_card_failures) for case in cases]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    csv_path = Path(args.csv_output)

    build_output(rows)
    build_csv(csv_path, rows)
    print(f"json={output_path}")
    print(f"csv={csv_path}")


if __name__ == "__main__":
    main()
