from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    source_key: str
    title: str
    author: str | None = None
    publisher: str | None = None
    source_type: str
    url: str | None = None
    chunk_id: str
    film_slug: str | None = None
    score: float | None = None
    excerpt: str | None = None


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=3)
    film_slugs: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    top_k: int = Field(default=12, ge=3, le=40)


class RetrievedChunkResponse(BaseModel):
    chunk_id: str
    text: str
    film_slug: str
    source_key: str
    source_type: str
    score: float


class RetrieveResponse(BaseModel):
    query: str
    chunks: list[RetrievedChunkResponse]
    coverage_score: float
    coverage_level: str
    retrieval_notes: str


class AnswerRequest(RetrieveRequest):
    pass


class AnalysisResponse(BaseModel):
    consensus_interpretation: str
    alternative_interpretations: list[str]
    director_creator_perspective: str
    critical_reception: str
    related_films: list[str]
    cited_sources: list[SourceCitation]
    coverage_score: float
    coverage_level: str
    refused: bool
    retrieval_notes: str
