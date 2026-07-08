import psycopg

from app.core.config import settings


def get_connection():
    return psycopg.connect(settings.database_url)


def fetch_source_metadata(source_keys: list[str]) -> dict[str, dict]:
    if not source_keys:
        return {}

    query = """
        SELECT s.source_key, s.title, s.author, s.publisher, s.source_type::text, s.url
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
        }
        for row in rows
    }

