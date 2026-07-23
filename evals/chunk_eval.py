from __future__ import annotations

import sys
import argparse
import hashlib
import json
import math
import os
import re
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError





PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
CHUNKS_PATH = BACKEND_DIR / "app" / "corpus" / "chunks.jsonl"

sys.path.insert(0, str(BACKEND_DIR))

from app.models import (
    ChunkEvaluationResult,
    ChunkLLMEvaluation,
    DeterministicEvaluation,
    EvaluationOutput,
    EvaluationSummary,
    InputChunk,
)
# ============================================================
# Constants
# ============================================================

CONTINUATION_WORDS = {
    "also",
    "although",
    "and",
    "because",
    "but",
    "consequently",
    "furthermore",
    "he",
    "her",
    "his",
    "however",
    "it",
    "its",
    "moreover",
    "she",
    "such",
    "that",
    "their",
    "therefore",
    "these",
    "they",
    "this",
    "those",
    "though",
    "thus",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whose",
}

TRAILING_CLAUSE_WORDS = {
    "although",
    "and",
    "because",
    "but",
    "however",
    "if",
    "including",
    "or",
    "that",
    "therefore",
    "unless",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whose",
}

CLOSING_PUNCTUATION = {
    ",",
    ";",
    ":",
    ")",
    "]",
    "}",
}

TERMINAL_PUNCTUATION = {
    ".",
    "!",
    "?",
    '"',
    "'",
    "”",
    "’",
    ")",
    "]",
    "}",
}

EVALUATOR_INSTRUCTIONS = """
You evaluate the overall quality of a document chunk.

The previous and next chunks are provided only to help identify bad chunk
boundaries. Evaluate the TARGET CHUNK itself.

Return:

1. score
An integer from 1 to 5.

5 = excellent:
The chunk is coherent, self-contained, focused, and starts and ends naturally.

4 = good:
The chunk is useful and mostly self-contained, with one minor issue.

3 = usable:
The chunk contains useful information but has a meaningful problem, such as
missing context, a weak boundary, or multiple loosely connected topics.

2 = poor:
The chunk is difficult to understand, badly split, or strongly dependent on
neighboring chunks.

1 = unusable:
The chunk is empty, meaningless, severely incomplete, or cannot function as
a useful retrieval unit.

2. reason
Give exactly one short sentence explaining the most important reason for the
score. Keep it under 25 words.

3. suggestion
Give exactly one short actionable sentence explaining how to improve the
chunk. Keep it under 25 words.

Do not provide multiple scores.
Do not provide a long explanation.
Do not generate questions.
Do not repeat the entire chunk.
"""


# ============================================================
# Utility functions
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def calculate_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_tokenizer(model: str) -> Any:
    """
    Try the tokenizer associated with the selected model.

    If the installed tiktoken version does not recognize the model,
    fall back to o200k_base.
    """

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str, tokenizer: Any) -> int:
    return len(tokenizer.encode(text))


def normalized_words(text: str) -> list[str]:
    return re.findall(r"\b[a-z0-9']+\b", text.lower())


def first_word(text: str) -> str:
    words = normalized_words(text)
    return words[0] if words else ""


def starts_with_lowercase(text: str) -> bool:
    for character in text.lstrip():
        if character.isalpha():
            return character.islower()

    return False


def starts_with_closing_punctuation(text: str) -> bool:
    stripped = text.lstrip()

    return bool(stripped) and stripped[0] in CLOSING_PUNCTUATION


def ends_with_terminal_punctuation(text: str) -> bool:
    stripped = text.rstrip()

    return bool(stripped) and stripped[-1] in TERMINAL_PUNCTUATION


def contains_incomplete_trailing_clause(text: str) -> bool:
    stripped = text.strip().lower()

    if not stripped:
        return True

    cleaned = re.sub(r"[^\w\s]", "", stripped)
    words = cleaned.split()

    if not words:
        return True

    return words[-1] in TRAILING_CLAUSE_WORDS


