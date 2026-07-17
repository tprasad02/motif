from collections import Counter

from app.db.postgres import fetch_source_metadata
from app.models import (
    AnalysisResponse,
    FilmComparisonResponse,
    InterpretationMapResponse,
    RetrieveResponse,
    RetrievedChunkResponse,
    SourceCitation,
    ThemeExplorerResponse,
)
from app.services.retrieval import RetrievedChunk, retrieve_chunks


FILM_TITLES = {
    "shawshank-redemption": "The Shawshank Redemption",
    "fight-club": "Fight Club",
    "one-flew-over-the-cuckoos-nest": "One Flew Over the Cuckoo's Nest",
    "se7en": "Se7en",
    "silence-of-the-lambs": "The Silence of the Lambs",
    "the-prestige": "The Prestige",
    "memento": "Memento",
    "taxi-driver": "Taxi Driver",
    "shutter-island": "Shutter Island",
    "black-swan": "Black Swan",
    "sixth-sense": "The Sixth Sense",
    "prisoners": "Prisoners",
    "gone-girl": "Gone Girl",
    "requiem-for-a-dream": "Requiem for a Dream",
    "donnie-darko": "Donnie Darko",
    "the-machinist": "The Machinist",
    "mulholland-drive": "Mulholland Drive",
    "truman-show": "The Truman Show",
}


FILM_READINGS = {
    "shawshank-redemption": "turns prison time into a test of inner authorship: the institution controls bodies, but hope becomes the private act that keeps a self alive",
    "fight-club": "splits the self into consumer numbness and charismatic violence, making the double a fantasy of escape that curdles into control",
    "one-flew-over-the-cuckoos-nest": "frames sanity and rebellion as a struggle over who gets to define normal behavior inside an institution built to flatten difference",
    "se7en": "makes detective procedure feel like moral contamination, where meaning arrives through cruelty and the city itself seems to author despair",
    "silence-of-the-lambs": "turns investigation into a charged exchange of looking and being looked at, with Clarice fighting to keep authority over her own story",
    "the-prestige": "treats art as sacrifice and obsession as craft, making the magic trick a machine for splitting identity into performance and cost",
    "memento": "makes memory a broken editing system, so identity has to be rebuilt from clues that may already be corrupted",
    "taxi-driver": "builds identity out of isolation, movie-fed masculinity, and ritualized performance: Travis rehearses himself until the persona becomes more real than the man",
    "shutter-island": "turns investigation into self-defense, with role-play and institutional theater protecting a mind from the truth it cannot survive",
    "black-swan": "makes artistic perfection feel like possession: the dancer tries to become the role until the role starts consuming the self",
    "sixth-sense": "uses the ghost story as grief grammar, letting the twist reframe isolation as unfinished recognition",
    "prisoners": "pushes parental love into moral captivity, where certainty becomes as dangerous as doubt",
    "gone-girl": "turns marriage and media into mutually reinforcing performances, with identity weaponized as public narrative",
    "requiem-for-a-dream": "cuts desire into addiction, spectacle, and bodily collapse, making fantasy feel chemically and culturally manufactured",
    "donnie-darko": "folds adolescence, doom, and alternate timelines into a mood where madness may be prophecy or metaphor",
    "the-machinist": "externalizes guilt through the body, making insomnia and emaciation feel like evidence from a hidden trial",
    "mulholland-drive": "turns Hollywood fantasy into a hall of mirrors, where desire invents a brighter self and guilt slowly breaks the illusion apart",
    "truman-show": "turns everyday life into a set, asking what freedom means when identity has been authored for an audience",
}


