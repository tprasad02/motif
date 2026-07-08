from collections import Counter

from app.db.postgres import fetch_source_metadata
from app.models import AnalysisResponse, SourceCitation
from app.services.retrieval import RetrievedChunk, retrieve_chunks


def coverage_score(chunks: list[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    source_types = {chunk.source_type for chunk in chunks if chunk.source_type}
    films = {chunk.film_slug for chunk in chunks if chunk.film_slug}
    type_component = min(len(source_types) / 5, 1.0)
    volume_component = min(len(chunks) / 12, 1.0)
    film_component = min(len(films) / 2, 1.0)
    return round((type_component * 0.45) + (volume_component * 0.35) + (film_component * 0.20), 2)


def synthesize(request_query: str, chunks: list[RetrievedChunk]) -> AnalysisResponse:
    source_keys = sorted({chunk.source_key for chunk in chunks})
    source_metadata = fetch_source_metadata(source_keys)
    citations = []
    for chunk in chunks:
        meta = source_metadata.get(chunk.source_key)
        if not meta:
            continue
        citations.append(SourceCitation(**meta, chunk_id=chunk.chunk_id))

    films = [film for film, _ in Counter(chunk.film_slug for chunk in chunks).most_common()]
    types = {chunk.source_type for chunk in chunks}
    score = coverage_score(chunks)

    if score < 0.35:
        note = "Insufficient corpus coverage. Add more source types before trusting synthesis."
    else:
        note = "Draft synthesis from retrieved evidence. Replace template synthesis with an LLM call after API credentials are configured."

    context_hint = " ".join(chunk.text[:240] for chunk in chunks[:4]).strip()
    if not context_hint:
        context_hint = "No supporting chunks were retrieved."

    return AnalysisResponse(
        consensus_interpretation=f"Evidence retrieved for '{request_query}' clusters around: {context_hint}",
        alternative_interpretations=[
            "Map minority readings from academic, essay, and video-essay sources once the corpus is fully ingested.",
            "Separate symbolic, psychological, industrial, and autobiographical interpretations during synthesis.",
        ],
        director_creator_perspective="Primary-source coverage found." if "interview" in types or "production_notes" in types else "No creator-perspective source retrieved for this query.",
        critical_reception="Review and essay coverage found." if "review" in types or "essay" in types else "No critical reception source retrieved for this query.",
        related_films=films[1:6],
        cited_sources=citations,
        coverage_score=score,
        retrieval_notes=note,
    )


def analyze_query(query: str, film_slugs: list[str], max_chunks: int) -> AnalysisResponse:
    chunks = retrieve_chunks(query=query, film_slugs=film_slugs, limit=max_chunks)
    return synthesize(query, chunks)

