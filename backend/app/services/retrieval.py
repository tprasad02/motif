from dataclasses import dataclass
import math
from urllib.parse import urlparse

import httpx
import psycopg

from app.core.config import settings
from app.services.embeddings import local_embedding


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    film_slug: str
    source_key: str
    source_type: str
    score: float


def _base_url() -> str:
    parsed = urlparse(settings.weaviate_url)
    if parsed.scheme:
        return settings.weaviate_url.rstrip("/")
    return f"http://{settings.weaviate_url.rstrip('/')}"


def _combine_filters(filters):
    active = [item for item in filters if item is not None]
    if not active:
        return None
    combined = active[0]
    for item in active[1:]:
        combined = combined & item
    return combined


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


def _postgres_fallback(query: str, film_slugs: list[str], source_types: list[str], limit: int) -> list[RetrievedChunk]:
    clauses = []
    params: list[object] = []
    if film_slugs:
        clauses.append("f.slug = ANY(%s)")
        params.append(film_slugs)
    if source_types:
        clauses.append("s.source_type::text = ANY(%s)")
        params.append(source_types)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT c.id, c.text, f.slug, s.source_key, s.source_type::text
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
            for chunk_id, text, film_slug, source_key, source_type in cur.fetchall():
                score = _cosine_similarity(query_vector, local_embedding(text))
                chunks.append(
                    RetrievedChunk(
                        chunk_id=str(chunk_id),
                        text=str(text),
                        film_slug=str(film_slug),
                        source_key=str(source_key),
                        source_type=str(source_type),
                        score=max(0.0, score),
                    )
                )

    chunks.sort(key=lambda chunk: chunk.score, reverse=True)
    return chunks[:limit]


def retrieve_chunks(query: str, film_slugs: list[str], source_types: list[str], limit: int) -> list[RetrievedChunk]:
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
            raise RuntimeError(payload["errors"])
    except (httpx.HTTPError, RuntimeError):
        return _postgres_fallback(query, film_slugs, source_types, limit)

    objects = payload.get("data", {}).get("Get", {}).get(settings.motif_collection, [])
    if not objects:
        return _postgres_fallback(query, film_slugs, source_types, limit)

    chunks = []
    for props in objects:
        distance = props.get("_additional", {}).get("distance", 1.0)
        chunks.append(
            RetrievedChunk(
                chunk_id=str(props.get("chunk_id")),
                text=str(props.get("text", "")),
                film_slug=str(props.get("film_slug", "")),
                source_key=str(props.get("source_key", "")),
                source_type=str(props.get("source_type", "")),
                score=max(0.0, 1.0 - float(distance or 1.0)),
            )
        )
    return chunks
