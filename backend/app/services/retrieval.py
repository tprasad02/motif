from dataclasses import dataclass

import weaviate

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


def _client():
    return weaviate.connect_to_local(
        host=settings.weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
        port=8080,
    )


def _combine_filters(filters):
    active = [item for item in filters if item is not None]
    if not active:
        return None
    combined = active[0]
    for item in active[1:]:
        combined = combined & item
    return combined


def retrieve_chunks(query: str, film_slugs: list[str], source_types: list[str], limit: int) -> list[RetrievedChunk]:
    client = _client()
    try:
        collection = client.collections.get(settings.motif_collection)
        filters = []
        if film_slugs:
            filters.append(weaviate.classes.query.Filter.by_property("film_slug").contains_any(film_slugs))
        if source_types:
            filters.append(weaviate.classes.query.Filter.by_property("source_type").contains_any(source_types))

        result = collection.query.near_vector(
            near_vector=local_embedding(query),
            limit=limit,
            filters=_combine_filters(filters),
            return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
        )
        chunks = []
        for obj in result.objects:
            props = obj.properties
            distance = obj.metadata.distance if obj.metadata else 1.0
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
    finally:
        client.close()
