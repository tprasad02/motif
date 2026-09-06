import json
import re
from collections import defaultdict
from pathlib import Path
import sys, os
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.db.postgres import fetch_source_metadata
from app.film_config import FILM_TITLES, expand_film_lens_terms, expand_lens_terms
from app.models import (
    AnalysisResponse,
    AnswerRequest,
    FilmComparisonResponse,
    GuidedAnswerRequest,
    InterpretationMapResponse,
    RetrieveResponse,
    RetrievedChunkResponse,
    SourceCitation,
    LensExplorerResponse,
)
from app.services.retrieval import RetrievedChunk, retrieve_chunks
from app.services.lens_profiles import all_published_lenses, is_published_lens, lens_names, shared_lenses


EVIDENCE_JOBS = ["Scene", "Character", "Pattern", "Counterreading"]
REFUSAL_TEXT = "Motif does not have enough strong material to make that reading yet."
BANNED_PHRASES = [
    "at its core",
    "profound exploration",
    "complex interplay",
    "the human condition",
    "serves as a metaphor",
    "invites the viewer",
    "matters because",
    "not only",
    "but also",
    "not just",
    "serves as",
    "underscores",
    "illustrating how",
]
FALLBACK_FRAGMENT_PATTERNS = [
    "the relevant film detail is:",
    "pattern built through repeated scenes and formal choices",
    "not as an idea stated in dialogue",
    "lens context",
    "awards and reception",
    "cast and performance",
    "american psychological",
    "directed by",
    "starring",
]
ANSWER_CACHE_PATH = Path(__file__).resolve().parents[1] / "corpus" / "answer_cache.json"


class LLMGenerationError(RuntimeError):
    pass


