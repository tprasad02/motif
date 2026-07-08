import csv
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from ingestion.cleaning import clean_text


RAW_DIR = Path("data/raw/public")
CACHE_DIR = Path("data/raw/public_cache")
PUBLIC_SOURCES = Path("data/public_sources.csv")
USER_AGENT = "MotifCinemaResearch/0.1 (public corpus builder)"


@dataclass(frozen=True)
class FilmPublicPlan:
    slug: str
    title: str
    director: str
    wikipedia_page: str
    director_page: str
    theme_page: str
    ebert_url: str | None = None


FILMS = [
    FilmPublicPlan("mulholland-drive", "Mulholland Drive", "David Lynch", "Mulholland Drive (film)", "David Lynch", "Surrealism", "https://www.rogerebert.com/reviews/mulholland-drive-2001"),
    FilmPublicPlan("persona", "Persona", "Ingmar Bergman", "Persona (1966 film)", "Ingmar Bergman", "Persona (psychology)", None),
    FilmPublicPlan("black-swan", "Black Swan", "Darren Aronofsky", "Black Swan (film)", "Darren Aronofsky", "Body horror", "https://www.rogerebert.com/reviews/black-swan-2010"),
    FilmPublicPlan("perfect-blue", "Perfect Blue", "Satoshi Kon", "Perfect Blue", "Satoshi Kon", "Psychological thriller", None),
    FilmPublicPlan("taxi-driver", "Taxi Driver", "Martin Scorsese", "Taxi Driver", "Martin Scorsese", "Vigilante film", None),
    FilmPublicPlan("fight-club", "Fight Club", "David Fincher", "Fight Club", "David Fincher", "Consumerism", "https://www.rogerebert.com/reviews/fight-club-1999"),
    FilmPublicPlan("the-lighthouse", "The Lighthouse", "Robert Eggers", "The Lighthouse (2019 film)", "Robert Eggers", "Psychological horror", "https://www.rogerebert.com/reviews/the-lighthouse-movie-review-2019"),
    FilmPublicPlan("shutter-island", "Shutter Island", "Martin Scorsese", "Shutter Island (film)", "Martin Scorsese", "Psychological thriller", "https://www.rogerebert.com/reviews/shutter-island-2010"),
    FilmPublicPlan("eternal-sunshine", "Eternal Sunshine of the Spotless Mind", "Michel Gondry", "Eternal Sunshine of the Spotless Mind", "Michel Gondry", "Memory", "https://www.rogerebert.com/reviews/eternal-sunshine-of-the-spotless-mind-2004"),
    FilmPublicPlan("synecdoche-new-york", "Synecdoche, New York", "Charlie Kaufman", "Synecdoche, New York", "Charlie Kaufman", "Postmodernist film", "https://www.rogerebert.com/reviews/synecdoche-new-york-2008"),
]


