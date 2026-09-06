"use client";

import { type CSSProperties, useEffect, useMemo, useState } from "react";
import { ArrowLeft, RotateCcw } from "lucide-react";
import { films } from "./filmConfig";

type Mode = "analyze_film" | "compare_films" | "explore_lens";
type Step = "mode" | "film" | "lens" | "answer";

type DebugChunk = {
  chunk_id: string;
  text: string;
  film_slug: string;
  source_key: string;
  source_title?: string;
  source_type: string;
  score: number;
  vector_score?: number;
  bm25_score?: number;
  rerank_score?: number;
  quality_score: string;
  source_role: string;
  lens_tags: string[];
  section_title?: string;
  chunk_role: string;
  selection_reason?: string;
  used_by_evidence_cards?: string[];
};

type AnswerResponse = {
  mode: Mode;
  answer: string;
  thesis?: string;
  sections: Array<{ label?: string; title?: string; body?: string; chunk_ids?: string }>;
  evidence_cards?: Array<{ label?: string; title?: string; body?: string; chunk_ids?: string }>;
  lens_films?: Array<{ rank?: number; slug: string; title: string; year?: number; director?: string; summary?: string }>;
  coverage_score: number;
  coverage_level: "high" | "medium" | "low";
  refused: boolean;
  retrieval_notes: string;
  debug_chunks: DebugChunk[];
  suggested_pairings?: Array<{ film_slug: string; title: string; lens: string; score?: number }>;
};