def _answer_cache_key(request: GuidedAnswerRequest) -> str:
    payload = {
        "mode": request.mode,
        "film_a": request.film_a or "",
        "film_b": request.film_b or "",
        "lens": request.lens,
        "optional_question": request.optional_question or "",
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _load_answer_cache() -> dict[str, dict]:
    if not ANSWER_CACHE_PATH.exists():
        return {}
    try:
        with ANSWER_CACHE_PATH.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _cached_answer(request: GuidedAnswerRequest) -> AnalysisResponse | None:
    cached = _load_answer_cache().get(_answer_cache_key(request))
    if not isinstance(cached, dict):
        return None
    try:
        cached["debug_chunks"] = []
        cached["retrieval_notes"] = f"{cached.get('retrieval_notes', '').strip()} Cached generated reading.".strip()
        response = AnalysisResponse(**cached)
        if _contains_stray_letter_artifact(
            " ".join(
                [
                    response.thesis or "",
                    *[str(card.get("title", "")) for card in response.evidence_cards],
                    *[str(card.get("body", "")) for card in response.evidence_cards],
                ]
            )
        ):
            return None
        return response
    except Exception:
        return None


def _write_cached_answer(request: GuidedAnswerRequest, response: AnalysisResponse) -> None:
    if response.refused or request.mode == "explore_lens":
        return
    cache = _load_answer_cache()
    payload = response.model_dump(mode="json")
    payload["debug_chunks"] = []
    cache[_answer_cache_key(request)] = payload
    try:
        ANSWER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ANSWER_CACHE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError:
        pass


FILM_META = {
    "shawshank-redemption": {"year": 1994, "director": "Frank Darabont"},
    "fight-club": {"year": 1999, "director": "David Fincher"},
    "one-flew-over-the-cuckoos-nest": {"year": 1975, "director": "Milos Forman"},
    "se7en": {"year": 1995, "director": "David Fincher"},
    "silence-of-the-lambs": {"year": 1991, "director": "Jonathan Demme"},
    "the-prestige": {"year": 2006, "director": "Christopher Nolan"},
    "memento": {"year": 2000, "director": "Christopher Nolan"},
    "taxi-driver": {"year": 1976, "director": "Martin Scorsese"},
    "shutter-island": {"year": 2010, "director": "Martin Scorsese"},
    "black-swan": {"year": 2010, "director": "Darren Aronofsky"},
    "sixth-sense": {"year": 1999, "director": "M. Night Shyamalan"},
    "prisoners": {"year": 2013, "director": "Denis Villeneuve"},
    "gone-girl": {"year": 2014, "director": "David Fincher"},
    "requiem-for-a-dream": {"year": 2000, "director": "Darren Aronofsky"},
    "donnie-darko": {"year": 2001, "director": "Richard Kelly"},
    "the-machinist": {"year": 2004, "director": "Brad Anderson"},
    "mulholland-drive": {"year": 2001, "director": "David Lynch"},
    "truman-show": {"year": 1998, "director": "Peter Weir"},
}

ACTIVE_FILM_SLUGS = set(FILM_TITLES)
NON_CORPUS_FILM_TITLES = [
    "A Beautiful Mind",
    "Eternal Sunshine",
    "Eternal Sunshine of the Spotless Mind",
    "Perfect Blue",
    "Persona",
    "Synecdoche, New York",
    "The Lighthouse",
    "Vertigo",
]

FILM_SUMMARIES = {
    "shawshank-redemption": "A banker sentenced to life in prison forms an unlikely friendship with a fellow inmate while holding onto hope for freedom.",
    "fight-club": "An insomniac office worker's life changes when he meets a mysterious man who introduces him to an underground fight club.",
    "one-flew-over-the-cuckoos-nest": "A rebellious criminal fakes insanity to avoid prison but finds himself battling the oppressive authority of a psychiatric hospital.",
    "se7en": "Two detectives hunt a serial killer who uses the seven deadly sins as inspiration for a series of gruesome murders.",
    "silence-of-the-lambs": "A young FBI trainee seeks the help of an imprisoned cannibal to catch a serial killer who skins his victims.",
    "the-prestige": "Two rival magicians become consumed by their competition, sacrificing everything in their pursuit of the ultimate illusion.",
    "memento": "A man with short-term memory loss tries to find his wife's killer by relying on photographs, notes, and tattoos to piece together the truth.",
    "taxi-driver": "A lonely and disturbed New York taxi driver becomes increasingly obsessed with cleaning up the city's corruption and violence.",
    "shutter-island": "A U.S. marshal investigates the disappearance of a patient from an isolated mental institution and begins to question his own reality.",
    "black-swan": "A perfectionist ballerina spirals into paranoia and obsession as she struggles to embody both sides of the lead role in Swan Lake.",
    "sixth-sense": "A troubled boy who claims to see dead people seeks help from a child psychologist who is struggling with his own personal failures.",
    "prisoners": "When his young daughter and her friend disappear, a desperate father takes matters into his own hands while a detective investigates the case.",
    "gone-girl": "When a woman mysteriously disappears on her wedding anniversary, suspicion falls on her husband as the media turns their marriage into a spectacle.",
    "requiem-for-a-dream": "Four people become consumed by their addictions as their dreams of a better life give way to increasingly devastating consequences.",
    "donnie-darko": "A troubled teenager begins experiencing visions of a mysterious figure in a rabbit costume who tells him the world will soon end.",
    "the-machinist": "A machinist who has not slept in a year becomes increasingly paranoid as his deteriorating mental state draws him into a disturbing mystery.",
    "mulholland-drive": "An aspiring actress and an amnesiac woman become entangled in a strange mystery that blurs the line between Hollywood dreams and reality.",
    "truman-show": "A man living an idyllic suburban life gradually discovers that his entire existence is a reality television show filmed without his knowledge.",
}


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
    if request.mode == "explore_lens":
        return []
    return [request.film_a] if request.film_a else []


def _query_for_request(request: GuidedAnswerRequest) -> str:
    angle = f" Angle: {request.optional_question.strip()}" if request.optional_question else ""
    film_lenses = " ".join(lens for slug in _film_slugs_for_request(request) for lens in lens_names(slug))
    if request.mode == "compare_films":
        companion_terms = " ".join(
            term
            for slug in _film_slugs_for_request(request)
            for term in expand_film_lens_terms(slug, request.lens)
        )
        return f"Compare {_display_title(request.film_a)} and {_display_title(request.film_b)}. Lens: {request.lens}. Related search terms: {companion_terms}. Available lenses: {film_lenses}.{angle}"
    if request.mode == "explore_lens":
        return f"Explore lens: {request.lens}. Film collection only.{angle}"
    companion_terms = " ".join(expand_film_lens_terms(request.film_a, request.lens))
    return f"Analyze {_display_title(request.film_a)}. Lens: {request.lens}. Related search terms: {companion_terms}. Available lenses: {film_lenses}.{angle}"


def _request_from_values(mode: str, film_a: str | None, film_b: str | None, lens: str) -> GuidedAnswerRequest:
    return GuidedAnswerRequest(mode=mode, film_a=film_a, film_b=film_b, lens=lens, top_k=12)


def _normalize_answer_request(request: AnswerRequest) -> GuidedAnswerRequest:
    if request.mode:
        return GuidedAnswerRequest(
            mode=request.mode,
            film_a=request.film_a or (request.film_slugs[0] if request.film_slugs else None),
            film_b=request.film_b or (request.film_slugs[1] if len(request.film_slugs) > 1 else None),
            lens=request.lens or (request.lenses[0] if request.lenses else "Identity"),
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
        lens=request.lenses[0] if request.lenses else "Identity",
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


def _selection_reason(chunk: RetrievedChunk, request: GuidedAnswerRequest | None = None) -> str:
    reasons = []
    if chunk.rerank_score is not None:
        reasons.append("ranked highly after reranking")
    if chunk.vector_score is not None:
        reasons.append("matched semantic search")
    if chunk.bm25_score is not None:
        reasons.append("matched keyword search")
    if request and _chunk_lens_match(chunk, request.lens):
        reasons.append("matched the selected lens")
    if chunk.chunk_role in {"scene_evidence", "formal_observation", "creator_commentary"}:
        reasons.append(f"contains {chunk.chunk_role.replace('_', ' ')}")
    if chunk.quality_score == "high":
        reasons.append("comes from a high-quality source")
    if request and chunk.film_slug in _film_slugs_for_request(request):
        reasons.append("matches the selected film")
    return "; ".join(dict.fromkeys(reasons)) or "selected by retrieval score"


def _evidence_usage(evidence_cards: list[dict[str, str]] | None) -> dict[str, list[str]]:
    usage: dict[str, list[str]] = defaultdict(list)
    for card in evidence_cards or []:
        label = str(card.get("label") or "Evidence")
        raw_ids = card.get("chunk_ids") or "[]"
        try:
            chunk_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
        except json.JSONDecodeError:
            chunk_ids = [raw_ids]
        for chunk_id in chunk_ids or []:
            usage[str(chunk_id)].append(label)
    return usage


def _debug_chunks(
    chunks: list[RetrievedChunk],
    include_debug: bool,
    request: GuidedAnswerRequest | None = None,
    evidence_cards: list[dict[str, str]] | None = None,
) -> list[RetrievedChunkResponse]:
    if not include_debug:
        return []
    source_metadata = fetch_source_metadata(sorted({chunk.source_key for chunk in chunks}))
    usage = _evidence_usage(evidence_cards)
    return [
        RetrievedChunkResponse(
            **{
                **chunk.__dict__,
                "lens_tags": chunk.lens_tags or [],
                "source_title": source_metadata.get(chunk.source_key, {}).get("title", chunk.source_key),
                "selection_reason": _selection_reason(chunk, request),
                "used_by_evidence_cards": usage.get(chunk.chunk_id, []),
            }
        )
        for chunk in chunks
    ]


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
    compare_contract = ""
    if mode == "compare_films":
        compare_contract = (
            "For comparison mode, every evidence card must compare both selected films directly. "
            "Mention both film titles in every card body. "
            "Do not split the answer into separate cards for each film. "
            "Each card should name what the first film does, what the second film does, and the meaningful difference or similarity between them. "
        )
    return (
        "You are Motif, a film close-reading assistant. Produce an evidence board, not an essay. "
        "Write plainly and specifically. Avoid grand philosophical language, generic AI phrasing, and claims about people or humanity in general. "
        "Use enough plot context to identify the moment, but do not retell the whole plot. "
        "Do not output stray isolated letter artifacts such as ' l ' or half-formed words. "
        "Do not use these phrases or structures: at its core, profound exploration, complex interplay, the human condition, serves as, invites the viewer, matters because, underscores, illustrating how, not only, but also, not just. "
        "Do not mention source titles, publishers, source types, citations, or phrases like 'according to'. "
        "You may mention the selected topic naturally, but do not expose interface phrasing such as 'lens', 'through the lens of', 'in this lens', or 'selected lens'. "
        f"Only discuss these films: {', '.join(FILM_TITLES.values())}. "
        "Explain what the film shows and how the detail supports or complicates the thesis. "
        "Use only retrieved context and attach chunk IDs to each evidence item. "
        f"{compare_contract}"
        "Return strict JSON with keys: thesis, evidence_1, evidence_2, evidence_3, evidence_4. "
        "The thesis must be 30-60 words, one or two sentences, mention the selected film title or both selected film titles, mention the selected topic naturally, and make a film-bound arguable claim. "
        "Each evidence item must be an object with keys: label, title, body, chunk_ids. "
        "The four labels must be exactly: Scene, Character, Pattern, Counterreading. "
        "Scene: choose the single strongest scene or sequence that directly demonstrates the thesis. Name what happens in that moment and what the viewer sees or hears. "
        "Character: explain how a character's behavior, performance, relationships, or psychological trajectory embodies the thesis. Use a specific action, reaction, or performance detail. "
        "Pattern: identify a recurring symbol, visual motif, image, line of dialogue, sound cue, editing pattern, or filmmaking technique that quietly reinforces the thesis. "
        "Counterreading: give the strongest evidence that challenges, complicates, or contradicts the thesis. Do not make this a fourth supporting point. "
        "Each body must be 70-120 words, concrete, not containing any chunk id or citation reference, and distinct from the other cards."
    )


def _user_prompt(request: GuidedAnswerRequest, chunks: list[RetrievedChunk]) -> str:
    films = ", ".join(_display_title(slug) for slug in _film_slugs_for_request(request)) or "the indexed collection"
    comparison_requirement = ""
    if request.mode == "compare_films":
        comparison_requirement = (
            f"\nComparison requirement: every evidence card body must include the exact titles "
            f"'{_display_title(request.film_a)}' and '{_display_title(request.film_b)}' and must explain a direct comparison."
        )
    return f"""
Workflow: {request.mode}
Selected film(s): {films}
Lens: {request.lens}
Optional angle: {request.optional_question or "None"}
{comparison_requirement}

Retrieved context:
{_context(chunks)}
""".strip()


def _plan_evidence(request: GuidedAnswerRequest, chunks: list[RetrievedChunk]) -> dict:
    api_key = settings.openai_api_key
    if not api_key:
        raise LLMGenerationError("OPENAI_API_KEY is not configured.")
    base_url = "https://api.openai.com/v1"
    model = settings.openai_model

    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _system_prompt(request.mode)},
            {"role": "user", "content": _user_prompt(request, chunks)},
        ],
        "temperature": 0.35 if request.mode == "compare_films" else 0.55,
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
    except httpx.HTTPStatusError as error:
        raise LLMGenerationError(f"OpenAI request failed with status {error.response.status_code}.") from error
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
        raise LLMGenerationError("OpenAI request failed before Motif could generate a reading.") from error
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise LLMGenerationError("OpenAI returned a response Motif could not parse.") from error


