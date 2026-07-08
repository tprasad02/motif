import csv
from collections import Counter, defaultdict
from pathlib import Path

REQUIRED_TYPES = {
    "review",
    "interview",
    "essay",
    "academic",
    "screenplay",
    "production_notes",
}


def main() -> None:
    films_path = Path("data/seed_films.csv")
    sources_path = Path("data/public_sources.csv")

    films = list(csv.DictReader(films_path.open(newline="", encoding="utf-8")))
    sources = list(csv.DictReader(sources_path.open(newline="", encoding="utf-8")))

    by_film = defaultdict(list)
    for source in sources:
        by_film[source["film_slug"]].append(source)

    failures = []
    for film in films:
        film_sources = by_film[film["slug"]]
        source_count = len(film_sources)
        source_types = {source["source_type"] for source in film_sources}
        if not 8 <= source_count <= 15:
            failures.append(f"{film['slug']} has {source_count} sources")
        missing_types = REQUIRED_TYPES - source_types
        if missing_types:
            failures.append(f"{film['slug']} missing source types: {', '.join(sorted(missing_types))}")

    located = [source for source in sources if source.get("local_path") or source.get("url")]
    local_docs = [source for source in sources if source.get("local_path") and Path(source["local_path"]).exists()]
    print(f"films={len(films)}")
    print(f"sources={len(sources)}")
    print(f"source_counts={dict(Counter(source['film_slug'] for source in sources))}")
    print(f"source_types={dict(Counter(source['source_type'] for source in sources))}")
    print(f"sources_with_url_or_local_path={len(located)}")
    print(f"local_documents={len(local_docs)}")

    if len(sources) != 150:
        failures.append(f"public corpus should have 150 sources; found {len(sources)}")
    if len(local_docs) != 150:
        failures.append(f"public corpus should have 150 local documents; found {len(local_docs)}")

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
