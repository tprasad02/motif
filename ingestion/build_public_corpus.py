import csv
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from ingestion.cleaning import clean_text


RAW_DIR = Path("data/raw/public")
CACHE_DIR = Path("data/raw/public_cache")
PUBLIC_SOURCES = Path("data/public_sources.csv")
MISSING_REPORT = Path("data/manual_curation_needed.csv")
USER_AGENT = "MotifCinemaResearch/1.0 (+public-source-audit)"
MIN_WORDS = 140
TARGET_PER_FILM = 8
MAX_PER_FILM = 12


@dataclass(frozen=True)
class FilmPlan:
    slug: str
    title: str
    director: str
    year: int


@dataclass(frozen=True)
class SourceSlot:
    key: str
    source_type: str
    label: str
    queries: tuple[str, ...]
    domains: tuple[str, ...]
    is_primary: bool = False
    required: bool = False


FILMS = [
    FilmPlan("shawshank-redemption", "The Shawshank Redemption", "Frank Darabont", 1994),
    FilmPlan("fight-club", "Fight Club", "David Fincher", 1999),
    FilmPlan("one-flew-over-the-cuckoos-nest", "One Flew Over the Cuckoo's Nest", "Milos Forman", 1975),
    FilmPlan("se7en", "Se7en", "David Fincher", 1995),
    FilmPlan("silence-of-the-lambs", "The Silence of the Lambs", "Jonathan Demme", 1991),
    FilmPlan("the-prestige", "The Prestige", "Christopher Nolan", 2006),
    FilmPlan("memento", "Memento", "Christopher Nolan", 2000),
    FilmPlan("taxi-driver", "Taxi Driver", "Martin Scorsese", 1976),
    FilmPlan("shutter-island", "Shutter Island", "Martin Scorsese", 2010),
    FilmPlan("black-swan", "Black Swan", "Darren Aronofsky", 2010),
    FilmPlan("sixth-sense", "The Sixth Sense", "M. Night Shyamalan", 1999),
    FilmPlan("prisoners", "Prisoners", "Denis Villeneuve", 2013),
    FilmPlan("gone-girl", "Gone Girl", "David Fincher", 2014),
    FilmPlan("requiem-for-a-dream", "Requiem for a Dream", "Darren Aronofsky", 2000),
    FilmPlan("donnie-darko", "Donnie Darko", "Richard Kelly", 2001),
    FilmPlan("the-machinist", "The Machinist", "Brad Anderson", 2004),
    FilmPlan("mulholland-drive", "Mulholland Drive", "David Lynch", 2001),
    FilmPlan("truman-show", "The Truman Show", "Peter Weir", 1998),
]


DIRECT_URLS = {
    ("shawshank-redemption", "screenplay"): ("https://imsdb.com/scripts/Shawshank-Redemption,-The.html",),
    ("fight-club", "screenplay"): ("https://imsdb.com/scripts/Fight-Club.html",),
    ("one-flew-over-the-cuckoos-nest", "screenplay"): ("https://imsdb.com/scripts/One-Flew-Over-the-Cuckoo's-Nest.html",),
    ("se7en", "screenplay"): ("https://imsdb.com/scripts/Se7en.html",),
    ("silence-of-the-lambs", "screenplay"): ("https://imsdb.com/scripts/Silence-of-the-Lambs,-The.html",),
    ("the-prestige", "screenplay"): ("https://imsdb.com/scripts/Prestige,-The.html",),
    ("memento", "screenplay"): ("https://imsdb.com/scripts/Memento.html",),
    ("taxi-driver", "screenplay"): ("https://www.imsdb.com/scripts/Taxi-Driver.html",),
    ("shutter-island", "screenplay"): ("https://www.scriptslug.com/script/shutter-island-2010",),
    ("black-swan", "screenplay"): ("https://imsdb.com/scripts/Black-Swan.html",),
    ("sixth-sense", "screenplay"): ("https://imsdb.com/scripts/Sixth-Sense,-The.html",),
    ("prisoners", "screenplay"): ("https://www.scriptslug.com/script/prisoners-2013",),
    ("gone-girl", "screenplay"): ("https://www.scriptslug.com/script/gone-girl-2014",),
    ("requiem-for-a-dream", "screenplay"): ("https://www.scriptslug.com/script/requiem-for-a-dream-2000",),
    ("donnie-darko", "screenplay"): ("https://www.scriptslug.com/script/donnie-darko-2001",),
    ("the-machinist", "screenplay"): ("https://www.scriptslug.com/script/the-machinist-2004",),
    ("mulholland-drive", "screenplay"): ("https://imsdb.com/scripts/Mulholland-Drive.html",),
    ("truman-show", "screenplay"): ("https://imsdb.com/scripts/Truman-Show,-The.html",),
}