THEME_CONNECTIONS = {
    "identity": "Across these films, identity is not treated as a stable core waiting to be discovered. It behaves more like a role under pressure: rehearsed, mirrored, defended, and sometimes broken by desire.",
    "doubling": "The double is less a twist than a pressure point. It gives hidden wishes and disowned fears a body, then forces the character to live beside what they tried to separate from themselves.",
    "performance": "Performance matters because these characters do not simply pretend. They use acting, ritual, costume, fantasy, or professional roles to survive, and the performance eventually starts giving orders back.",
    "memory": "Memory functions like an editor: it cuts, loops, protects, and distorts. What looks like confusion is often the film showing how the mind reshapes a wound into a story it can bear.",
    "influence": "The strongest influence pattern here runs through psychological modernism, noir, melodrama, and surrealism: films borrowing the shape of a thriller to stage an interior crisis.",
    "loneliness": "Loneliness is not just a mood in this corpus. It becomes an atmosphere, a rhythm, and finally a distorted way of reading the world.",
    "obsession": "Obsession works like a private editing machine. It narrows the frame until every person, place, and image seems to point back to the character's wound.",
    "violence": "Violence usually arrives after fantasy has failed. These films make brutality feel less like power than like a desperate attempt to turn inner chaos into an outward shape.",
    "ending": "The endings in these films rarely close the case. They change the terms of the case, asking whether resolution matters less than the emotional pattern we have been watching.",
    "ambiguity": "Ambiguity is not a lack of meaning here. It is the method: the films keep competing explanations alive so the viewer feels the instability the characters live inside.",
    "love": "Love in this corpus is rarely clean comfort. It is memory, projection, dependence, fantasy, and recognition tangled together.",
    "masculinity": "Masculinity often appears as a costume under strain: discipline, toughness, genius, and control become roles that hide fear until they start to crack.",
    "madness": "Madness is staged less as a diagnosis than as a cinematic point of view: sound, repetition, unreliable memory, and performance make the viewer share the pressure.",
}


THEME_KEYWORDS = {
    "identity": {"identity", "self", "persona", "who", "subjectivity"},
    "doubling": {"double", "doubling", "doppelganger", "mirror", "split", "twin"},
    "performance": {"performance", "perform", "role", "acting", "actor", "actress", "mask"},
    "memory": {"memory", "remember", "forget", "erased", "flashback", "past"},
    "influence": {"influence", "inspired", "inspiration", "borrow", "echo", "reference"},
    "loneliness": {"loneliness", "lonely", "alone", "isolation", "alienation", "isolated"},
    "obsession": {"obsession", "obsessed", "fixation", "desire", "compulsion"},
    "violence": {"violence", "violent", "brutality", "murder", "blood", "rage"},
    "ending": {"ending", "end", "finale", "conclusion", "twist", "last scene"},
    "ambiguity": {"ambiguous", "ambiguity", "unclear", "confusing", "dream", "real", "explain"},
    "love": {"love", "romance", "relationship", "intimacy", "heartbreak"},
    "masculinity": {"masculinity", "manhood", "male", "men", "masculine"},
    "madness": {"madness", "insanity", "sanity", "psychosis", "delusion", "mental"},
}


RELATED_BY_THEME = {
    "shawshank-redemption": ["one-flew-over-the-cuckoos-nest", "prisoners", "truman-show", "taxi-driver"],
    "fight-club": ["taxi-driver", "black-swan", "gone-girl", "memento"],
    "one-flew-over-the-cuckoos-nest": ["shawshank-redemption", "shutter-island", "prisoners", "taxi-driver"],
    "se7en": ["silence-of-the-lambs", "prisoners", "taxi-driver", "gone-girl"],
    "silence-of-the-lambs": ["se7en", "gone-girl", "prisoners", "black-swan"],
    "the-prestige": ["memento", "black-swan", "gone-girl", "mulholland-drive"],
    "memento": ["shutter-island", "donnie-darko", "the-machinist", "the-prestige"],
    "taxi-driver": ["fight-club", "se7en", "prisoners", "the-machinist"],
    "shutter-island": ["memento", "the-machinist", "donnie-darko", "sixth-sense"],
    "black-swan": ["fight-club", "mulholland-drive", "requiem-for-a-dream", "gone-girl"],
    "sixth-sense": ["shutter-island", "donnie-darko", "mulholland-drive", "memento"],
    "prisoners": ["se7en", "taxi-driver", "silence-of-the-lambs", "shawshank-redemption"],
    "gone-girl": ["fight-club", "silence-of-the-lambs", "se7en", "the-prestige"],
    "requiem-for-a-dream": ["black-swan", "the-machinist", "taxi-driver", "fight-club"],
    "donnie-darko": ["memento", "shutter-island", "the-machinist", "sixth-sense"],
    "the-machinist": ["memento", "shutter-island", "requiem-for-a-dream", "fight-club"],
    "mulholland-drive": ["black-swan", "sixth-sense", "the-prestige", "donnie-darko"],
    "truman-show": ["shawshank-redemption", "gone-girl", "mulholland-drive", "fight-club"],
}


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


