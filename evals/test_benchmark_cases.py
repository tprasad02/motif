import json
from pathlib import Path

from app.services.analysis import THEME_LENS_FILMS


def test_benchmark_has_100_unique_supported_cases():
    payload = json.loads(Path("evals/benchmark_cases.json").read_text(encoding="utf-8"))
    assert {name: len(cases) for name, cases in payload.items()} == {"analyze": 24, "compare": 64, "theme": 12}
    cases = [case for group in payload.values() for case in group]
    assert len(cases) == 100
    assert len({case["id"] for case in cases}) == 100
    for case in cases:
        for film in (case.get("film_a"), case.get("film_b")):
            if film:
                assert film in THEME_LENS_FILMS[case["lens"]]
