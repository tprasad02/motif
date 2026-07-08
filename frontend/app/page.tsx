"use client";

import { FormEvent, useState } from "react";
import { Clapperboard, Search, SlidersHorizontal } from "lucide-react";

type Citation = {
  source_key: string;
  title: string;
  author?: string;
  publisher?: string;
  source_type: string;
  url?: string;
  chunk_id: string;
};

type AnalysisResponse = {
  consensus_interpretation: string;
  alternative_interpretations: string[];
  director_creator_perspective: string;
  critical_reception: string;
  related_films: string[];
  cited_sources: Citation[];
  coverage_score: number;
  retrieval_notes: string;
};

const films = [
  ["mulholland-drive", "Mulholland Drive"],
  ["persona", "Persona"],
  ["black-swan", "Black Swan"],
  ["perfect-blue", "Perfect Blue"],
  ["taxi-driver", "Taxi Driver"],
];

export default function Home() {
  const [query, setQuery] = useState("How do doubling and performance fracture identity?");
  const [selectedFilms, setSelectedFilms] = useState<string[]>([]);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setResult(null);
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, film_slugs: selectedFilms, max_chunks: 12 }),
    });
    setResult(await response.json());
    setLoading(false);
  }

  function toggleFilm(slug: string) {
    setSelectedFilms((current) =>
      current.includes(slug) ? current.filter((item) => item !== slug) : [...current, slug],
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
              <p>Cinema analysis corpus</p>
            </div>
          </div>

          <div className="filterHeader">
            <SlidersHorizontal size={18} />
            <span>Corpus Focus</span>
          </div>
          <div className="filmList">
            {films.map(([slug, title]) => (
              <label key={slug} className="filmToggle">
                <input
                  type="checkbox"
                  checked={selectedFilms.includes(slug)}
                  onChange={() => toggleFilm(slug)}
                />
                <span>{title}</span>
              </label>
            ))}
          </div>
        </aside>

        <section className="analysisPane">
          <form onSubmit={submit} className="queryBar">
            <Search size={20} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} />
            <button disabled={loading}>{loading ? "Searching" : "Analyze"}</button>
          </form>

          {result ? (
            <div className="answerGrid">
              <section className="primaryAnswer">
                <div className="score">Coverage {Math.round(result.coverage_score * 100)}%</div>
                <h2>Consensus Interpretation</h2>
                <p>{result.consensus_interpretation}</p>
              </section>

              <section>
                <h2>Alternative Interpretations</h2>
                {result.alternative_interpretations.map((item) => (
                  <p key={item}>{item}</p>
                ))}
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

              <section>
                <h2>Cited Sources</h2>
                <div className="sources">
                  {result.cited_sources.map((source) => (
                    <a key={`${source.source_key}-${source.chunk_id}`} href={source.url ?? "#"}>
                      <span>{source.source_type}</span>
                      {source.title}
                    </a>
                  ))}
                </div>
              </section>
            </div>
          ) : (
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

