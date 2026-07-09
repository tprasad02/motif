import csv
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_TYPES = {
    "review",
    "interview",
    "essay",
    "academic",
    "screenplay",
    "production_notes",
}

REFERENCE_DOMAINS = {"en.wikipedia.org", "wikipedia.org"}
REVIEW_DOMAINS = {"www.rogerebert.com", "rogerebert.com"}
SCRIPT_DOMAINS = {
    "imsdb.com",
    "www.imsdb.com",
    "thescriptsavant.com",
    "www.scriptslug.com",
    "scriptslug.com",
    "www.dailyscript.com",
}
ACADEMIC_DOMAINS = {
    "jstor.org",
    "www.jstor.org",
    "muse.jhu.edu",
    "academic.oup.com",
    "www.tandfonline.com",
    "online.ucpress.edu",
    "www.researchgate.net",
}
INTERVIEW_HINTS = {"interview", "conversation", "q-a", "qanda"}


def domain_for(url: str) -> str:
    if not url:
        return ""
    return urlparse(url).netloc.lower()


def looks_like_claimed_type(source: dict) -> bool:
    source_type = source["source_type"]
    url = source.get("url", "").lower()
    domain = domain_for(url)
    title = source.get("title", "").lower()
    notes = source.get("notes", "").lower()

    if source_type == "review":
        return domain not in REFERENCE_DOMAINS and (domain in REVIEW_DOMAINS or "review" in title or "review" in notes)
    if source_type == "screenplay":
        return domain in SCRIPT_DOMAINS or "screenplay" in title or "script" in title or "screenplay" in notes
    if source_type == "academic":
        return domain in ACADEMIC_DOMAINS or "journal" in notes or "academic" in notes and domain not in REFERENCE_DOMAINS
    if source_type == "interview":
        return any(hint in url or hint in title or hint in notes for hint in INTERVIEW_HINTS) and domain not in REFERENCE_DOMAINS
    if source_type == "production_notes":
        return domain not in REFERENCE_DOMAINS or "production" in title or "production" in notes
    if source_type == "essay":
        return domain not in REFERENCE_DOMAINS or "essay" in notes
    return False


def main() -> None:
    sources = list(csv.DictReader(Path("data/public_sources.csv").open(newline="", encoding="utf-8")))
    by_film = defaultdict(list)
    for source in sources:
        by_film[source["film_slug"]].append(source)

    failures = []
    print(f"sources={len(sources)}")
    for film, film_sources in sorted(by_film.items()):
        types = Counter(source["source_type"] for source in film_sources)
        domains = Counter(domain_for(source["url"]) for source in film_sources)
        missing = REQUIRED_TYPES - set(types)
        mislabeled = [source["source_key"] for source in film_sources if not looks_like_claimed_type(source)]
        print(f"{film}: docs={len(film_sources)} types={dict(types)} domains={dict(domains)}")
        if missing:
            failures.append(f"{film} missing source types: {', '.join(sorted(missing))}")
        if mislabeled:
            failures.append(f"{film} has questionable type claims: {', '.join(mislabeled[:8])}")

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
