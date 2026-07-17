from dataclasses import dataclass
import json
import math
from pathlib import Path
from urllib.parse import urlparse

import httpx
import psycopg

from app.core.config import settings
from app.db.postgres import ensure_runtime_schema
from app.services.embeddings import local_embedding

_file_chunks_cache: list["RetrievedChunk"] | None = None


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    film_slug: str
    source_key: str
    source_type: str
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None
    quality_score: str = "medium"
    source_role: str = "criticism"
    lens_tags: list[str] | None = None


def _base_url() -> str:
    parsed = urlparse(settings.weaviate_url)
    if parsed.scheme:
        return settings.weaviate_url.rstrip("/")
    return f"http://{settings.weaviate_url.rstrip('/')}"


def _where_filter(film_slugs: list[str], source_types: list[str]) -> str:
    operands = []
    if film_slugs:
        values = ", ".join(f'"{slug}"' for slug in film_slugs)
        operands.append(f'{{path:["film_slug"], operator:ContainsAny, valueTextArray:[{values}]}}')
    if source_types:
        values = ", ".join(f'"{source_type}"' for source_type in source_types)
        operands.append(f'{{path:["source_type"], operator:ContainsAny, valueTextArray:[{values}]}}')
    if not operands:
        return ""
    if len(operands) == 1:
        return f", where:{operands[0]}"
    return f", where:{{operator:And, operands:[{', '.join(operands)}]}}"


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return dot / (left_norm * right_norm)


def _metadata_filter_sql(
    film_slugs: list[str],
    source_types: list[str],
    directors: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    critics: list[str] | None = None,
    themes: list[str] | None = None,
    lens_tags: list[str] | None = None,
    include_low_quality: bool = False,
) -> tuple[str, list[object]]:
    clauses = []
    params: list[object] = []
    if film_slugs:
        clauses.append("f.slug = ANY(%s)")
        params.append(film_slugs)
    if source_types:
        clauses.append("s.source_type::text = ANY(%s)")
        params.append(source_types)
    if directors:
        clauses.append("f.director = ANY(%s)")
        params.append(directors)
    if year_start is not None:
        clauses.append("f.release_year >= %s")
        params.append(year_start)
    if year_end is not None:
        clauses.append("f.release_year <= %s")
        params.append(year_end)
    if critics:
        clauses.append("s.author = ANY(%s)")
        params.append(critics)
    if themes:
        clauses.append("f.themes && %s")
        params.append(themes)
    if lens_tags:
        clauses.append("(c.lens_tags && %s OR s.lens_tags && %s)")
        params.extend([lens_tags, lens_tags])
    if not include_low_quality:
        clauses.append("s.quality_score <> 'low'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def _row_to_chunk(row, score: float, *, vector_score: float | None = None, bm25_score: float | None = None) -> RetrievedChunk:
    chunk_id, text, film_slug, source_key, source_type, quality_score, source_role, lens_tags = row
    return RetrievedChunk(
        chunk_id=str(chunk_id),
        text=str(text),
        film_slug=str(film_slug),
        source_key=str(source_key),
        source_type=str(source_type),
        score=score,
        vector_score=vector_score,
        bm25_score=bm25_score,
        quality_score=str(quality_score or "medium"),
        source_role=str(source_role or "criticism"),
        lens_tags=list(lens_tags or []),
    )


def _postgres_vector_search(
    query: str,
    film_slugs: list[str],
    source_types: list[str],
    limit: int,
    directors: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    critics: list[str] | None = None,
    themes: list[str] | None = None,
    lens_tags: list[str] | None = None,
    include_low_quality: bool = False,
) -> list[RetrievedChunk]:
    where, params = _metadata_filter_sql(
        film_slugs, source_types, directors, year_start, year_end, critics, themes, lens_tags, include_low_quality
    )
    sql = f"""
        SELECT c.id, c.text, f.slug, s.source_key, s.source_type::text, s.quality_score, s.source_role, c.lens_tags
        FROM chunks c
        JOIN films f ON f.id = c.film_id
        JOIN sources s ON s.id = c.source_id
        {where}
    """
    query_vector = local_embedding(query)
    chunks: list[RetrievedChunk] = []
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                score = max(0.0, _cosine_similarity(query_vector, local_embedding(row[1])))
                chunks.append(_row_to_chunk(row, score, vector_score=score))
    chunks.sort(key=lambda chunk: chunk.vector_score or 0.0, reverse=True)
    return chunks[:limit]


def _bm25_search(
    query: str,
    film_slugs: list[str],
    source_types: list[str],
    limit: int,
    directors: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    critics: list[str] | None = None,
    themes: list[str] | None = None,
    lens_tags: list[str] | None = None,
    include_low_quality: bool = False,
) -> list[RetrievedChunk]:
    where, params = _metadata_filter_sql(
        film_slugs, source_types, directors, year_start, year_end, critics, themes, lens_tags, include_low_quality
    )
    filter_sql = f"{where} AND" if where else "WHERE"
    sql = f"""
        WITH q AS (SELECT websearch_to_tsquery('english', %s) AS query)
        SELECT c.id, c.text, f.slug, s.source_key, s.source_type::text, s.quality_score, s.source_role, c.lens_tags,
               ts_rank_cd(to_tsvector('english', c.text), q.query) AS rank
        FROM chunks c
        JOIN films f ON f.id = c.film_id
        JOIN sources s ON s.id = c.source_id
        CROSS JOIN q
        {filter_sql} to_tsvector('english', c.text) @@ q.query
        ORDER BY rank DESC
        LIMIT %s
    """
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [query, *params, limit])
            rows = cur.fetchall()

    max_rank = max((float(row[8] or 0.0) for row in rows), default=1.0) or 1.0
    chunks = []
    for row in rows:
        score = float(row[8] or 0.0) / max_rank
        chunks.append(_row_to_chunk(row[:8], score, bm25_score=score))
    return chunks