def _normalize_card(raw_card, label: str) -> dict[str, str]:
    if not isinstance(raw_card, dict):
        raw_card = {}
    chunk_ids = raw_card.get("chunk_ids") or []
    if isinstance(chunk_ids, str):
        chunk_ids = [chunk_ids]
    return {
        "label": label,
        "title": str(raw_card.get("title") or label).strip(),
        "body": str(raw_card.get("body") or "").strip(),
        "chunk_ids": json.dumps([str(chunk_id) for chunk_id in chunk_ids]),
    }


def _resolve_card_chunk_ids(evidence_cards: list[dict[str, str]], chunks: list[RetrievedChunk]) -> list[dict[str, str]]:
    """Resolve model-supplied context ordinals to stable retrieved chunk IDs."""
    valid_ids = {chunk.chunk_id for chunk in chunks}
    for card in evidence_cards:
        raw_ids = card.get("chunk_ids") or "[]"
        try:
            values = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
        except json.JSONDecodeError:
            values = [raw_ids]
        resolved = []
        for value in values or []:
            chunk_id = str(value).strip()
            if chunk_id in valid_ids:
                resolved.append(chunk_id)
            elif chunk_id.isdigit() and 1 <= int(chunk_id) <= len(chunks):
                resolved.append(chunks[int(chunk_id) - 1].chunk_id)
        card["chunk_ids"] = json.dumps(list(dict.fromkeys(resolved)))
    return evidence_cards


