import csv
import argparse
from collections import Counter, defaultdict
from pathlib import Path

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Motif corpus manifest coverage")
    parser.add_argument("--sources", default="data/manual_sources.csv")
    parser.add_argument("--min-per-film", type=int, default=4)
    args = parser.parse_args()

    films_path = Path("data/seed_films.csv")
    sources_path = Path(args.sources)

    films = list(csv.DictReader(films_path.open(newline="", encoding="utf-8")))
    sources = list(csv.DictReader(sources_path.open(newline="", encoding="utf-8")))

    by_film = defaultdict(list)
    for source in sources:
        by_film[source["film_slug"]].append(source)

    failures = []
    warnings = []
    for film in films:
        film_sources = by_film[film["slug"]]
        source_count = len(film_sources)
        source_types = {source["source_type"] for source in film_sources}
        if not args.min_per_film <= source_count <= 15:
            failures.append(f"{film['slug']} has {source_count} sources")
        missing_types = REQUIRED_TYPES - source_types
        if missing_types:
            warnings.append(f"{film['slug']} missing source types: {', '.join(sorted(missing_types))}")
        if not (source_types & PREFERRED_TYPES):
            warnings.append(f"{film['slug']} has no preferred secondary source type")

    located = [source for source in sources if source.get("local_path") or source.get("url")]
    local_docs = [source for source in sources if source.get("local_path") and Path(source["local_path"]).exists()]
    print(f"films={len(films)}")
    print(f"sources={len(sources)}")
    print(f"source_counts={dict(Counter(source['film_slug'] for source in sources))}")
    print(f"source_types={dict(Counter(source['source_type'] for source in sources))}")
    print(f"sources_with_url_or_local_path={len(located)}")
    print(f"local_documents={len(local_docs)}")
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"- {warning}")

    expected_max = len(films) * 8
    if len(sources) > expected_max:
        failures.append(f"manual corpus should have at most {expected_max} sources for {len(films)} films; found {len(sources)}")
    if len(local_docs) != len(sources):
        failures.append(f"all manual corpus rows should have local documents; found {len(local_docs)} of {len(sources)}")

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
