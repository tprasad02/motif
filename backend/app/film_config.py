FILMS = [
    {"slug": "shawshank-redemption", "title": "The Shawshank Redemption"},
    {"slug": "fight-club", "title": "Fight Club"},
    {"slug": "one-flew-over-the-cuckoos-nest", "title": "One Flew Over the Cuckoo's Nest"},
    {"slug": "se7en", "title": "Se7en"},
    {"slug": "silence-of-the-lambs", "title": "The Silence of the Lambs"},
    {"slug": "the-prestige", "title": "The Prestige"},
    {"slug": "memento", "title": "Memento"},
    {"slug": "taxi-driver", "title": "Taxi Driver"},
    {"slug": "shutter-island", "title": "Shutter Island"},
    {"slug": "black-swan", "title": "Black Swan"},
    {"slug": "sixth-sense", "title": "The Sixth Sense"},
    {"slug": "prisoners", "title": "Prisoners"},
    {"slug": "gone-girl", "title": "Gone Girl"},
    {"slug": "requiem-for-a-dream", "title": "Requiem for a Dream"},
    {"slug": "donnie-darko", "title": "Donnie Darko"},
    {"slug": "the-machinist", "title": "The Machinist"},
    {"slug": "mulholland-drive", "title": "Mulholland Drive"},
    {"slug": "truman-show", "title": "The Truman Show"},
]

FILM_TITLES = {film["slug"]: film["title"] for film in FILMS}

PRIMARY_LENSES = [
    "Memory",
    "Identity",
    "Obsession",
    "Reality vs Illusion",
    "Control",
    "Freedom",
    "Isolation",
    "Guilt",
    "Performance",
    "Violence",
    "Justice",
    "Trauma",
]

FILM_LENSES = {
    "shawshank-redemption": ["Freedom", "Justice", "Control", "Hope", "Institutional Control", "Friendship"],
    "fight-club": ["Identity", "Violence", "Obsession", "Masculinity", "Consumerism", "Doubles"],
    "one-flew-over-the-cuckoos-nest": ["Control", "Freedom", "Identity", "Institutional Power", "Rebellion", "Madness"],
    "se7en": ["Justice", "Violence", "Moral Decay", "Obsession", "Guilt"],
    "silence-of-the-lambs": ["Power", "Fear", "Identity", "Gender", "Control"],
    "the-prestige": ["Obsession", "Performance", "Sacrifice", "Doubles", "Truth"],
    "memento": ["Memory", "Identity", "Guilt", "Reality vs Illusion", "Truth", "Self-Deception"],
    "taxi-driver": ["Isolation", "Masculinity", "Violence", "Alienation", "Moral Delusion"],
    "shutter-island": ["Reality vs Illusion", "Trauma", "Guilt", "Denial", "Madness"],
    "black-swan": ["Performance", "Identity", "Obsession", "Control", "Doubles"],
    "sixth-sense": ["Trauma", "Reality vs Illusion", "Isolation", "Grief", "Perception", "Childhood", "Revelation"],
    "prisoners": ["Justice", "Faith", "Violence", "Obsession", "Moral Ambiguity"],
    "gone-girl": ["Performance", "Marriage", "Media", "Control", "Identity"],
    "requiem-for-a-dream": ["Obsession", "Control", "Trauma", "Addiction", "Desire", "Decay", "Body"],
    "donnie-darko": ["Reality vs Illusion", "Isolation", "Trauma", "Time", "Fate", "Madness"],
    "the-machinist": ["Guilt", "Trauma", "Identity", "Insomnia", "Body", "Self-Punishment"],
    "mulholland-drive": ["Dream Logic", "Identity", "Desire", "Hollywood", "Reality vs Illusion"],
    "truman-show": ["Surveillance", "Freedom", "Reality vs Illusion", "Control", "Performance"],
}

ALL_LENSES = sorted({lens for lenses in FILM_LENSES.values() for lens in lenses})

SECONDARY_TO_PRIMARY = {
    "Addiction": ["Obsession", "Control", "Trauma"],
    "Alienation": ["Isolation", "Identity"],
    "Authorship": ["Control", "Performance"],
    "Body": ["Trauma", "Identity"],
    "Childhood": ["Trauma"],
    "Consumerism": ["Control", "Identity"],
    "Decay": ["Trauma", "Obsession"],
    "Denial": ["Reality vs Illusion", "Trauma", "Guilt"],
    "Desire": ["Obsession", "Identity"],
    "Doubles": ["Identity", "Reality vs Illusion", "Performance"],
    "Dream Logic": ["Reality vs Illusion", "Identity"],
    "Faith": ["Justice", "Guilt"],
    "Fate": ["Reality vs Illusion", "Control"],
    "Fear": ["Trauma", "Control"],
    "Friendship": ["Freedom"],
    "Gender": ["Identity", "Control"],
    "Grief": ["Trauma", "Guilt"],
    "Hollywood": ["Performance", "Reality vs Illusion"],
    "Hope": ["Freedom"],
    "Insomnia": ["Trauma", "Guilt"],
    "Institutional Control": ["Control", "Freedom"],
    "Institutional Power": ["Control", "Freedom"],
    "Madness": ["Reality vs Illusion", "Trauma", "Identity"],
    "Manipulation": ["Control", "Performance"],
    "Marriage": ["Performance", "Identity", "Control"],
    "Masculinity": ["Identity", "Violence", "Isolation"],
    "Media": ["Performance", "Control"],
    "Moral Ambiguity": ["Justice", "Guilt"],
    "Moral Decay": ["Justice", "Violence"],
    "Moral Delusion": ["Reality vs Illusion", "Violence", "Isolation"],
    "Perception": ["Reality vs Illusion"],
    "Power": ["Control"],
    "Punishment": ["Justice", "Violence", "Guilt"],
    "Rebellion": ["Freedom", "Control"],
    "Revelation": ["Reality vs Illusion"],
    "Sacrifice": ["Obsession", "Performance", "Guilt"],
    "Self-Deception": ["Memory", "Reality vs Illusion", "Guilt"],
    "Self-Punishment": ["Guilt", "Trauma"],
    "Surveillance": ["Control", "Reality vs Illusion", "Freedom"],
    "Time": ["Memory", "Reality vs Illusion"],
    "Truth": ["Reality vs Illusion", "Memory", "Guilt"],
}

