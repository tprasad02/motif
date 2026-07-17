"use client";

import { FormEvent, useState } from "react";
import { AlertTriangle, BookOpen, Clapperboard, Filter, Loader2, Search, Sparkles } from "lucide-react";

type Citation = {
  source_key: string;
  title: string;
  author?: string;
  publisher?: string;
  source_type: string;
  url?: string;
  chunk_id: string;
  film_slug?: string;
  score?: number;
  excerpt?: string;
  trail_note?: string;
};

type AnalysisResponse = {
  consensus_interpretation: string;
  alternative_interpretations: string[];
  director_creator_perspective: string;
  critical_reception: string;
  related_films: string[];
  cited_sources: Citation[];
  coverage_score: number;
  coverage_level: "high" | "medium" | "low";
  refused: boolean;
  retrieval_notes: string;
};

type InterpretationMapResponse = {
  query: string;
  central_reading: string;
  interpretive_branches: string[];
  tensions: string[];
  related_films: string[];
  trail: Citation[];
  coverage_score: number;
  coverage_level: "high" | "medium" | "low";
};

type FilmComparisonResponse = {
  query: string;
  films: string[];
  shared_terrain: string;
  key_differences: string[];
  bridge_films: string[];
  trail: Citation[];
  coverage_score: number;
  coverage_level: "high" | "medium" | "low";
};

type ThemeExplorerResponse = {
  query: string;
  theme: string;
  overview: string;
  motif_patterns: string[];
  films_to_follow: string[];
  trail: Citation[];
  coverage_score: number;
  coverage_level: "high" | "medium" | "low";
};

type Mode = "answer" | "interpretation-map" | "film-comparison" | "theme-explorer";
type Result =
  | { mode: "answer"; data: AnalysisResponse }
  | { mode: "interpretation-map"; data: InterpretationMapResponse }
  | { mode: "film-comparison"; data: FilmComparisonResponse }
  | { mode: "theme-explorer"; data: ThemeExplorerResponse };

const films = [
  ["shawshank-redemption", "The Shawshank Redemption"],
  ["fight-club", "Fight Club"],
  ["one-flew-over-the-cuckoos-nest", "One Flew Over the Cuckoo's Nest"],
  ["se7en", "Se7en"],
  ["silence-of-the-lambs", "The Silence of the Lambs"],
  ["the-prestige", "The Prestige"],
  ["memento", "Memento"],
  ["taxi-driver", "Taxi Driver"],
  ["shutter-island", "Shutter Island"],
  ["black-swan", "Black Swan"],
  ["sixth-sense", "The Sixth Sense"],
  ["prisoners", "Prisoners"],
  ["gone-girl", "Gone Girl"],
  ["requiem-for-a-dream", "Requiem for a Dream"],
  ["donnie-darko", "Donnie Darko"],
  ["the-machinist", "The Machinist"],
  ["mulholland-drive", "Mulholland Drive"],
  ["truman-show", "The Truman Show"],
];

const sourceTypes = [
  ["interview", "Creator Clues"],
  ["screenplay", "Story Beats"],
  ["production_notes", "Behind the Scenes"],
  ["festival_qa", "Festival Q&As"],
  ["academic", "Theory"],
  ["educational_essay", "Deep Reads"],
  ["video_essay_transcript", "Video Essays"],
  ["cast_interview", "Cast Signals"],
  ["craft_article", "Visual Craft"],
  ["film_history", "History"],
];

const sourceLabels: Record<string, string> = {
  review: "Review",
  interview: "Interview",
  festival_qa: "Q&A",
  educational_essay: "Essay",
  academic: "Criticism",
  screenplay: "Story",
  production_notes: "Behind the Scenes",
  video_essay_transcript: "Video Essay",
  director_commentary: "Commentary",
  cast_interview: "Cast",
  craft_article: "Craft",
  film_history: "History",
  book_excerpt: "Book",
};

const coverageLabels: Record<AnalysisResponse["coverage_level"], string> = {
  high: "Rich trail",
  medium: "Good trail",
  low: "Thin trail",
};

const promptIdeas = [
  "How do prison films turn routine into psychological pressure?",
  "Compare the twist endings in The Sixth Sense and Shutter Island.",
  "How does obsession become performance in The Prestige, Black Swan, and Gone Girl?",
  "What connects unreliable memory across Memento, Donnie Darko, and The Machinist?",
];

const modes: Array<{ id: Mode; label: string; helper: string }> = [
  { id: "answer", label: "The Read", helper: "Interpretation and sources" },
  { id: "interpretation-map", label: "Map", helper: "Competing readings" },
  { id: "film-comparison", label: "Compare", helper: "Two or more films" },
  { id: "theme-explorer", label: "Theme", helper: "Patterns across films" },
];

