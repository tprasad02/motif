"""Precompute evidence-backed Sentence-BERT comparison matches.

This keeps semantic comparison broad enough for users without loading the
Sentence-BERT/PyTorch runtime in the production web service.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = ROOT / "backend/app/corpus/lens_profiles.json"
DEFAULT_OUTPUT = ROOT / "backend/app/corpus/comparison_matches.json"
MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _valid(row: dict) -> bool:
    review = row.get("review") or {}
    return (
        row.get("status") == "published"
        and len(row.get("supporting_chunk_ids") or []) >= 3
        and len(set(row.get("source_roles") or [])) >= 2
        and review.get("faithfulness", 0) >= 4
        and review.get("answer_relevance", 0) >= 4
        and review.get("satisfaction", 0) >= 4
        and not any((review.get("deterministic_failures") or {}).values())
    )


def _key(left: str, right: str) -> str:
    return "::".join(sorted((left, right)))


def _comparison_label(left: dict, right: dict) -> str:
    if left.get("cluster_id") and left.get("cluster_id") == right.get("cluster_id"):
        return str(left.get("cluster_label") or right.get("cluster_label") or left["lens"])
    # Preserve both evidence-backed film-specific labels rather than inventing
    # an unsupported thematic name at runtime.
    return f"{left['lens']} / {right['lens']}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--threshold", type=float, default=0.60)
    args = parser.parse_args()

    payload = json.loads(args.profiles.read_text(encoding="utf-8"))
    rows = [
        (slug, row)
        for slug, film in payload.get("films", {}).items()
        for row in film.get("lenses", [])
        if _valid(row)
    ]
    if not rows:
        raise SystemExit("No valid published lens profiles found.")

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL, local_files_only=True)
    vectors = model.encode(
        [f"{row['lens']}. {row.get('definition', '')}" for _, row in rows],
        normalize_embeddings=True,
    )
    matches: dict[str, list[dict]] = {}
    for left_index, (left_slug, left) in enumerate(rows):
        for right_index in range(left_index + 1, len(rows)):
            right_slug, right = rows[right_index]
            if left_slug == right_slug:
                continue
            similarity = float(vectors[left_index] @ vectors[right_index])
            shared_cluster = bool(left.get("cluster_id") and left.get("cluster_id") == right.get("cluster_id"))
            if not shared_cluster and similarity < args.threshold:
                continue
            key = _key(left_slug, right_slug)
            matches.setdefault(key, []).append(
                {
                    "lens": _comparison_label(left, right),
                    "similarity": round(1.0 if shared_cluster else similarity, 3),
                    "film_a": left_slug,
                    "film_a_lens": left["lens"],
                    "film_b": right_slug,
                    "film_b_lens": right["lens"],
                    "match_type": "cluster" if shared_cluster else "semantic",
                }
            )

    # Do not show near-duplicate choices for the same film-lens pair.
    for key, candidates in matches.items():
        chosen: list[dict] = []
        used: set[tuple[str, str]] = set()
        for candidate in sorted(candidates, key=lambda item: item["similarity"], reverse=True):
            signature = tuple(sorted((candidate["film_a_lens"].casefold(), candidate["film_b_lens"].casefold())))
            if signature not in used:
                chosen.append(candidate)
                used.add(signature)
        matches[key] = chosen[:5]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "embedding_model": MODEL,
                "similarity_threshold": args.threshold,
                "pairs": matches,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    partner_counts = {slug: 0 for slug in payload.get("films", {})}
    for key in matches:
        left_slug, right_slug = key.split("::")
        partner_counts[left_slug] += 1
        partner_counts[right_slug] += 1
    print(f"pairs={len(matches)} min_partners={min(partner_counts.values(), default=0)}")


if __name__ == "__main__":
    main()
