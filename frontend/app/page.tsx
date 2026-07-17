"use client";

import { useMemo, useState } from "react";
import { ArrowRight, Clapperboard, Eye, Film, Loader2, ScanLine, Sparkles, SplitSquareHorizontal } from "lucide-react";
import { allLenses, demos, films } from "./filmConfig";

type Mode = "analyze_film" | "compare_films" | "explore_theme";

type DebugChunk = {
  chunk_id: string;
  text: string;
  film_slug: string;
  source_key: string;
  source_type: string;
  score: number;
  vector_score?: number;
  bm25_score?: number;
  rerank_score?: number;
  quality_score: string;
  source_role: string;
  lens_tags: string[];
};

type AnswerResponse = {
  mode: Mode;
  answer: string;
  thesis?: string;
  sections: Array<{ title?: string; body?: string }>;
  coverage_score: number;
  coverage_level: "high" | "medium" | "low";
  refused: boolean;
  retrieval_notes: string;
  debug_chunks: DebugChunk[];
};

const modes: Array<{ id: Mode; label: string; copy: string; icon: typeof Film }> = [
  { id: "analyze_film", label: "Analyze a Film", copy: "Pick one film and one lens.", icon: ScanLine },
  { id: "compare_films", label: "Compare Films", copy: "Choose exactly two films.", icon: SplitSquareHorizontal },
  { id: "explore_theme", label: "Explore a Theme", copy: "Follow one idea across the collection.", icon: Eye },
];

const filmTitle = (slug?: string | null) => films.find((film) => film.slug === slug)?.title ?? "";

