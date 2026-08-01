import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from app.core.config import settings
from app.db.postgres import ensure_runtime_schema
from app.film_config import FILM_TITLES, PRIMARY_LENSES, SECONDARY_TO_PRIMARY, expand_lens_terms


QUALITY_WEIGHT = {"high": 1.35, "medium": 1.0, "low": 0.35}
SOURCE_ROLE_WEIGHT = {
    "creator_voice": 1.25,
    "scholarship": 1.2,
    "screenplay": 1.15,
    "production_context": 1.05,
    "criticism": 1.0,
}
CHUNK_ROLE_WEIGHT = {
    "scene_evidence": 1.3,
    "formal_observation": 1.25,
    "creator_commentary": 1.2,
    "interpretive_claim": 1.0,
    "plot_summary": 0.45,
}

FILM_WORDS = {
    normalized
    for title in FILM_TITLES.values()
    for word in re.findall(r"[A-Za-z][A-Za-z']+", title)
    if len(normalized := word.lower().removesuffix("'s")) > 2
}
DOMAIN_STOPWORDS = {
    "film",
    "films",
    "movie",
    "movies",
    "scene",
    "scenes",
    "story",
    "character",
    "characters",
    "director",
    "screenplay",
    "shot",
    "shots",
    "camera",
    "viewer",
    "viewers",
    "audience",
    "article",
    "interview",
    "review",
    "essay",
    "pdf",
    "page",
    "chapter",
    "press",
    "source",
    "black",
    "white",
    "new",
    "york",
    *FILM_WORDS,
}
STOPWORDS = ENGLISH_STOP_WORDS.union(DOMAIN_STOPWORDS)


def _chunk_weight(chunk: dict[str, Any]) -> float:
    return (
        QUALITY_WEIGHT.get(str(chunk.get("quality_score", "medium")), 1.0)
        * SOURCE_ROLE_WEIGHT.get(str(chunk.get("source_role", "criticism")), 1.0)
        * CHUNK_ROLE_WEIGHT.get(str(chunk.get("chunk_role", "interpretive_claim")), 1.0)
    )


