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

const films = [
  ["mulholland-drive", "Mulholland Drive"],
  ["persona", "Persona"],
  ["black-swan", "Black Swan"],
  ["perfect-blue", "Perfect Blue"],
  ["taxi-driver", "Taxi Driver"],
  ["fight-club", "Fight Club"],
  ["the-lighthouse", "The Lighthouse"],
  ["shutter-island", "Shutter Island"],
  ["eternal-sunshine", "Eternal Sunshine"],
  ["synecdoche-new-york", "Synecdoche, New York"],
];

const sourceTypes = [
  ["review", "Reviews"],
  ["interview", "Interviews"],
  ["essay", "Essays"],
  ["academic", "Academic"],
  ["screenplay", "Screenplays"],
  ["production_notes", "Production Notes"],
  ["video_essay_transcript", "Video Essays"],
];

const sourceLabels: Record<string, string> = {
  review: "Review",
  interview: "Interview",
  essay: "Essay",
  academic: "Criticism",
  screenplay: "Story",
  production_notes: "Behind the Scenes",
  video_essay_transcript: "Video Essay",
};

const coverageLabels: Record<AnalysisResponse["coverage_level"], string> = {
  high: "Rich trail",
  medium: "Good trail",
  low: "Thin trail",
};

const promptIdeas = [
  "Why does Taxi Driver feel so lonely?",
  "Is Black Swan more about art or madness?",
  "How does Perfect Blue influence later identity thrillers?",
  "What makes Mulholland Drive resist one explanation?",
];

function titleForSlug(slug?: string) {
  return films.find(([filmSlug]) => filmSlug === slug)?.[1] ?? slug?.replaceAll("-", " ");
}

export default function Home() {
  const [query, setQuery] = useState("How do doubling and performance fracture identity across the corpus?");
  const [selectedFilms, setSelectedFilms] = useState<string[]>([]);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          film_slugs: selectedFilms,
          source_types: selectedTypes,
          top_k: 12,
        }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }
      setResult(await response.json());
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
              <span>The Shelf</span>
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

          {result && (
            <div className="answerGrid">
              <section className={result.refused ? "primaryAnswer warningPanel" : "primaryAnswer"}>
                <div className={`score ${result.coverage_level}`}>{coverageLabels[result.coverage_level]}</div>
                <div className="sectionKicker">
                  <Sparkles size={16} />
                  <span>Motif's take</span>
                </div>
                <h2>The Read</h2>
                <p>{result.consensus_interpretation}</p>
                <p className="note">{result.retrieval_notes}</p>
              </section>

              <section>
                <h2>Other Cuts</h2>
                {result.alternative_interpretations.length ? (
                  result.alternative_interpretations.map((item) => <p key={item}>{item}</p>)
                ) : (
                  <p>This pass points in one main direction. Broader filters may surface stranger side doors.</p>
                )}
              </section>

              <section>
                <h2>Director's Chair</h2>
                <p>{result.director_creator_perspective}</p>
              </section>

              <section>
                <h2>Critical Pulse</h2>
                <p>{result.critical_reception}</p>
              </section>

              <section>
                <h2>Double Features</h2>
                <div className="filmChips">
                  {result.related_films.length ? (
                    result.related_films.map((film) => <span key={film}>{film}</span>)
                  ) : (
                    <p>No close echoes found in this pass.</p>
                  )}
                </div>
              </section>

              <section className="citationPanel">
                <h2>Follow the Trail</h2>
                <div className="sources">
                  {result.cited_sources.map((source) => (
                    <a
                      className="citationCard"
                      key={`${source.source_key}-${source.chunk_id}`}
                      href={source.url ?? "#"}
                    >
                      <span>{sourceLabels[source.source_type] ?? source.source_type.replaceAll("_", " ")}</span>
                      <strong>{source.title}</strong>
                      <small>
                        {titleForSlug(source.film_slug)}
                      </small>
                      {source.excerpt && <p>{source.excerpt}</p>}
                    </a>
                  ))}
                </div>
              </section>
            </div>
          )}

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
