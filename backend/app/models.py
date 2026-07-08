from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    source_key: str
    title: str
    author: str | None = None
    publisher: str | None = None
    source_type: str
    url: str | None = None
    chunk_id: str


class AnalysisRequest(BaseModel):
    query: str = Field(min_length=3)
    film_slugs: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    max_chunks: int = Field(default=12, ge=3, le=30)


class AnalysisResponse(BaseModel):
    consensus_interpretation: str
    alternative_interpretations: list[str]
    director_creator_perspective: str
    critical_reception: str
    related_films: list[str]
    cited_sources: list[SourceCitation]
    coverage_score: float
    retrieval_notes: str