function titleForSlug(slug?: string) {
  return films.find(([filmSlug]) => filmSlug === slug)?.[1] ?? slug?.replaceAll("-", " ");
}

export default function Home() {
  const [query, setQuery] = useState("How do doubling and performance fracture identity across the corpus?");
  const [mode, setMode] = useState<Mode>("answer");
  const [selectedFilms, setSelectedFilms] = useState<string[]>([]);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function endpointFor(activeMode: Mode) {
    if (activeMode === "answer") return "/answer";
    return `/workflows/${activeMode}`;
  }

  function payloadFor(activeMode: Mode) {
    const base = {
      query,
      film_slugs: selectedFilms,
      source_types: selectedTypes,
      top_k: 12,
    };
    if (activeMode === "theme-explorer") {
      return {
        ...base,
        theme: query,
        themes: query ? [query] : [],
      };
    }
    if (activeMode === "film-comparison") {
      return {
        ...base,
        comparison_films: selectedFilms,
      };
    }
    if (activeMode === "interpretation-map") {
      return {
        ...base,
        primary_film: selectedFilms[0] ?? null,
      };
    }
    return base;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mode === "film-comparison" && selectedFilms.length < 2) {
      setError("Pick at least two films for Compare mode.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${endpointFor(mode)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloadFor(mode)),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }
      setResult({ mode, data: await response.json() } as Result);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Unable to reach Motif";
      setError(`Motif could not open that reel. ${detail}`);
    } finally {
      setLoading(false);
    }
  }

  function toggle(value: string, setter: (next: string[]) => void, current: string[]) {
    setter(current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  }

  function renderTrail(sources: Citation[]) {
    return (
      <section className="citationPanel">
        <h2>Follow the Trail</h2>
        <div className="sources">
          {sources.map((source) => (
            <a className="citationCard" key={`${source.source_key}-${source.chunk_id}`} href={source.url ?? "#"}>
              <span>{sourceLabels[source.source_type] ?? source.source_type.replaceAll("_", " ")}</span>
              <strong>{source.title}</strong>
              <small>
                {titleForSlug(source.film_slug)}
                {source.publisher ? ` / ${source.publisher}` : ""}
              </small>
              <p>{source.trail_note ?? "Opens another path into the film's interpretation."}</p>
            </a>
          ))}
        </div>
      </section>
    );
  }

  function renderResult(current: Result) {
    if (current.mode === "answer") {
      const data = current.data;
      return (
        <div className="answerGrid">
          <section className={data.refused ? "primaryAnswer warningPanel" : "primaryAnswer"}>
            <div className={`score ${data.coverage_level}`}>{coverageLabels[data.coverage_level]}</div>
            <div className="sectionKicker">
              <Sparkles size={16} />
              <span>Motif's take</span>
            </div>
            <h2>The Read</h2>
            <p>{data.consensus_interpretation}</p>
            <p className="note">{data.retrieval_notes}</p>
          </section>

          <section>
            <h2>Other Cuts</h2>
            {data.alternative_interpretations.length ? (
              data.alternative_interpretations.map((item) => <p key={item}>{item}</p>)
            ) : (
              <p>This pass points in one main direction. Broader filters may surface stranger side doors.</p>
            )}
          </section>

          <section>
            <h2>Director's Chair</h2>
            <p>{data.director_creator_perspective}</p>
          </section>

          <section>
            <h2>Critical Pulse</h2>
            <p>{data.critical_reception}</p>
          </section>

          <section>
            <h2>Double Features</h2>
            <div className="filmChips">
              {data.related_films.length ? data.related_films.map((film) => <span key={film}>{film}</span>) : <p>No close echoes found in this pass.</p>}
            </div>
          </section>

          {renderTrail(data.cited_sources)}
        </div>
      );
    }

    if (current.mode === "interpretation-map") {
      const data = current.data;
      return (
        <div className="answerGrid">
          <section className="primaryAnswer">
            <div className={`score ${data.coverage_level}`}>{coverageLabels[data.coverage_level]}</div>
            <div className="sectionKicker">
              <Sparkles size={16} />
              <span>Interpretation Map</span>
            </div>
            <h2>Central Reading</h2>
            <p>{data.central_reading}</p>
          </section>
          <section>
            <h2>Branches</h2>
            {data.interpretive_branches.map((item) => <p key={item}>{item}</p>)}
          </section>
          <section>
            <h2>Tensions</h2>
            {data.tensions.map((item) => <p key={item}>{item}</p>)}
          </section>
          <section>
            <h2>Related Films</h2>
            <div className="filmChips">{data.related_films.map((film) => <span key={film}>{film}</span>)}</div>
          </section>
          {renderTrail(data.trail)}
        </div>
      );
    }

    if (current.mode === "film-comparison") {
      const data = current.data;
      return (
        <div className="answerGrid">
          <section className="primaryAnswer">
            <div className={`score ${data.coverage_level}`}>{coverageLabels[data.coverage_level]}</div>
            <div className="sectionKicker">
              <Sparkles size={16} />
              <span>Film Comparison</span>
            </div>
            <h2>Shared Terrain</h2>
            <p>{data.shared_terrain}</p>
          </section>
          <section>
            <h2>Key Differences</h2>
            {data.key_differences.map((item) => <p key={item}>{item}</p>)}
          </section>
          <section>
            <h2>Bridge Films</h2>
            <div className="filmChips">{data.bridge_films.map((film) => <span key={film}>{film}</span>)}</div>
          </section>
          <section>
            <h2>Compared</h2>
            <div className="filmChips">{data.films.map((film) => <span key={film}>{titleForSlug(film)}</span>)}</div>
          </section>
          {renderTrail(data.trail)}
        </div>
      );
    }

    const data = current.data;
    return (
      <div className="answerGrid">
        <section className="primaryAnswer">
          <div className={`score ${data.coverage_level}`}>{coverageLabels[data.coverage_level]}</div>
          <div className="sectionKicker">
            <Sparkles size={16} />
            <span>Theme Explorer</span>
          </div>
          <h2>{data.theme || "Theme"}</h2>
          <p>{data.overview}</p>
        </section>
        <section>
          <h2>Motif Patterns</h2>
          {data.motif_patterns.map((item) => <p key={item}>{item}</p>)}
        </section>
        <section>
          <h2>Films to Follow</h2>
          <div className="filmChips">{data.films_to_follow.map((film) => <span key={film}>{film}</span>)}</div>
        </section>
        {renderTrail(data.trail)}
      </div>
    );
  }

  return (
    <main className="shell">
      <section className="workspace">
        <aside className="sidebar">
          <div className="brand">
            <Clapperboard size={28} />
            <div>
              <h1>Motif</h1>
              <p>Dream logic. Doubles. Dangerous close-ups.</p>
            </div>
          </div>

          <div className="filterBlock">
            <div className="filterHeader">
              <Filter size={18} />
              <span>Films</span>
            </div>
            <div className="filmList">
              {films.map(([slug, title]) => (
                <label key={slug} className="filmToggle">
                  <input
                    type="checkbox"
                    checked={selectedFilms.includes(slug)}
                    onChange={() => toggle(slug, setSelectedFilms, selectedFilms)}
                  />
                  <span>{title}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="filterBlock">
            <div className="filterHeader">
              <BookOpen size={18} />
              <span>Material Mix</span>
            </div>
            <div className="filmList">
              {sourceTypes.map(([type, label]) => (
                <label key={type} className="filmToggle">
                  <input
                    type="checkbox"
                    checked={selectedTypes.includes(type)}
                    onChange={() => toggle(type, setSelectedTypes, selectedTypes)}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </div>
        </aside>

        <section className="analysisPane">
          <div className="marquee">
            <div>
              <span className="eyebrow">Now analyzing</span>
              <h2>Psychological cinema, without the plot-summary fog.</h2>
            </div>
            <p>Ask Motif for a reading, a rivalry between interpretations, a director angle, or a path through related films.</p>
          </div>

          <div className="modeSwitcher" aria-label="Analysis mode">
            {modes.map((item) => (
              <button
                key={item.id}
                type="button"
                className={mode === item.id ? "active" : ""}
                onClick={() => {
                  setMode(item.id);
                  setResult(null);
                  setError(null);
                }}
              >
                <strong>{item.label}</strong>
                <span>{item.helper}</span>
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="queryBar">
            <Search size={20} />
            <input
              aria-label="Ask Motif"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask about interpretation, influence, comparison, or theme"
            />
            <button disabled={loading}>{loading ? <Loader2 className="spin" size={18} /> : "Roll"}</button>
          </form>

          {error && (
            <div className="errorState">
              <AlertTriangle size={20} />
              <div>
                <strong>The projector jammed.</strong>
                <span>{error}</span>
              </div>
            </div>
          )}

          {loading && (
            <div className="emptyState">
              <h2>Threading the scene</h2>
              <p>Motif is looking for the cleanest path through the films, criticism, and behind-the-scenes material.</p>
            </div>
          )}

          {result && renderResult(result)}

          {!result && !loading && !error && (
            <div className="emptyState">
              <h2>What scene are we opening?</h2>
              <p>Try a question about obsession, doubles, unreliable memory, performance, influence, or why a film refuses to explain itself.</p>
              <div className="promptDeck">
                {promptIdeas.map((idea) => (
                  <button key={idea} type="button" onClick={() => setQuery(idea)}>
                    {idea}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