def _vector_search_weaviate(query: str, film_slugs: list[str], source_types: list[str], limit: int) -> list[RetrievedChunk]:
    vector = ", ".join(str(value) for value in local_embedding(query))
    where = _where_filter(film_slugs, source_types)
    graphql = {
        "query": f"""
        {{
          Get {{
            {settings.motif_collection}(
              nearVector: {{vector: [{vector}]}}
              limit: {limit}
              {where}
            ) {{
              chunk_id
              text
              film_slug
              source_key
              source_type
              quality_score
              source_role
              lens_tags
              _additional {{ distance }}
            }}
          }}
        }}
        """
    }
    try:
        response = httpx.post(f"{_base_url()}/v1/graphql", json=graphql, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            return []
    except httpx.HTTPError:
        return []

    chunks = []
    for props in payload.get("data", {}).get("Get", {}).get(settings.motif_collection, []):
        distance = props.get("_additional", {}).get("distance", 1.0)
        score = max(0.0, 1.0 - float(distance or 1.0))
        if props.get("quality_score") == "low":
            continue
        chunks.append(
            RetrievedChunk(
                chunk_id=str(props.get("chunk_id")),
                text=str(props.get("text", "")),
                film_slug=str(props.get("film_slug", "")),
                source_key=str(props.get("source_key", "")),
                source_type=str(props.get("source_type", "")),
                score=score,
                vector_score=score,
                quality_score=str(props.get("quality_score", "medium")),
                source_role=str(props.get("source_role", "criticism")),
                lens_tags=list(props.get("lens_tags") or []),
            )
        )
    return chunks


def _overlap_score(query: str, text: str) -> float:
    query_terms = {term.strip(".,?!;:()[]{}\"'").lower() for term in query.split() if len(term) > 3}
    if not query_terms:
        return 0.0
    text_terms = {term.strip(".,?!;:()[]{}\"'").lower() for term in text.split()}
    return len(query_terms & text_terms) / len(query_terms)


def _merge_dedupe(vector_chunks: list[RetrievedChunk], bm25_chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    merged: dict[str, RetrievedChunk] = {}
    for chunk in [*vector_chunks, *bm25_chunks]:
        existing = merged.get(chunk.chunk_id)
        if not existing:
            merged[chunk.chunk_id] = chunk
            continue
        existing.vector_score = max(existing.vector_score or 0.0, chunk.vector_score or 0.0) or None
        existing.bm25_score = max(existing.bm25_score or 0.0, chunk.bm25_score or 0.0) or None
        existing.lens_tags = sorted(set((existing.lens_tags or []) + (chunk.lens_tags or [])))
        existing.score = max(existing.score, chunk.score)
    return list(merged.values())


def _rerank(query: str, chunks: list[RetrievedChunk], lens_tags: list[str] | None = None) -> list[RetrievedChunk]:
    lens_terms = {lens.lower() for lens in (lens_tags or [])}
    for chunk in chunks:
        overlap = _overlap_score(query, chunk.text)
        vector = chunk.vector_score or 0.0
        bm25 = chunk.bm25_score or 0.0
        quality_boost = {"high": 0.12, "medium": 0.04, "low": -0.35}.get(chunk.quality_score, 0.0)
        role_boost = {"creator_voice": 0.05, "scholarship": 0.05, "screenplay": 0.04, "production_context": 0.03}.get(
            chunk.source_role, 0.0
        )
        chunk_lenses = {lens.lower() for lens in (chunk.lens_tags or [])}
        lens_boost = 0.12 if lens_terms and chunk_lenses.intersection(lens_terms) else 0.0
        chunk.rerank_score = (0.42 * overlap) + (0.28 * bm25) + (0.18 * vector) + quality_boost + role_boost + lens_boost
        chunk.score = chunk.rerank_score
    return sorted(chunks, key=lambda item: item.rerank_score or 0.0, reverse=True)


def _supplement_source_diversity(query: str, chunks: list[RetrievedChunk], film_slugs: list[str]) -> list[RetrievedChunk]:
    if len(film_slugs) != 1 or len({chunk.source_key for chunk in chunks}) >= 5:
        return chunks

    selected_sources = {chunk.source_key for chunk in chunks}
    sql = """
        SELECT DISTINCT ON (s.source_key)
            c.id, c.text, f.slug, s.source_key, s.source_type::text, s.quality_score, s.source_role, c.lens_tags
        FROM chunks c
        JOIN films f ON f.id = c.film_id
        JOIN sources s ON s.id = c.source_id
        WHERE f.slug = %s
          AND s.quality_score <> 'low'
          AND NOT (s.source_key = ANY(%s))
        ORDER BY s.source_key, c.token_count DESC
    """
    query_vector = local_embedding(query)
    supplements: list[RetrievedChunk] = []
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (film_slugs[0], list(selected_sources)))
            for row in cur.fetchall():
                score = max(0.0, _cosine_similarity(query_vector, local_embedding(row[1])))
                supplements.append(_row_to_chunk(row, score, vector_score=score))

    supplements.sort(
        key=lambda chunk: (
            {"creator_voice": 4, "scholarship": 3, "production_context": 2, "screenplay": 1, "criticism": 0}.get(
                chunk.source_role, 0
            ),
            chunk.vector_score or 0.0,
        ),
        reverse=True,
    )
    return _merge_dedupe(chunks, supplements[: max(0, 6 - len(selected_sources))])


def _balanced_top(chunks: list[RetrievedChunk], limit: int, required_films: list[str]) -> list[RetrievedChunk]:
    selected: list[RetrievedChunk] = []
    source_counts: dict[str, int] = {}

    for film in required_films:
        for chunk in chunks:
            if chunk.film_slug == film and chunk not in selected:
                selected.append(chunk)
                source_counts[chunk.source_key] = source_counts.get(chunk.source_key, 0) + 1
                break

    for chunk in chunks:
        if len(selected) >= limit:
            break
        if chunk in selected or source_counts.get(chunk.source_key, 0) >= 2:
            continue
        selected.append(chunk)
        source_counts[chunk.source_key] = source_counts.get(chunk.source_key, 0) + 1

    for chunk in chunks:
        if len(selected) >= limit:
            break
        if chunk not in selected:
            selected.append(chunk)

    return selected[:limit]


def _load_file_chunks() -> list[RetrievedChunk]:
    global _file_chunks_cache
    if _file_chunks_cache is not None:
        return _file_chunks_cache
    corpus_path = Path(__file__).resolve().parents[1] / "corpus" / "chunks.jsonl"
    chunks: list[RetrievedChunk] = []
    if corpus_path.exists():
        with corpus_path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                chunks.append(
                    RetrievedChunk(
                        chunk_id=str(row["chunk_id"]),
                        text=str(row["text"]),
                        film_slug=str(row["film_slug"]),
                        source_key=str(row["source_key"]),
                        source_type=str(row["source_type"]),
                        score=0,
                        quality_score=str(row.get("quality_score", "medium")),
                        source_role=str(row.get("source_role", "criticism")),
                        lens_tags=list(row.get("lens_tags") or []),
                    )
                )
    _file_chunks_cache = chunks
    return chunks


def _file_fallback_search(
    query: str,
    film_slugs: list[str],
    source_types: list[str],
    limit: int,
    lens_tags: list[str] | None = None,
    include_low_quality: bool = False,
) -> list[RetrievedChunk]:
    query_vector = local_embedding(query)
    candidates = []
    for chunk in _load_file_chunks():
        if film_slugs and chunk.film_slug not in film_slugs:
            continue
        if source_types and chunk.source_type not in source_types:
            continue
        if not include_low_quality and chunk.quality_score == "low":
            continue
        score = max(0.0, _cosine_similarity(query_vector, local_embedding(chunk.text)))
        candidates.append(
            RetrievedChunk(
                **{
                    **chunk.__dict__,
                    "score": score,
                    "vector_score": score,
                }
            )
        )
    reranked = _rerank(query, candidates, lens_tags)
    return _balanced_top(reranked, min(max(limit, 8), 12), film_slugs if len(film_slugs) >= 2 else [])


def retrieve_chunks(
    query: str,
    film_slugs: list[str],
    source_types: list[str],
    limit: int,
    directors: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    critics: list[str] | None = None,
    themes: list[str] | None = None,
    lens_tags: list[str] | None = None,
    include_low_quality: bool = False,
) -> list[RetrievedChunk]:
    try:
        ensure_runtime_schema()
        use_postgres_vector = bool(directors or year_start is not None or year_end is not None or critics or themes or include_low_quality)
        vector_chunks = [] if use_postgres_vector else _vector_search_weaviate(query, film_slugs, source_types, 25)
        if use_postgres_vector or len(vector_chunks) < 25:
            postgres_vector_chunks = _postgres_vector_search(
                query,
                film_slugs,
                source_types,
                25,
                directors,
                year_start,
                year_end,
                critics,
                themes,
                None,
                include_low_quality,
            )
            vector_chunks = _merge_dedupe(vector_chunks, postgres_vector_chunks)
        bm25_chunks = _bm25_search(
            query,
            film_slugs,
            source_types,
            25,
            directors,
            year_start,
            year_end,
            critics,
            themes,
            None,
            include_low_quality,
        )
        merged = _merge_dedupe(vector_chunks, bm25_chunks)
        if not merged:
            return _file_fallback_search(query, film_slugs, source_types, limit, lens_tags, include_low_quality)
        merged = _supplement_source_diversity(query, merged, film_slugs)
        reranked = _rerank(query, merged, lens_tags)
        output_limit = min(max(limit, 8), 12)
        return _balanced_top(reranked, output_limit, film_slugs if len(film_slugs) >= 2 else [])
    except Exception:
        return _file_fallback_search(query, film_slugs, source_types, limit, lens_tags, include_low_quality)