def _clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text or "")
    text = re.sub(r"[^A-Za-z0-9' -]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _valid_concept(term: str) -> bool:
    words = [word for word in re.findall(r"[a-z][a-z']+", term.lower()) if word]
    if not words or len(words) > 3:
        return False
    if any(len(word) < 3 for word in words):
        return False
    if all(word in STOPWORDS for word in words):
        return False
    if any(word in {"copyright", "www", "http", "html", "retrieved"} for word in words):
        return False
    return True


def _display_concept(term: str) -> str:
    minor = {"and", "or", "of", "the", "in", "on", "to", "for", "with", "vs"}
    words = []
    for word in re.findall(r"[A-Za-z][A-Za-z']+", term):
        lowered = word.lower()
        words.append(lowered if lowered in minor else lowered.capitalize())
    return " ".join(words)


def _extract_text_concepts(chunks: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    usable_chunks = [chunk for chunk in chunks if str(chunk.get("quality_score", "medium")) != "low"]
    if not usable_chunks:
        return {}
    texts = [_clean_text(str(chunk.get("text", ""))) for chunk in usable_chunks]
    try:
        vectorizer = TfidfVectorizer(
            stop_words=list(STOPWORDS),
            ngram_range=(1, 3),
            min_df=2 if len(texts) >= 12 else 1,
            max_df=0.72,
            max_features=1600,
        )
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return {}

    terms = vectorizer.get_feature_names_out()
    concepts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row_index, chunk in enumerate(usable_chunks):
        film_slug = str(chunk.get("film_slug", ""))
        if film_slug not in FILM_TITLES:
            continue
        row = matrix.getrow(row_index)
        weight = _chunk_weight(chunk)
        for term_index, value in zip(row.indices, row.data):
            term = str(terms[term_index])
            if _valid_concept(term):
                concepts[film_slug][_display_concept(term)] += float(value) * weight
    return concepts


def _lens_text_score(text: str, lens: str) -> float:
    lowered = _clean_text(text)
    terms = [lens, *[secondary for secondary, primaries in SECONDARY_TO_PRIMARY.items() if lens in primaries]]
    score = 0.0
    for term in terms:
        normalized = _clean_text(term)
        if len(normalized) < 3:
            continue
        if re.search(rf"\b{re.escape(normalized)}\b", lowered):
            score += 1.0 if normalized == _clean_text(lens) else 0.22
    return min(score, 2.5)


def _concept_primary_targets(concept: str) -> list[str]:
    direct = _primary_targets(concept)
    if direct:
        return direct
    concept_text = _clean_text(concept)
    targets = []
    for lens in PRIMARY_LENSES:
        lens_terms = [_clean_text(term) for term in expand_lens_terms(lens)]
        if any(concept_text == term or concept_text in term or term in concept_text for term in lens_terms if len(term) >= 4):
            targets.append(lens)
    return targets


def _primary_targets(tag: str) -> list[str]:
    if tag in PRIMARY_LENSES:
        return [tag]
    return [target for target in SECONDARY_TO_PRIMARY.get(tag, []) if target in PRIMARY_LENSES]


def _load_chunks_from_postgres() -> list[dict[str, Any]]:
    ensure_runtime_schema()
    sql = """
        SELECT c.id, c.text, f.slug, s.source_key, s.quality_score, s.source_role, c.lens_tags, c.chunk_role
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
                    "lens_tags": list(row[6] or []),
                    "chunk_role": str(row[7] or "interpretive_claim"),
                }
                for row in cur.fetchall()
            ]


def _load_chunks_from_file() -> list[dict[str, Any]]:
    corpus_path = Path(__file__).resolve().parents[1] / "corpus" / "chunks.jsonl"
    chunks: list[dict[str, Any]] = []
    if not corpus_path.exists():
        return chunks
    with corpus_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("quality_score") == "low":
                continue
            chunks.append(row)
    return chunks


def load_recommendation_chunks() -> list[dict[str, Any]]:
    if not settings.use_runtime_databases:
        return _load_chunks_from_file()
    try:
        return _load_chunks_from_postgres()
    except Exception:
        return _load_chunks_from_file()


@lru_cache(maxsize=1)
def build_film_profiles() -> dict[str, dict[str, Any]]:
    chunks = load_recommendation_chunks()
    extracted_concepts = _extract_text_concepts(chunks)
    primary_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    secondary_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    source_sets: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for chunk in chunks:
        film_slug = str(chunk.get("film_slug", ""))
        if film_slug not in FILM_TITLES:
            continue
        weight = _chunk_weight(chunk)
        source_key = str(chunk.get("source_key", ""))
        text = str(chunk.get("text", ""))
        for lens in PRIMARY_LENSES:
            text_score = _lens_text_score(text, lens)
            if text_score:
                primary_scores[film_slug][lens] += weight * text_score * 0.34
                source_sets[film_slug][lens].add(source_key)
        for tag in chunk.get("lens_tags") or []:
            tag = str(tag).strip()
            if not tag:
                continue
            if tag in PRIMARY_LENSES:
                primary_scores[film_slug][tag] += weight
                source_sets[film_slug][tag].add(source_key)
            else:
                secondary_scores[film_slug][tag] += weight
                for primary in _primary_targets(tag):
                    primary_scores[film_slug][primary] += weight * 0.82
                    source_sets[film_slug][primary].add(source_key)

    for film_slug, concept_scores in extracted_concepts.items():
        for concept, score in concept_scores.items():
            targets = _concept_primary_targets(concept)
            if targets:
                for primary in targets:
                    primary_scores[film_slug][primary] += score * 0.28
            else:
                secondary_scores[film_slug][concept] += score

    profiles: dict[str, dict[str, Any]] = {}
    for slug, title in FILM_TITLES.items():
        lens_rows = []
        for lens, score in primary_scores[slug].items():
            diversity_boost = min(len(source_sets[slug][lens]) * 0.2, 1.0)
            lens_rows.append({"lens": lens, "score": round(score + diversity_boost, 3)})
        lens_rows.sort(key=lambda row: row["score"], reverse=True)

        angle_rows = [
            {"angle": angle, "score": round(score, 3), "maps_to": targets}
            for angle, score in secondary_scores[slug].items()
            if score >= 0.45 and (targets := _concept_primary_targets(angle))
        ]
        angle_rows.sort(key=lambda row: row["score"], reverse=True)

        profiles[slug] = {
            "slug": slug,
            "title": title,
            "lenses": lens_rows[:5],
            "specific_angles": angle_rows[:6],
        }
    return profiles


def score_film_lens(profiles: dict[str, dict[str, Any]], film_slug: str, lens: str) -> float:
    for row in profiles.get(film_slug, {}).get("lenses", []):
        if row["lens"] == lens:
            return float(row["score"])
    expanded = set(expand_lens_terms(lens))
    score = 0.0
    for angle in profiles.get(film_slug, {}).get("specific_angles", []):
        if expanded.intersection({str(angle["angle"]), *angle.get("maps_to", [])}):
            score += float(angle["score"]) * 0.45
    return score


def comparison_lens_suggestions(film_a: str, film_b: str, limit: int = 3) -> list[dict[str, Any]]:
    profiles = build_film_profiles()
    suggestions = []
    for lens in PRIMARY_LENSES:
        score_a = score_film_lens(profiles, film_a, lens)
        score_b = score_film_lens(profiles, film_b, lens)
        if not score_a or not score_b:
            continue
        if min(score_a, score_b) < 25:
            continue
        balance = min(score_a, score_b)
        average = (score_a + score_b) / 2
        contrast = abs(score_a - score_b) / max(average, 0.01)
        score = (0.62 * balance) + (0.28 * average) + (0.10 * min(contrast, 1.0))
        suggestions.append(
            {
                "lens": lens,
                "score": round(score, 3),
                "film_a_score": round(score_a, 3),
                "film_b_score": round(score_b, 3),
            }
        )
    suggestions.sort(key=lambda row: row["score"], reverse=True)
    return suggestions[:limit]


def pairing_suggestions(film_slug: str, lens: str, limit: int = 4) -> list[dict[str, Any]]:
    profiles = build_film_profiles()
    anchor_score = score_film_lens(profiles, film_slug, lens)
    suggestions = []
    if not anchor_score:
        return suggestions
    for candidate_slug, title in FILM_TITLES.items():
        if candidate_slug == film_slug:
            continue
        candidate_score = score_film_lens(profiles, candidate_slug, lens)
        if not candidate_score:
            continue
        score = (0.7 * min(anchor_score, candidate_score)) + (0.3 * ((anchor_score + candidate_score) / 2))
        suggestions.append(
            {
                "film_slug": candidate_slug,
                "title": title,
                "lens": lens,
                "score": round(score, 3),
            }
        )
    suggestions.sort(key=lambda row: row["score"], reverse=True)
    return suggestions[:limit]
