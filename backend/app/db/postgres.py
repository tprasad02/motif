import json
from pathlib import Path

import psycopg

from app.core.config import settings

_schema_checked = False
_file_sources_cache: dict[str, dict] | None = None


def get_connection():
    return psycopg.connect(settings.database_url)


def ensure_runtime_schema() -> None:
    global _schema_checked
    if _schema_checked:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
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
        conn.commit()
    _schema_checked = True


def fetch_source_metadata(source_keys: list[str]) -> dict[str, dict]:
    if not source_keys:
        return {}
    file_sources = _load_file_sources()
    try:
        ensure_runtime_schema()
    except Exception:
        return {key: file_sources[key] for key in source_keys if key in file_sources}

    query = """
        SELECT s.source_key, s.title, s.author, s.publisher, s.source_type::text, s.url,
               s.quality_score, s.source_role, s.lens_tags
        FROM sources s
        WHERE s.source_key = ANY(%s)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (source_keys,))
            rows = cur.fetchall()

    metadata = {
        row[0]: {
            "source_key": row[0],
            "title": row[1],
            "author": row[2],
            "publisher": row[3],
            "source_type": row[4],
            "url": row[5],
            "quality_score": row[6],
            "source_role": row[7],
            "lens_tags": row[8] or [],
        }
        for row in rows
    }
    for key in source_keys:
        if key not in metadata and key in file_sources:
            metadata[key] = file_sources[key]
    return metadata


def _load_file_sources() -> dict[str, dict]:
    global _file_sources_cache
    if _file_sources_cache is not None:
        return _file_sources_cache
    corpus_path = Path(__file__).resolve().parents[1] / "corpus" / "sources.jsonl"
    sources: dict[str, dict] = {}
    if corpus_path.exists():
        with corpus_path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                sources[str(row["source_key"])] = row
    _file_sources_cache = sources
    return sources