SLOTS = [
    SourceSlot(
        "screenplay",
        "screenplay",
        "Screenplay",
        ("{title} screenplay", "{title} script pdf", "{title} script"),
        ("imsdb.com", "scriptslug.com", "dailyscript.com", "script-o-rama.com", "screenplays.io", "scriptpdf.com"),
        True,
        True,
    ),
    SourceSlot(
        "director-interview-1",
        "interview",
        "Director Interview",
        ("{title} {director} interview", "{title} director interview"),
        ("indiewire.com", "variety.com", "collider.com", "deadline.com", "bfi.org.uk", "filmmakermagazine.com", "moviemaker.com", "slashfilm.com", "criterion.com", "npr.org", "academy.org"),
        True,
        True,
    ),
    SourceSlot(
        "director-interview-2",
        "interview",
        "Second Director Interview",
        ("{director} interview {title}", "{title} filmmaker interview"),
        ("indiewire.com", "variety.com", "collider.com", "deadline.com", "bfi.org.uk", "filmmakermagazine.com", "moviemaker.com", "slashfilm.com", "criterion.com", "npr.org", "academy.org"),
        True,
    ),
    SourceSlot(
        "festival-qa",
        "festival_qa",
        "Festival or Academy Q&A",
        ("{title} {director} Q&A", "{title} TIFF Q&A", "{title} BFI Q&A", "{title} Academy conversation"),
        ("youtube.com", "youtu.be", "tiff.net", "festival-cannes.com", "labiennale.org", "sundance.org", "bfi.org.uk", "oscars.org", "academy.org"),
        True,
    ),
    SourceSlot(
        "production-notes",
        "production_notes",
        "Production Notes or Press Kit",
        ("{title} production notes pdf", "{title} press kit pdf", "{title} AFI Catalog"),
        ("catalog.afi.com", "afi.com", "oscars.org", "focusfeatures.com", "sonyclassics.com", "warnerbros.com", "paramount.com", "lionsgatepublicity.com", "filmratings.com"),
        True,
        True,
    ),
    SourceSlot(
        "academic-1",
        "academic",
        "Open Academic Paper",
        ("{title} open access academic film analysis", "{title} scholarly analysis film", "{title} university repository film analysis"),
        ("core.ac.uk", "doaj.org", "semanticscholar.org", "researchgate.net", "sensesofcinema.com", "film-philosophy.com", "offscreen.com", "ejumpcut.org", "brightlightsfilm.com"),
    ),
    SourceSlot(
        "academic-2",
        "academic",
        "Second Open Academic Paper",
        ("{title} academic paper pdf film", "{title} film journal analysis", "{title} psychoanalysis film essay"),
        ("core.ac.uk", "doaj.org", "semanticscholar.org", "researchgate.net", "sensesofcinema.com", "film-philosophy.com", "offscreen.com", "ejumpcut.org", "brightlightsfilm.com"),
    ),
    SourceSlot(
        "educational-essay",
        "educational_essay",
        "Educational Essay",
        ("{title} BFI essay", "{title} MoMA film essay", "{title} Film at Lincoln Center essay", "{title} Academy Museum essay"),
        ("bfi.org.uk", "moma.org", "filmlinc.org", "academymuseum.org", "criterion.com", "sensesofcinema.com", "museumoffilmhistory.org"),
    ),
    SourceSlot(
        "video-essay",
        "video_essay_transcript",
        "Video Essay Transcript",
        ("{title} video essay", "{title} Lessons from the Screenplay", "{title} StudioBinder analysis"),
        ("youtube.com", "youtu.be", "studiobinder.com", "lessonsfromthescreenplay.com", "nerdwriter.com"),
    ),
    SourceSlot(
        "cast-interview",
        "cast_interview",
        "Cast Interview",
        ("{title} cast interview", "{title} actor interview character"),
        ("variety.com", "collider.com", "hollywoodreporter.com", "deadline.com", "npr.org", "interviewmagazine.com", "academy.org"),
        True,
    ),
    SourceSlot(
        "craft-article",
        "craft_article",
        "Cinematography or Craft Article",
        ("{title} cinematography article", "{title} American Cinematographer", "{title} production design craft"),
        ("theasc.com", "studiobinder.com", "kodak.com", "filmmakermagazine.com", "bfi.org.uk", "britishcinematographer.co.uk"),
    ),
    SourceSlot(
        "film-history",
        "film_history",
        "Film History Context",
        ("{title} film history article", "{title} BFI history", "{title} Britannica film"),
        ("bfi.org.uk", "britannica.com", "afi.com", "catalog.afi.com", "moma.org", "filmlinc.org"),
    ),
]


