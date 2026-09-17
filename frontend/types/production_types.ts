import type { components } from "@/types/generated/api";
import type { DebugChunk } from "@/types/debug_types";

export type ApiAnalysisResponse = components["schemas"]["AnalysisResponse"];
export type GuidedAnswerRequest = components["schemas"]["GuidedAnswerRequest"];
export type RetrievedChunk = components["schemas"]["RetrievedChunkResponse"];
export type RetrieveResponse = components["schemas"]["RetrieveResponse"];

export type Mode = "analyze_film" | "compare_films" | "explore_lens";
export type Step = "mode" | "film" | "lens" | "answer";
export type LensOption = { lens: string };

// This narrows the generated API model to the fields the reading UI renders.
export type AnswerResponse = Omit<
  ApiAnalysisResponse,
  "mode" | "thesis" | "sections" | "evidence_cards" | "lens_films" | "debug_chunks" | "suggested_pairings"
> & {
  mode: Mode;
  thesis?: string;
  generation_failed?: boolean;
  sections: Array<{ label?: string; title?: string; body?: string; chunk_ids?: string }>;
  evidence_cards?: Array<{ label?: string; title?: string; body?: string; chunk_ids?: string }>;
  lens_films?: Array<{ rank?: number; slug: string; title: string; year?: number; director?: string; summary?: string }>;
  debug_chunks: DebugChunk[];
  suggested_pairings?: Array<{ film_slug: string; title: string; lens: string; score?: number }>;
};

// These endpoints currently return service-composed objects, so their display
// shapes remain explicit until response models are added to the backend routes.
export type FilmRecommendation = {
  lenses: Array<{ lens?: string; semantic_score?: number; definition?: string }>;
};

export type RecommendationsResponse = {
  films: Record<string, FilmRecommendation>;
  collection_lenses?: string[];
};

export type CompareLensSuggestion = {
  lens: string;
  score: number;
  film_a_score: number;
  film_b_score: number;
};

export type PosterRecord = {
  slug: string;
  title: string;
  year: number;
  director: string;
  posterUrl: string | null;
  tmdbId: number | null;
};
