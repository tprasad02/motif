"""Precompute semantic evidence plans for published, selectable film lenses.

Run this offline after rebuilding lens profiles. The web service uses the
resulting small JSON artifact and never loads Sentence-BERT/PyTorch.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "backend" / "app" / "corpus" / "lens_profiles.json"
CHUNK_PATH = ROOT / "backend" / "app" / "corpus" / "chunks.jsonl"
OUTPUT_PATH = ROOT / "backend" / "app" / "corpus" / "retrieval_plans.json"

ROLE_PRIORITY = {"screenplay": 4, "creator_voice": 4, "scholarship": 3, "production_context": 2, "criticism": 1}
CHUNK_PRIORITY = {"scene_evidence": 4, "formal_observation": 3, "creator_commentary": 3, "interpretive_claim": 2, "plot_summary": 1}


def published(row: dict) -> bool:
    review = row.get("review") or {}
    return row.get("status") == "published" and all(review.get(metric, 0) >= 4 for metric in ("faithfulness", "answer_relevance", "satisfaction"))


def select_diverse(rows: list[dict], scores: list[float], limit: int = 12) -> list[str]:
    ranked = [row for _, row in sorted(zip(scores, rows), key=lambda pair: pair[0], reverse=True)]
    selected: list[dict] = []
    roles: set[str] = set()
    source_counts: dict[str, int] = defaultdict(int)
    for row in ranked:
        if len(selected) >= limit:
            break
        role = str(row.get("source_role") or "criticism")
        source = str(row.get("source_key") or "")
        if source_counts[source] >= 2:
            continue
        # Guarantee source-role diversity early, then preserve semantic rank.
        if len(selected) < 5 and role in roles and any(str(item.get("source_role")) not in roles for item in ranked):
            continue
        selected.append(row)
        roles.add(role)
        source_counts[source] += 1
    for row in ranked:
        if len(selected) >= limit:
            break
        if row not in selected and source_counts[str(row.get("source_key") or "")] < 2:
            selected.append(row)
            source_counts[str(row.get("source_key") or "")] += 1
    return [str(row["chunk_id"]) for row in selected]


def main() -> None:
    from sentence_transformers import SentenceTransformer

    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    chunks_by_film: dict[str, list[dict]] = defaultdict(list)
    for line in CHUNK_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("quality_score") != "low":
            chunks_by_film[str(row["film_slug"])].append(row)

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", local_files_only=True)
    output: dict[str, object] = {"version": 1, "embedding_model": "sentence-transformers/all-MiniLM-L6-v2", "films": {}}
    for slug, film in profiles.get("films", {}).items():
        rows = chunks_by_film.get(slug, [])
        if not rows:
            continue
        chunk_vectors = model.encode([str(row.get("text", ""))[:1800] for row in rows], normalize_embeddings=True, batch_size=64)
        plans = []
        for profile in film.get("lenses", []):
            if not published(profile):
                continue
            query = f"{profile.get('lens', '')}. {profile.get('definition', '')}"
            query_vector = model.encode(query, normalize_embeddings=True)
            scores = [float(query_vector @ vector) for vector in chunk_vectors]
            aliases = [str(profile.get("lens", ""))]
            if profile.get("cluster_label"):
                aliases.append(str(profile["cluster_label"]))
            plans.append({"aliases": list(dict.fromkeys(alias for alias in aliases if alias)), "chunk_ids": select_diverse(rows, scores)})
        output["films"][slug] = plans
        print(f"{slug}: {len(plans)} plans", flush=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"plans={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
