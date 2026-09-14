// utilities.ts
import type { Mode, Step } from "@/types/production_types";

export function reselectFilms(
    setMode: (mode:Mode) => void,
    setStep: (step:Step) => void,
    setFilmA: (film: string) => void,
    setFilmB: (film: string)=> void
)
{
    
    setMode("compare_films");
    setStep("film");
    setFilmA("");
    setFilmB("");
}