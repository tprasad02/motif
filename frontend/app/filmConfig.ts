export const films = [
  { slug: "shawshank-redemption", title: "The Shawshank Redemption", lenses: ["Freedom", "Hope", "Institutional Control", "Friendship", "Justice"] },
  { slug: "fight-club", title: "Fight Club", lenses: ["Identity", "Masculinity", "Consumerism", "Violence", "Doubles"] },
  { slug: "one-flew-over-the-cuckoos-nest", title: "One Flew Over the Cuckoo's Nest", lenses: ["Control", "Institutional Power", "Freedom", "Rebellion", "Madness"] },
  { slug: "se7en", title: "Se7en", lenses: ["Justice", "Violence", "Moral Decay", "Obsession", "Guilt"] },
  { slug: "silence-of-the-lambs", title: "The Silence of the Lambs", lenses: ["Power", "Fear", "Identity", "Gender", "Control"] },
  { slug: "the-prestige", title: "The Prestige", lenses: ["Obsession", "Performance", "Sacrifice", "Doubles", "Truth"] },
  { slug: "memento", title: "Memento", lenses: ["Memory", "Truth", "Identity", "Guilt", "Self-Deception"] },
  { slug: "taxi-driver", title: "Taxi Driver", lenses: ["Isolation", "Masculinity", "Violence", "Alienation", "Moral Delusion"] },
  { slug: "shutter-island", title: "Shutter Island", lenses: ["Reality vs Illusion", "Trauma", "Guilt", "Denial", "Madness"] },
  { slug: "black-swan", title: "Black Swan", lenses: ["Performance", "Identity", "Obsession", "Control", "Doubles"] },
  { slug: "sixth-sense", title: "The Sixth Sense", lenses: ["Grief", "Perception", "Denial", "Childhood", "Revelation"] },
  { slug: "prisoners", title: "Prisoners", lenses: ["Justice", "Faith", "Violence", "Obsession", "Moral Ambiguity"] },
  { slug: "gone-girl", title: "Gone Girl", lenses: ["Performance", "Marriage", "Media", "Control", "Identity"] },
  { slug: "requiem-for-a-dream", title: "Requiem for a Dream", lenses: ["Addiction", "Obsession", "Desire", "Decay", "Control"] },
  { slug: "donnie-darko", title: "Donnie Darko", lenses: ["Time", "Fate", "Reality vs Illusion", "Alienation", "Madness"] },
  { slug: "the-machinist", title: "The Machinist", lenses: ["Guilt", "Insomnia", "Body", "Madness", "Self-Punishment"] },
  { slug: "mulholland-drive", title: "Mulholland Drive", lenses: ["Dream Logic", "Identity", "Desire", "Hollywood", "Reality vs Illusion"] },
  { slug: "truman-show", title: "The Truman Show", lenses: ["Surveillance", "Freedom", "Reality vs Illusion", "Control", "Performance"] },
] as const;

export const allLenses: string[] = Array.from(new Set(films.flatMap((film) => film.lenses))).sort();

export const demos = [
  { mode: "analyze_film", filmA: "memento", lens: "Memory", label: "Memento", helper: "Memory" },
  { mode: "analyze_film", filmA: "mulholland-drive", lens: "Reality vs Illusion", label: "Mulholland Drive", helper: "Reality vs Illusion" },
  { mode: "analyze_film", filmA: "black-swan", lens: "Performance", label: "Black Swan", helper: "Performance" },
  { mode: "analyze_film", filmA: "taxi-driver", lens: "Isolation", label: "Taxi Driver", helper: "Isolation" },
  { mode: "analyze_film", filmA: "truman-show", lens: "Control", label: "The Truman Show", helper: "Control" },
] as const;