def _display_title(slug: str) -> str:
    return FILM_TITLES.get(slug, slug.replace("-", " ").title())


def _query_lenses(query: str) -> list[str]:
    lowered = query.lower()
    lenses = []
    words = set(lowered.replace("?", " ").replace(",", " ").replace(".", " ").split())
    for lens, keywords in THEME_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords) or words.intersection(keywords):
            lenses.append(lens)
    unique = []
    for lens in lenses:
        if lens not in unique:
            unique.append(lens)
    return unique[:3] or ["ambiguity"]


def _source_label(source_type: str) -> str:
    labels = {
        "review": "criticism",
        "interview": "creator material",
        "essay": "essay",
        "academic": "scholarship",
        "screenplay": "story text",
        "production_notes": "production context",
        "festival_qa": "festival Q&A",
        "educational_essay": "institutional essay",
        "video_essay_transcript": "video essay",
        "director_commentary": "commentary",
        "cast_interview": "cast interview",
        "craft_article": "craft analysis",
        "film_history": "film history",
        "book_excerpt": "book excerpt",
    }
    return labels.get(source_type, source_type.replace("_", " "))


def _source_trail_note(source_type: str, title: str, film_slug: str, query: str) -> str:
    film = _display_title(film_slug)
    lowered = query.lower()
    if source_type == "review":
        return f"Opens up how critics framed {film}'s emotional effect and what viewers are meant to feel unsettled by."
    if source_type == "interview":
        return f"Looks for creator-side clues about intention, process, and the artistic choices behind {film}."
    if source_type == "essay":
        return f"Pushes past plot into motifs, symbols, and the bigger interpretive questions around {film}."
    if source_type == "academic":
        return f"Tests the deeper theoretical frame: identity, genre, psychology, and why {film} keeps inviting competing readings."
    if source_type == "screenplay":
        return f"Returns to story structure: what the scenes, reversals, and character beats make possible."
    if source_type == "production_notes":
        return f"Checks the behind-the-scenes choices that shape the film's mood, performances, and visual logic."
    if source_type == "festival_qa":
        return f"Looks for the live explanation layer: what the filmmaker emphasized when answering audience questions about {film}."
    if source_type == "educational_essay":
        return f"Offers a curated critical pathway into {film}'s motifs, genre history, and interpretive pressure points."
    if source_type == "video_essay_transcript":
        return f"Follows a modern scene-by-scene reading, useful for visual motifs and the question of how {film} teaches us to watch it."
    if source_type == "cast_interview":
        return f"Tracks how performance choices shape character psychology and the emotional temperature of {film}."
    if source_type == "craft_article":
        return f"Looks at the visual and sonic machinery behind the mood: framing, light, production design, and texture."
    if source_type == "film_history":
        return f"Places {film} in its release moment and genre lineage, opening questions about context and influence."
    if "influence" in lowered:
        return f"Helps trace what {film} seems to borrow, transform, or pass on to later films."
    return f"Adds another angle on the question this reading is circling in {film}."


def _coverage_note(level: str, chunks: list[RetrievedChunk]) -> str:
    film_count = len({chunk.film_slug for chunk in chunks})
    source_count = len({chunk.source_key for chunk in chunks})
    if level == "high":
        return f"Strong trail: this read draws on {source_count} pieces across {film_count} film{'s' if film_count != 1 else ''}."
    if level == "medium":
        return f"Good trail: there is enough material for a reading, with room for a richer pass as the library grows."
    return "Thin trail: Motif needs more relevant material before it can make this reading confidently."


