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

def _normalized_lens(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))

def _contains_lens(left: str, right: str) -> bool:
    return left == right or f" {left} " in f" {right} " or f" {right} " in f" {left} "

def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain the shorter canonical name when labels are lexical duplicates."""
    selected: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (len(_normalized_lens(item.get("lens"))), _normalized_lens(item.get("lens")))):
        name = _normalized_lens(row.get("lens"))
        if name and not any(_contains_lens(name, _normalized_lens(existing.get("lens"))) for existing in selected):
            selected.append(row)
    return selected

def load_profiles() -> dict[str, Any]:
    try:
        value = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return value if value.get("version") == PROFILE_SCHEMA_VERSION else {"films": {}}
    except (OSError, json.JSONDecodeError): return {"films": {}}

def reload_profiles() -> None:
    """Compatibility hook; profile files are re-read on every request."""
    _profile_embedding.cache_clear()
    _label_embedding.cache_clear()

def _valid(row: dict[str, Any]) -> bool:
    review = row.get("review") or {}
    words = {word.lower() for word in re.findall(r"[A-Za-z]+", f"{row.get('lens', '')} {row.get('definition', '')}")}
    return (row.get("status") == "published" and 1 <= len(str(row.get("lens", "")).split()) <= 3
        and not (words & NON_THEME_TERMS)
        and len(row.get("supporting_chunk_ids") or []) >= 3 and len(set(row.get("source_roles") or [])) >= 2
        and review.get("faithfulness", 0) >= 4 and review.get("answer_relevance", 0) >= 4
        and review.get("satisfaction", 0) >= 4 and not any((review.get("deterministic_failures") or {}).values()))

def published_lenses(film_slug: str) -> list[dict[str, Any]]:
    rows = [row for row in (load_profiles().get("films", {}).get(film_slug) or {}).get("lenses", []) if _valid(row)]
    return _dedupe_rows(rows)

def lens_names(film_slug: str) -> list[str]: return [str(row["lens"]) for row in published_lenses(film_slug)]
def is_published_lens(film_slug: str, lens: str) -> bool: return lens in lens_names(film_slug)
def all_published_lenses() -> list[str]:
    rows = [{"lens": lens} for slug in load_profiles().get("films", {}) for lens in lens_names(slug)]
    selected: list[str] = []
    for row in _dedupe_rows(rows):
        lens = str(row["lens"])
        vector = _label_embedding(lens)
        if any(sum(a * b for a, b in zip(vector, _label_embedding(existing))) >= 0.85 for existing in selected):
            continue
        selected.append(lens)
    return sorted(selected, key=str.casefold)

@lru_cache(maxsize=512)
def _profile_embedding(lens: str, definition: str) -> tuple[float, ...]:
    """Cache profile vectors: validation compares the same profiles many times."""
    return tuple(local_embedding(f"{lens}. {definition}"))

@lru_cache(maxsize=128)
def _label_embedding(lens: str) -> tuple[float, ...]:
    return tuple(local_embedding(lens))

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
    selected: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: item["similarity"], reverse=True):
        duplicate = any(
            _contains_lens(_normalized_lens(row["film_a_lens"]), _normalized_lens(existing["film_a_lens"]))
            or _contains_lens(_normalized_lens(row["film_b_lens"]), _normalized_lens(existing["film_b_lens"]))
            for existing in selected
        )
        if not duplicate:
            selected.append(row)
    return selected

def shared_lenses(film_a: str, film_b: str) -> list[str]: return [str(row["lens"]) for row in comparison_lenses(film_a, film_b)]
def is_comparison_lens(film_a: str, film_b: str, lens: str) -> bool: return lens in shared_lenses(film_a, film_b)
