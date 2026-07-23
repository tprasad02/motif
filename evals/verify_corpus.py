import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROLE_BY_TYPE = {
    "academic": "scholarship",
    "cast_interview": "creator_voice",
    "craft_article": "production_context",
    "educational_essay": "criticism",
    "festival_qa": "creator_voice",
    "film_history": "criticism",
    "interview": "creator_voice",
    "production_notes": "production_context",
    "review": "criticism",
    "screenplay": "screenplay",
    "video_essay_transcript": "criticism",
}

REQUIRED_TYPES = {
    "interview",
    "academic",
    "screenplay",
    "production_notes",
}

PREFERRED_TYPES = {
    "festival_qa",
    "educational_essay",
    "video_essay_transcript",
    "cast_interview",
    "craft_article",
    "film_history",
}


def load_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


def load_chunks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    chunks = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                chunks.append(json.loads(line))
    return chunks


def latest_chunk_eval_report(reports_dir: Path) -> Path | None:
    candidates = sorted(
        [*reports_dir.glob("chunk_evaluation_results*.json"), *reports_dir.glob("chunks_evaluation*.json")],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_chunk_scores(report_path: Path | None) -> dict[str, int]:
    if not report_path or not report_path.exists():
        return {}
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    scores = {}
    for row in payload.get("chunks", []):
        llm = row.get("llm") or {}
        score = llm.get("score")
        if score is not None:
            scores[row["chunk_id"]] = int(score)
    return scores


def coverage_level(
    source_count: int,
    source_role_count: int,
    source_type_diversity: int,
    local_file_exists_rate: float,
    chunk_count: int,
    avg_chunk_score: float | None,
) -> str:
    score = 0
    if source_count >= 6:
        score += 2
    elif source_count >= 4:
        score += 1

    if source_role_count >= 4:
        score += 2
    elif source_role_count >= 2:
        score += 1

    if source_type_diversity >= 5:
        score += 2
    elif source_type_diversity >= 3:
        score += 1

    if local_file_exists_rate >= 0.95:
        score += 2
    elif local_file_exists_rate >= 0.75:
        score += 1

    if chunk_count >= 40:
        score += 2
    elif chunk_count >= 20:
        score += 1

    if avg_chunk_score is not None:
        if avg_chunk_score >= 4.0:
            score += 2
        elif avg_chunk_score >= 3.0:
            score += 1

    if score >= 9:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def warnings_for_film(
    source_count: int,
    source_types: set[str],
    local_file_exists_rate: float,
    chunk_count: int,
    avg_chunk_score: float | None,
    min_per_film: int,
) -> list[str]:
    warnings = []
    if source_count < min_per_film:
        warnings.append(f"only {source_count} sources")
    if source_count > 15:
        warnings.append(f"{source_count} sources exceeds target max 15")
    missing_types = REQUIRED_TYPES - source_types
    if missing_types:
        warnings.append(f"missing required types: {', '.join(sorted(missing_types))}")
    if not (source_types & PREFERRED_TYPES):
        warnings.append("no preferred secondary source type")
    if local_file_exists_rate < 1.0:
        warnings.append(f"local file exists rate {local_file_exists_rate:.0%}")
    if chunk_count < 20:
        warnings.append(f"only {chunk_count} chunks")
    if avg_chunk_score is not None and avg_chunk_score < 3.0:
        warnings.append(f"low average chunk score {avg_chunk_score:.2f}")
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Motif corpus coverage by film")
    parser.add_argument("--sources", default="data/manual_sources.csv")
    parser.add_argument("--films", default="data/seed_films.csv")
    parser.add_argument("--chunks", default="backend/app/corpus/chunks.jsonl")
    parser.add_argument("--chunk-eval-report", default=None)
    parser.add_argument("--min-per-film", type=int, default=4)
    parser.add_argument("--output", default=None, help="Optional CSV output path for per-film coverage rows.")
    args = parser.parse_args()

    films = load_csv(Path(args.films))
    sources = load_csv(Path(args.sources))
    chunks = load_chunks(Path(args.chunks))
    report_path = Path(args.chunk_eval_report) if args.chunk_eval_report else latest_chunk_eval_report(Path("evals/Reports"))
    chunk_scores = load_chunk_scores(report_path)

    sources_by_film = defaultdict(list)
    for source in sources:
        sources_by_film[source["film_slug"]].append(source)

    chunks_by_film = defaultdict(list)
    for chunk in chunks:
        chunks_by_film[chunk.get("film_slug")].append(chunk)

    rows = []
    failures = []
    for film in films:
        film_slug = film["slug"]
        film_sources = sources_by_film[film_slug]
        film_chunks = chunks_by_film[film_slug]
        source_types = {source["source_type"] for source in film_sources if source.get("source_type")}
        source_roles = {
            source.get("source_role") or ROLE_BY_TYPE.get(source.get("source_type", ""), "unknown")
            for source in film_sources
        }
        local_sources = [source for source in film_sources if source.get("local_path")]
        existing_local_sources = [source for source in local_sources if Path(source["local_path"]).exists()]
        local_file_exists_rate = len(existing_local_sources) / len(film_sources) if film_sources else 0.0
        scored_chunks = [chunk_scores[chunk["chunk_id"]] for chunk in film_chunks if chunk.get("chunk_id") in chunk_scores]
        avg_chunk_score = round(sum(scored_chunks) / len(scored_chunks), 2) if scored_chunks else None
        film_warnings = warnings_for_film(
            len(film_sources),
            source_types,
            local_file_exists_rate,
            len(film_chunks),
            avg_chunk_score,
            args.min_per_film,
        )
        level = coverage_level(
            len(film_sources),
            len(source_roles),
            len(source_types),
            local_file_exists_rate,
            len(film_chunks),
            avg_chunk_score,
        )
        if level == "low":
            failures.append(f"{film_slug} has low coverage")
        rows.append(
            {
                "film": film_slug,
                "source_count": len(film_sources),
                "source_roles": "|".join(sorted(source_roles)),
                "source_role_count": len(source_roles),
                "source_type_diversity": len(source_types),
                "local_file_exists_rate": f"{local_file_exists_rate:.2f}",
                "chunk_count": len(film_chunks),
                "avg_chunk_score": "" if avg_chunk_score is None else f"{avg_chunk_score:.2f}",
                "coverage_level": level,
                "warnings": "; ".join(film_warnings),
            }
        )

    fieldnames = [
        "film",
        "source_count",
        "source_roles",
        "source_role_count",
        "source_type_diversity",
        "local_file_exists_rate",
        "chunk_count",
        "avg_chunk_score",
        "coverage_level",
        "warnings",
    ]
    print(",".join(fieldnames))
    for row in rows:
        print(",".join(f'"{row[field]}"' for field in fieldnames))

    print()
    print(f"films={len(films)}")
    print(f"sources={len(sources)}")
    print(f"chunks={len(chunks)}")
    print(f"source_counts={dict(Counter(source['film_slug'] for source in sources))}")
    print(f"source_types={dict(Counter(source['source_type'] for source in sources))}")
    print(f"chunk_eval_report={report_path or 'none'}")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"coverage_csv={output_path}")

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
