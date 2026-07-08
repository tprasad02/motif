from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader


def extract_html(source: str) -> str:
    if source.startswith("http://") or source.startswith("https://"):
        html = httpx.get(source, timeout=30).text
    else:
        html = Path(source).read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text("\n")


def extract_pdf(path: str) -> str:
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def extract_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def extract_by_path(path_or_url: str) -> str:
    lowered = path_or_url.lower()
    if lowered.startswith("http://") or lowered.startswith("https://") or lowered.endswith((".html", ".htm")):
        return extract_html(path_or_url)
    if lowered.endswith(".pdf"):
        return extract_pdf(path_or_url)
    return extract_text(path_or_url)

