from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models import (
    AnalysisResponse,
    AnswerRequest,
    FilmComparisonResponse,
    GuidedAnswerRequest,
    InterpretationMapResponse,
    RetrieveRequest,
    RetrieveResponse,
    ThemeExplorerResponse,
    WorkflowRequest,
)
from app.services.analysis import (
    LLMGenerationError,
    answer_from_request,
    answer_query,
    film_comparison_query,
    interpretation_map_query,
    retrieve_query,
    theme_explorer_query,
)
from app.services.recommendations import build_film_profiles, comparison_lens_suggestions, pairing_suggestions

app = FastAPI(title="Motif API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:\d+|http://127\.0\.0\.1:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/recommendations")
def recommendations():
    return {"films": build_film_profiles()}


@app.get("/recommendations/compare")
def compare_recommendations(film_a: str, film_b: str):
    if not film_a or not film_b or film_a == film_b:
        raise HTTPException(status_code=400, detail="Choose two different films.")
    return {"lenses": comparison_lens_suggestions(film_a, film_b)}


@app.get("/recommendations/pairings")
def pairing_recommendations(film: str, lens: str):
    if not film or not lens:
        raise HTTPException(status_code=400, detail="Choose a film and lens.")
    return {"pairings": pairing_suggestions(film, lens)}


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: RetrieveRequest):
    return retrieve_query(
        query=request.query,
        film_slugs=request.film_slugs,
        source_types=request.source_types,
        top_k=request.top_k,
        directors=request.directors,
        year_start=request.year_start,
        year_end=request.year_end,
        critics=request.critics,
        themes=request.themes,
    )


@app.post("/answer", response_model=AnalysisResponse)
def answer(request: GuidedAnswerRequest | AnswerRequest):
    try:
        return answer_from_request(request)
    except LLMGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnswerRequest):
    try:
        return answer_from_request(request)
    except LLMGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/workflows/interpretation-map", response_model=InterpretationMapResponse)
def interpretation_map(request: WorkflowRequest):
    film_slugs = request.film_slugs or ([request.primary_film] if request.primary_film else [])
    return interpretation_map_query(
        query=request.query,
        film_slugs=[film for film in film_slugs if film],
        source_types=request.source_types,
        top_k=request.top_k,
    )


@app.post("/workflows/film-comparison", response_model=FilmComparisonResponse)
def film_comparison(request: WorkflowRequest):
    film_slugs = request.film_slugs or request.comparison_films
    return film_comparison_query(
        query=request.query,
        film_slugs=film_slugs,
        source_types=request.source_types,
        top_k=request.top_k,
    )


@app.post("/workflows/theme-explorer", response_model=ThemeExplorerResponse)
def theme_explorer(request: WorkflowRequest):
    return theme_explorer_query(
        query=request.query,
        theme=request.theme or (request.themes[0] if request.themes else ""),
        film_slugs=request.film_slugs,
        source_types=request.source_types,
        top_k=request.top_k,
    )
