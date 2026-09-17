from functools import lru_cache
import math

from app.core.config import settings


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    # The model is provisioned during setup. Avoid a remote revision check on
    # every request so retrieval remains available offline and deterministic.
    return SentenceTransformer(settings.sentence_bert_model, local_files_only=True)


def local_embedding(text: str) -> list[float]:
    """Return a normalized Sentence-BERT embedding for semantic retrieval."""
    return _model().encode(text or "", normalize_embeddings=True).tolist()


def local_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed a small group in one model invocation.

    Sentence-BERT has meaningful per-call overhead on the production CPU.
    Batching avoids turning one comparison into dozens of inferences.
    """
    if not texts:
        return []
    return _model().encode(texts, normalize_embeddings=True, batch_size=64).tolist()


def openai_embedding(text: str) -> list[float]:
    """Return a normalized OpenAI query embedding without loading PyTorch."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    response = OpenAI(api_key=settings.openai_api_key).embeddings.create(
        model=settings.openai_embedding_model,
        input=text or "",
    )
    vector = response.data[0].embedding
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]
