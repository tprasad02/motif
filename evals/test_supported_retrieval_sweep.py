import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.film_config import FILM_LENSES, FILM_TITLES, PRIMARY_LENSES, expand_film_lens_terms
from app.services.retrieval import retrieve_chunks
from evals.utilities import get_current_time_string


CONCRETE_ROLES = {"scene_evidence", "formal_observation", "creator_commentary", "interpretive_claim"}
PLOT_ROLE = "plot_summary"


def lens_matches(chunk, lens: str) -> bool:
    expanded = [term.lower() for term in expand_film_lens_terms(chunk.film_slug, lens)]
    lowered = lens.lower()
    lens_tags = [tag.lower() for tag in (chunk.lens_tags or [])]
    text = chunk.text.lower()
    parts = [
        part.strip()
        for term in [lowered, *expanded]
        for part in re.split(r"\s+vs\.?\s+|\s+and\s+", term)
        if len(part.strip()) >= 4
    ]
    return (
        any(term in lens_tags or term in text for term in expanded if len(term) >= 4)
        or lowered in lens_tags
        or lowered in text
        or any(part in lens_tags or part in text for part in parts)
    )


def query_for_pair(film_slug: str, lens: str) -> str:
    title = FILM_TITLES.get(film_slug, film_slug)
    related = " ".join(FILM_LENSES.get(film_slug, []))
    expanded = " ".join(expand_film_lens_terms(film_slug, lens))
    return f"Analyze {title}. Lens focus: {lens}. Related search terms: {expanded}. Available lenses: {related}."


def evaluate_pair(film_slug: str, lens: str, top_k: int) -> dict:
    chunks = retrieve_chunks(
        query=query_for_pair(film_slug, lens),
        film_slugs=[film_slug],
        source_types=[],
        limit=top_k,
        lens_tags=[lens],
    )
    chunk_count = len(chunks) or 1
    film_match_count = sum(1 for chunk in chunks if chunk.film_slug == film_slug)
    lens_match_count = sum(1 for chunk in chunks if lens_matches(chunk, lens))
    concrete_count = sum(1 for chunk in chunks if chunk.chunk_role in CONCRETE_ROLES and chunk.chunk_role != PLOT_ROLE)
    plot_summary_count = sum(1 for chunk in chunks if chunk.chunk_role == PLOT_ROLE)
    source_roles = {chunk.source_role for chunk in chunks if chunk.source_role}
    source_keys = {chunk.source_key for chunk in chunks if chunk.source_key}
    chunk_roles = Counter(chunk.chunk_role for chunk in chunks)

    film_match_rate = film_match_count / chunk_count
    lens_match_rate = lens_match_count / chunk_count
    concrete_evidence_rate = concrete_count / chunk_count
    plot_summary_rate = plot_summary_count / chunk_count
    passed = (
        film_match_count >= min(8, len(chunks))
        and lens_match_count >= min(6, len(chunks))
        and concrete_evidence_rate >= 0.60
        and plot_summary_rate <= 0.40
        and len(source_roles) >= min(2, len(source_keys))
    )

    return {
        "id": f"{film_slug}__{lens.lower().replace(' ', '_').replace('/', '_')}",
        "film_slug": film_slug,
        "film_title": FILM_TITLES.get(film_slug, film_slug),
        "lens": lens,
        "lens_scope": "primary" if lens in PRIMARY_LENSES else "secondary",
        "chunk_count": len(chunks),
        "film_match_rate": round(film_match_rate, 3),
        "lens_match_rate": round(lens_match_rate, 3),
        "concrete_evidence_rate": round(concrete_evidence_rate, 3),
        "plot_summary_rate": round(plot_summary_rate, 3),
        "source_diversity": len(source_keys),
        "source_role_diversity": len(source_roles),
        "source_roles": "|".join(sorted(source_roles)),
        "chunk_roles": json.dumps(dict(chunk_roles), sort_keys=True),
        "overall": "pass" if passed else "fail",
        "top_chunks": [
            {
                "rank": index + 1,
                "chunk_id": chunk.chunk_id,
                "source_key": chunk.source_key,
                "source_role": chunk.source_role,
                "chunk_role": chunk.chunk_role,
                "lens_tags": chunk.lens_tags or [],
                "score": round(chunk.score, 4),
            }
            for index, chunk in enumerate(chunks)
        ],
    }


def main() -> None:
    timestamp = get_current_time_string()
    parser = argparse.ArgumentParser(description="Cheap retrieval sweep for all supported Motif film-lens pairs.")
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--scope", choices=["primary", "secondary", "all"], default="primary")
    parser.add_argument("--output", default=None)
    parser.add_argument("--json-output", default=None)
    args = parser.parse_args()

    pairs = [(film_slug, lens) for film_slug, lenses in FILM_LENSES.items() for lens in lenses]
    if args.scope == "primary":
        pairs = [(film_slug, lens) for film_slug, lens in pairs if lens in PRIMARY_LENSES]
    elif args.scope == "secondary":
        pairs = [(film_slug, lens) for film_slug, lens in pairs if lens not in PRIMARY_LENSES]
    if args.limit is not None:
        pairs = pairs[: args.limit]

    rows = [evaluate_pair(film_slug, lens, args.top_k) for film_slug, lens in pairs]

    csv_path = Path(args.output or f"evals/Reports/supported_retrieval_sweep_{args.scope}_{timestamp}.csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "film_slug",
        "film_title",
        "lens",
        "lens_scope",
        "chunk_count",
        "film_match_rate",
        "lens_match_rate",
        "concrete_evidence_rate",
        "plot_summary_rate",
        "source_diversity",
        "source_role_diversity",
        "source_roles",
        "chunk_roles",
        "overall",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fieldnames})

    json_path = Path(args.json_output or f"evals/Reports/supported_retrieval_sweep_{args.scope}_{timestamp}.json")
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    passed = sum(row["overall"] == "pass" for row in rows)
    print(f"supported retrieval sweep scope={args.scope} passed={passed}/{len(rows)}")
    failures = [row for row in rows if row["overall"] == "fail"]
    for row in failures[:25]:
        print(
            f"FAIL {row['film_slug']} + {row['lens']}: "
            f"lens={row['lens_match_rate']:.2f} concrete={row['concrete_evidence_rate']:.2f} "
            f"plot={row['plot_summary_rate']:.2f} roles={row['source_role_diversity']}"
        )
    if len(failures) > 25:
        print(f"...and {len(failures) - 25} more failures")
    print(f"csv={csv_path}")
    print(f"json={json_path}")


if __name__ == "__main__":
    main()