def cosine_similarity(text_a: str, text_b: str) -> float:
    """
    Calculate lexical cosine similarity using word-frequency vectors.

    This is useful for detecting unusually high duplication or overlap
    between adjacent chunks. It is not embedding similarity.
    """

    words_a = normalized_words(text_a)
    words_b = normalized_words(text_b)

    if not words_a or not words_b:
        return 0.0

    frequencies_a = Counter(words_a)
    frequencies_b = Counter(words_b)

    shared_words = set(frequencies_a) & set(frequencies_b)

    dot_product = sum(
        frequencies_a[word] * frequencies_b[word]
        for word in shared_words
    )

    magnitude_a = math.sqrt(
        sum(value * value for value in frequencies_a.values())
    )
    magnitude_b = math.sqrt(
        sum(value * value for value in frequencies_b.values())
    )

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return round(
        dot_product / (magnitude_a * magnitude_b),
        4,
    )


def make_neighbor_excerpt(
    text: str | None,
    maximum_characters: int = 1500,
) -> str:
    """
    Neighbor chunks are shortened to control evaluator input size.

    The complete target chunk is always retained.
    """

    if text is None:
        return "[No neighboring chunk]"

    if len(text) <= maximum_characters:
        return text

    half = maximum_characters // 2

    return (
        text[:half]
        + "\n...[neighbor excerpt shortened]...\n"
        + text[-half:]
    )


def safe_mean(values: list[int | float]) -> float | None:
    if not values:
        return None

    return round(float(statistics.mean(values)), 4)


def calculate_rate(flags: list[bool]) -> float:
    if not flags:
        return 0.0

    return round(sum(flags) / len(flags), 4)


# ============================================================
# JSONL loading
# ============================================================

def load_chunks(path: Path) -> list[InputChunk]:
    if not path.exists():
        raise SystemExit(f"Input file not found: {path}")

    if not path.is_file():
        raise SystemExit(f"Input path is not a file: {path}")

    chunks: list[InputChunk] = []
    seen_chunk_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()

            if not stripped:
                continue

            try:
                raw_chunk = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise SystemExit(
                    f"Invalid JSON on line {line_number}: "
                    f"{error.msg}"
                ) from error

            try:
                chunk = InputChunk.model_validate(raw_chunk)
            except ValidationError as error:
                raise SystemExit(
                    f"Invalid chunk on line {line_number}:\n{error}"
                ) from error

            if chunk.chunk_id in seen_chunk_ids:
                raise SystemExit(
                    f"Duplicate chunk_id on line {line_number}: "
                    f"{chunk.chunk_id}"
                )

            seen_chunk_ids.add(chunk.chunk_id)
            chunks.append(chunk)

    if not chunks:
        raise SystemExit(f"No chunks were found in {path}")

    return chunks


# ============================================================
# Deterministic evaluation
# ============================================================

def evaluate_deterministically(
    chunk: InputChunk,
    previous_chunk: InputChunk | None,
    next_chunk: InputChunk | None,
    tokenizer: Any,
    minimum_tokens: int | None,
    maximum_tokens: int | None,
) -> DeterministicEvaluation:
    token_count = count_tokens(chunk.text, tokenizer)
    words = normalized_words(chunk.text)

    previous_similarity = (
        cosine_similarity(previous_chunk.text, chunk.text)
        if previous_chunk is not None
        else None
    )

    next_similarity = (
        cosine_similarity(chunk.text, next_chunk.text)
        if next_chunk is not None
        else None
    )

    return DeterministicEvaluation(
        character_count=len(chunk.text),
        word_count=len(words),
        token_count=token_count,
        starts_with_lowercase=starts_with_lowercase(chunk.text),
        starts_with_continuation_word=(
            first_word(chunk.text) in CONTINUATION_WORDS
        ),
        starts_with_closing_punctuation=(
            starts_with_closing_punctuation(chunk.text)
        ),
        ends_with_terminal_punctuation=(
            ends_with_terminal_punctuation(chunk.text)
        ),
        contains_incomplete_trailing_clause=(
            contains_incomplete_trailing_clause(chunk.text)
        ),
        previous_chunk_similarity=previous_similarity,
        next_chunk_similarity=next_similarity,
        below_min_tokens=(
            minimum_tokens is not None
            and token_count < minimum_tokens
        ),
        above_max_tokens=(
            maximum_tokens is not None
            and token_count > maximum_tokens
        ),
        near_empty=token_count < 10,
    )


