"""Build Motif's resumable, disk-backed OpenAI retrieval index.

The index is SQLite rather than JSON so the deployed API can read vectors for
one selected film without holding the complete embedding corpus in memory.
"""

from array import array
import json
import os
from pathlib import Path
import sqlite3

from openai import OpenAI

from app.core.config import settings


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/app/corpus/chunks.jsonl"
OUTPUT = ROOT / "backend/app/corpus/openai_retrieval_index.sqlite3"
MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
BATCH_SIZE = 100


def _open_index() -> sqlite3.Connection:
    connection = sqlite3.connect(OUTPUT)
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS embeddings (chunk_id TEXT PRIMARY KEY, vector BLOB NOT NULL)")
    return connection


def main() -> None:
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required to build the retrieval index.")

    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    client = OpenAI(api_key=api_key)
    with _open_index() as connection:
        indexed = {row[0] for row in connection.execute("SELECT chunk_id FROM embeddings")}
        pending = [row for row in rows if row["chunk_id"] not in indexed]
        print(f"index contains {len(indexed)}/{len(rows)} chunks; {len(pending)} remaining", flush=True)

        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start : start + BATCH_SIZE]
            response = client.embeddings.create(model=MODEL, input=[row["text"][:8000] for row in batch])
            connection.executemany(
                "INSERT OR REPLACE INTO embeddings (chunk_id, vector) VALUES (?, ?)",
                [
                    (row["chunk_id"], sqlite3.Binary(array("f", item.embedding).tobytes()))
                    for row, item in zip(batch, response.data)
                ],
            )
            connection.commit()
            print(f"embedded {min(start + len(batch), len(pending))}/{len(pending)} remaining chunks", flush=True)

        dimension = connection.execute("SELECT length(vector) / 4 FROM embeddings LIMIT 1").fetchone()[0]
        connection.executemany(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            [("model", MODEL), ("dimensions", str(dimension)), ("chunk_count", str(len(rows)))],
        )
        connection.commit()
    print(f"index={OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
