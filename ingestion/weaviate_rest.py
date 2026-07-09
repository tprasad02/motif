from urllib.parse import urlparse

import httpx

from ingestion.config import MOTIF_COLLECTION, WEAVIATE_URL


def base_url() -> str:
    parsed = urlparse(WEAVIATE_URL)
    if parsed.scheme:
        return WEAVIATE_URL.rstrip("/")
    return f"http://{WEAVIATE_URL.rstrip('/')}"


def ensure_schema() -> None:
    url = base_url()
    schema = httpx.get(f"{url}/v1/schema/{MOTIF_COLLECTION}", timeout=30)
    if schema.status_code == 200:
        return
    if schema.status_code != 404:
        schema.raise_for_status()

    payload = {
        "class": MOTIF_COLLECTION,
        "vectorizer": "none",
        "properties": [
            {"name": "chunk_id", "dataType": ["text"]},
            {"name": "text", "dataType": ["text"]},
            {"name": "film_slug", "dataType": ["text"]},
            {"name": "source_key", "dataType": ["text"]},
            {"name": "source_type", "dataType": ["text"]},
            {"name": "title", "dataType": ["text"]},
        ],
    }
    response = httpx.post(f"{url}/v1/schema", json=payload, timeout=30)
    response.raise_for_status()


def delete_schema() -> None:
    url = base_url()
    response = httpx.delete(f"{url}/v1/schema/{MOTIF_COLLECTION}", timeout=30)
    if response.status_code not in {200, 404}:
        response.raise_for_status()


def batch_objects(objects: list[dict]) -> None:
    if not objects:
        return
    response = httpx.post(f"{base_url()}/v1/batch/objects", json={"objects": objects}, timeout=60)
    response.raise_for_status()