def _clean_public_text(text: str, request: GuidedAnswerRequest) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = re.sub(r"^the relevant film detail is:\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"(?<![A-Za-z])l(?![A-Za-z])", " ", cleaned)
    cleaned = re.sub(r"\bmatters because\b", "shows this by", cleaned, flags=re.I)
    cleaned = re.sub(r"\bnot only\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\bbut also\b", "and", cleaned, flags=re.I)
    cleaned = re.sub(r"\bnot just\b", "more than", cleaned, flags=re.I)
    cleaned = re.sub(r"\bserves as\b", "works like", cleaned, flags=re.I)
    cleaned = re.sub(r"\bunderscores\b", "sharpens", cleaned, flags=re.I)
    cleaned = re.sub(r"\billustrating how\b", "showing how", cleaned, flags=re.I)
    for phrase in BANNED_PHRASES:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.I)
    cleaned = re.sub(r"\baccording to\b[^.?!]*(?:[.?!]|$)", "", cleaned, flags=re.I)
    cleaned = re.sub(
        r"\b(?:in|from)\s+(?:the\s+)?(?:Guardian|Variety|Deadline|IndieWire|Collider|BFI|Criterion|Roger Ebert|craft article|academic|review|interview|essay|source)\b[^.?!]*(?:[.?!]|$)",
        "",
        cleaned,
        flags=re.I,
    )
    if request.lens:
        escaped_lens = re.escape(request.lens)
        cleaned = re.sub(rf"\bthrough\s+(?:the\s+)?{escaped_lens}\s+lens\b", f"through {request.lens}", cleaned, flags=re.I)
        cleaned = re.sub(rf"\bthrough\s+(?:the\s+)?lens\s+of\s+{escaped_lens}\b", f"through {request.lens}", cleaned, flags=re.I)
        cleaned = re.sub(rf"\bin\s+(?:this|the)\s+{escaped_lens}\s+lens\b", f"in its treatment of {request.lens}", cleaned, flags=re.I)
        cleaned = re.sub(rf"\b(?:this|the|selected)\s+{escaped_lens}\s+lens\b", request.lens, cleaned, flags=re.I)
        cleaned = re.sub(r"\b(?:this|the|selected)\s+(?:lens)\b", "this lens", cleaned, flags=re.I)
        cleaned = re.sub(r"\b(?:lens)\b", "lens", cleaned, flags=re.I)
    for title in NON_CORPUS_FILM_TITLES:
        cleaned = re.sub(re.escape(title), "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip(" -:;,.") or text.strip()


def _contains_stray_letter_artifact(text: str) -> bool:
    return bool(re.search(r"(?<![A-Za-z])l(?![A-Za-z])", text or ""))


def _clean_card_title(title: str, label: str, request: GuidedAnswerRequest) -> str:
    cleaned = _clean_public_text(title, request)
    if cleaned.lower() in {"main argument", "interview exchange", "untitled", "evidence"}:
        return label
    return cleaned


def _sanitize_thesis(thesis: str, request: GuidedAnswerRequest) -> str:
    thesis = _clean_public_text(thesis, request)
    film = _display_title(request.film_a) if request.mode != "explore_lens" else "Motif"
    if film and film not in thesis and request.mode != "explore_lens":
        thesis = f"{film} frames {request.lens} through performance, structure, and repeated images: {thesis[:180]}"
    return thesis[:360].strip()


def _reject_fallback_reading(thesis: str, evidence_cards: list[dict[str, str]]) -> None:
    if not thesis or len(evidence_cards) != 4:
        raise LLMGenerationError("OpenAI returned an incomplete reading.")

    combined = " ".join(
        [thesis, *[card.get("title", "") for card in evidence_cards], *[card.get("body", "") for card in evidence_cards]]
    ).lower()
    pattern_hits = sum(1 for pattern in FALLBACK_FRAGMENT_PATTERNS if pattern in combined)
    if _contains_stray_letter_artifact(combined):
        raise LLMGenerationError("OpenAI returned stray letter artifacts.")
    weak_cards = 0
    for card in evidence_cards:
        body = (card.get("body") or "").strip()
        lowered = f"{card.get('title', '')} {body}".lower()
        if not body:
            weak_cards += 1
            continue
        if any(pattern in lowered for pattern in FALLBACK_FRAGMENT_PATTERNS):
            weak_cards += 1
            continue
        if len(body.split()) < 45:
            weak_cards += 1

    if pattern_hits >= 2 or weak_cards >= 2:
        raise LLMGenerationError("OpenAI returned retrieved text instead of a generated reading.")


def _reject_weak_comparison(request: GuidedAnswerRequest, evidence_cards: list[dict[str, str]]) -> None:
    if request.mode != "compare_films":
        return
    film_a = _display_title(request.film_a)
    film_b = _display_title(request.film_b)
    if not film_a or not film_b:
        return
    missing_cards = 0
    for card in evidence_cards:
        text = f"{card.get('title', '')} {card.get('body', '')}"
        if not re.search(rf"\b{re.escape(film_a)}\b", text) or not re.search(rf"\b{re.escape(film_b)}\b", text):
            missing_cards += 1
    if missing_cards:
        raise LLMGenerationError("OpenAI returned comparison cards that did not compare both films.")


def _lens_card_body(slug: str, lens: str) -> str:
    if slug in FILM_SUMMARIES:
        return FILM_SUMMARIES[slug]
    return f"A collection film where {lens.lower()} can be followed through character choices, setting, and repeated visual details."


def _lens_matches(selected_lens: str, candidate_lens: str) -> bool:
    selected_terms = {term.lower() for term in expand_lens_terms(selected_lens)}
    candidate = candidate_lens.lower()
    candidate_terms = {term.lower() for term in expand_lens_terms(candidate_lens)}
    return bool(selected_terms.intersection(candidate_terms)) or any(
        selected in candidate or candidate in selected for selected in selected_terms
    )


def _chunk_lens_match(chunk: RetrievedChunk, lens: str) -> bool:
    terms = {term.lower() for term in expand_film_lens_terms(chunk.film_slug, lens)}
    chunk_lenses = {tag.lower() for tag in (chunk.lens_tags or [])}
    text = chunk.text[:1200].lower()
    return bool(terms.intersection(chunk_lenses)) or any(term in text for term in terms if len(term) >= 4)


def _retrieval_confidence(request: GuidedAnswerRequest, chunks: list[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    required_films = _film_slugs_for_request(request)
    source_keys = {chunk.source_key for chunk in chunks if chunk.source_key}
    source_roles = {chunk.source_role for chunk in chunks if chunk.source_role}
    concrete_roles = {"scene_evidence", "formal_observation", "creator_commentary", "interpretive_claim"}
    concrete_rate = sum(1 for chunk in chunks if chunk.chunk_role in concrete_roles) / len(chunks)
    plot_rate = sum(1 for chunk in chunks if chunk.chunk_role == "plot_summary") / len(chunks)
    lens_rate = sum(1 for chunk in chunks if _chunk_lens_match(chunk, request.lens)) / len(chunks)
    volume_component = min(len(chunks) / max(request.top_k, 1), 1.0)
    source_component = min(len(source_keys) / 5, 1.0)
    role_component = min(len(source_roles) / 3, 1.0)
    film_component = 1.0
    if request.mode == "compare_films" and len(required_films) == 2:
        counts = {film: sum(1 for chunk in chunks if chunk.film_slug == film) for film in required_films}
        film_component = min(min(counts.values()) / 4, 1.0)
    elif required_films:
        film_component = sum(1 for chunk in chunks if chunk.film_slug in required_films) / len(chunks)
    score = (
        (0.20 * volume_component)
        + (0.18 * source_component)
        + (0.14 * role_component)
        + (0.18 * film_component)
        + (0.20 * lens_rate)
        + (0.14 * concrete_rate)
        - (0.10 * plot_rate)
    )
    return round(max(0.0, min(score, 1.0)), 3)


def _selection_supported(request: GuidedAnswerRequest, allow_unpublished_lens: bool = False) -> bool:
    if request.mode == "explore_lens":
        return request.lens in all_published_lenses()
    if request.mode == "analyze_film":
        return bool(request.film_a and (allow_unpublished_lens or is_published_lens(request.film_a, request.lens)))
    if request.mode == "compare_films":
        films = [slug for slug in [request.film_a, request.film_b] if slug]
        return len(films) == 2 and (allow_unpublished_lens or request.lens in shared_lenses(films[0], films[1]))
    return False


def _candidate_confidence(mode: str, film_a: str | None, film_b: str | None, lens: str) -> float:
    candidate_request = _request_from_values(mode, film_a, film_b, lens)
    chunks = retrieve_chunks(
        query=_query_for_request(candidate_request),
        film_slugs=_film_slugs_for_request(candidate_request),
        source_types=[],
        limit=12,
        lens_tags=[lens],
    )
    return _retrieval_confidence(candidate_request, chunks)


def _best_lens_suggestions(request: GuidedAnswerRequest, limit: int = 3) -> list[str]:
    if request.mode == "compare_films":
        candidates = sorted(
            set(shared_lenses(request.film_a or "", request.film_b or ""))
        )
    else:
        candidates = lens_names(request.film_a or "")
    scored = []
    for lens in candidates:
        if lens == request.lens:
            continue
        confidence = _candidate_confidence(request.mode, request.film_a, request.film_b, lens)
        scored.append((confidence, lens))
    return [lens for confidence, lens in sorted(scored, reverse=True)[:limit] if confidence >= 0.55]


def _best_pairing_suggestions(request: GuidedAnswerRequest, limit: int = 2) -> list[str]:
    if request.mode != "compare_films" or not request.film_a or not request.film_b:
        return []
    suggestions = []
    selected = {request.film_a, request.film_b}
    for anchor in [request.film_a, request.film_b]:
        for candidate_slug in ACTIVE_FILM_SLUGS:
            if candidate_slug in selected or not is_published_lens(candidate_slug, request.lens):
                continue
            confidence = _candidate_confidence("compare_films", anchor, candidate_slug, request.lens)
            suggestions.append((confidence, anchor, candidate_slug))
    ranked = sorted(suggestions, reverse=True)[:limit]
    return [
        f"{_display_title(anchor)} with {_display_title(candidate)}"
        for confidence, anchor, candidate in ranked
        if confidence >= 0.55
    ]


def _answer_pairing_suggestions(request: GuidedAnswerRequest, limit: int = 4) -> list[dict[str, object]]:
    if request.mode != "analyze_film" or not request.film_a or not request.lens:
        return []
    suggestions = []
    for candidate_slug in ACTIVE_FILM_SLUGS:
        if candidate_slug == request.film_a or not is_published_lens(candidate_slug, request.lens):
            continue
        confidence = _candidate_confidence("compare_films", request.film_a, candidate_slug, request.lens)
        if confidence < 0.55:
            continue
        suggestions.append(
            {
                "film_slug": candidate_slug,
                "title": _display_title(candidate_slug),
                "lens": request.lens,
                "score": round(confidence, 3),
            }
        )
    suggestions.sort(key=lambda row: float(row["score"]), reverse=True)
    return suggestions[:limit]


def _refusal_cards(request: GuidedAnswerRequest) -> list[dict[str, str]]:
    lens_suggestions = _best_lens_suggestions(request)
    pairing_suggestions = _best_pairing_suggestions(request)
    cards: list[dict[str, str]] = []
    if lens_suggestions:
        cards.append(
            {
                "label": "Try a stronger lens",
                "title": ", ".join(lens_suggestions),
                "body": "These choices have stronger material in the current collection.",
            }
        )
    if pairing_suggestions:
        cards.append(
            {
                "label": "Try a stronger pairing",
                "title": "; ".join(pairing_suggestions),
                "body": "These pairings are better supported for a side-by-side reading.",
            }
        )
    if not cards:
        cards.append(
            {
                "label": "Try another path",
                "title": "Choose one of the recommended lenses",
                "body": "The current collection is stronger when Motif follows the primary lenses shown after a film is selected.",
            }
        )
    return cards


def _lens_films(request: GuidedAnswerRequest, chunks: list[RetrievedChunk]) -> list[dict[str, object]]:
    grouped: dict[str, list[RetrievedChunk]] = defaultdict(list)
    for chunk in chunks:
        if chunk.film_slug in ACTIVE_FILM_SLUGS:
            grouped[chunk.film_slug].append(chunk)

    scored = []
    eligible_slugs = sorted(grouped)
    for slug in eligible_slugs:
        film_chunks = grouped.get(slug, [])
        if slug not in ACTIVE_FILM_SLUGS:
            continue
        chunk_lens_match = any(_lens_matches(request.lens, lens) for chunk in film_chunks for lens in (chunk.lens_tags or []))
        source_count = len({chunk.source_key for chunk in film_chunks})
        role_count = len({chunk.chunk_role for chunk in film_chunks})
        lens_match = is_published_lens(slug, request.lens)
        if not lens_match:
            continue
        retrieval_score = min(sum(max(chunk.score, 0) for chunk in film_chunks), 20.0)
        score = retrieval_score + (0.22 * source_count) + (0.16 * role_count) + (1.0 if lens_match else 0) + (0.8 if chunk_lens_match else 0)
        scored.append((score, slug, film_chunks))

    ranked = sorted(scored, key=lambda item: item[0], reverse=True)[:6]
    cards = []
    for rank, (score, slug, film_chunks) in enumerate(ranked, start=1):
        meta = FILM_META.get(slug, {})
        cards.append(
            {
                "rank": rank,
                "slug": slug,
                "title": FILM_TITLES[slug],
                "year": meta.get("year"),
                "director": meta.get("director"),
                "summary": _lens_card_body(slug, request.lens),
                "score": round(score, 3),
            }
        )
    return cards


def _synthesize_lens(request: GuidedAnswerRequest, chunks: list[RetrievedChunk]) -> AnalysisResponse:
    active_chunks = [chunk for chunk in chunks if chunk.film_slug in ACTIVE_FILM_SLUGS]
    score = coverage_score(active_chunks)
    level = coverage_level(score)
    cards = _lens_films(request, active_chunks)
    refused = not cards
    debug_chunks = _debug_chunks(active_chunks, request.include_debug, request)
    answer = "Films ranked by relevance."
    return AnalysisResponse(
        mode=request.mode,
        answer=answer,
        thesis=None,
        sections=[],
        evidence_cards=[],
        lens_films=cards,
        consensus_interpretation=answer,
        alternative_interpretations=[],
        director_creator_perspective="",
        critical_reception="",
        related_films=[str(card["title"]) for card in cards],
        cited_sources=[],
        coverage_score=score,
        coverage_level=level,
        refused=refused,
        retrieval_notes=f"{level.title()} coverage from {len({chunk.source_key for chunk in active_chunks})} sources.",
        debug_chunks=debug_chunks,
        suggested_pairings=[],
    )


def _synthesize_guided(request: GuidedAnswerRequest, chunks: list[RetrievedChunk], allow_unpublished_lens: bool = False) -> AnalysisResponse:
    if request.mode == "explore_lens":
        return _synthesize_lens(request, chunks)

    required_films = _film_slugs_for_request(request)
    score = coverage_score(chunks, required_films)
    confidence = _retrieval_confidence(request, chunks)
    level = coverage_level(max(score, confidence))
    refused = not _selection_supported(request, allow_unpublished_lens) or confidence < 0.52 or score < 0.38
    citations = _citations(chunks)

    if refused:
        thesis = REFUSAL_TEXT
        evidence_cards = _refusal_cards(request)
    else:
        last_error: LLMGenerationError | None = None
        max_attempts = 3 if request.mode == "compare_films" else 2
        for _attempt in range(max_attempts):
            try:
                payload = _plan_evidence(request, chunks)
                thesis = _sanitize_thesis(str(payload.get("thesis") or ""), request)
                evidence_cards = [
                    _normalize_card(payload.get(f"evidence_{index}"), label)
                    for index, label in enumerate(EVIDENCE_JOBS, start=1)
                ]
                evidence_cards = [
                    {
                        **card,
                        "title": _clean_card_title(card["title"], card["label"], request),
                        "body": _clean_public_text(card["body"], request),
                    }
                    for card in evidence_cards
                ]
                _reject_fallback_reading(thesis, evidence_cards)
                _reject_weak_comparison(request, evidence_cards)
                break
            except LLMGenerationError as error:
                last_error = error
        else:
            error = last_error or LLMGenerationError("Motif could not generate that reading right now.")
            cached = _cached_answer(request)
            if cached:
                if request.include_debug:
                    cached.debug_chunks = _debug_chunks(chunks, request.include_debug, request)
                return cached
            message = str(error)
            thesis = "OpenAI key not configured." if "OPENAI_API_KEY" in message else "Motif could not generate that reading right now."
            return AnalysisResponse(
                mode=request.mode,
                answer=thesis,
                thesis=thesis,
                sections=[],
                evidence_cards=[],
                lens_films=[],
                consensus_interpretation=thesis,
                alternative_interpretations=[],
                director_creator_perspective="",
                critical_reception="",
                related_films=[],
                cited_sources=[],
                coverage_score=score,
                coverage_level=level,
                refused=True,
                retrieval_notes="",
                debug_chunks=_debug_chunks(chunks, request.include_debug, request),
            )
    evidence_cards = _resolve_card_chunk_ids(evidence_cards, chunks)
    answer = thesis
    sections = evidence_cards
    alternative_interpretations = [card["body"] for card in evidence_cards]

    response = AnalysisResponse(
        mode=request.mode,
        answer=answer,
        thesis=thesis,
        sections=sections,
        evidence_cards=evidence_cards,
        lens_films=[],
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
        debug_chunks=_debug_chunks(chunks, request.include_debug, request, evidence_cards),
        suggested_pairings=_answer_pairing_suggestions(request),
    )
    _write_cached_answer(request, response)
    return response


def answer_guided(request: GuidedAnswerRequest, allow_unpublished_lens: bool = False) -> AnalysisResponse:
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
    return _synthesize_guided(request, chunks, allow_unpublished_lens)


def answer_from_request(request: AnswerRequest | GuidedAnswerRequest) -> AnalysisResponse:
    if isinstance(request, GuidedAnswerRequest) or (
        getattr(request, "mode", None) in {"analyze_film", "compare_films", "explore_lens"}
        and hasattr(request, "film_a")
        and hasattr(request, "lens")
        and not hasattr(request, "film_slugs")
    ):
        return answer_guided(
            GuidedAnswerRequest(
                mode=request.mode,
                film_a=getattr(request, "film_a", None),
                film_b=getattr(request, "film_b", None),
                lens=request.lens,
                optional_question=getattr(request, "optional_question", None),
                top_k=getattr(request, "top_k", 12),
                include_debug=getattr(request, "include_debug", False),
                include_low_quality=getattr(request, "include_low_quality", False),
            )
        )
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
    lenses: list[str] | None = None,
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
        themes=lenses,
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
    lenses: list[str] | None = None,
) -> AnalysisResponse:
    mode = "compare_films" if len(film_slugs) >= 2 else "analyze_film"
    request = GuidedAnswerRequest(
        mode=mode,
        film_a=film_slugs[0] if film_slugs else None,
        film_b=film_slugs[1] if len(film_slugs) > 1 else None,
        lens=lenses[0] if lenses else "Identity",
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


def lens_explorer_query(query: str, lens: str, film_slugs: list[str], source_types: list[str], top_k: int) -> LensExplorerResponse:
    request = GuidedAnswerRequest(mode="explore_lens", lens=lens or query, optional_question=query, top_k=min(max(top_k, 8), 12))
    analysis = answer_guided(request)
    return LensExplorerResponse(
        query=query,
        lens=lens or query,
        overview=analysis.answer,
        motif_patterns=analysis.alternative_interpretations,
        films_to_follow=[],
        trail=analysis.cited_sources,
        coverage_score=analysis.coverage_score,
        coverage_level=analysis.coverage_level,
    )
