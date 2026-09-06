"""Published, evidence-gated film lens profiles.

This is intentionally the runtime source of truth for selectable lenses. Each
published profile pairs one canonical, one-word lens with a short film-specific
angle. Only profiles that pass semantic evidence and answer-quality validation
are exposed to users.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROFILE_PATH = Path(__file__).resolve().parents[1] / "corpus" / "lens_profiles.json"
PROFILE_SCHEMA_VERSION = 2


def _valid_angle(value: object) -> bool:
    words = str(value or "").split()
    return 2 <= len(words) <= 5


@lru_cache(maxsize=1)
def load_profiles() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        return {"films": {}}
    try:
        payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != PROFILE_SCHEMA_VERSION:
            return {"films": {}}
        return payload
    except (OSError, json.JSONDecodeError):
        return {"films": {}}


def reload_profiles() -> None:
    load_profiles.cache_clear()


def published_lenses(film_slug: str) -> list[dict[str, Any]]:
    film = load_profiles().get("films", {}).get(film_slug, {})
    rows = [
        row
        for row in film.get("lenses", [])
        if row.get("status") == "published" and row.get("lens") and _valid_angle(row.get("angle"))
    ]
    # One button per broad lens; retain the strongest film-specific angle.
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("lens_id") or row.get("lens") or "")
        if key and (key not in best or row.get("semantic_score", 0) > best[key].get("semantic_score", 0)):
            best[key] = row
    return sorted(best.values(), key=lambda row: row.get("semantic_score", 0), reverse=True)


def lens_names(film_slug: str) -> list[str]:
    return [str(row["lens"]) for row in published_lenses(film_slug) if row.get("lens")]


def is_published_lens(film_slug: str, lens: str) -> bool:
    return lens in lens_names(film_slug)


def shared_lenses(film_a: str, film_b: str) -> list[str]:
    return sorted(set(lens_names(film_a)).intersection(lens_names(film_b)))


def all_published_lenses() -> list[str]:
    return sorted({lens for profiles in load_profiles().get("films", {}).values() for row in profiles.get("lenses", []) if row.get("status") == "published" for lens in [str(row.get("lens", ""))] if lens})
