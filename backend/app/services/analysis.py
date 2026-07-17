import json
import re
from collections import Counter
from pathlib import Path

import httpx

from app.core.config import settings
from app.db.postgres import fetch_source_metadata
from app.film_config import FILM_LENSES, FILM_TITLES
from app.models import (
    AnalysisResponse,
    AnswerRequest,
    FilmComparisonResponse,
    GuidedAnswerRequest,
    InterpretationMapResponse,
    RetrieveResponse,
    RetrievedChunkResponse,
    SourceCitation,
    ThemeExplorerResponse,
)
from app.services.retrieval import RetrievedChunk, retrieve_chunks


EVIDENCE_JOBS = ["Scene or Motif", "Formal Technique", "Character or Performance", "Ambiguity or Counterreading"]
BANNED_PHRASES = [
    "at its core",
    "profound exploration",
    "complex interplay",
    "the human condition",
    "serves as a metaphor",
    "invites the viewer",
]


def coverage_score(chunks: list[RetrievedChunk], required_films: list[str] | None = None) -> float:
    if not chunks:
        return 0.0
    source_keys = {chunk.source_key for chunk in chunks}
    source_roles = {chunk.source_role for chunk in chunks if chunk.source_role}
    films = {chunk.film_slug for chunk in chunks if chunk.film_slug}
    volume_component = min(len(source_keys) / 6, 1.0)
    role_component = min(len(source_roles) / 4, 1.0)
    if required_films and len(required_films) > 1:
        film_component = len(set(required_films).intersection(films)) / len(set(required_films))
    else:
        film_component = 1.0 if films else 0.0
    return round((volume_component * 0.42) + (role_component * 0.34) + (film_component * 0.24), 2)


def coverage_level(score: float) -> str:
    if score >= 0.72:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _display_title(slug: str | None) -> str:
    if not slug:
        return ""
    return FILM_TITLES.get(slug, slug.replace("-", " ").title())


def _film_slugs_for_request(request: GuidedAnswerRequest) -> list[str]:
    if request.mode == "compare_films":
        return [slug for slug in [request.film_a, request.film_b] if slug]
    if request.mode == "explore_theme":
        return []
    return [request.film_a] if request.film_a else []


def _query_for_request(request: GuidedAnswerRequest) -> str:
    angle = f" Angle: {request.optional_question.strip()}" if request.optional_question else ""
    film_lenses = " ".join(
        lens
        for slug in _film_slugs_for_request(request)
        for lens in FILM_LENSES.get(slug, [])
    )
    if request.mode == "compare_films":
        return f"Compare {_display_title(request.film_a)} and {_display_title(request.film_b)} through {request.lens}. Related lenses: {film_lenses}.{angle}"
    if request.mode == "explore_theme":
        return f"Explore {request.lens} across the indexed film collection.{angle}"
    return f"Analyze {_display_title(request.film_a)} through {request.lens}. Related lenses: {film_lenses}.{angle}"


def _normalize_answer_request(request: AnswerRequest) -> GuidedAnswerRequest:
    if request.mode:
        return GuidedAnswerRequest(
            mode=request.mode,
            film_a=request.film_a or (request.film_slugs[0] if request.film_slugs else None),
            film_b=request.film_b or (request.film_slugs[1] if len(request.film_slugs) > 1 else None),
            lens=request.lens or (request.themes[0] if request.themes else "Identity"),
            optional_question=request.optional_question or request.query,
            top_k=min(max(request.top_k, 8), 12),
            include_debug=request.include_debug,
            include_low_quality=request.include_low_quality,
        )

    film_a = request.film_slugs[0] if request.film_slugs else None
    film_b = request.film_slugs[1] if len(request.film_slugs) > 1 else None
    mode = "compare_films" if film_b else "analyze_film"
    return GuidedAnswerRequest(
        mode=mode,
        film_a=film_a,
        film_b=film_b,
        lens=request.themes[0] if request.themes else "Identity",
        optional_question=request.query,
        top_k=min(max(request.top_k, 8), 12),
        include_debug=request.include_debug,
        include_low_quality=request.include_low_quality,
    )


