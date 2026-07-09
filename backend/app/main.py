from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models import AnalysisResponse, AnswerRequest, RetrieveRequest, RetrieveResponse
from app.services.analysis import answer_query, retrieve_query

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
    )


@app.post("/answer", response_model=AnalysisResponse)
def answer(request: AnswerRequest):
    return answer_query(
        query=request.query,
        film_slugs=request.film_slugs,
        source_types=request.source_types,
        top_k=request.top_k,
    )


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnswerRequest):
    return answer_query(
        query=request.query,
        film_slugs=request.film_slugs,
        source_types=request.source_types,
        top_k=request.top_k,
    )
