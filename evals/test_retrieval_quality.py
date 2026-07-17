import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.retrieval import _bm25_search, _merge_dedupe, _postgres_vector_search, _rerank

QUERIES = [
    ("memento", "Memory", "Analyze Memento through Memory."),
    ("donnie-darko", "Reality vs Illusion", "Analyze Donnie Darko through Reality vs Illusion."),
    ("black-swan", "Performance", "Analyze Black Swan through Performance."),
    ("the-machinist", "Guilt", "Analyze The Machinist through Guilt."),
    ("taxi-driver", "Alienation", "Analyze Taxi Driver through Alienation."),
]


def reciprocal_rank(chunks, expected_film: str) -> float:
    for index, chunk in enumerate(chunks, start=1):
        if chunk.film_slug == expected_film:
            return 1 / index
    return 0.0


def main() -> None:
    before = []
    after = []
    for expected_film, lens, query in QUERIES:
        vector = _postgres_vector_search(query, [expected_film], [], 25, lens_tags=[lens])
        bm25 = _bm25_search(query, [expected_film], [], 25, lens_tags=[lens])
        hybrid = _rerank(query, _merge_dedupe(vector, bm25), [lens])[:12]
        before_score = reciprocal_rank(vector[:12], expected_film)
        after_score = reciprocal_rank(hybrid, expected_film)
        before.append(before_score)
        after.append(after_score)
        print(f"{query}")
        print(f"  vector_mrr={before_score:.2f} top={[chunk.film_slug for chunk in vector[:5]]}")
        print(f"  hybrid_mrr={after_score:.2f} top={[chunk.film_slug for chunk in hybrid[:5]]}")

    print(f"mean_vector_mrr={sum(before)/len(before):.2f}")
    print(f"mean_hybrid_mrr={sum(after)/len(after):.2f}")


if __name__ == "__main__":
    main()