DOC_PLANS = [
    ("overview", "essay", "Overview", "film overview and context"),
    ("plot", "screenplay", "Plot", "public plot summary used as screenplay-proxy until licensed scripts are added"),
    ("production", "production_notes", "Production", "public production history"),
    ("themes", "academic", "Themes", "public analysis and interpretive context"),
    ("reception", "review", "Reception", "public reception summary"),
    ("legacy", "essay", "Legacy", "public influence and legacy context"),
    ("director", "interview", "Director", "public creator biographical context"),
    ("theme-context", "academic", "Theme Context", "public thematic background"),
    ("cast", "production_notes", "Cast and Performance", "public cast and performance context"),
    ("release", "production_notes", "Release", "public release and distribution context"),
    ("awards", "review", "Awards and Reception", "public awards and reception context"),
    ("critical-context", "review", "Critical Context", "public critical reception context"),
    ("director-style", "academic", "Director Style", "public director style and influence context"),
    ("genre-context", "academic", "Genre Context", "public genre and movement background"),
    ("influence-context", "essay", "Influence Context", "public influence and related-work context"),
]


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def fetch_url(url: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = slugify(url)[:180]
    cache_path = CACHE_DIR / f"{cache_key}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
        for attempt in range(4):
            response = client.get(url)
            if response.status_code != 429:
                response.raise_for_status()
                cache_path.write_text(response.text, encoding="utf-8")
                time.sleep(0.5)
                return response.text
            wait = 2 + attempt * 3
            print(f"Throttled request; waiting {wait}s")
            time.sleep(wait)
        response.raise_for_status()
        raise RuntimeError("unreachable")


def wiki_url(page: str) -> str:
    return f"https://en.wikipedia.org/wiki/{quote(page.replace(' ', '_'))}"


def wiki_soup(page: str) -> tuple[BeautifulSoup, str]:
    url = wiki_url(page)
    html = fetch_url(url)
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("div", {"id": "mw-content-text"}) or soup
    for tag in body(["style", "script", "table", "sup", "nav"]):
        tag.decompose()
    return body, url


def wiki_summary(page: str) -> tuple[str, str]:
    body, url = wiki_soup(page)
    paragraphs = []
    for child in body.find_all(["p", "h2"], recursive=True):
        if child.name == "h2":
            break
        text = child.get_text(" ", strip=True)
        if len(text) > 80:
            paragraphs.append(text)
    if not paragraphs:
        paragraphs = [p.get_text(" ", strip=True) for p in body.find_all("p")[:4]]
    return "\n\n".join(paragraphs), url


def wiki_section_text(page: str, keywords: list[str]) -> tuple[str, str]:
    body, url = wiki_soup(page)
    texts = []
    headings = body.find_all(["h2", "h3"])
    for heading in headings:
        heading_text = heading.get_text(" ", strip=True)
        if not any(keyword.lower() in heading_text.lower() for keyword in keywords):
            continue
        parts = [heading_text]
        for sibling in heading.find_next_siblings():
            if sibling.name in ["h2", "h3"]:
                break
            text = sibling.get_text(" ", strip=True)
            if len(text) > 60:
                parts.append(text)
        texts.append("\n\n".join(parts))
        if len(texts) >= 3:
            break
    return "\n\n".join(texts), url


def web_article(url: str) -> str:
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
        response_text = fetch_url(url)
    soup = BeautifulSoup(response_text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    article = soup.find("article") or soup.find("main") or soup
    return article.get_text("\n")


def write_doc(source_key: str, text: str) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = clean_text(text)
    path = RAW_DIR / f"{source_key}.txt"
    path.write_text(cleaned + "\n", encoding="utf-8")
    return str(path)


def build_doc(film: FilmPublicPlan, doc_kind: str) -> tuple[str, str]:
    if doc_kind == "overview":
        return wiki_summary(film.wikipedia_page)
    if doc_kind == "plot":
        return wiki_section_text(film.wikipedia_page, ["Plot"])
    if doc_kind == "production":
        return wiki_section_text(film.wikipedia_page, ["Production", "Development", "Filming", "Casting"])
    if doc_kind == "themes":
        return wiki_section_text(film.wikipedia_page, ["Themes", "Analysis", "Interpretation", "Style"])
    if doc_kind == "reception":
        if film.ebert_url:
            try:
                return web_article(film.ebert_url), film.ebert_url
            except Exception:
                pass
        return wiki_section_text(film.wikipedia_page, ["Reception", "Critical response"])
    if doc_kind == "legacy":
        return wiki_section_text(film.wikipedia_page, ["Legacy", "Influence", "Accolades", "Awards"])
    if doc_kind == "director":
        return wiki_summary(film.director_page)
    if doc_kind == "theme-context":
        return wiki_summary(film.theme_page)
    if doc_kind == "cast":
        return wiki_section_text(film.wikipedia_page, ["Cast"])
    if doc_kind == "release":
        return wiki_section_text(film.wikipedia_page, ["Release", "Marketing", "Distribution"])
    if doc_kind == "awards":
        return wiki_section_text(film.wikipedia_page, ["Awards", "Accolades", "Nominations"])
    if doc_kind == "critical-context":
        return wiki_section_text(film.wikipedia_page, ["Critical response", "Reception"])
    if doc_kind == "director-style":
        return wiki_section_text(film.director_page, ["Style", "Themes", "Influences", "Legacy"])
    if doc_kind == "genre-context":
        return wiki_summary(film.theme_page)
    if doc_kind == "influence-context":
        text, url = wiki_section_text(film.wikipedia_page, ["Legacy", "Influence"])
        if clean_text(text).split():
            return text, url
        return wiki_section_text(film.director_page, ["Influences", "Style", "Themes"])
    raise ValueError(f"Unknown doc kind: {doc_kind}")


def build_public_corpus() -> None:
    rows = []
    for film in FILMS:
        for doc_kind, source_type, label, note in DOC_PLANS:
            source_key = f"{film.slug}-public-{doc_kind}"
            title = f"{film.title} - {label}"
            try:
                text, url = build_doc(film, doc_kind)
                if len(clean_text(text).split()) < 120:
                    fallback, fallback_url = wiki_summary(film.wikipedia_page)
                    text = f"{title}\n\n{fallback}"
                    url = fallback_url
                local_path = write_doc(source_key, text)
            except Exception as exc:
                fallback, fallback_url = wiki_summary(film.wikipedia_page)
                local_path = write_doc(source_key, f"{title}\n\n{fallback}\n\nFetch note: {exc}")
                url = fallback_url

            rows.append(
                {
                    "film_slug": film.slug,
                    "source_key": source_key,
                    "title": title,
                    "author": "",
                    "publisher": "Wikipedia/RogerEbert public web",
                    "source_type": source_type,
                    "url": url,
                    "publication_date": "",
                    "is_primary": "false",
                    "credibility_score": "0.74" if source_type != "review" else "0.84",
                    "local_path": local_path,
                    "notes": note,
                }
            )
            print(f"Wrote {source_key}")
            time.sleep(0.2)

    with PUBLIC_SOURCES.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {PUBLIC_SOURCES} with {len(rows)} documents")


if __name__ == "__main__":
    build_public_corpus()
