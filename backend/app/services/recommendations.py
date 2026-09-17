"""Recommendations derived exclusively from published lens profiles."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg

from app.core.config import settings
from app.db.postgres import ensure_runtime_schema
from app.film_config import FILM_TITLES
from app.services.lens_profiles import comparison_lenses, published_lenses


def _load_chunks_from_postgres() -> list[dict[str, Any]]:
    ensure_runtime_schema()
    sql = """
        SELECT c.id, c.text, f.slug, s.source_key, s.quality_score, s.source_role, c.chunk_role
        FROM chunks c
        JOIN films f ON f.id = c.film_id
        JOIN sources s ON s.id = c.source_id
        WHERE s.quality_score <> 'low'
    """
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [
                {
                    "chunk_id": str(row[0]),
                    "text": str(row[1]),
                    "film_slug": str(row[2]),
                    "source_key": str(row[3]),
                    "quality_score": str(row[4] or "medium"),
                    "source_role": str(row[5] or "criticism"),
                    "chunk_role": str(row[6] or "interpretive_claim"),
                }
                for row in cur.fetchall()
            ]


def _load_chunks_from_file() -> list[dict[str, Any]]:
    corpus_path = Path(__file__).resolve().parents[1] / "corpus" / "chunks.jsonl"
    if not corpus_path.exists():
        return []
    with corpus_path.open(encoding="utf-8") as handle:
        rows = (json.loads(line) for line in handle)
        return [row for row in rows if row.get("quality_score") != "low"]


def load_recommendation_chunks() -> list[dict[str, Any]]:
    if not settings.use_runtime_databases:
        return _load_chunks_from_file()
    try:
        return _load_chunks_from_postgres()
    except Exception:
        return _load_chunks_from_file()


@lru_cache(maxsize=1)
def build_film_profiles() -> dict[str, dict[str, Any]]:
    """Expose only evidence-backed profiles that passed publication gates."""
    return {
        slug: {"slug": slug, "title": title, "lenses": published_lenses(slug)}
        for slug, title in FILM_TITLES.items()
    }


def comparison_lens_suggestions(film_a: str, film_b: str, limit: int = 3) -> list[dict[str, Any]]:
    suggestions = []
    for match in comparison_lenses(film_a, film_b):
        suggestions.append({"lens": match["lens"], "score": match["similarity"], "film_a_lens": match["film_a_lens"], "film_b_lens": match["film_b_lens"]})
    return sorted(suggestions, key=lambda row: row["score"], reverse=True)[:limit]


def pairing_suggestions(film_slug: str, lens: str, limit: int = 4) -> list[dict[str, Any]]:
    suggestions = []
    for candidate_slug, title in FILM_TITLES.items():
        if candidate_slug == film_slug:
            continue
        matches = [row for row in comparison_lenses(film_slug, candidate_slug) if row["film_a_lens"] == lens]
        if matches:
            best = max(matches, key=lambda row: row["similarity"])
            suggestions.append({"film_slug": candidate_slug, "title": title, "lens": best["lens"], "score": best["similarity"]})
    return sorted(suggestions, key=lambda row: row["score"], reverse=True)[:limit]
