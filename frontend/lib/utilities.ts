import type { Step } from "@/types/production_types";

export function reselectFilms(
  setStep: (step: Step) => void,
  setFilmA: (film: string) => void,
  setFilmB: (film: string) => void,
) {
  setFilmA("");
  setFilmB("");
  setStep("film");
}
