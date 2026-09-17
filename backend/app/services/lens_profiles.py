"""Evidence-gated film lenses and semantic comparison matching."""
from __future__ import annotations
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PROFILE_PATH = Path(__file__).resolve().parents[1] / "corpus" / "lens_profiles.json"
COMPARISON_MATCH_PATH = Path(__file__).resolve().parents[1] / "corpus" / "comparison_matches.json"
PROFILE_SCHEMA_VERSION = 4
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
    _comparison_matches.cache_clear()

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


def _collection_label(row: dict[str, Any]) -> str:
    return str(row.get("cluster_label") or row.get("lens") or "")


def collection_lens_profiles(selection: str) -> list[tuple[str, dict[str, Any]]]:
    """Return one strongest validated profile per film for a collection lens."""
    target = _normalized_lens(selection)
    matches: list[tuple[str, dict[str, Any]]] = []
    for slug in load_profiles().get("films", {}):
        candidates = [
            row
            for row in published_lenses(slug)
            if _normalized_lens(_collection_label(row)) == target or _normalized_lens(row.get("lens")) == target
        ]
        if not candidates:
            continue
        strongest = max(
            candidates,
            key=lambda row: (
                sum((row.get("review") or {}).get(metric, 0) for metric in ("faithfulness", "answer_relevance", "satisfaction")),
                len(row.get("source_roles") or []),
            ),
        )
        matches.append((slug, strongest))
    return matches


def all_published_lenses() -> list[str]:
    # Explore is a collection workflow, so do not offer a lens that only one
    # film supports. Cluster labels are assigned by the offline BERT pipeline.
    by_label: dict[str, set[str]] = {}
    display_labels: dict[str, str] = {}
    for slug in load_profiles().get("films", {}):
        for row in published_lenses(slug):
            label = _collection_label(row)
            normalized = _normalized_lens(label)
            if normalized:
                by_label.setdefault(normalized, set()).add(slug)
                display_labels.setdefault(normalized, label)
    return sorted(
        [display_labels[label] for label, films in by_label.items() if len(films) >= 2],
        key=str.casefold,
    )

@lru_cache(maxsize=1)
def _comparison_matches() -> dict[str, list[dict[str, Any]]]:
    try:
        payload = json.loads(COMPARISON_MATCH_PATH.read_text(encoding="utf-8"))
        return payload.get("pairs", {}) if payload.get("version") == 1 else {}
    except (OSError, json.JSONDecodeError):
        return {}

def selected_profile_terms(film_slug: str, selection: str) -> list[str]:
    """Terms for a film lens or a semantic comparison label."""
    terms = [selection]
    paired_names = {part.strip() for part in selection.split(" / ")}
    for row in published_lenses(film_slug):
        if row.get("lens") == selection or row.get("cluster_label") == selection or row.get("lens") in paired_names:
            terms.extend([str(row.get("lens", "")), str(row.get("definition", ""))])
    return [term for term in terms if term]

def comparison_lenses(film_a: str, film_b: str) -> list[dict[str, Any]]:
    key = "::".join(sorted((film_a, film_b)))
    rows = []
    for match in _comparison_matches().get(key, []):
        if match.get("film_a") == film_a:
            rows.append({key: value for key, value in match.items() if key not in {"film_a", "film_b", "match_type"}})
        else:
            rows.append(
                {
                    "lens": match["lens"],
                    "similarity": match["similarity"],
                    "film_a_lens": match["film_b_lens"],
                    "film_b_lens": match["film_a_lens"],
                }
            )
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
