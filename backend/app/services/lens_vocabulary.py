"""Versioned corpus-level vocabulary for reusable, one-word lenses."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

VOCABULARY_PATH = Path(__file__).resolve().parents[1] / "corpus" / "lens_vocabulary.json"


@lru_cache(maxsize=1)
def lenses() -> list[dict]:
    try:
        payload = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
        return [row for row in payload.get("lenses", []) if row.get("status") == "published"]
    except (OSError, json.JSONDecodeError):
        return []


def reload_lenses() -> None:
    lenses.cache_clear()
