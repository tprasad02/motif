from collections import Counter

from app.db.postgres import fetch_source_metadata
from app.models import AnalysisResponse, RetrieveResponse, RetrievedChunkResponse, SourceCitation
from app.prompts.interpretation import build_interpretation_prompt
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


def coverage_level(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def retrieval_response(query: str, chunks: list[RetrievedChunk]) -> RetrieveResponse:
    score = coverage_score(chunks)
    level = coverage_level(score)
    if not chunks:
        notes = "No chunks were retrieved. Ingest source documents before asking interpretive questions."
    elif level == "low":
        notes = "Low coverage: retrieved evidence is too narrow for a trustworthy synthesis."
    else:
        notes = "Retrieved top-k vector matches from the curated Motif corpus."
    return RetrieveResponse(
        query=query,
        chunks=[RetrievedChunkResponse(**chunk.__dict__) for chunk in chunks],
        coverage_score=score,
        coverage_level=level,
        retrieval_notes=notes,
    )


def synthesize(request_query: str, chunks: list[RetrievedChunk]) -> AnalysisResponse:
    source_keys = sorted({chunk.source_key for chunk in chunks})
    source_metadata = fetch_source_metadata(source_keys)
    citations = []
    for chunk in chunks:
        meta = source_metadata.get(chunk.source_key)
        if not meta:
            continue
        citations.append(
            SourceCitation(
                **meta,
                chunk_id=chunk.chunk_id,
                film_slug=chunk.film_slug,
                score=round(chunk.score, 3),
                excerpt=chunk.text[:360],
            )
        )

    films = [film for film, _ in Counter(chunk.film_slug for chunk in chunks).most_common()]
    types = {chunk.source_type for chunk in chunks}
    score = coverage_score(chunks)
    level = coverage_level(score)
    refused = level == "low"

    if refused:
        note = "Refused: the corpus evidence is insufficient for a grounded Motif answer. Add more ingested source types or broaden filters."
    else:
        context = "\n\n".join(
            f"[{chunk.chunk_id}] {chunk.film_slug} / {chunk.source_key} / {chunk.source_type}\n{chunk.text}"
            for chunk in chunks[:8]
        )
        prompt = build_interpretation_prompt(request_query, context)
        note = f"Grounded draft from retrieved evidence. Prompt prepared for LLM synthesis ({len(prompt)} chars)."

    context_hint = " ".join(chunk.text[:240] for chunk in chunks[:4]).strip()
    if not context_hint:
        context_hint = "No supporting chunks were retrieved."

    if refused:
        consensus = "I cannot provide a grounded consensus interpretation from the current retrieved evidence."
        alternatives = []
    else:
        consensus = f"Evidence retrieved for '{request_query}' clusters around: {context_hint}"
        alternatives = [
            "Map minority readings from academic, essay, and video-essay sources once the corpus is fully ingested.",
            "Separate symbolic, psychological, industrial, and autobiographical interpretations during synthesis.",
        ]

    return AnalysisResponse(
        consensus_interpretation=consensus,
        alternative_interpretations=alternatives,
        director_creator_perspective="Primary-source coverage found." if "interview" in types or "production_notes" in types else "No creator-perspective source retrieved for this query.",
        critical_reception="Review and essay coverage found." if "review" in types or "essay" in types else "No critical reception source retrieved for this query.",
        related_films=films[1:6],
        cited_sources=citations,
        coverage_score=score,
        coverage_level=level,
        refused=refused,
        retrieval_notes=note,
    )


def retrieve_query(query: str, film_slugs: list[str], source_types: list[str], top_k: int) -> RetrieveResponse:
    chunks = retrieve_chunks(query=query, film_slugs=film_slugs, source_types=source_types, limit=top_k)
    return retrieval_response(query, chunks)


def answer_query(query: str, film_slugs: list[str], source_types: list[str], top_k: int) -> AnalysisResponse:
    chunks = retrieve_chunks(query=query, film_slugs=film_slugs, source_types=source_types, limit=top_k)
    return synthesize(query, chunks)