BLOCKED_DOMAINS = {
    "wikipedia.org",
    "imdb.com",
    "rottentomatoes.com",
    "metacritic.com",
    "fandom.com",
    "screenrant.com",
    "cbr.com",
    "looper.com",
}


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def domain_for(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def unwrap_duckduckgo(href: str) -> str:
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc:
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return href


def cache_path_for(url: str, suffix: str = ".html") -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{slugify(url)[:190]}{suffix}"


def get_url(url: str) -> str:
    cache_path = cache_path_for(url)
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=22, follow_redirects=True, verify=False) as client:
        response = client.get(url)
        response.raise_for_status()
        cache_path.write_text(response.text, encoding="utf-8")
        time.sleep(0.45)
        return response.text


def search(query: str) -> list[str]:
    try:
        results = duckduckgo_search(query)
    except Exception:
        results = []
    if results:
        return results
    return bing_search(query)


def duckduckgo_search(query: str) -> list[str]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    html = get_url(url)
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for anchor in soup.select(".result__a"):
        href = unwrap_duckduckgo(anchor.get("href", ""))
        if href.startswith("http") and href not in urls:
            urls.append(href)
    return urls


def bing_search(query: str) -> list[str]:
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    html = get_url(url)
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for anchor in soup.select("li.b_algo h2 a, .b_title a"):
        href = anchor.get("href", "")
        if href.startswith("http") and href not in urls:
            urls.append(href)
    return urls


