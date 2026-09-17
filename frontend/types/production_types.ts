import type { components } from "@/types/generated/api";

export type Mode = "analyze_film" | "compare_films" | "explore_lens";
export type Step = "mode" | "film" | "lens" | "answer";
export type LensOption = { lens: string; angle?: string };
export type PosterRecord = {
  slug: string;
  title: string;
  year: number;
  director: string;
  posterUrl: string | null;
  tmdbId: number | null;
};

// we keep this for now, but eventually they need to go to backend models
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
export type AnalysisResponse =
  components["schemas"]["AnalysisResponse"];

// export type FilmRecommendation =
//   components["schemas"]["FilmRecommendation"];

// export type RecommendationsResponse =
//   components["schemas"]["RecommendationsResponse"];

// export type CompareLensSuggestion =
//   components["schemas"]["CompareLensSuggestion"];