# ============================================================
# OpenAI evaluation
# ============================================================

def evaluate_with_openai(
    client: OpenAI,
    model: str,
    chunk: InputChunk,
    previous_chunk: InputChunk | None,
    next_chunk: InputChunk | None,
    maximum_retries: int,
) -> ChunkLLMEvaluation:
    evaluator_input = f"""
PREVIOUS CHUNK
--------------
{make_neighbor_excerpt(
    previous_chunk.text if previous_chunk is not None else None
)}

TARGET CHUNK
------------
{chunk.text}

NEXT CHUNK
----------
{make_neighbor_excerpt(
    next_chunk.text if next_chunk is not None else None
)}
"""

    last_error: Exception | None = None

    for attempt in range(maximum_retries + 1):
        try:
            response = client.responses.parse(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": EVALUATOR_INSTRUCTIONS,
                    },
                    {
                        "role": "user",
                        "content": evaluator_input,
                    },
                ],
                text_format=ChunkLLMEvaluation,
            )

            parsed = response.output_parsed

            if parsed is None:
                raise RuntimeError(
                    "OpenAI returned no parsed evaluation result."
                )

            return parsed

        except Exception as error:
            last_error = error

            if attempt >= maximum_retries:
                break

            sleep_seconds = 2 ** (attempt + 1)
            time.sleep(sleep_seconds)

    raise RuntimeError(
        f"OpenAI evaluation failed after "
        f"{maximum_retries + 1} attempt(s): {last_error}"
    )


# ============================================================
# Summary calculation
# ============================================================

def summarize_results(
    model: str,
    results: list[ChunkEvaluationResult],
) -> EvaluationSummary:
    deterministic_results = [
        result.deterministic
        for result in results
    ]

    successful_llm_results = [
        result.llm
        for result in results
        if result.llm is not None
    ]

    token_counts = [
        result.token_count
        for result in deterministic_results
    ]

    adjacent_similarities = [
        result.next_chunk_similarity
        for result in deterministic_results
        if result.next_chunk_similarity is not None
    ]

    llm_scores = [
        result.score
        for result in successful_llm_results
    ]

    invalid_start_flags = [
        (
            result.starts_with_lowercase
            or result.starts_with_continuation_word
            or result.starts_with_closing_punctuation
        )
        for result in deterministic_results
    ]

    invalid_ending_flags = [
        (
            not result.ends_with_terminal_punctuation
            or result.contains_incomplete_trailing_clause
        )
        for result in deterministic_results
    ]

    successful_count = len(successful_llm_results)

    failed_count = sum(
        result.error is not None
        for result in results
    )

    return EvaluationSummary(
        model=model,
        chunk_count=len(results),
        successful_count=successful_count,
        failed_count=failed_count,

        total_characters=sum(
            result.character_count
            for result in deterministic_results
        ),

        total_tokens=sum(token_counts),

        average_tokens=round(
            float(statistics.mean(token_counts)),
            4,
        ),

        median_tokens=round(
            float(statistics.median(token_counts)),
            4,
        ),

        token_standard_deviation=round(
            float(statistics.pstdev(token_counts)),
            4,
        ),

        minimum_tokens=min(token_counts),
        maximum_tokens=max(token_counts),

        below_min_token_rate=calculate_rate(
            [
                result.below_min_tokens
                for result in deterministic_results
            ]
        ),

        above_max_token_rate=calculate_rate(
            [
                result.above_max_tokens
                for result in deterministic_results
            ]
        ),

        invalid_start_rate=calculate_rate(
            invalid_start_flags
        ),

        invalid_ending_rate=calculate_rate(
            invalid_ending_flags
        ),

        average_adjacent_similarity=safe_mean(
            adjacent_similarities
        ),

        average_score=safe_mean(
            llm_scores
        ),
    )


# ============================================================
# Output
# ============================================================

