"""Verify that selectable lens profiles meet Motif's publication contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.film_config import FILM_TITLES
from app.services.lens_profiles import comparison_lenses, reload_profiles


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", default="backend/app/corpus/lens_profiles.json")
    parser.add_argument("--min-comparisons-per-film", type=int, default=2)
    args = parser.parse_args()
    payload = json.loads(Path(args.profiles).read_text(encoding="utf-8"))
    failures: list[str] = []
    if payload.get("version") != 4:
        failures.append("profiles must use schema version 4")
    minimum, maximum = 3, 5
    film_lenses: dict[str, list[dict]] = {}
    for slug in FILM_TITLES:
        rows = (payload.get("films", {}).get(slug) or {}).get("lenses", [])
        published = []
        for row in rows:
            review = row.get("review") or {}
            valid = (
                row.get("status") == "published"
                and 1 <= len(str(row.get("lens", "")).split()) <= 3
                and len(row.get("supporting_chunk_ids") or []) >= 3
                and len(set(row.get("source_roles") or [])) >= 2
                and review.get("faithfulness", 0) >= 4
                and review.get("answer_relevance", 0) >= 4
                and review.get("satisfaction", 0) >= 4
                and not any((review.get("deterministic_failures") or {}).values())
                and bool(row.get("cluster_id")) and bool(row.get("cluster_label"))
            )
            if valid:
                published.append(row)
        if len(published) < minimum:
            failures.append(f"{slug}: {len(published)}/{minimum} passing profiles")
        if len(published) > maximum:
            failures.append(f"{slug}: {len(published)}/{maximum} profiles exceeds the publication maximum")
        film_lenses[slug] = published

    # Each film must have two distinct BERT-backed comparison partners.
    reload_profiles()
    comparisons = {
        slug: [other for other in FILM_TITLES if other != slug and comparison_lenses(slug, other)]
        for slug in FILM_TITLES
    }
    for slug, related in comparisons.items():
        if len(related) < args.min_comparisons_per_film:
            failures.append(f"{slug}: {len(related)}/{args.min_comparisons_per_film} semantic comparison partners")

    if failures:
        print("Lens-profile validation failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        raise SystemExit(1)
    print(f"passing_profiles={sum(len(values) for values in film_lenses.values())}")
    print(f"Every active film has {minimum}-{maximum} passing profiles and at least {args.min_comparisons_per_film} BERT-backed comparison partners.")


if __name__ == "__main__":
    main()
