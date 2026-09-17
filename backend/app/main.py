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
    LensExplorerResponse,
    WorkflowRequest,
)
from app.services.analysis import (
    LLMGenerationError,
    answer_from_request,
    answer_query,
    film_comparison_query,
    interpretation_map_query,
    retrieve_query,
    lens_explorer_query,
)
from app.services.lens_profiles import all_published_lenses
from app.services.recommendations import build_film_profiles, comparable_film_slugs, comparison_lens_suggestions, pairing_suggestions

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
    # Keep the first interactive request free of Sentence-BERT work. Film
    # profiles are already evidence-validated and can be served immediately.
    return {"films": build_film_profiles()}


@app.get("/recommendations/collection")
def collection_recommendations():
    """Load the collection-wide semantic lens list only for Explore Lenses."""
    return {"collection_lenses": all_published_lenses()}


@app.get("/recommendations/compare")
def compare_recommendations(film_a: str, film_b: str):
    if not film_a or not film_b or film_a == film_b:
        raise HTTPException(status_code=400, detail="Choose two different films.")
    lenses = comparison_lens_suggestions(film_a, film_b)
    if not lenses:
        raise HTTPException(status_code=422, detail="These films do not have an evidence-backed semantic comparison lens.")
    return {"lenses": lenses}


@app.get("/recommendations/comparable-films")
def comparable_films(film: str):
    if not film:
        raise HTTPException(status_code=400, detail="Choose a film first.")
    return {"film": film, "comparable_film_slugs": comparable_film_slugs(film)}


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
        lenses=request.lenses,
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


@app.post("/workflows/lens-explorer", response_model=LensExplorerResponse)
def lens_explorer(request: WorkflowRequest):
    return lens_explorer_query(
        query=request.query,
        lens=request.lens or (request.lenses[0] if request.lenses else ""),
        film_slugs=request.film_slugs,
        source_types=request.source_types,
        top_k=request.top_k,
    )