LENS_ALIASES = {
    "Memory": ["memory", "remember", "remembering", "forgetting", "amnesia", "recollection", "photograph", "tattoo", "past"],
    "Identity": ["identity", "self", "double", "split", "persona", "role", "mask", "mirror", "name"],
    "Obsession": ["obsession", "compulsion", "fixation", "desire", "pursuit", "addiction", "rivalry", "perfection"],
    "Reality vs Illusion": ["reality", "illusion", "dream", "fantasy", "delusion", "perception", "truth", "unreliable", "constructed"],
    "Control": ["control", "power", "authority", "institution", "surveillance", "manipulation", "discipline", "confinement"],
    "Freedom": ["freedom", "escape", "hope", "release", "rebellion", "liberation", "choice", "outside"],
    "Isolation": ["isolation", "loneliness", "alienation", "alone", "detachment", "outsider", "urban", "disconnection"],
    "Guilt": ["guilt", "confession", "sin", "responsibility", "shame", "remorse", "punishment", "repression"],
    "Performance": ["performance", "role", "stage", "act", "acting", "show", "spectacle", "mask", "presentation"],
    "Violence": ["violence", "brutality", "blood", "murder", "fight", "punishment", "threat", "body"],
    "Justice": ["justice", "law", "detective", "punishment", "revenge", "trial", "crime", "morality"],
    "Trauma": ["trauma", "wound", "grief", "denial", "repression", "loss", "fear", "nightmare", "damage"],
}

FILM_LENS_COMPANIONS = {
    ("fight-club", "Obsession"): ["Identity", "Violence", "Consumerism", "Masculinity"],
    ("shawshank-redemption", "Justice"): ["Freedom", "Hope", "Institutional Control"],
    ("se7en", "Guilt"): ["Justice", "Violence", "Moral Decay", "punishment", "sin"],
    ("se7en", "Obsession"): ["Justice", "Violence", "Moral Decay", "Guilt", "punishment", "sin"],
    ("sixth-sense", "Isolation"): ["Grief", "Perception", "Denial", "Trauma"],
    ("prisoners", "Obsession"): ["Justice", "Faith", "Violence", "revenge", "desperation", "fixation"],
}


def primary_lenses_for_film(film_slug: str) -> list[str]:
    return [lens for lens in FILM_LENSES.get(film_slug, []) if lens in PRIMARY_LENSES]


def secondary_lenses_for_film(film_slug: str) -> list[str]:
    return [lens for lens in FILM_LENSES.get(film_slug, []) if lens not in PRIMARY_LENSES]


def mapped_primary_lenses(lens: str) -> list[str]:
    if lens in PRIMARY_LENSES:
        return [lens]
    return SECONDARY_TO_PRIMARY.get(lens, [])


def expand_lens_terms(lens: str | None) -> list[str]:
    if not lens:
        return []
    terms: list[str] = [lens]
    if lens in PRIMARY_LENSES:
        terms.extend(
            secondary
            for secondary, primaries in SECONDARY_TO_PRIMARY.items()
            if lens in primaries
        )
    for primary in mapped_primary_lenses(lens):
        terms.append(primary)
        terms.extend(LENS_ALIASES.get(primary, []))
        terms.extend(
            secondary
            for secondary, primaries in SECONDARY_TO_PRIMARY.items()
            if primary in primaries
        )
    if lens not in PRIMARY_LENSES:
        terms.extend(LENS_ALIASES.get(lens, []))
    seen = set()
    expanded = []
    for term in terms:
        normalized = str(term).strip()
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            expanded.append(normalized)
    return expanded


def expand_film_lens_terms(film_slug: str | None, lens: str | None) -> list[str]:
    terms = expand_lens_terms(lens)
    if film_slug and lens:
        terms.extend(FILM_LENS_COMPANIONS.get((film_slug, lens), []))
    seen = set()
    expanded = []
    for term in terms:
        normalized = str(term).strip()
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            expanded.append(normalized)
    return expanded
