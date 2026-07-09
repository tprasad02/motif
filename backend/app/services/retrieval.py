from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

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
    response = httpx.post(f"{_base_url()}/v1/graphql", json=graphql, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])

    objects = payload.get("data", {}).get("Get", {}).get(settings.motif_collection, [])
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
