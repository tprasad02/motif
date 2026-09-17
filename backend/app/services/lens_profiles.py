"""Evidence-gated film lenses and semantic comparison matching."""
from __future__ import annotations
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from app.services.embeddings import local_embedding

PROFILE_PATH = Path(__file__).resolve().parents[1] / "corpus" / "lens_profiles.json"
PROFILE_SCHEMA_VERSION = 4
COMPARISON_SIMILARITY = 0.56
NON_THEME_TERMS = {"genre", "horror", "thriller", "noir", "comedy", "drama", "cinematic", "cinema", "visual", "style", "stylistic", "aesthetic", "aesthetics", "narrative", "storytelling", "structure", "technique", "techniques", "editing", "cinematography", "format", "spectator", "audience", "realism", "surrealism", "postmodern", "literary", "allusion", "symbolism", "symbolic", "mythic", "mythical", "temporal", "displacement", "resonance"}

@lru_cache(maxsize=1)
def load_profiles() -> dict[str, Any]:
    try:
        value = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return value if value.get("version") == PROFILE_SCHEMA_VERSION else {"films": {}}
    except (OSError, json.JSONDecodeError): return {"films": {}}

def reload_profiles() -> None:
    load_profiles.cache_clear()
    _profile_embedding.cache_clear()

def _valid(row: dict[str, Any]) -> bool:
    review = row.get("review") or {}
    words = {word.lower() for word in re.findall(r"[A-Za-z]+", f"{row.get('lens', '')} {row.get('definition', '')}")}
    return (row.get("status") == "published" and 1 <= len(str(row.get("lens", "")).split()) <= 3
        and not (words & NON_THEME_TERMS)
        and len(row.get("supporting_chunk_ids") or []) >= 3 and len(set(row.get("source_roles") or [])) >= 2
        and review.get("faithfulness", 0) >= 4 and review.get("answer_relevance", 0) >= 4
        and review.get("satisfaction", 0) >= 4 and not any((review.get("deterministic_failures") or {}).values()))

def published_lenses(film_slug: str) -> list[dict[str, Any]]:
    return [row for row in (load_profiles().get("films", {}).get(film_slug) or {}).get("lenses", []) if _valid(row)]

def lens_names(film_slug: str) -> list[str]: return [str(row["lens"]) for row in published_lenses(film_slug)]
def is_published_lens(film_slug: str, lens: str) -> bool: return lens in lens_names(film_slug)
def all_published_lenses() -> list[str]: return sorted({lens for slug in load_profiles().get("films", {}) for lens in lens_names(slug)})

@lru_cache(maxsize=512)
def _profile_embedding(lens: str, definition: str) -> tuple[float, ...]:
    """Cache profile vectors: validation compares the same profiles many times."""
    return tuple(local_embedding(f"{lens}. {definition}"))

def selected_profile_terms(film_slug: str, selection: str) -> list[str]:
    """Terms for a film lens or a semantic comparison label."""
    terms = [selection]
    paired_names = {part.strip() for part in selection.split(" / ")}
    for row in published_lenses(film_slug):
        if row.get("lens") == selection or row.get("cluster_label") == selection or row.get("lens") in paired_names:
            terms.extend([str(row.get("lens", "")), str(row.get("definition", ""))])
    return [term for term in terms if term]

def comparison_lenses(film_a: str, film_b: str, threshold: float = COMPARISON_SIMILARITY) -> list[dict[str, Any]]:
    rows = []
    for left in published_lenses(film_a):
        left_vector = _profile_embedding(str(left.get("lens", "")), str(left.get("definition", "")))
        for right in published_lenses(film_b):
            same_cluster = bool(left.get("cluster_id") and left.get("cluster_id") == right.get("cluster_id"))
            right_vector = _profile_embedding(str(right.get("lens", "")), str(right.get("definition", "")))
            score = 1.0 if same_cluster else sum(a * b for a, b in zip(left_vector, right_vector))
            if score >= threshold:
                label = (left.get("cluster_label") if same_cluster else None) or (right.get("cluster_label") if same_cluster else None) or f"{left['lens']} / {right['lens']}"
                rows.append({"lens": label, "similarity": round(score, 3), "film_a_lens": left["lens"], "film_b_lens": right["lens"]})
    return sorted(rows, key=lambda row: row["similarity"], reverse=True)

def shared_lenses(film_a: str, film_b: str) -> list[str]: return [str(row["lens"]) for row in comparison_lenses(film_a, film_b)]
def is_comparison_lens(film_a: str, film_b: str, lens: str) -> bool: return lens in shared_lenses(film_a, film_b)