def _citations(chunks: list[RetrievedChunk]) -> list[SourceCitation]:
    source_keys = sorted({chunk.source_key for chunk in chunks})
    source_metadata = fetch_source_metadata(source_keys)
    citations: list[SourceCitation] = []
    seen_sources = set()
    for chunk in chunks:
        if chunk.source_key in seen_sources:
            continue
        meta = source_metadata.get(chunk.source_key)
        if not meta:
            continue
        seen_sources.add(chunk.source_key)
        citation_meta = {
            key: value
            for key, value in meta.items()
            if key in SourceCitation.model_fields and key not in {"chunk_id", "film_slug", "score", "excerpt", "trail_note"}
        }
        citations.append(
            SourceCitation(
                **citation_meta,
                chunk_id=chunk.chunk_id,
                film_slug=chunk.film_slug,
                score=round(chunk.score, 3),
                excerpt=chunk.text[:420],
                trail_note=None,
            )
        )
    return citations


def _debug_chunks(chunks: list[RetrievedChunk], include_debug: bool) -> list[RetrievedChunkResponse]:
    if not include_debug:
        return []
    return [RetrievedChunkResponse(**{**chunk.__dict__, "lens_tags": chunk.lens_tags or []}) for chunk in chunks]


def _context(chunks: list[RetrievedChunk]) -> str:
    source_metadata = fetch_source_metadata(sorted({chunk.source_key for chunk in chunks}))
    lines = []
    for index, chunk in enumerate(chunks, start=1):
        meta = source_metadata.get(chunk.source_key, {})
        lines.append(
            "\n".join(
                [
                    f"[{index}] Film: {_display_title(chunk.film_slug)}",
                    f"Title: {meta.get('title', chunk.source_key)}",
                    f"Chunk ID: {chunk.chunk_id}",
                    f"Section: {chunk.section_title or 'Untitled'}",
                    f"Role: {chunk.chunk_role}; Source role: {chunk.source_role}; Quality: {chunk.quality_score}",
                    f"Text: {chunk.text}",
                ]
            )
        )
    return "\n\n---\n\n".join(lines)


def _system_prompt(mode: str) -> str:
    return (
        "You are Motif, a film close-reading assistant. Produce an evidence board, not an essay. "
        "Write plainly. Avoid grand philosophical language, plot summary, and claims about people or humanity in general. "
        "Do not use these phrases: at its core, profound exploration, complex interplay, the human condition, serves as a metaphor, invites the viewer. "
        "Explain what the film does, how it does it, and why that matters. "
        "Use only retrieved context and attach chunk IDs to each evidence item. "
        "Return strict JSON with keys: thesis, evidence_1, evidence_2, evidence_3, evidence_4. "
        "The thesis must be 30-60 words, one or two sentences, mention the selected film and lens directly, and make a film-bound arguable claim. "
        "Each evidence item must be an object with keys: label, title, body, chunk_ids. "
        "The four labels must be exactly: Scene or Motif, Formal Technique, Character or Performance, Ambiguity or Counterreading. "
        "Each body must be 80-140 words and must mention a visible or audible film element: a scene, image, line, camera movement, cut, sound cue, color, performance detail, prop, setting, structure, or repeated motif."
    )


def _user_prompt(request: GuidedAnswerRequest, chunks: list[RetrievedChunk]) -> str:
    films = ", ".join(_display_title(slug) for slug in _film_slugs_for_request(request)) or "the indexed collection"
    return f"""
Workflow: {request.mode}
Selected film(s): {films}
Lens: {request.lens}
Optional angle: {request.optional_question or "None"}

Retrieved context:
{_context(chunks)}
""".strip()


def _fallback_answer(request: GuidedAnswerRequest, chunks: list[RetrievedChunk]) -> dict:
    film = _display_title(request.film_a) if request.mode != "explore_theme" else "the selected films"
    thesis = f"{film} treats {request.lens} as something the film builds through repeated scenes and formal choices, not as a theme stated in dialogue."
    cards = []
    for label, chunk in zip(EVIDENCE_JOBS, chunks[:4]):
        cards.append(
            {
                "label": label,
                "title": chunk.section_title or label,
                "body": (
                    f"This point comes from {chunk.chunk_role.replace('_', ' ')} in {chunk.source_type.replace('_', ' ')}. "
                    f"The relevant film detail is: {chunk.text[:520].strip()}"
                )[:760],
                "chunk_ids": [chunk.chunk_id],
            }
        )
    while len(cards) < 4:
        label = EVIDENCE_JOBS[len(cards)]
        cards.append({"label": label, "title": label, "body": "The current retrieval pass did not find enough concrete film evidence for this slot.", "chunk_ids": []})
    return {"thesis": thesis, "evidence_1": cards[0], "evidence_2": cards[1], "evidence_3": cards[2], "evidence_4": cards[3]}


