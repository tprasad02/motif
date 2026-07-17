import argparse
import csv
import json
from pathlib import Path

from ingestion.chunking import chunk_text
from ingestion.cleaning import clean_text
from ingestion.extractors import extract_by_path
from ingestion.storage import FILM_LENSES, _infer_quality, _infer_source_role, _lens_tags_for_text, content_hash


def _source_record(row: dict[str, str]) -> dict[str, object]:
    quality_score = row.get("quality_score") or _infer_quality(row["source_type"], row.get("publisher", ""), row.get("title", ""))
    source_role = row.get("source_role") or _infer_source_role(row["source_type"])
    lens_tags = row.get("lens_tags")
    if lens_tags:
        parsed_lenses = [lens.strip() for lens in lens_tags.split(";") if lens.strip()]
    else:
        parsed_lenses = FILM_LENSES.get(row["film_slug"], [])[:3]
    return {
        "film_slug": row["film_slug"],
        "source_key": row["source_key"],
        "title": row["title"],
        "author": row.get("author") or None,
        "publisher": row.get("publisher") or None,
        "source_type": row["source_type"],
        "url": row.get("url") or None,
        "publication_date": row.get("publication_date") or None,
        "is_primary": row.get("is_primary", "").lower() == "true",
        "credibility_score": float(row.get("credibility_score") or 0),
        "quality_score": quality_score,
        "source_role": source_role,
        "lens_tags": parsed_lenses,
        "notes": row.get("notes") or None,
    }


def build_backend_corpus(sources_path: str, output_dir: str) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    chunks_path = output / "chunks.jsonl"
    sources_out_path = output / "sources.jsonl"

    source_count = 0
    chunk_count = 0
    with open(sources_path, newline="", encoding="utf-8") as handle, chunks_path.open("w", encoding="utf-8") as chunks_out, sources_out_path.open(
        "w", encoding="utf-8"
    ) as sources_out:
        for row in csv.DictReader(handle):
            local_path = row.get("local_path", "").strip()
            url = row.get("url", "").strip()
            source_location = local_path or url
            if not source_location:
                continue
            if local_path and not Path(local_path).exists():
                continue

            source = _source_record(row)
            raw_text = extract_by_path(source_location).replace("\x00", "")
            cleaned = clean_text(raw_text)
            hash_value = content_hash(cleaned)
            chunks = chunk_text(row["source_key"], hash_value, cleaned, source_type=row["source_type"])
            if not chunks:
                continue

            sources_out.write(json.dumps(source, ensure_ascii=False) + "\n")
            source_count += 1
            for chunk in chunks:
                chunk_record = {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "film_slug": row["film_slug"],
                    "source_key": row["source_key"],
                    "source_type": row["source_type"],
                    "quality_score": source["quality_score"],
                    "source_role": source["source_role"],
                    "lens_tags": _lens_tags_for_text(row["film_slug"], chunk.text),
                    "section_title": chunk.section_title,
                    "chunk_role": chunk.chunk_role,
                }
                chunks_out.write(json.dumps(chunk_record, ensure_ascii=False) + "\n")
                chunk_count += 1

    print(f"Wrote {source_count} sources and {chunk_count} chunks to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build backend JSONL corpus fallback")
    parser.add_argument("--sources", default="data/manual_sources.csv")
    parser.add_argument("--output-dir", default="backend/app/corpus")
    args = parser.parse_args()
    build_backend_corpus(args.sources, args.output_dir)


if __name__ == "__main__":
    main()
