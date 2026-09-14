import type { DebugChunk  } from "@/types/debug_types";

export type Mode = "analyze_film" | "compare_films" | "explore_lens";
export type Step = "mode" | "film" | "lens" | "answer";

export type AnswerResponse = {
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

export type FilmRecommendation = {
  lenses: Array<{ lens?: string; angle?: string; semantic_score: number; definition?: string }>;
  specific_angles: Array<{ angle: string; score: number; maps_to?: string[] }>;
};

export type RecommendationsResponse = {
  films: Record<string, FilmRecommendation>;
};

export type CompareLensSuggestion = {
  lens: string;
  score: number;
  film_a_score: number;
  film_b_score: number;
};

export type LensOption = { lens: string; angle?: string };

export type PosterRecord = {
  slug: string;
  title: string;
  year: number;
  director: string;
  posterUrl: string | null;
  tmdbId: number | null;
};