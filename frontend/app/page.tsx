"use client";

import { FormEvent, useState } from "react";
import { AlertTriangle, BookOpen, Clapperboard, Filter, Loader2, Search } from "lucide-react";

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
      setError(err instanceof Error ? err.message : "Unable to reach Motif API");
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
              <p>Cinema analysis corpus</p>
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
              <span>Sources</span>
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
          <form onSubmit={submit} className="queryBar">
            <Search size={20} />
            <input
              aria-label="Ask Motif"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask about interpretation, influence, comparison, or theme"
            />
            <button disabled={loading}>{loading ? <Loader2 className="spin" size={18} /> : "Answer"}</button>
          </form>

          {error && (
            <div className="errorState">
              <AlertTriangle size={20} />
              <span>{error}</span>
            </div>
          )}

          {loading && (
            <div className="emptyState">
              <h2>Retrieving evidence</h2>
              <p>Motif is searching the curated corpus and checking whether source coverage is strong enough to answer.</p>
            </div>
          )}

          {result && (
            <div className="answerGrid">
              <section className={result.refused ? "primaryAnswer warningPanel" : "primaryAnswer"}>
                <div className={`score ${result.coverage_level}`}>{result.coverage_level} coverage</div>
                <h2>Consensus Interpretation</h2>
                <p>{result.consensus_interpretation}</p>
                <p className="note">{result.retrieval_notes}</p>
              </section>

              <section>
                <h2>Alternative Interpretations</h2>
                {result.alternative_interpretations.length ? (
                  result.alternative_interpretations.map((item) => <p key={item}>{item}</p>)
                ) : (
                  <p>No grounded alternatives available at this coverage level.</p>
                )}
              </section>

              <section>
                <h2>Creator Perspective</h2>
                <p>{result.director_creator_perspective}</p>
              </section>

              <section>
                <h2>Critical Reception</h2>
                <p>{result.critical_reception}</p>
              </section>

              <section>
                <h2>Related Films</h2>
                <p>{result.related_films.length ? result.related_films.join(", ") : "No related films retrieved yet."}</p>
              </section>

              <section className="citationPanel">
                <h2>Cited Sources</h2>
                <div className="sources">
                  {result.cited_sources.map((source) => (
                    <a
                      className="citationCard"
                      key={`${source.source_key}-${source.chunk_id}`}
                      href={source.url ?? "#"}
                    >
                      <span>{source.source_type}</span>
                      <strong>{source.title}</strong>
                      <small>
                        {source.film_slug} {source.score ? `score ${source.score}` : ""}
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
              <h2>Ask an interpretive question</h2>
              <p>Compare films, trace influences, test readings, or explore a recurring theme across the curated corpus.</p>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