type FilmRecommendation = {
  lenses: Array<{ lens?: string; angle?: string; semantic_score: number; definition?: string }>;
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
type LensOption = { lens: string; angle?: string };

type PosterRecord = {
  slug: string;
  title: string;
  year: number;
  director: string;
  posterUrl: string | null;
  tmdbId: number | null;
};

const fallbackAnswerPatterns = [
  "the relevant film detail is:",
  "pattern built through repeated scenes and formal choices",
  "not as an idea stated in dialogue",
  "lens context",
  "awards and reception",
  "cast and performance",
];

const workflows: Array<{ id: Mode; title: string; body: string; kicker: string }> = [
  { id: "analyze_film", title: "Analyze a Film", body: "One film, one idea, four pieces of evidence.", kicker: "Close Reading" },
  { id: "compare_films", title: "Compare Films", body: "Two films considered side by side through a shared concern.", kicker: "Pairing" },
  { id: "explore_lens", title: "Explore Lenses", body: "A ranked path through the collection.", kicker: "Collection" },
];

const titleFor = (slug?: string | null) => films.find((film) => film.slug === slug)?.title ?? "";
const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const posterCacheKey = "motifPosterCache:v1";

function apiUrl(path: string) {
  return `${apiBase}/${path.replace(/^\/+/, "")}`;
}

function loadFailedMessage(error: unknown) {
  const message = error instanceof Error ? error.message : "";
  if (!message) return "Load failed.";
  if (message.toLowerCase().startsWith("load failed")) return message;
  return `Load failed. ${message}`;
}

function looksLikeFallbackReading(body: AnswerResponse) {
  if (body.mode === "explore_lens") return false;
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
  const [posters, setPosters] = useState<Record<string, PosterRecord>>({});

  const debug =
    typeof window !== "undefined" &&
    (new URLSearchParams(window.location.search).get("debug") === "1" || window.location.pathname.startsWith("/debug"));

  useEffect(() => {
    let cancelled = false;
    fetch(apiUrl("/recommendations"))
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
    let cancelled = false;
    try {
      const cached = window.localStorage.getItem(posterCacheKey);
      if (cached) {
        const parsed = JSON.parse(cached) as { posters?: PosterRecord[] };
        if (parsed.posters?.length) {
          setPosters(Object.fromEntries(parsed.posters.map((poster) => [poster.slug, poster])));
        }
      }
    } catch {
      // Poster cache is optional.
    }

    fetch("/api/posters")
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { posters?: PosterRecord[] } | null) => {
        if (cancelled || !body?.posters?.length) return;
        setPosters(Object.fromEntries(body.posters.map((poster) => [poster.slug, poster])));
        try {
          window.localStorage.setItem(posterCacheKey, JSON.stringify({ posters: body.posters, cachedAt: Date.now() }));
        } catch {
          // Ignore storage quota or privacy-mode failures.
        }
      })
      .catch(() => {
        // Text-only film cards remain the fallback.
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
    fetch(apiUrl(`/recommendations/compare?film_a=${encodeURIComponent(filmA)}&film_b=${encodeURIComponent(filmB)}`))
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
    return recommendations?.films?.[slug]?.lenses?.map((item) => ({ lens: item.lens ?? "", angle: item.angle })).filter((item) => item.lens).slice(0, 5) ?? [];
  }

  function specificAnglesFor(slug?: string) {
    if (!slug) return [];
    const dynamic = recommendations?.films?.[slug]?.specific_angles?.map((item) => item.angle);
    if (dynamic?.length) return dynamic.slice(0, 6);
    return [];
  }

  const collectionLenses: LensOption[] = useMemo(
    () => Array.from(new Set(Object.values(recommendations?.films ?? {}).flatMap((film) => film.lenses.map((item) => item.lens ?? "")).filter(Boolean))).sort().map((lens) => ({ lens })),
    [recommendations],
  );

  const recommendedLenses = useMemo<LensOption[]>(() => {
    if (!mode || mode === "explore_lens") return collectionLenses;
    if (mode === "compare_films") {
      if (compareLensSuggestions.length) return compareLensSuggestions.map((item) => ({ lens: item.lens }));
      const first = filmLensesFor(filmA);
      const second = filmLensesFor(filmB);
      return first.filter((item) => second.some((other) => other.lens === item.lens));
    }
    return filmLensesFor(filmA);
  }, [mode, filmA, filmB, recommendations, compareLensSuggestions, collectionLenses]);

  const specificAngles = useMemo(() => {
    if (mode === "analyze_film") return specificAnglesFor(filmA);
    if (mode === "compare_films") {
      return Array.from(new Set([...specificAnglesFor(filmA), ...specificAnglesFor(filmB)]));
    }
    return [];
  }, [mode, filmA, filmB, recommendations]);

  const hasRequiredFilms =
    mode === "explore_lens" ||
    (mode === "analyze_film" && Boolean(filmA)) ||
    (mode === "compare_films" && Boolean(filmA) && Boolean(filmB) && filmA !== filmB);
  const canGenerate = step === "lens" && Boolean(mode && hasRequiredFilms && lens && recommendedLenses.some((item) => item.lens === lens));

  const disabledReason = !mode
    ? "Choose a workflow first."
    : mode === "analyze_film" && !filmA
        ? "Choose a film."
        : mode === "compare_films" && (!filmA || !filmB || filmA === filmB)
          ? "Choose two different films."
          : recommendedLenses.length === 0
            ? "Motif has not published an evidence-validated lens for this selection yet."
          : !lens
            ? mode === "explore_lens"
              ? "Choose a lens."
              : "Choose a lens."
            : "";

  useEffect(() => {
    if (lens && !recommendedLenses.some((item) => item.lens === lens)) setLens("");
  }, [lens, recommendedLenses]);

  function startWorkflow(nextMode: Mode) {
    setMode(nextMode);
    setFilmA("");
    setFilmB("");
    setLens("");
    setAnswer(null);
    setError(null);
    setLoading(false);
    setStep(nextMode === "explore_lens" ? "lens" : "film");
  }

  function exploreFeaturedFilm(slug: string) {
    setMode("analyze_film");
    setFilmA(slug);
    setFilmB("");
    setLens("");
    setAnswer(null);
    setError(null);
    setLoading(false);
    setStep("lens");
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
      setStep(mode === "explore_lens" ? "mode" : "film");
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
      const response = await fetch(apiUrl("/answer"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          film_a: mode === "explore_lens" ? null : filmA,
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
      setError(loadFailedMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const progressStages =
    mode === "explore_lens"
      ? ["Reading Collection", "Ranking Films", "Shaping Cards", "Finishing"]
      : ["Retrieving Sources", "Analyzing Evidence", "Synthesizing Reading", "Writing Analysis"];
  const evidenceCards = answer?.evidence_cards?.length ? answer.evidence_cards : answer?.sections ?? [];
  const lensFilms = answer?.lens_films ?? [];
  const suggestedPairings = answer?.suggested_pairings ?? [];
  const featuredFilms = [...films, ...films];

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
        <p>Explore lenses and ideas across psychological films.</p>
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
        <div className="pageTurn">
          <section className="featuredShelf" aria-label="Featured film shelf">
            <div className="shelfHeader">
              <span>Featured Shelf</span>
              <img src="/tmdb-logo.svg" alt="The Movie Database" />
            </div>
            <div className="posterMarquee">
              <div className="posterTrack">
                {featuredFilms.map((film, index) => {
                  const poster = posters[film.slug]?.posterUrl;
                  return (
                    <button key={`${film.slug}-${index}`} className="featuredPoster" onClick={() => exploreFeaturedFilm(film.slug)}>
                      {poster ? <img src={poster} alt={`${film.title} poster`} /> : <span>{film.title}</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          </section>
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
        </div>
      )}

      {step === "film" && mode && mode !== "explore_lens" && (
        <section className="stepPanel pageTurn">
          <div className="stepHeader">
            <span>Step 1</span>
            <h1>{mode === "compare_films" ? "Choose two films" : "Choose a film"}</h1>
            <p>{mode === "compare_films" ? "First click sets Film A. Second click sets Film B." : "Pick the film Motif should read closely."}</p>
          </div>
          <div className="filmShelf" aria-label="Choose a film">
            {films.map((film) => {
              const isA = film.slug === filmA;
              const isB = film.slug === filmB;
              const poster = posters[film.slug]?.posterUrl;
              return (
                <button key={film.slug} className={isA || isB ? "shelfFilmCard selected" : "shelfFilmCard"} onClick={() => selectFilm(film.slug)}>
                  {(isA || isB) && (
                    <span className="selectedBadge">
                      {mode === "compare_films" ? (isA ? "Film A" : "Film B") : "Selected"}
                    </span>
                  )}
                  <div className="posterFrame">
                    {poster ? <img src={poster} alt={`${film.title} poster`} /> : <span>{film.title}</span>}
                  </div>
                  <strong>{film.title}</strong>
                  <small>
                    {film.year} / {film.director}
                  </small>
                  {(isA || isB) && (
                    <div className="selectedLenses">
                      {filmLensesFor(film.slug).map((item) => (
                        <span key={item.lens}>{item.lens}</span>
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
        <section className="stepPanel pageTurn">
          <div className="stepHeader">
            <span>{mode === "explore_lens" ? "Step 1" : "Step 2"}</span>
            <h1>{mode === "explore_lens" ? "Choose a lens" : "Choose a lens"}</h1>
            <p>
              {mode === "analyze_film" && `${titleFor(filmA)} will be read through one recommended lens.`}
              {mode === "compare_films" && `${titleFor(filmA)} and ${titleFor(filmB)} will be compared through one shared lens.`}
              {mode === "explore_lens" && "Pick one primary lens to follow across the film collection."}
            </p>
          </div>
          <div className="lensGrid">
            {recommendedLenses.map((item, index) => (
              <button
                key={item.lens}
                className={lens === item.lens ? "lensPill active" : "lensPill"}
                style={{ "--i": index } as CSSProperties}
                onClick={() => setLens(item.lens)}
              >
                <span>{item.lens}</span>
                {item.angle && <small>{item.angle}</small>}
              </button>
            ))}
          </div>
          {recommendedLenses.length === 0 && <p className="inlineError">No evidence-validated lenses are available yet.</p>}
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
              Generate Reading
            </button>
            {!loading && <span className={canGenerate ? "readyText" : "inlineError"}>{canGenerate ? `Selected: ${lens}` : disabledReason}</span>}
          </div>
          {loading && canGenerate && <ReadingProgress stages={progressStages} />}
        </section>
      )}

      {error && step !== "film" && <section className="errorState">{error}</section>}

      {step === "answer" && answer && (
        <section className={answer.refused ? "answerPanel refused pageTurn" : "answerPanel pageTurn"}>
          <div className="answerMeta">
            <span>{mode === "compare_films" ? "Film Comparison" : mode === "explore_lens" ? "Lens Exploration" : "Film Analysis"}</span>
          </div>
          {mode === "explore_lens" && lensFilms.length > 0 && (
            <div className="lensFilmGrid">
              {lensFilms.map((film) => (
                <article key={film.slug} className="lensFilmCard">
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
          {mode !== "explore_lens" && answer.thesis && (
            <div className="thesisBoard">
              <span>{answer.refused ? "Not enough material" : "Thesis"}</span>
              <h1>{answer.thesis}</h1>
            </div>
          )}
          {mode !== "explore_lens" && answer.refused && evidenceCards.length > 0 && (
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
          {mode !== "explore_lens" && !answer.refused && evidenceCards.length > 0 && (
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
          <p>
            Hidden developer view showing what retrieval sent into the reading pipeline. Normal users do not see this panel.
          </p>
          {answer.debug_chunks.map((chunk, index) => (
            <details key={chunk.chunk_id}>
              <summary>
                {index + 1}. {titleFor(chunk.film_slug)} / {chunk.source_title || chunk.source_key}
              </summary>
              <dl>
                <div>
                  <dt>Source role</dt>
                  <dd>{chunk.source_role}</dd>
                </div>
                <div>
                  <dt>Chunk role</dt>
                  <dd>{chunk.chunk_role}</dd>
                </div>
                <div>
                  <dt>Rerank score</dt>
                  <dd>{chunk.rerank_score?.toFixed(3) ?? chunk.score.toFixed(3)}</dd>
                </div>
                <div>
                  <dt>Vector / BM25</dt>
                  <dd>
                    {chunk.vector_score?.toFixed(3) ?? "-"} / {chunk.bm25_score?.toFixed(3) ?? "-"}
                  </dd>
                </div>
                <div>
                  <dt>Selected because</dt>
                  <dd>{chunk.selection_reason || "selected by retrieval score"}</dd>
                </div>
                <div>
                  <dt>Evidence card</dt>
                  <dd>{chunk.used_by_evidence_cards?.length ? chunk.used_by_evidence_cards.join(", ") : "Not directly cited by a card"}</dd>
                </div>
                <div>
                  <dt>Lens tags</dt>
                  <dd>{chunk.lens_tags.join(", ") || "-"}</dd>
                </div>
              </dl>
              <pre>{chunk.text}</pre>
            </details>
          ))}
        </section>
      ) : null}
    </main>
  );
}

function ReadingProgress({ stages }: { stages: string[] }) {
  return (
    <div className="readingProgress" aria-live="polite">
      <div className="progressStageWindow">
        {stages.map((stage, index) => (
          <span key={stage} style={{ "--i": index } as CSSProperties}>
            {stage}
          </span>
        ))}
      </div>
      <div className="progressBar">
        <span />
      </div>
    </div>
  );
}
