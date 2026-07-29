"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Loader2, RotateCcw } from "lucide-react";
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
  sections: Array<{ label?: string; title?: string; body?: string }>;
  evidence_cards?: Array<{ label?: string; title?: string; body?: string }>;
  theme_films?: Array<{ rank?: number; slug: string; title: string; year?: number; director?: string; summary?: string }>;
  coverage_score: number;
  coverage_level: "high" | "medium" | "low";
  refused: boolean;
  retrieval_notes: string;
  debug_chunks: DebugChunk[];
  suggested_pairings?: Array<{ film_slug: string; title: string; lens: string; score?: number }>;
};

type FilmRecommendation = {
  lenses: Array<{ lens: string; score: number }>;
  specific_angles: Array<{ angle: string; score: number; maps_to?: string[] }>;
};

type RecommendationsResponse = {
  films: Record<string, FilmRecommendation>;
};

type CompareLensSuggestion = {
  lens: string;
  score: number;
  film_a_score: number;
  film_b_score: number;
};

const fallbackAnswerPatterns = [
  "the relevant film detail is:",
  "pattern built through repeated scenes and formal choices",
  "not as an idea stated in dialogue",
  "theme context",
  "awards and reception",
  "cast and performance",
];

const workflows: Array<{ id: Mode; title: string; body: string; kicker: string }> = [
  { id: "analyze_film", title: "Analyze a Film", body: "One film, one idea, four pieces of evidence.", kicker: "Close Reading" },
  { id: "compare_films", title: "Compare Films", body: "Two films considered side by side through a shared concern.", kicker: "Pairing" },
  { id: "explore_theme", title: "Explore a Theme", body: "A ranked path through the collection.", kicker: "Collection" },
];

const titleFor = (slug?: string | null) => films.find((film) => film.slug === slug)?.title ?? "";
const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function looksLikeFallbackReading(body: AnswerResponse) {
  if (body.mode === "explore_theme") return false;
  if (body.refused) return false;
  const cards = body.evidence_cards?.length ? body.evidence_cards : body.sections ?? [];
  if (!body.thesis || cards.length < 4) return true;
  const combined = [body.thesis, ...cards.flatMap((card) => [card.title ?? "", card.body ?? ""])]
    .join(" ")
    .toLowerCase();
  const patternHits = fallbackAnswerPatterns.filter((pattern) => combined.includes(pattern)).length;
  const weakCards = cards.filter((card) => {
    const text = `${card.title ?? ""} ${card.body ?? ""}`.toLowerCase();
    return (
      !card.body ||
      text.includes("the relevant film detail is:") ||
      text.includes("american psychological") ||
      text.includes("directed by") ||
      text.includes("starring")
    );
  }).length;
  return patternHits >= 2 || weakCards >= 2;
}