def html_text(url: str) -> str:
    html = get_url(url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()
    article = soup.find("article") or soup.find("main") or soup
    title = soup.find("title")
    title_text = title.get_text(" ", strip=True) if title else url
    return f"{title_text}\n\n{article.get_text(chr(10), strip=True)}"


def youtube_transcript(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{8,})", url)
    if not match:
        raise ValueError("no YouTube video id")
    video_id = match.group(1)
    timedtext = f"https://video.google.com/timedtext?lang=en&v={video_id}"
    xml = get_url(timedtext)
    soup = BeautifulSoup(xml, "html.parser")
    pieces = [node.get_text(" ", strip=True) for node in soup.find_all("text")]
    if not pieces:
        raise ValueError("no public transcript")
    return "\n".join(pieces)


def extract_text(url: str) -> str:
    domain = domain_for(url)
    if domain in {"youtube.com", "youtu.be"}:
        return youtube_transcript(url)
    return html_text(url)


def acceptable(url: str, domains: tuple[str, ...], used_urls: set[str], used_domains: set[str]) -> bool:
    if url in used_urls:
        return False
    domain = domain_for(url)
    if any(domain == blocked or domain.endswith(f".{blocked}") for blocked in BLOCKED_DOMAINS):
        return False
    if domain in used_domains:
        return False
    return any(domain == allowed or domain.endswith(f".{allowed}") for allowed in domains)


def write_doc(source_key: str, text: str) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{source_key}.txt"
    path.write_text(clean_text(text) + "\n", encoding="utf-8")
    return str(path)


def row_for(film: FilmPlan, slot: SourceSlot, url: str, text: str) -> dict:
    domain = domain_for(url)
    source_key = f"{film.slug}-{slot.key}-{slugify(domain)}"
    local_path = write_doc(source_key, f"{film.title} - {slot.label}\n{url}\n\n{text}")
    score = "0.94" if slot.is_primary else "0.88"
    if slot.source_type in {"academic", "educational_essay", "craft_article", "film_history"}:
        score = "0.9"
    return {
        "film_slug": film.slug,
        "source_key": source_key,
        "title": f"{film.title} - {slot.label}",
        "author": "",
        "publisher": domain,
        "source_type": slot.source_type,
        "url": url,
        "publication_date": "",
        "is_primary": "true" if slot.is_primary else "false",
        "credibility_score": score,
        "local_path": local_path,
        "notes": f"Curated {slot.label.lower()} source for the new 20-film corpus.",
    }


def build_slot(film: FilmPlan, slot: SourceSlot, used_urls: set[str], used_domains: set[str]) -> dict | None:
    candidates = list(DIRECT_URLS.get((film.slug, slot.key), ()))
    for template in slot.queries:
        query = template.format(title=f"{film.title} {film.year}", director=film.director)
        try:
            candidates.extend(search(query))
        except Exception as exc:
            print(f"Search failed {film.slug}/{slot.key}: {exc}", flush=True)
    for url in candidates:
        if not acceptable(url, slot.domains, used_urls, used_domains):
            continue
        try:
            cleaned = clean_text(extract_text(url))
        except Exception as exc:
            print(f"Skip {film.slug}/{slot.key}: {url} ({exc})", flush=True)
            continue
        if len(cleaned.split()) < MIN_WORDS:
            print(f"Skip {film.slug}/{slot.key}: {url} (too short)", flush=True)
            continue
        used_urls.add(url)
        used_domains.add(domain_for(url))
        return row_for(film, slot, url, cleaned)
    return None


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_public_corpus() -> None:
    rows = []
    missing = []
    for film in FILMS:
        film_rows = []
        used_urls: set[str] = set()
        used_domains: set[str] = set()
        for slot in SLOTS:
            if len(film_rows) >= MAX_PER_FILM:
                break
            row = build_slot(film, slot, used_urls, used_domains)
            if row:
                film_rows.append(row)
                print(f"Wrote {row['source_key']}", flush=True)
            elif slot.required:
                missing.append(
                    {
                        "film_slug": film.slug,
                        "title": film.title,
                        "slot": slot.key,
                        "source_type": slot.source_type,
                        "needed": slot.label,
                        "suggested_queries": " | ".join(
                            query.format(title=f"{film.title} {film.year}", director=film.director)
                            for query in slot.queries
                        ),
                    }
                )
                print(f"FAILED required {film.slug}/{slot.key}", flush=True)
        if len(film_rows) < TARGET_PER_FILM:
            missing.append(
                {
                    "film_slug": film.slug,
                    "title": film.title,
                    "slot": "minimum-count",
                    "source_type": "mixed",
                    "needed": f"{TARGET_PER_FILM - len(film_rows)} more verified public sources",
                    "suggested_queries": f"{film.title} {film.year} interview essay screenplay production notes",
                }
            )
        rows.extend(film_rows)

    write_csv(PUBLIC_SOURCES, rows)
    if missing:
        write_csv(MISSING_REPORT, missing)
        print(f"Wrote {PUBLIC_SOURCES} with {len(rows)} verified documents")
        print(f"Wrote {MISSING_REPORT} with {len(missing)} gaps")
        raise SystemExit(1)
    if MISSING_REPORT.exists():
        MISSING_REPORT.unlink()
    print(f"Wrote {PUBLIC_SOURCES} with {len(rows)} verified documents")


if __name__ == "__main__":
    build_public_corpus()
