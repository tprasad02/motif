from functools import lru_cache

from app.core.config import settings


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.sentence_bert_model)


def local_embedding(text: str) -> list[float]:
    """Return a normalized Sentence-BERT embedding for semantic retrieval."""
    return _model().encode(text or "", normalize_embeddings=True).tolist()