def _puter_token_from_deployment_doc() -> str | None:
    for candidate in [
        Path("docs/deployment.md"),
        Path(__file__).resolve().parents[3] / "docs" / "deployment.md",
    ]:
        if not candidate.exists():
            continue
        match = re.search(r"^PUTER_AUTH_TOKEN=(.+)$", candidate.read_text(encoding="utf-8"), re.MULTILINE)
        if not match:
            continue
        token = match.group(1).strip()
        if token and not token.startswith("<"):
            return token
    return None


def _plan_evidence(request: GuidedAnswerRequest, chunks: list[RetrievedChunk]) -> dict:
    puter_token = settings.puter_auth_token or _puter_token_from_deployment_doc()
    api_key = settings.openai_api_key or puter_token
    if not api_key:
        return _fallback_answer(request, chunks)
    base_url = "https://api.openai.com/v1"
    model = settings.openai_model
    if puter_token and not settings.openai_api_key:
        base_url = "https://api.puter.com/puterai/openai/v1"
        model = settings.puter_model

    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _system_prompt(request.mode)},
            {"role": "user", "content": _user_prompt(request, chunks)},
        ],
        "temperature": 0.55,
    }
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return _fallback_answer(request, chunks)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return _fallback_answer(request, chunks)


def _normalize_card(raw_card, label: str) -> dict[str, str]:
    if not isinstance(raw_card, dict):
        raw_card = {}
    chunk_ids = raw_card.get("chunk_ids") or []
    if isinstance(chunk_ids, str):
        chunk_ids = [chunk_ids]
    return {
        "label": label,
        "title": str(raw_card.get("title") or label),
        "body": str(raw_card.get("body") or "").strip(),
        "chunk_ids": json.dumps([str(chunk_id) for chunk_id in chunk_ids]),
    }


def _sanitize_thesis(thesis: str, request: GuidedAnswerRequest) -> str:
    thesis = re.sub(r"\s+", " ", thesis).strip()
    film = _display_title(request.film_a) if request.mode != "explore_theme" else "Motif"
    if film and film not in thesis and request.mode != "explore_theme":
        thesis = f"{film} uses {request.lens} to frame a specific problem: {thesis[:180]}"
    for phrase in BANNED_PHRASES:
        thesis = re.sub(re.escape(phrase), "", thesis, flags=re.I)
    return thesis[:360].strip()


def _synthesize_guided(request: GuidedAnswerRequest, chunks: list[RetrievedChunk]) -> AnalysisResponse:
    required_films = _film_slugs_for_request(request)
    score = coverage_score(chunks, required_films)
    level = coverage_level(score)
    refused = level == "low"
    citations = _citations(chunks)
    debug_chunks = _debug_chunks(chunks, request.include_debug)

    if refused:
        thesis = "There is not enough concrete film evidence to build this reading yet."
        evidence_cards = []
    else:
        payload = _plan_evidence(request, chunks)
        thesis = _sanitize_thesis(str(payload.get("thesis") or ""), request)
        evidence_cards = [
            _normalize_card(payload.get(f"evidence_{index}"), label)
            for index, label in enumerate(EVIDENCE_JOBS, start=1)
        ]
    answer = thesis
    sections = evidence_cards
    alternative_interpretations = [card["body"] for card in evidence_cards]

    return AnalysisResponse(
        mode=request.mode,
        answer=answer,
        thesis=thesis,
        sections=sections,
        evidence_cards=evidence_cards,
        consensus_interpretation=answer,
        alternative_interpretations=alternative_interpretations,
        director_creator_perspective="",
        critical_reception="",
        related_films=[],
        cited_sources=citations,
        coverage_score=score,
        coverage_level=level,
        refused=refused,
        retrieval_notes=f"{level.title()} coverage from {len({chunk.source_key for chunk in chunks})} sources.",
        debug_chunks=debug_chunks,
    )


