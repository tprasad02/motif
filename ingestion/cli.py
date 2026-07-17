import argparse
import csv
from pathlib import Path

from ingestion.chunking import chunk_text
from ingestion.cleaning import clean_text
from ingestion.embeddings import embed_text
from ingestion.extractors import extract_by_path
from ingestion.storage import content_hash, ensure_weaviate_schema, load_films, load_sources, reset_stores, store_document_and_chunks


def ingest_sources(sources_path: str, reset: bool = False) -> None:
    if reset:
        reset_stores()
    load_films()
    load_sources(sources_path)
    ensure_weaviate_schema()

    with open(sources_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            local_path = row.get("local_path", "").strip()
            url = row.get("url", "").strip()
            source_location = local_path or url
            if not source_location:
                print(f"Skipping {row['source_key']}: no local_path or url yet")
                continue
            if local_path and not Path(local_path).exists():
                print(f"Skipping {row['source_key']}: missing {local_path}")
                continue

            raw_text = extract_by_path(source_location).replace("\x00", "")
            cleaned = clean_text(raw_text)
            hash_value = content_hash(cleaned)
            chunks = chunk_text(row["source_key"], hash_value, cleaned)
            embeddings = [embed_text(chunk.text) for chunk in chunks]
            store_document_and_chunks(row["source_key"], raw_text, cleaned, chunks, embeddings)
            print(f"Ingested {row['source_key']}: {len(chunks)} chunks")


def main() -> None:
    parser = argparse.ArgumentParser(description="Motif corpus ingestion")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("--sources", default="data/seed_sources.csv")
    ingest.add_argument("--reset", action="store_true")

    args = parser.parse_args()
    if args.command == "ingest":
        ingest_sources(args.sources, reset=args.reset)


if __name__ == "__main__":
    main()
