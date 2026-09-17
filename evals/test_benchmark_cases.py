import json
from pathlib import Path

def test_benchmark_has_100_unique_supported_cases():
    payload = json.loads(Path("evals/benchmark_cases.json").read_text(encoding="utf-8"))
    assert {name: len(cases) for name, cases in payload.items()} == {"analyze": 24, "compare": 64, "lens": 12}
    cases = [case for group in payload.values() for case in group]
    assert len(cases) == 100
    assert len({case["id"] for case in cases}) == 100