def _build_consensus(query: str, chunks: list[RetrievedChunk], level: str) -> str:
    films = [film for film, _ in Counter(chunk.film_slug for chunk in chunks).most_common()]
    lenses = _query_lenses(query)
    lead = THEME_CONNECTIONS[lenses[0]]
    film_sentence_parts = []
    for film in films[:4]:
        reading = FILM_READINGS.get(film)
        if reading:
            film_sentence_parts.append(f"{_display_title(film)} {reading}.")

    if not film_sentence_parts:
        return "Motif does not have enough relevant material to shape a confident interpretation yet."

    if len(films) == 1:
        body = film_sentence_parts[0]
        lens = lenses[0]
        if lens == "loneliness":
            turn = "The film's loneliness is active rather than passive: it turns solitude into suspicion, fantasy, and finally a dangerous performance of purpose."
        elif lens == "ending":
            turn = "The ending matters because it does not simply reveal what happened; it reveals what kind of story the character needed to believe."
        elif lens == "violence":
            turn = "The violence reads as a failed language: a way to force the world to answer when ordinary connection has collapsed."
        elif lens == "obsession":
            turn = "The obsession is the engine of the film: it gives the character structure while quietly shrinking their world."
        elif lens == "influence":
            turn = "The influence is less a copied plot than a shared grammar of looking: noir suspicion, psychological subjectivity, and images that behave like symptoms."
        else:
            turn = "The fracture is not just psychological; it is cinematic. Behavior, framing, repetition, and role-play show a person becoming trapped inside an image of themselves."
        return (
            f"{lead} {body} {turn}"
        )

    connection = " ".join(THEME_CONNECTIONS[lens] for lens in lenses[1:])
    comparison = "; ".join(film_sentence_parts)
    return (
        f"{lead} {connection} Motif's read is that these films make the self feel cinematic: something edited, performed, doubled, "
        f"watched, or obsessively replayed. {comparison} Together, they suggest that the question is not solved by picking one literal explanation. "
        "The pattern is emotional: the image, role, memory, or fixation becomes the place where the character tries to survive."
    )


def _build_alternatives(query: str, chunks: list[RetrievedChunk]) -> list[str]:
    lenses = _query_lenses(query)
    films = [film for film, _ in Counter(chunk.film_slug for chunk in chunks).most_common()]
    alternatives = []
    if "doubling" in lenses or "identity" in lenses:
        alternatives.append("A psychoanalytic reading sees the double as a return of the disowned self: desire, shame, aggression, or grief made visible.")
    if "performance" in lenses:
        alternatives.append("A performance reading treats the fracture as social rather than purely internal: the character is damaged by the roles their world rewards.")
    if "loneliness" in lenses:
        alternatives.append("A social reading treats loneliness as environmental: city streets, rehearsal rooms, stages, apartments, and institutions become machines that keep people apart.")
    if "ending" in lenses or "ambiguity" in lenses:
        alternatives.append("A puzzle-box reading asks what literally happened; a stronger emotional reading asks why the film needs reality to feel unstable in the first place.")
    if "violence" in lenses:
        alternatives.append("A political reading sees violence as a symptom of systems that give characters spectacle and control instead of intimacy or care.")
    if "obsession" in lenses:
        alternatives.append("A formal reading follows repetition: the same image, gesture, or fantasy returns until obsession starts directing the film.")
    if len(films) > 1:
        alternatives.append("A formal reading focuses less on plot and more on structure: repetition, unreliable perspective, and abrupt tonal shifts make the viewer experience the split.")
    if not alternatives:
        alternatives.append("A symbolic reading treats the film's strange details as emotional logic rather than puzzle pieces to decode one by one.")
    return alternatives[:3]


def _creator_perspective(types: set[str], films: list[str]) -> str:
    film_names = ", ".join(_display_title(film) for film in films[:3])
    if "interview" in types or "production_notes" in types:
        return (
            f"The production and creator-adjacent material points toward construction rather than accident: in {film_names}, style, casting, setting, "
            "and performance are part of the argument about identity."
        )
    return "Motif found mostly critical material here, so the creator angle should be treated as suggestive rather than definitive."


def _critical_reception(types: set[str], films: list[str]) -> str:
    if "review" in types or "essay" in types or "academic" in types:
        names = ", ".join(_display_title(film) for film in films[:3])
        return (
            f"The critical trail around {names} tends to circle ambiguity, performance, and psychological instability. The useful tension is that critics often read these films both as character studies and as machines for making the viewer feel unstable too."
        )
    return "The current trail is light on criticism, so Motif is keeping this part modest."