def save_results(
    output_path: Path,
    input_path: Path,
    minimum_tokens: int | None,
    maximum_tokens: int | None,
    summary: EvaluationSummary,
    results: list[ChunkEvaluationResult],
) -> None:
    output = EvaluationOutput(
        input_file=str(input_path),
        evaluated_at=utc_now(),
        minimum_tokens=minimum_tokens,
        maximum_tokens=maximum_tokens,
        summary=summary,
        chunks=results,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            output.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def format_optional_score(
    label: str,
    value: float | None,
    suffix: str = "",
) -> str:
    formatted = "N/A" if value is None else f"{value:.2f}{suffix}"
    return f"{label:<34}{formatted}"


def format_summary(summary: EvaluationSummary) -> str:
    lines: list[str] = [
        "",
        "Chunk evaluation complete",
        "=" * 62,
        f"{'Model:':<34}{summary.model}",
        f"{'Chunks:':<34}{summary.chunk_count}",
        (
            f"{'Successful LLM evaluations:':<34}"
            f"{summary.successful_count}"
        ),
        (
            f"{'Failed LLM evaluations:':<34}"
            f"{summary.failed_count}"
        ),
        "-" * 62,
        f"{'Total tokens:':<34}{summary.total_tokens}",
        f"{'Average tokens:':<34}{summary.average_tokens:.2f}",
        f"{'Median tokens:':<34}{summary.median_tokens:.2f}",
        (
            f"{'Token standard deviation:':<34}"
            f"{summary.token_standard_deviation:.2f}"
        ),
        f"{'Minimum tokens:':<34}{summary.minimum_tokens}",
        f"{'Maximum tokens:':<34}{summary.maximum_tokens}",
        "-" * 62,
        (
            f"{'Below minimum token rate:':<34}"
            f"{summary.below_min_token_rate:.1%}"
        ),
        (
            f"{'Above maximum token rate:':<34}"
            f"{summary.above_max_token_rate:.1%}"
        ),
        (
            f"{'Likely invalid start rate:':<34}"
            f"{summary.invalid_start_rate:.1%}"
        ),
        (
            f"{'Likely invalid ending rate:':<34}"
            f"{summary.invalid_ending_rate:.1%}"
        ),
    ]

    if summary.average_adjacent_similarity is not None:
        lines.append(
            f"{'Average adjacent similarity:':<34}"
            f"{summary.average_adjacent_similarity:.3f}"
        )

    lines.extend(
        [
            "-" * 62,
            format_optional_score(
                "Average chunk score:",
                summary.average_score,
                "/5",
            ),
        ]
    )

    return "\n".join(lines)

def save_summary_report(
    summary_path: Path,
    summary_text: str,
) -> None:
    summary_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_path.write_text(
        summary_text + "\n",
        encoding="utf-8",
    )

# ============================================================
# CLI
# ============================================================

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate chunks from a JSONL file using deterministic checks "
            "and optional OpenAI LLM scoring."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Path to the input chunks.jsonl file.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("chunk_evaluation_results.json"),
        help=(
            "Output JSON path. "
            "Default: chunk_evaluation_results.json"
        ),
    )

    parser.add_argument(
        "--model",
        default=None,
        help=(
            "OpenAI model. Defaults to OPENAI_MODEL from .env. "
            "OPENAI_MODEL must be set when this argument is omitted."
        ),
    )

    parser.add_argument(
        "--min-tokens",
        type=int,
        default=None,
        help="Minimum desired token count for each chunk.",
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Maximum desired token count for each chunk.",
    )

    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Run deterministic checks without calling OpenAI.",
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximum retries for each OpenAI request. Default: 2.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate only the first N chunks.",
    )

    return parser.parse_args()


def validate_arguments(arguments: argparse.Namespace) -> None:
    if arguments.min_tokens is not None and arguments.min_tokens < 0:
        raise SystemExit("--min-tokens cannot be negative.")

    if arguments.max_tokens is not None and arguments.max_tokens < 1:
        raise SystemExit("--max-tokens must be at least 1.")

    if (
        arguments.min_tokens is not None
        and arguments.max_tokens is not None
        and arguments.min_tokens > arguments.max_tokens
    ):
        raise SystemExit(
            "--min-tokens cannot be greater than --max-tokens."
        )

    if arguments.limit is not None and arguments.limit < 1:
        raise SystemExit("--limit must be at least 1.")

    if arguments.max_retries < 0:
        raise SystemExit("--max-retries cannot be negative.")