export default function Home() {
  const [mode, setMode] = useState<Mode | null>(null);
  const [step, setStep] = useState<Step>("mode");
  const [filmA, setFilmA] = useState("");
  const [filmB, setFilmB] = useState("");
  const [lens, setLens] = useState("");
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationsResponse | null>(null);
  const [compareLensSuggestions, setCompareLensSuggestions] = useState<CompareLensSuggestion[]>([]);

  const debug = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("debug") === "1";

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiBase}/recommendations`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body: RecommendationsResponse | null) => {
        if (!cancelled && body?.films) setRecommendations(body);
      })
      .catch(() => {
        // Static filmConfig remains the fallback when the backend is unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (mode !== "compare_films" || !filmA || !filmB || filmA === filmB) {
      setCompareLensSuggestions([]);
      return;
    }
    let cancelled = false;
    fetch(`${apiBase}/recommendations/compare?film_a=${encodeURIComponent(filmA)}&film_b=${encodeURIComponent(filmB)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { lenses?: CompareLensSuggestion[] } | null) => {
        if (!cancelled) setCompareLensSuggestions(body?.lenses ?? []);
      })
      .catch(() => {
        if (!cancelled) setCompareLensSuggestions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, filmA, filmB]);

  function filmLensesFor(slug?: string) {
    if (!slug) return [];
    const dynamic = recommendations?.films?.[slug]?.lenses
      ?.map((item) => item.lens)
      .filter((item) => globalLenses.includes(item as (typeof globalLenses)[number]));
    if (dynamic?.length) return dynamic.slice(0, 5);
    return [...(films.find((film) => film.slug === slug)?.lenses ?? [])];
  }

  function specificAnglesFor(slug?: string) {
    if (!slug) return [];
    const dynamic = recommendations?.films?.[slug]?.specific_angles?.map((item) => item.angle);
    if (dynamic?.length) return dynamic.slice(0, 6);
    return [...(films.find((film) => film.slug === slug)?.specificAngles ?? [])];
  }

  const recommendedLenses = useMemo(() => {
    if (!mode || mode === "explore_theme") return [...globalLenses];
    if (mode === "compare_films") {
      if (compareLensSuggestions.length) return compareLensSuggestions.map((item) => item.lens);
      const first: string[] = filmLensesFor(filmA);
      const second: string[] = filmLensesFor(filmB);
      const shared = first.filter((item) => second.includes(item));
      return shared.length ? shared : globalLenses.filter((item) => first.includes(item) || second.includes(item));
    }
    return filmLensesFor(filmA);
  }, [mode, filmA, filmB, recommendations, compareLensSuggestions]);

  const specificAngles = useMemo(() => {
    if (mode === "analyze_film") return specificAnglesFor(filmA);
    if (mode === "compare_films") {
      return Array.from(new Set([...specificAnglesFor(filmA), ...specificAnglesFor(filmB)]));
    }
    return [];
  }, [mode, filmA, filmB, recommendations]);

  const hasRequiredFilms =
    mode === "explore_theme" ||
    (mode === "analyze_film" && Boolean(filmA)) ||
    (mode === "compare_films" && Boolean(filmA) && Boolean(filmB) && filmA !== filmB);
  const canGenerate = step === "lens" && Boolean(mode && hasRequiredFilms && lens);

  const disabledReason = !mode
    ? "Choose a workflow first."
    : mode === "analyze_film" && !filmA
        ? "Choose a film."
        : mode === "compare_films" && (!filmA || !filmB || filmA === filmB)
          ? "Choose two different films."
          : !lens
            ? mode === "explore_theme"
              ? "Choose a theme."
              : "Choose a lens."
            : "";

  function startWorkflow(nextMode: Mode) {
    setMode(nextMode);
    setFilmA("");
    setFilmB("");
    setLens("");
    setAnswer(null);
    setError(null);
    setLoading(false);
    setStep(nextMode === "explore_theme" ? "lens" : "film");
  }

  function startOver() {
    setMode(null);
    setFilmA("");
    setFilmB("");
    setLens("");
    setAnswer(null);
    setError(null);
    setLoading(false);
    setStep("mode");
  }

  function goBack() {
    setError(null);
    setLoading(false);
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
    setLoading(false);
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
      const response = await fetch(`${apiBase}/answer`, {
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
      if (!response.ok) {
        let message = `The backend returned ${response.status}.`;
        try {
          const problem = (await response.json()) as { detail?: string };
          if (problem.detail) message = problem.detail;
        } catch {
          // Keep the status-based message if the backend did not return JSON.
        }
        throw new Error(message);
      }
      const body = (await response.json()) as AnswerResponse;
      if (looksLikeFallbackReading(body)) {
        throw new Error("The backend returned retrieved text instead of a generated reading. Check the Render OpenAI key and redeploy the backend.");
      }
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
  const evidenceCards = answer?.evidence_cards?.length ? answer.evidence_cards : answer?.sections ?? [];
  const themeFilms = answer?.theme_films ?? [];
  const suggestedPairings = answer?.suggested_pairings ?? [];

  function jumpToPairing(pairing: { film_slug: string; lens: string }) {
    setMode("compare_films");
    setFilmA(filmA);
    setFilmB(pairing.film_slug);
    setLens(pairing.lens);
    setAnswer(null);
    setError(null);
    setLoading(false);
    setStep("lens");
  }

  return (
    <main className="appShell">
      <section className="hero">
        <div className="logoLockup">
          <span>Motif</span>
        </div>
        <p>Explore themes and ideas across psychological films.</p>
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
            {workflows.map((workflow) => (
              <button key={workflow.id} className="workflowCard" onClick={() => startWorkflow(workflow.id)}>
                <strong>{workflow.title}</strong>
                <small>{workflow.kicker}</small>
                <span>{workflow.body}</span>
              </button>
            ))}
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
                      {mode === "compare_films" ? (isA ? "Film A" : "Film B") : "Selected"}
                    </span>
                  )}
                  <strong>{film.title}</strong>
                  <small>
                    {film.year} / {film.director}
                  </small>
                  {(isA || isB) && (
                    <div className="selectedLenses">
                      {filmLensesFor(film.slug).map((item) => (
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
              {loading && canGenerate ? <Loader2 className="spin" size={18} /> : null}
              Generate Reading
            </button>
            <span className={canGenerate ? "readyText" : "inlineError"}>
              {loading && canGenerate ? loadingText : canGenerate ? `Selected: ${lens}` : disabledReason}
            </span>
          </div>
        </section>
      )}

      {error && step !== "film" && <section className="errorState">{error}</section>}

      {step === "answer" && answer && (
        <section className={answer.refused ? "answerPanel refused" : "answerPanel"}>
          <div className="answerMeta">
            <span>{mode === "compare_films" ? "Film Comparison" : mode === "explore_theme" ? "Theme Exploration" : "Film Analysis"}</span>
          </div>
          {mode === "explore_theme" && themeFilms.length > 0 && (
            <div className="themeFilmGrid">
              {themeFilms.map((film) => (
                <article key={film.slug} className="themeFilmCard">
                  <span>#{film.rank}</span>
                  <strong>{film.title}</strong>
                  <small>
                    {film.year} / {film.director}
                  </small>
                  <p>{film.summary}</p>
                </article>
              ))}
            </div>
          )}
          {mode !== "explore_theme" && answer.thesis && (
            <div className="thesisBoard">
              <span>{answer.refused ? "Not enough material" : "Thesis"}</span>
              <h1>{answer.thesis}</h1>
            </div>
          )}
          {mode !== "explore_theme" && answer.refused && evidenceCards.length > 0 && (
            <div className="suggestionGrid">
              {evidenceCards.map((section, index) => (
                <article key={`${section.label ?? section.title ?? "suggestion"}-${index}`}>
                  <span>{section.label || "Suggestion"}</span>
                  <strong>{section.title || "Try another path"}</strong>
                  <p>{section.body || ""}</p>
                </article>
              ))}
            </div>
          )}
          {mode !== "explore_theme" && !answer.refused && evidenceCards.length > 0 && (
            <div className="evidenceGrid">
              {evidenceCards.slice(0, 4).map((section, index) => (
                <article key={`${section.label ?? section.title ?? "evidence"}-${index}`}>
                  <span>{section.label || "Evidence"}</span>
                  <strong>{section.title || section.label || "Evidence"}</strong>
                  <p>{section.body || ""}</p>
                </article>
              ))}
            </div>
          )}
          {mode === "analyze_film" && !answer.refused && suggestedPairings.length > 0 && (
            <div className="pairingRail">
              <h2>Compare this with</h2>
              <div>
                {suggestedPairings.map((pairing) => (
                  <button key={`${pairing.film_slug}-${pairing.lens}`} onClick={() => jumpToPairing(pairing)}>
                    <span>{pairing.lens}</span>
                    <strong>{pairing.title}</strong>
                  </button>
                ))}
              </div>
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