def _related_films(films: list[str]) -> list[str]:
    related = []
    for film in films:
        for candidate in RELATED_BY_THEME.get(film, []):
            if candidate not in films and candidate in FILM_TITLES and candidate not in related:
                related.append(candidate)
    return [_display_title(film) for film in related[:5]]


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
    seen_sources = set()
    for chunk in chunks:
        if chunk.source_key in seen_sources:
            continue
        meta = source_metadata.get(chunk.source_key)
        if not meta:
            continue
        seen_sources.add(chunk.source_key)
        citations.append(
            SourceCitation(
                **meta,
                chunk_id=chunk.chunk_id,
                film_slug=chunk.film_slug,
                score=round(chunk.score, 3),
                excerpt=None,
                trail_note=_source_trail_note(
                    source_type=str(meta.get("source_type", "")),
                    title=str(meta.get("title", "")),
                    film_slug=chunk.film_slug,
                    query=request_query,
                ),
            )
        )

    films = [film for film, _ in Counter(chunk.film_slug for chunk in chunks).most_common()]
    types = {chunk.source_type for chunk in chunks}
    score = coverage_score(chunks)
    level = coverage_level(score)
    refused = level == "low"

    if refused:
        note = _coverage_note(level, chunks)
    else:
        note = _coverage_note(level, chunks)

    films = [film for film, _ in Counter(chunk.film_slug for chunk in chunks).most_common()]
    if refused:
        consensus = "Motif does not have enough of a trail to answer this in a way that would feel honest. Try broadening the film filters or asking across the full library."
        alternatives = []
    else:
        consensus = _build_consensus(request_query, chunks, level)
        alternatives = _build_alternatives(request_query, chunks)

    return AnalysisResponse(
        consensus_interpretation=consensus,
        alternative_interpretations=alternatives,
        director_creator_perspective=_creator_perspective(types, films),
        critical_reception=_critical_reception(types, films),
        related_films=_related_films(films),
        cited_sources=citations,
        coverage_score=score,
        coverage_level=level,
        refused=refused,
        retrieval_notes=note,
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
    )
    return synthesize(query, chunks)


def interpretation_map_query(query: str, film_slugs: list[str], source_types: list[str], top_k: int) -> InterpretationMapResponse:
    analysis = answer_query(query, film_slugs, source_types, top_k)
    return InterpretationMapResponse(
        query=query,
        central_reading=analysis.consensus_interpretation,
        interpretive_branches=analysis.alternative_interpretations,
        tensions=[
            "literal plot explanation vs emotional logic",
            "creator intention vs viewer interpretation",
            "psychological realism vs cinematic dream structure",
        ],
        related_films=analysis.related_films,
        trail=analysis.cited_sources,
        coverage_score=analysis.coverage_score,
        coverage_level=analysis.coverage_level,
    )


def film_comparison_query(query: str, film_slugs: list[str], source_types: list[str], top_k: int) -> FilmComparisonResponse:
    analysis = answer_query(query, film_slugs, source_types, top_k)
    films = [_display_title(film) for film in film_slugs]
    return FilmComparisonResponse(
        query=query,
        films=films,
        shared_terrain=analysis.consensus_interpretation,
        key_differences=analysis.alternative_interpretations
        or ["One film may externalize the crisis through genre while the other internalizes it through performance and point of view."],
        bridge_films=analysis.related_films,
        trail=analysis.cited_sources,
        coverage_score=analysis.coverage_score,
        coverage_level=analysis.coverage_level,
    )


def theme_explorer_query(query: str, theme: str, film_slugs: list[str], source_types: list[str], top_k: int) -> ThemeExplorerResponse:
    themed_query = f"{theme}: {query}" if theme else query
    analysis = answer_query(themed_query, film_slugs, source_types, top_k)
    return ThemeExplorerResponse(
        query=query,
        theme=theme or _query_lenses(query)[0],
        overview=analysis.consensus_interpretation,
        motif_patterns=analysis.alternative_interpretations,
        films_to_follow=analysis.related_films,
        trail=analysis.cited_sources,
        coverage_score=analysis.coverage_score,
        coverage_level=analysis.coverage_level,
    )
