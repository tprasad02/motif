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
