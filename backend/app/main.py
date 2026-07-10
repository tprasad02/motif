from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models import (
    AnalysisResponse,
    AnswerRequest,
    FilmComparisonResponse,
    InterpretationMapResponse,
    RetrieveRequest,
    RetrieveResponse,
    ThemeExplorerResponse,
    WorkflowRequest,
)
from app.services.analysis import (
    answer_query,
    film_comparison_query,
    interpretation_map_query,
    retrieve_query,
    theme_explorer_query,
)

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
def answer(request: AnswerRequest):
    return answer_query(
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


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnswerRequest):
    return answer_query(
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