# ============================================================
# Main execution
# ============================================================

def main() -> None:
    load_dotenv()

    arguments = parse_arguments()
    validate_arguments(arguments)

    evals_directory = Path(__file__).resolve().parent
    reports_directory = evals_directory / "reports"

    reports_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    chunks = load_chunks(arguments.input)

    if arguments.limit is not None:
        chunks = chunks[:arguments.limit]

    rows_evaluated = len(chunks)

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    if arguments.output is not None:
        supplied_path = Path(arguments.output.name)

        output_filename = (
            f"{supplied_path.stem}"
            f"_rows-{rows_evaluated}"
            f"_{timestamp}"
            f"{supplied_path.suffix or '.json'}"
        )
    else:
        output_filename = (
            f"{arguments.input.stem}"
            f"_evaluation"
            f"_rows-{rows_evaluated}"
            f"_{timestamp}.json"
        )

    output_path = reports_directory / output_filename

    print(f"Input file:  {arguments.input.resolve()}")
    print(f"Rows:        {rows_evaluated}")
    print(f"Output file: {output_path.resolve()}")

    model = arguments.model or os.getenv("OPENAI_MODEL")

    if not model:
        raise SystemExit(
            "No OpenAI model was provided. Add OPENAI_MODEL to .env "
            "or pass --model."
        )

    tokenizer = get_tokenizer(model)

    client: OpenAI | None = None

    if not arguments.skip_llm:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise SystemExit(
                "OPENAI_API_KEY is missing. Add it to your .env file."
            )

        client = OpenAI(api_key=api_key)

    results: list[ChunkEvaluationResult] = []

    for index, chunk in enumerate(chunks):
        previous_chunk = (
            chunks[index - 1]
            if index > 0
            else None
        )

        next_chunk = (
            chunks[index + 1]
            if index + 1 < len(chunks)
            else None
        )

        print(
            f"Evaluating {index + 1}/{len(chunks)}: "
            f"{chunk.chunk_id}"
        )

        deterministic_result = evaluate_deterministically(
            chunk=chunk,
            previous_chunk=previous_chunk,
            next_chunk=next_chunk,
            tokenizer=tokenizer,
            minimum_tokens=arguments.min_tokens,
            maximum_tokens=arguments.max_tokens,
        )

        llm_result: ChunkLLMEvaluation | None = None
        error_message: str | None = None

        if client is not None:
            try:
                llm_result = evaluate_with_openai(
                    client=client,
                    model=model,
                    chunk=chunk,
                    previous_chunk=previous_chunk,
                    next_chunk=next_chunk,
                    maximum_retries=arguments.max_retries,
                )

                print(f"  Score:      {llm_result.score}/5")
                print(f"  Reason:     {llm_result.reason}")
                print(f"  Suggestion: {llm_result.suggestion}")

            except Exception as error:
                error_message = str(error)
                print(f"  Warning: {error_message}")

        result = ChunkEvaluationResult(
            chunk_id=chunk.chunk_id,
            chunk_index=index,
            text=chunk.text,
            content_hash=calculate_content_hash(chunk.text),
            deterministic=deterministic_result,
            llm=llm_result,
            error=error_message,
        )

        results.append(result)

    summary = summarize_results(
        model=model,
        results=results,
    )

    save_results(
        output_path=output_path,
        input_path=arguments.input,
        minimum_tokens=arguments.min_tokens,
        maximum_tokens=arguments.max_tokens,
        summary=summary,
        results=results,
    )

    summary_text = format_summary(summary)

    # Show the summary in the terminal.
    print(summary_text)

    # Save the same terminal summary as a text file.
    summary_path = output_path.with_name(
        f"{output_path.stem}_summary.txt"
    )

    save_summary_report(
        summary_path=summary_path,
        summary_text=summary_text,
    )

    print()
    print(f"JSON results written to: {output_path.resolve()}")
    print(f"Summary report written to: {summary_path.resolve()}")


if __name__ == "__main__":
    main()