"use client";

import { useMemo, useState } from "react";
import { ArrowLeft, Check, Clapperboard, Eye, Film, Loader2, RotateCcw, ScanLine, SplitSquareHorizontal } from "lucide-react";
import { films, globalLenses } from "./filmConfig";

type Mode = "analyze_film" | "compare_films" | "explore_theme";
type Step = "mode" | "film" | "lens" | "answer";

type DebugChunk = {
  chunk_id: string;
  text: string;
  film_slug: string;
  source_key: string;
  source_type: string;
  score: number;
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

const workflows: Array<{ id: Mode; title: string; body: string; icon: typeof Film }> = [
  { id: "analyze_film", title: "Analyze a Film", body: "Choose one film and a strong lens for a close reading.", icon: ScanLine },
  { id: "compare_films", title: "Compare Films", body: "Choose two films and one shared lens.", icon: SplitSquareHorizontal },
  { id: "explore_theme", title: "Explore a Theme", body: "Choose one theme and trace it across the collection.", icon: Eye },
];

const titleFor = (slug?: string | null) => films.find((film) => film.slug === slug)?.title ?? "";

export default function Home() {
  const [mode, setMode] = useState<Mode | null>(null);
  const [step, setStep] = useState<Step>("mode");
  const [filmA, setFilmA] = useState("");
  const [filmB, setFilmB] = useState("");
  const [lens, setLens] = useState("");
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const debug = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("debug") === "1";
  const selectedFilmA = films.find((film) => film.slug === filmA);
  const selectedFilmB = films.find((film) => film.slug === filmB);

  const recommendedLenses = useMemo(() => {
    if (!mode || mode === "explore_theme") return [...globalLenses];
    if (mode === "compare_films") {
      const first: string[] = selectedFilmA ? [...selectedFilmA.lenses] : [];
      const second: string[] = selectedFilmB ? [...selectedFilmB.lenses] : [];
      const shared = first.filter((item) => second.includes(item));
      return shared.length ? shared : globalLenses.filter((item) => first.includes(item) || second.includes(item));
    }
    return selectedFilmA ? [...selectedFilmA.lenses] : [];
  }, [mode, selectedFilmA, selectedFilmB]);

  const specificAngles = useMemo(() => {
    if (mode === "analyze_film") return selectedFilmA ? [...selectedFilmA.specificAngles] : [];
    if (mode === "compare_films") {
      return Array.from(new Set([...(selectedFilmA?.specificAngles ?? []), ...(selectedFilmB?.specificAngles ?? [])]));
    }
    return [];
  }, [mode, selectedFilmA, selectedFilmB]);

  const canGenerate =
    Boolean(mode && lens) &&
    ((mode === "analyze_film" && Boolean(filmA)) ||
      (mode === "compare_films" && Boolean(filmA) && Boolean(filmB) && filmA !== filmB) ||
      mode === "explore_theme");

  const disabledReason = !mode
    ? "Choose a workflow first."
    : !lens
      ? mode === "explore_theme"
        ? "Choose a theme."
        : "Choose a lens."
      : mode === "analyze_film" && !filmA
        ? "Choose a film."
        : mode === "compare_films" && (!filmA || !filmB || filmA === filmB)
          ? "Choose two different films."
          : "";

  function startWorkflow(nextMode: Mode) {
    setMode(nextMode);
    setFilmA("");
    setFilmB("");
    setLens("");
    setAnswer(null);
    setError(null);
    setStep(nextMode === "explore_theme" ? "lens" : "film");
  }

  function startOver() {
    setMode(null);
    setFilmA("");
    setFilmB("");
    setLens("");
    setAnswer(null);
    setError(null);
    setStep("mode");
  }

  function goBack() {
    setError(null);
    if (step === "answer") {
      setAnswer(null);
      setStep("lens");
      return;
    }
    if (step === "lens") {
      setLens("");
      setStep(mode === "explore_theme" ? "mode" : "film");
      return;
    }
    if (step === "film") {
      setFilmA("");
      setFilmB("");
      setStep("mode");
      return;
    }
    startOver();
  }

  function selectFilm(slug: string) {
    setAnswer(null);
    setError(null);
    setLens("");
    if (mode === "compare_films") {
      if (!filmA || slug === filmA) {
        setFilmA(slug);
        return;
      }
      setFilmB(slug);
      return;
    }
    setFilmA(slug);
  }

  function continueFromFilm() {
    if (mode === "analyze_film" && !filmA) {
      setError("Choose a film to continue.");
      return;
    }
    if (mode === "compare_films" && (!filmA || !filmB || filmA === filmB)) {
      setError("Choose two different films to continue.");
      return;
    }
    setError(null);
    setStep("lens");
  }

  async function generateReading() {
    if (!mode || !canGenerate) return;
    setLoading(true);
    setError(null);
    setAnswer(null);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          film_a: mode === "explore_theme" ? null : filmA,
          film_b: mode === "compare_films" ? filmB : null,
          lens,
          optional_question: null,
          top_k: 12,
          include_debug: debug,
        }),
      });
      if (!response.ok) throw new Error(`The backend returned ${response.status}.`);
      const body = (await response.json()) as AnswerResponse;
      setAnswer(body);
      setStep("answer");
    } catch (err) {
      setError(err instanceof Error ? `Load failed. ${err.message}` : "Load failed.");
    } finally {
      setLoading(false);
    }
  }

  const loadingText =
    mode === "compare_films" ? "Comparing the films..." : mode === "explore_theme" ? "Exploring the theme..." : "Building the reading...";

  return (
    <main className="appShell">
      <section className="hero">
        <div className="logoLockup">
          <Clapperboard size={38} />
          <span>Motif</span>
        </div>
        <p>Motif: Explore themes and ideas across psychological films.</p>
      </section>

      <nav className="topActions" aria-label="Navigation actions">
        {step !== "mode" && (
          <button onClick={goBack}>
            <ArrowLeft size={17} />
            Back
          </button>
        )}
        {step !== "mode" && (
          <button onClick={startOver}>
            <RotateCcw size={17} />
            Start over
          </button>
        )}
      </nav>

      {step === "mode" && (
        <section className="workflowIntro">
          <h1>What do you want to explore?</h1>
          <div className="workflowGrid">
            {workflows.map((workflow) => {
              const Icon = workflow.icon;
              return (
                <button key={workflow.id} className="workflowCard" onClick={() => startWorkflow(workflow.id)}>
                  <Icon size={28} />
                  <strong>{workflow.title}</strong>
                  <span>{workflow.body}</span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {step === "film" && mode && mode !== "explore_theme" && (
        <section className="stepPanel">
          <div className="stepHeader">
            <span>Step 1</span>
            <h1>{mode === "compare_films" ? "Choose two films" : "Choose a film"}</h1>
            <p>{mode === "compare_films" ? "First click sets Film A. Second click sets Film B." : "Pick the film Motif should read closely."}</p>
          </div>
          <div className="filmGrid">
            {films.map((film) => {
              const isA = film.slug === filmA;
              const isB = film.slug === filmB;
              return (
                <button key={film.slug} className={isA || isB ? "filmCard selected" : "filmCard"} onClick={() => selectFilm(film.slug)}>
                  {(isA || isB) && (
                    <span className="selectedBadge">
                      <Check size={14} />
                      {mode === "compare_films" ? (isA ? "Film A" : "Film B") : "Selected"}
                    </span>
                  )}
                  <strong>{film.title}</strong>
                  <small>
                    {film.year} / {film.director}
                  </small>
                  {(isA || isB) && (
                    <div className="selectedLenses">
                      {film.lenses.map((item) => (
                        <span key={item}>{item}</span>
                      ))}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          <div className="footerAction">
            <button className="primaryButton" onClick={continueFromFilm} disabled={mode === "analyze_film" ? !filmA : !filmA || !filmB || filmA === filmB}>
              Choose lens
            </button>
            {error && <span className="inlineError">{error}</span>}
          </div>
        </section>
      )}

      {step === "lens" && mode && (
        <section className="stepPanel">
          <div className="stepHeader">
            <span>{mode === "explore_theme" ? "Step 1" : "Step 2"}</span>
            <h1>{mode === "explore_theme" ? "Choose a theme" : "Choose a lens"}</h1>
            <p>
              {mode === "analyze_film" && `${titleFor(filmA)} will be read through one recommended lens.`}
              {mode === "compare_films" && `${titleFor(filmA)} and ${titleFor(filmB)} will be compared through one shared lens.`}
              {mode === "explore_theme" && "Pick one primary theme to follow across the film collection."}
            </p>
          </div>
          <div className="lensGrid">
            {recommendedLenses.map((item) => (
              <button key={item} className={lens === item ? "lensPill active" : "lensPill"} onClick={() => setLens(item)}>
                {item}
              </button>
            ))}
          </div>
          {specificAngles.length > 0 && (
            <div className="specificAngles">
              <h2>More specific angles</h2>
              <div>
                {specificAngles.map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>
          )}
          <div className="footerAction">
            <button className="primaryButton" onClick={generateReading} disabled={!canGenerate || loading}>
              {loading ? <Loader2 className="spin" size={18} /> : null}
              Generate Reading
            </button>
            <span className={canGenerate ? "readyText" : "inlineError"}>{loading ? loadingText : canGenerate ? `Selected lens: ${lens}` : disabledReason}</span>
          </div>
        </section>
      )}

      {error && step !== "film" && <section className="errorState">{error}</section>}

      {step === "answer" && answer && (
        <section className={answer.refused ? "answerPanel refused" : "answerPanel"}>
          <div className="answerMeta">
            <span>{mode === "compare_films" ? "Film comparison" : mode === "explore_theme" ? "Theme exploration" : "Film analysis"}</span>
            <span>{answer.coverage_level} confidence</span>
          </div>
          {answer.thesis && <h1>{answer.thesis}</h1>}
          <p className="answerText">{answer.answer}</p>
          {answer.sections?.length > 0 && (
            <div className="readingBeats">
              {answer.sections.map((section, index) => (
                <article key={`${section.title ?? "point"}-${index}`}>
                  <strong>{section.title || `Point ${index + 1}`}</strong>
                  <p>{section.body || ""}</p>
                </article>
              ))}
            </div>
          )}
          <div className="answerActions">
            {mode !== "explore_theme" && <button onClick={() => setStep("film")}>Change film</button>}
            <button onClick={() => setStep("lens")}>{mode === "explore_theme" ? "Change theme" : "Change lens"}</button>
            <button onClick={startOver}>Start over</button>
          </div>
        </section>
      )}

      {debug && answer?.debug_chunks?.length ? (
        <section className="debugPanel">
          <h2>Debug Retrieval</h2>
          {answer.debug_chunks.map((chunk, index) => (
            <details key={chunk.chunk_id}>
              <summary>
                {index + 1}. {titleFor(chunk.film_slug)} / {chunk.source_key} / {chunk.quality_score} / {chunk.rerank_score?.toFixed(3)}
              </summary>
              <p>{chunk.source_role} / {chunk.lens_tags.join(", ")}</p>
              <pre>{chunk.text}</pre>
            </details>
          ))}
        </section>
      ) : null}
    </main>
  );
}
