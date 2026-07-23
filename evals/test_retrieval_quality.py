import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

from app.film_config import FILM_TITLES
from app.services.analysis import THEME_LENS_FILMS
from app.services.retrieval import retrieve_chunks


CONCRETE_ROLES = {"scene_evidence", "formal_observation", "creator_commentary", "interpretive_claim"}
PLOT_ROLE = "plot_summary"
SOURCE_SYSTEM_PATTERNS = [
    r"\baccording to\b",
    r"\bretrieved\b",
    r"\bsource\b",
    r"\bcitation\b",
    r"\bchunk\b",
    r"\bcorpus\b",
]


def load_cases(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def query_for_case(case: dict) -> str:
    mode = case["mode"]
    lens = case["lens"]
    film_a = case.get("film_a")
    film_b = case.get("film_b")
    if mode == "compare_films":
        return f"Compare {film_a} and {film_b}: {lens}"
    if mode == "explore_theme":
        return f"Explore {lens} across the film collection"
    return f"Analyze {film_a}: {lens}"


def lens_matches(chunk, lens: str) -> bool:
    lowered = lens.lower()
    lens_tags = [tag.lower() for tag in (chunk.lens_tags or [])]
    text = chunk.text.lower()
    parts = [part.strip() for part in re.split(r"\s+vs\.?\s+|\s+and\s+", lowered) if len(part.strip()) >= 4]
    return lowered in lens_tags or lowered in text or any(part in lens_tags or part in text for part in parts)


def has_concrete_evidence(chunk) -> bool:
    return chunk.chunk_role in CONCRETE_ROLES and chunk.chunk_role != PLOT_ROLE


def evaluate_retrieval_case(case: dict, top_k: int) -> dict:
    mode = case["mode"]
    lens = case["lens"]
    film_slugs = []
    if mode == "analyze_film":
        film_slugs = [case["film_a"]]
    elif mode == "compare_films":
        film_slugs = [case["film_a"], case["film_b"]]

    chunks = retrieve_chunks(
        query=query_for_case(case),
        film_slugs=film_slugs,
        source_types=[],
        limit=top_k,
        lens_tags=[lens],
    )
    film_counts = Counter(chunk.film_slug for chunk in chunks)
    source_roles = {chunk.source_role for chunk in chunks if chunk.source_role}
    chunk_roles = Counter(chunk.chunk_role for chunk in chunks)
    expected_films = set(film_slugs)
    if mode == "explore_theme":
        expected_films = set(THEME_LENS_FILMS.get(lens, []))

    film_match_count = sum(1 for chunk in chunks if not expected_films or chunk.film_slug in expected_films)
    theme_match_count = sum(1 for chunk in chunks if lens_matches(chunk, lens))
    concrete_count = sum(1 for chunk in chunks if has_concrete_evidence(chunk))
    plot_summary_count = sum(1 for chunk in chunks if chunk.chunk_role == PLOT_ROLE)
    source_system_count = sum(
        1 for chunk in chunks if any(re.search(pattern, chunk.text, flags=re.I) for pattern in SOURCE_SYSTEM_PATTERNS)
    )

    chunk_count = len(chunks) or 1
    film_match_rate = film_match_count / chunk_count
    theme_match_rate = theme_match_count / chunk_count
    concrete_evidence_rate = concrete_count / chunk_count
    plot_summary_rate = plot_summary_count / chunk_count

    comparison_balance_pass = True
    if mode == "compare_films":
        comparison_balance_pass = film_counts[case["film_a"]] >= 4 and film_counts[case["film_b"]] >= 4

    analyze_pass = True
    if mode == "analyze_film":
        analyze_pass = film_counts[case["film_a"]] >= 8

    theme_pass = True
    if mode == "explore_theme":
        returned_films = set(film_counts)
        theme_pass = bool(returned_films) and returned_films.issubset(expected_films)

    pass_rules = [
        analyze_pass,
        comparison_balance_pass,
        theme_pass,
        theme_match_count >= min(6, len(chunks)),
        plot_summary_rate <= 0.40,
        len(source_roles) >= min(2, len({chunk.source_key for chunk in chunks})),
    ]
    overall = "pass" if all(pass_rules) else "fail"

    return {
        "id": case["id"],
        "mode": mode,
        "film_a": case.get("film_a", ""),
        "film_b": case.get("film_b", ""),
        "lens": lens,
        "chunk_count": len(chunks),
        "film_match_rate": round(film_match_rate, 3),
        "theme_match_rate": round(theme_match_rate, 3),
        "concrete_evidence_rate": round(concrete_evidence_rate, 3),
        "plot_summary_rate": round(plot_summary_rate, 3),
        "source_diversity": len({chunk.source_key for chunk in chunks}),
        "source_role_diversity": len(source_roles),
        "source_roles": "|".join(sorted(source_roles)),
        "chunk_roles": json.dumps(dict(chunk_roles), sort_keys=True),
        "film_counts": json.dumps(dict(film_counts), sort_keys=True),
        "source_system_phrase_count": source_system_count,
        "comparison_balance_pass": comparison_balance_pass,
        "overall": overall,
        "top_chunks": [
            {
                "rank": index + 1,
                "chunk_id": chunk.chunk_id,
                "film": FILM_TITLES.get(chunk.film_slug, chunk.film_slug),
                "source_key": chunk.source_key,
                "chunk_role": chunk.chunk_role,
                "source_role": chunk.source_role,
                "lens_tags": chunk.lens_tags or [],
                "score": round(chunk.score, 4),
            }
            for index, chunk in enumerate(chunks)
        ],
    }


def flatten_cases(payload: dict, modes: list[str] | None = None) -> list[dict]:
    selected = []
    for group_name, cases in payload.items():
        if modes and group_name not in modes:
            continue
        selected.extend(cases)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Motif retrieval quality on benchmark cases.")
    parser.add_argument("--cases", default="evals/benchmark_cases.json")
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--modes", nargs="*", choices=["analyze", "compare", "theme"], default=None)
    parser.add_argument("--output", default="evals/Reports/retrieval_quality_results.csv")
    parser.add_argument("--json-output", default="evals/Reports/retrieval_quality_results.json")
    args = parser.parse_args()

    payload = load_cases(Path(args.cases))
    rows = [evaluate_retrieval_case(case, args.top_k) for case in flatten_cases(payload, args.modes)]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "mode",
        "film_a",
        "film_b",
        "lens",
        "chunk_count",
        "film_match_rate",
        "theme_match_rate",
        "concrete_evidence_rate",
        "plot_summary_rate",
        "source_diversity",
        "source_role_diversity",
        "source_roles",
        "chunk_roles",
        "film_counts",
        "source_system_phrase_count",
        "comparison_balance_pass",
        "overall",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fieldnames})

    json_output_path = Path(args.json_output)
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    for row in rows:
        print(
            f"{row['overall'].upper()} {row['id']}: "
            f"film_match={row['film_match_rate']:.2f} "
            f"theme_match={row['theme_match_rate']:.2f} "
            f"concrete={row['concrete_evidence_rate']:.2f} "
            f"plot={row['plot_summary_rate']:.2f} "
            f"roles={row['source_role_diversity']}"
        )

    pass_count = sum(row["overall"] == "pass" for row in rows)
    print(f"passed={pass_count}/{len(rows)}")
    print(f"csv={output_path}")
    print(f"json={json_output_path}")


if __name__ == "__main__":
    main()
