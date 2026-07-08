import csv
import hashlib
import uuid
from pathlib import Path

import psycopg
import weaviate
from weaviate.classes.config import Configure, DataType, Property

from ingestion.config import DATABASE_URL, MOTIF_COLLECTION, WEAVIATE_URL


def pg_conn():
    return psycopg.connect(DATABASE_URL)


def load_films(seed_films_path: str = "data/seed_films.csv") -> None:
    if not Path(seed_films_path).exists():
        return
    with pg_conn() as conn:
        with conn.cursor() as cur:
            with open(seed_films_path, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    themes = [theme.strip() for theme in row["themes"].split(";") if theme.strip()]
                    cur.execute(
                        """
                        INSERT INTO films (slug, title, release_year, director, country, themes)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (slug) DO UPDATE SET
                            title = EXCLUDED.title,
                            release_year = EXCLUDED.release_year,
                            director = EXCLUDED.director,
                            country = EXCLUDED.country,
                            themes = EXCLUDED.themes,
                            updated_at = now()
                        """,
                        (row["slug"], row["title"], int(row["release_year"]), row["director"], row["country"], themes),
                    )
            conn.commit()


def load_sources(seed_sources_path: str) -> None:
    with pg_conn() as conn:
        with conn.cursor() as cur:
            with open(seed_sources_path, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    cur.execute("SELECT id FROM films WHERE slug = %s", (row["film_slug"],))
                    film_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        INSERT INTO sources (
                            film_id, source_key, title, author, publisher, source_type, url,
                            publication_date, is_primary, credibility_score, notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, NULLIF(%s, ''), NULLIF(%s, '')::date, %s, %s, %s)
                        ON CONFLICT (source_key) DO UPDATE SET
                            title = EXCLUDED.title,
                            author = EXCLUDED.author,
                            publisher = EXCLUDED.publisher,
                            source_type = EXCLUDED.source_type,
                            url = EXCLUDED.url,
                            publication_date = EXCLUDED.publication_date,
                            is_primary = EXCLUDED.is_primary,
                            credibility_score = EXCLUDED.credibility_score,
                            notes = EXCLUDED.notes
                        """,
                        (
                            film_id,
                            row["source_key"],
                            row["title"],
                            row["author"] or None,
                            row["publisher"] or None,
                            row["source_type"],
                            row["url"],
                            row["publication_date"],
                            row["is_primary"].lower() == "true",
                            float(row["credibility_score"]),
                            row["notes"] or None,
                        ),
                    )
            conn.commit()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_weaviate_schema() -> None:
    host = WEAVIATE_URL.replace("http://", "").replace("https://", "").split(":")[0]
    client = weaviate.connect_to_local(host=host, port=8080)
    try:
        if client.collections.exists(MOTIF_COLLECTION):
            return
        client.collections.create(
            MOTIF_COLLECTION,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="chunk_id", data_type=DataType.TEXT),
                Property(name="text", data_type=DataType.TEXT),
                Property(name="film_slug", data_type=DataType.TEXT),
                Property(name="source_key", data_type=DataType.TEXT),
                Property(name="source_type", data_type=DataType.TEXT),
                Property(name="title", data_type=DataType.TEXT),
            ],
        )
    finally:
        client.close()


def reset_stores() -> None:
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE film_relations, chunks, documents, sources, films RESTART IDENTITY CASCADE")
        conn.commit()

    host = WEAVIATE_URL.replace("http://", "").replace("https://", "").split(":")[0]
    client = weaviate.connect_to_local(host=host, port=8080)
    try:
        if client.collections.exists(MOTIF_COLLECTION):
            client.collections.delete(MOTIF_COLLECTION)
    finally:
        client.close()


def store_document_and_chunks(source_key: str, raw_text: str, cleaned_text: str, chunks, embeddings) -> None:
    hash_value = content_hash(cleaned_text)
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.film_id, f.slug, s.source_type::text, s.title
                FROM sources s
                JOIN films f ON f.id = s.film_id
                WHERE s.source_key = %s
                """,
                (source_key,),
            )
            source_id, film_id, film_slug, source_type, title = cur.fetchone()
            cur.execute(
                """
                INSERT INTO documents (source_id, content_hash, raw_text, cleaned_text, token_count, status, ingested_at)
                VALUES (%s, %s, %s, %s, %s, 'ingested', now())
                ON CONFLICT (source_id, content_hash) DO UPDATE SET
                    raw_text = EXCLUDED.raw_text,
                    cleaned_text = EXCLUDED.cleaned_text,
                    token_count = EXCLUDED.token_count,
                    status = 'ingested',
                    error_message = NULL,
                    ingested_at = now()
                RETURNING id
                """,
                (source_id, hash_value, raw_text, cleaned_text, sum(chunk.token_count for chunk in chunks)),
            )
            document_id = cur.fetchone()[0]
            for chunk, (_, model) in zip(chunks, embeddings):
                cur.execute(
                    """
                    INSERT INTO chunks (
                        id, document_id, source_id, film_id, chunk_index, text,
                        token_count, start_char, end_char, embedding_model
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        chunk.chunk_id,
                        document_id,
                        source_id,
                        film_id,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.token_count,
                        chunk.start_char,
                        chunk.end_char,
                        model,
                    ),
                )
            conn.commit()

    host = WEAVIATE_URL.replace("http://", "").replace("https://", "").split(":")[0]
    client = weaviate.connect_to_local(host=host, port=8080)
    try:
        collection = client.collections.get(MOTIF_COLLECTION)
        with collection.batch.dynamic() as batch:
            for chunk, (vector, _) in zip(chunks, embeddings):
                batch.add_object(
                    uuid=uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id),
                    properties={
                        "chunk_id": chunk.chunk_id,
                        "text": chunk.text,
                        "film_slug": film_slug,
                        "source_key": source_key,
                        "source_type": source_type,
                        "title": title,
                    },
                    vector=vector,
                )
    finally:
        client.close()
