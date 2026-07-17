import psycopg

from app.core.config import settings

_schema_checked = False


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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_quality ON sources(quality_score)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_role ON sources(source_role)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_lens_tags ON sources USING GIN (lens_tags)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_lens_tags ON chunks USING GIN (lens_tags)")
        conn.commit()
    _schema_checked = True


def fetch_source_metadata(source_keys: list[str]) -> dict[str, dict]:
    if not source_keys:
        return {}
    ensure_runtime_schema()

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

    return {
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