def answer_guided(request: GuidedAnswerRequest) -> AnalysisResponse:
    query = _query_for_request(request)
    films = _film_slugs_for_request(request)
    if request.mode == "compare_films" and len(films) != 2:
        return AnalysisResponse(
            mode=request.mode,
            answer="Choose exactly two films to compare.",
            consensus_interpretation="Choose exactly two films to compare.",
            alternative_interpretations=[],
            director_creator_perspective="",
            critical_reception="",
            related_films=[],
            cited_sources=[],
            coverage_score=0,
            coverage_level="low",
            refused=True,
            retrieval_notes="Comparison mode requires two explicit films.",
        )

    chunks = retrieve_chunks(
        query=query,
        film_slugs=films,
        source_types=[],
        limit=request.top_k,
        lens_tags=[request.lens],
        include_low_quality=request.include_low_quality,
    )
    return _synthesize_guided(request, chunks)


def answer_from_request(request: AnswerRequest | GuidedAnswerRequest) -> AnalysisResponse:
    if isinstance(request, GuidedAnswerRequest):
        return answer_guided(request)
    return answer_guided(_normalize_answer_request(request))


def retrieval_response(query: str, chunks: list[RetrievedChunk]) -> RetrieveResponse:
    score = coverage_score(chunks)
    level = coverage_level(score)
    return RetrieveResponse(
        query=query,
        chunks=[RetrievedChunkResponse(**{**chunk.__dict__, "lens_tags": chunk.lens_tags or []}) for chunk in chunks],
        coverage_score=score,
        coverage_level=level,
        retrieval_notes=f"{level.title()} coverage from {len({chunk.source_key for chunk in chunks})} sources.",
    )


def retrieve_query(
    query: str,
    film_slugs: list[str],
    source_types: list[str],
    top_k: int,
    directors: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    critics: list[str] | None = None,
    themes: list[str] | None = None,
    lens_tags: list[str] | None = None,
    include_low_quality: bool = False,
) -> RetrieveResponse:
    chunks = retrieve_chunks(
        query=query,
        film_slugs=film_slugs,
        source_types=source_types,
        limit=top_k,
        directors=directors,
        year_start=year_start,
        year_end=year_end,
        critics=critics,
        themes=themes,
        lens_tags=lens_tags,
        include_low_quality=include_low_quality,
    )
    return retrieval_response(query, chunks)


def answer_query(
    query: str,
    film_slugs: list[str],
    source_types: list[str],
    top_k: int,
    directors: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    critics: list[str] | None = None,
    themes: list[str] | None = None,
) -> AnalysisResponse:
    mode = "compare_films" if len(film_slugs) >= 2 else "analyze_film"
    request = GuidedAnswerRequest(
        mode=mode,
        film_a=film_slugs[0] if film_slugs else None,
        film_b=film_slugs[1] if len(film_slugs) > 1 else None,
        lens=themes[0] if themes else "Identity",
        optional_question=query,
        top_k=min(max(top_k, 8), 12),
    )
    return answer_guided(request)


def interpretation_map_query(query: str, film_slugs: list[str], source_types: list[str], top_k: int) -> InterpretationMapResponse:
    analysis = answer_query(query, film_slugs, source_types, top_k)
    return InterpretationMapResponse(
        query=query,
        central_reading=analysis.answer,
        interpretive_branches=analysis.alternative_interpretations,
        tensions=[],
        related_films=[],
        trail=analysis.cited_sources,
        coverage_score=analysis.coverage_score,
        coverage_level=analysis.coverage_level,
    )


def film_comparison_query(query: str, film_slugs: list[str], source_types: list[str], top_k: int) -> FilmComparisonResponse:
    analysis = answer_query(query, film_slugs[:2], source_types, top_k)
    return FilmComparisonResponse(
        query=query,
        films=[_display_title(film) for film in film_slugs[:2]],
        shared_terrain=analysis.answer,
        key_differences=analysis.alternative_interpretations,
        bridge_films=[],
        trail=analysis.cited_sources,
        coverage_score=analysis.coverage_score,
        coverage_level=analysis.coverage_level,
    )


def theme_explorer_query(query: str, theme: str, film_slugs: list[str], source_types: list[str], top_k: int) -> ThemeExplorerResponse:
    request = GuidedAnswerRequest(mode="explore_theme", lens=theme or query, optional_question=query, top_k=min(max(top_k, 8), 12))
    analysis = answer_guided(request)
    return ThemeExplorerResponse(
        query=query,
        theme=theme or query,
        overview=analysis.answer,
        motif_patterns=analysis.alternative_interpretations,
        films_to_follow=[],
        trail=analysis.cited_sources,
        coverage_score=analysis.coverage_score,
        coverage_level=analysis.coverage_level,
    )
