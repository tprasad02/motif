"""Film catalog and dynamic lens-query expansion.
"""

from __future__ import annotations

import re

from app.services.lens_profiles import selected_profile_terms


FILMS = [
    {"slug": "shawshank-redemption", "title": "The Shawshank Redemption"},
    {"slug": "fight-club", "title": "Fight Club"},
    {"slug": "one-flew-over-the-cuckoos-nest", "title": "One Flew Over the Cuckoo's Nest"},
    {"slug": "se7en", "title": "Se7en"},
    {"slug": "silence-of-the-lambs", "title": "The Silence of the Lambs"},
    {"slug": "the-prestige", "title": "The Prestige"},
    {"slug": "memento", "title": "Memento"},
    {"slug": "taxi-driver", "title": "Taxi Driver"},
    {"slug": "shutter-island", "title": "Shutter Island"},
    {"slug": "black-swan", "title": "Black Swan"},
    {"slug": "sixth-sense", "title": "The Sixth Sense"},
    {"slug": "prisoners", "title": "Prisoners"},
    {"slug": "gone-girl", "title": "Gone Girl"},
    {"slug": "requiem-for-a-dream", "title": "Requiem for a Dream"},
    {"slug": "donnie-darko", "title": "Donnie Darko"},
    {"slug": "the-machinist", "title": "The Machinist"},
    {"slug": "mulholland-drive", "title": "Mulholland Drive"},
    {"slug": "truman-show", "title": "The Truman Show"},
]

FILM_TITLES = {film["slug"]: film["title"] for film in FILMS}


def _terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [value, *re.findall(r"[A-Za-z][A-Za-z'-]+", value)]


def _dedupe(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        normalized = str(term).strip()
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            result.append(normalized)
    return result


def expand_lens_terms(lens: str | None) -> list[str]:
    """Return the user-selected direct lens without a static vocabulary."""
    return _dedupe(_terms(lens))


def expand_film_lens_terms(film_slug: str | None, lens: str | None) -> list[str]:
    """Expand only from the evidence-backed direct profile definition."""
    if not lens:
        return []
    values = selected_profile_terms(film_slug, lens) if film_slug else [lens]
    return _dedupe([term for value in values for term in _terms(value)])
