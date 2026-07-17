import csv
import hashlib
import uuid
from pathlib import Path

import psycopg

from ingestion.config import DATABASE_URL, MOTIF_COLLECTION, WEAVIATE_URL
from ingestion.weaviate_rest import batch_objects, delete_schema, ensure_schema


FILM_LENSES = {
    "shawshank-redemption": ["Freedom", "Hope", "Institutional Control", "Friendship", "Justice"],
    "fight-club": ["Identity", "Masculinity", "Consumerism", "Violence", "Doubles"],
    "one-flew-over-the-cuckoos-nest": ["Control", "Institutional Power", "Freedom", "Rebellion", "Madness"],
    "se7en": ["Justice", "Violence", "Moral Decay", "Obsession", "Guilt"],
    "silence-of-the-lambs": ["Power", "Fear", "Identity", "Gender", "Control"],
    "the-prestige": ["Obsession", "Performance", "Sacrifice", "Doubles", "Truth"],
    "memento": ["Memory", "Truth", "Identity", "Guilt", "Self-Deception"],
    "taxi-driver": ["Isolation", "Masculinity", "Violence", "Alienation", "Moral Delusion"],
    "shutter-island": ["Reality vs Illusion", "Trauma", "Guilt", "Denial", "Madness"],
    "black-swan": ["Performance", "Identity", "Obsession", "Control", "Doubles"],
    "sixth-sense": ["Grief", "Perception", "Denial", "Childhood", "Revelation"],
    "prisoners": ["Justice", "Faith", "Violence", "Obsession", "Moral Ambiguity"],
    "gone-girl": ["Performance", "Marriage", "Media", "Control", "Identity"],
    "requiem-for-a-dream": ["Addiction", "Obsession", "Desire", "Decay", "Control"],
    "donnie-darko": ["Time", "Fate", "Reality vs Illusion", "Alienation", "Madness"],
    "the-machinist": ["Guilt", "Insomnia", "Body", "Madness", "Self-Punishment"],
    "mulholland-drive": ["Dream Logic", "Identity", "Desire", "Hollywood", "Reality vs Illusion"],
    "truman-show": ["Surveillance", "Freedom", "Reality vs Illusion", "Control", "Performance"],
}

HIGH_QUALITY_PUBLISHERS = {
    "afi.com",
    "catalog.afi.com",
    "academypublication.com",
    "bfi.org.uk",
    "criterion.com",
    "deadline.com",
    "dga.org",
    "indiewire.com",
    "jstor.org",
    "mdpi.com",
    "nottingham.ac.uk",
    "rogerebert.com",
    "scholarworks.umt.edu",
    "theasc.com",
    "theguardian.com",
    "vanityfair.com",
}

LOW_QUALITY_PUBLISHERS = {
    "medium.com",
    "angeladesousablog.wordpress.com",
    "thehutchfiles.com",
    "studsterkel-wfmt.com",
}


def pg_conn():
    return psycopg.connect(DATABASE_URL)


def _ensure_metadata_columns(cur) -> None:
    cur.execute("ALTER TABLE sources ADD COLUMN IF NOT EXISTS quality_score TEXT NOT NULL DEFAULT 'medium'")
    cur.execute("ALTER TABLE sources ADD COLUMN IF NOT EXISTS source_role TEXT NOT NULL DEFAULT 'criticism'")
    cur.execute("ALTER TABLE sources ADD COLUMN IF NOT EXISTS lens_tags TEXT[] NOT NULL DEFAULT '{}'")
    cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS lens_tags TEXT[] NOT NULL DEFAULT '{}'")
    cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_title TEXT")
    cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chunk_role TEXT NOT NULL DEFAULT 'interpretive_claim'")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_quality ON sources(quality_score)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_role ON sources(source_role)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_lens_tags ON sources USING GIN (lens_tags)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_lens_tags ON chunks USING GIN (lens_tags)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_role ON chunks(chunk_role)")


def _infer_source_role(source_type: str) -> str:
    if source_type in {"interview", "festival_qa", "director_commentary", "cast_interview"}:
        return "creator_voice"
    if source_type == "screenplay":
        return "screenplay"
    if source_type == "production_notes":
        return "production_context"
    if source_type == "academic":
        return "scholarship"
    return "criticism"