export default function Home() {
  const [mode, setMode] = useState<Mode>("analyze_film");
  const [filmA, setFilmA] = useState("memento");
  const [filmB, setFilmB] = useState("black-swan");
  const [lens, setLens] = useState("Memory");
  const [angle, setAngle] = useState("");
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const debug = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("debug") === "1";
  const activeFilm = films.find((film) => film.slug === filmA);
  const availableLenses = useMemo(() => {
    if (mode === "explore_theme") return allLenses;
    if (mode === "compare_films") {
      const first = films.find((film) => film.slug === filmA)?.lenses ?? [];
      const second = films.find((film) => film.slug === filmB)?.lenses ?? [];
      return Array.from(new Set([...first, ...second, ...allLenses.slice(0, 6)]));
    }
    return activeFilm?.lenses ?? allLenses;
  }, [activeFilm?.lenses, filmA, filmB, mode]);

  function chooseMode(nextMode: Mode) {
    setMode(nextMode);
    setAnswer(null);
    setError(null);
    if (nextMode === "explore_theme" && !allLenses.includes(lens)) setLens("Identity");
    if (nextMode === "analyze_film") setFilmB("");
    if (nextMode === "compare_films" && (!filmB || filmB === filmA)) setFilmB(films.find((film) => film.slug !== filmA)?.slug ?? "");
  }

  function chooseFilm(slug: string) {
    if (mode === "compare_films") {
      if (slug === filmA) {
        setFilmA(filmB || slug);
        setFilmB("");
        return;
      }
      if (slug === filmB) {
        setFilmB("");
        return;
      }
      if (!filmA) setFilmA(slug);
      else setFilmB(slug);
      return;
    }
    setFilmA(slug);
    const next = films.find((film) => film.slug === slug)?.lenses[0];
    if (next) setLens(next);
  }

  async function run(payloadOverride?: Partial<{ mode: Mode; filmA: string; filmB: string; lens: string }>) {
    const nextMode = payloadOverride?.mode ?? mode;
    const nextFilmA = payloadOverride?.filmA ?? filmA;
    const nextFilmB = payloadOverride?.filmB ?? filmB;
    const nextLens = payloadOverride?.lens ?? lens;

    if (nextMode === "analyze_film" && !nextFilmA) {
      setError("Choose a film first.");
      return;
    }
    if (nextMode === "compare_films" && (!nextFilmA || !nextFilmB || nextFilmA === nextFilmB)) {
      setError("Choose two different films.");
      return;
    }
    if (!nextLens) {
      setError("Choose a lens.");
      return;
    }

    setMode(nextMode);
    setFilmA(nextFilmA);
    if (nextMode === "compare_films") setFilmB(nextFilmB);
    setLens(nextLens);
    setLoading(true);
    setError(null);
    setAnswer(null);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: nextMode,
          film_a: nextMode === "explore_theme" ? null : nextFilmA,
          film_b: nextMode === "compare_films" ? nextFilmB : null,
          lens: nextLens,
          optional_question: angle.trim() || null,
          top_k: 12,
          include_debug: debug,
        }),
      });
      if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
      setAnswer(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="appShell">
      <section className="hero">
        <div className="brandMark">
          <Clapperboard size={34} />
          <span>Motif</span>
        </div>
        <div>
          <p className="eyebrow">Close readings for films that keep arguing back</p>
          <h1>What do you want to explore?</h1>
          <p className="heroCopy">
            Choose a path, pick the film or theme, and Motif will write a focused reading without turning the page into a research dashboard.
          </p>
        </div>
      </section>

      <section className="modeGrid" aria-label="Choose workflow">
        {modes.map((item) => {
          const Icon = item.icon;
          return (
            <button className={mode === item.id ? "modeCard active" : "modeCard"} key={item.id} onClick={() => chooseMode(item.id)}>
              <Icon size={22} />
              <strong>{item.label}</strong>
              <span>{item.copy}</span>
            </button>
          );
        })}
      </section>

      <section className="demoStrip">
        {demos.map((demo) => (
          <button key={`${demo.filmA}-${demo.lens}`} onClick={() => run({ mode: demo.mode as Mode, filmA: demo.filmA, lens: demo.lens })}>
            <span>{demo.label}</span>
            <strong>{demo.helper}</strong>
          </button>
        ))}
      </section>

      {mode !== "explore_theme" && (
        <section className="pickerBlock">
          <div className="blockHeader">
            <h2>{mode === "compare_films" ? "Choose two films" : "Choose a film"}</h2>
            {mode === "compare_films" && <p>{filmTitle(filmA) || "First film"} / {filmTitle(filmB) || "second film"}</p>}
          </div>
          <div className="filmGrid">
            {films.map((film) => {
              const selected = film.slug === filmA || film.slug === filmB;
              return (
                <button className={selected ? "filmCard selected" : "filmCard"} key={film.slug} onClick={() => chooseFilm(film.slug)}>
                  <strong>{film.title}</strong>
                  <span>{film.lenses.slice(0, 4).join(" / ")}</span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      <section className="pickerBlock">
        <div className="blockHeader">
          <h2>{mode === "explore_theme" ? "Choose a theme" : "Choose a lens"}</h2>
          <p>{lens}</p>
        </div>
        <div className="lensGrid">
          {availableLenses.map((item) => (
            <button className={lens === item ? "lensPill active" : "lensPill"} key={item} onClick={() => setLens(item)}>
              {item}
            </button>
          ))}
        </div>
      </section>

      <section className="angleBar">
        <label>
          <span>Add a specific angle</span>
          <input value={angle} onChange={(event) => setAngle(event.target.value)} placeholder="Optional, e.g. focus on structure" />
        </label>
        <button onClick={() => run()} disabled={loading}>
          {loading ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
          Read it
        </button>
      </section>

      {error && <section className="errorState">{error}</section>}

      {answer && (
        <section className={answer.refused ? "answerPanel refused" : "answerPanel"}>
          <div className="answerMeta">
            <span>{answer.coverage_level} confidence</span>
            <span>{answer.retrieval_notes}</span>
          </div>
          {answer.thesis && <h2>{answer.thesis}</h2>}
          <p className="answerText">{answer.answer}</p>
          {answer.sections?.length > 0 && (
            <div className="readingBeats">
              {answer.sections.map((section, index) => (
                <article key={`${section.title ?? "beat"}-${index}`}>
                  <strong>{section.title || `Point ${index + 1}`}</strong>
                  <p>{section.body || ""}</p>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {debug && answer?.debug_chunks?.length ? (
        <section className="debugPanel">
          <h2>Debug Retrieval</h2>
          {answer.debug_chunks.map((chunk, index) => (
            <details key={chunk.chunk_id}>
              <summary>
                {index + 1}. {filmTitle(chunk.film_slug)} / {chunk.source_key} / {chunk.quality_score} / {chunk.rerank_score?.toFixed(3)}
              </summary>
              <p>{chunk.source_role} / {chunk.lens_tags.join(", ")}</p>
              <pre>{chunk.text}</pre>
            </details>
          ))}
        </section>
      ) : null}

      <button className="floatingRun" onClick={() => run()} disabled={loading} aria-label="Run selected reading">
        <ArrowRight size={22} />
      </button>
    </main>
  );
}
