from fastapi import FastAPI

from app.models import AnalysisRequest, AnalysisResponse
from app.services.analysis import analyze_query

app = FastAPI(title="Motif API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnalysisRequest):
    return analyze_query(
        query=request.query,
        film_slugs=request.film_slugs,
        max_chunks=request.max_chunks,
    )