def _infer_quality(source_type: str, publisher: str, title: str) -> str:
    publisher = (publisher or "").lower()
    title = (title or "").lower()
    if publisher in LOW_QUALITY_PUBLISHERS or "imdb" in publisher or "blog" in publisher:
        return "low"
    if source_type in {"screenplay", "production_notes", "academic", "interview", "festival_qa"}:
        return "high"
    if publisher in HIGH_QUALITY_PUBLISHERS:
        return "high"
    if "wikipedia" in publisher or "wiki" in title:
        return "low"
    return "medium"


def _lens_tags_for_text(film_slug: str, text: str) -> list[str]:
    film_lenses = FILM_LENSES.get(film_slug, [])
    lowered = text.lower()
    tags = [lens for lens in film_lenses if lens.lower() in lowered]
    return tags or film_lenses[:3]


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
            _ensure_metadata_columns(cur)
            with open(seed_sources_path, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    cur.execute("SELECT id FROM films WHERE slug = %s", (row["film_slug"],))
                    film_id = cur.fetchone()[0]
                    quality_score = row.get("quality_score") or _infer_quality(
                        row["source_type"], row.get("publisher", ""), row.get("title", "")
                    )
                    source_role = row.get("source_role") or _infer_source_role(row["source_type"])
                    lens_tags = row.get("lens_tags")
                    if lens_tags:
                        parsed_lenses = [lens.strip() for lens in lens_tags.split(";") if lens.strip()]
                    else:
                        parsed_lenses = FILM_LENSES.get(row["film_slug"], [])[:3]
                    cur.execute(
                        """
                        INSERT INTO sources (
                            film_id, source_key, title, author, publisher, source_type, url,
                            publication_date, is_primary, credibility_score, quality_score,
                            source_role, lens_tags, notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, NULLIF(%s, ''), NULLIF(%s, '')::date, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (source_key) DO UPDATE SET
                            title = EXCLUDED.title,
                            author = EXCLUDED.author,
                            publisher = EXCLUDED.publisher,
                            source_type = EXCLUDED.source_type,
                            url = EXCLUDED.url,
                            publication_date = EXCLUDED.publication_date,
                            is_primary = EXCLUDED.is_primary,
                            credibility_score = EXCLUDED.credibility_score,
                            quality_score = EXCLUDED.quality_score,
                            source_role = EXCLUDED.source_role,
                            lens_tags = EXCLUDED.lens_tags,
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
                            quality_score,
                            source_role,
                            parsed_lenses,
                            row["notes"] or None,
                        ),
                    )
            conn.commit()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_weaviate_schema() -> None:
    ensure_schema()


def reset_stores() -> None:
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE film_relations, chunks, documents, sources, films RESTART IDENTITY CASCADE")
        conn.commit()

    delete_schema()


def store_document_and_chunks(source_key: str, raw_text: str, cleaned_text: str, chunks, embeddings) -> None:
    hash_value = content_hash(cleaned_text)
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.film_id, f.slug, s.source_type::text, s.title, s.quality_score, s.source_role
                FROM sources s
                JOIN films f ON f.id = s.film_id
                WHERE s.source_key = %s
                """,
                (source_key,),
            )
            source_id, film_id, film_slug, source_type, title, quality_score, source_role = cur.fetchone()
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
                lens_tags = _lens_tags_for_text(film_slug, chunk.text)
                cur.execute(
                    """
                    INSERT INTO chunks (
                        id, document_id, source_id, film_id, chunk_index, text,
                        token_count, start_char, end_char, section_title, chunk_role, embedding_model, lens_tags
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        chunk.section_title,
                        chunk.chunk_role,
                        model,
                        lens_tags,
                    ),
                )
            conn.commit()

    batch_objects(
        [
            {
                "class": MOTIF_COLLECTION,
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
                "properties": {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "film_slug": film_slug,
                    "source_key": source_key,
                    "source_type": source_type,
                    "title": title,
                    "quality_score": quality_score,
                    "source_role": source_role,
                    "lens_tags": _lens_tags_for_text(film_slug, chunk.text),
                    "section_title": chunk.section_title,
                    "chunk_role": chunk.chunk_role,
                },
                "vector": vector,
            }
            for chunk, (vector, _) in zip(chunks, embeddings)
        ]
    )
