from typing import Literal

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
    trail_note: str | None = None


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=3)
    film_slugs: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    year_start: int | None = None
    year_end: int | None = None
    critics: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    top_k: int = Field(default=12, ge=3, le=40)


class RetrievedChunkResponse(BaseModel):
    chunk_id: str
    text: str
    film_slug: str
    source_key: str
    source_type: str
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None
    quality_score: str = "medium"
    source_role: str = "criticism"
    lens_tags: list[str] = Field(default_factory=list)
    section_title: str | None = None
    chunk_role: str = "interpretive_claim"


class RetrieveResponse(BaseModel):
    query: str
    chunks: list[RetrievedChunkResponse]
    coverage_score: float
    coverage_level: str
    retrieval_notes: str


class AnswerRequest(RetrieveRequest):
    mode: Literal["analyze_film", "compare_films", "explore_theme"] | None = None
    film_a: str | None = None
    film_b: str | None = None
    lens: str | None = None
    optional_question: str | None = None
    include_debug: bool = False
    include_low_quality: bool = False


class GuidedAnswerRequest(BaseModel):
    mode: Literal["analyze_film", "compare_films", "explore_theme"]
    film_a: str | None = None
    film_b: str | None = None
    lens: str
    optional_question: str | None = None
    top_k: int = Field(default=12, ge=8, le=12)
    include_debug: bool = False
    include_low_quality: bool = False


class AnalysisResponse(BaseModel):
    mode: str = "analyze_film"
    answer: str = ""
    thesis: str | None = None
    sections: list[dict[str, str]] = Field(default_factory=list)
    evidence_cards: list[dict[str, str]] = Field(default_factory=list)
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
    debug_chunks: list[RetrievedChunkResponse] = Field(default_factory=list)


class WorkflowRequest(AnswerRequest):
    primary_film: str | None = None
    comparison_films: list[str] = Field(default_factory=list)
    theme: str | None = None


class InterpretationMapResponse(BaseModel):
    query: str
    central_reading: str
    interpretive_branches: list[str]
    tensions: list[str]
    related_films: list[str]
    trail: list[SourceCitation]
    coverage_score: float
    coverage_level: str


class FilmComparisonResponse(BaseModel):
    query: str
    films: list[str]
    shared_terrain: str
    key_differences: list[str]
    bridge_films: list[str]
    trail: list[SourceCitation]
    coverage_score: float
    coverage_level: str


class ThemeExplorerResponse(BaseModel):
    query: str
    theme: str
    overview: str
    motif_patterns: list[str]
    films_to_follow: list[str]
    trail: list[SourceCitation]
    coverage_score: float
    coverage_level: str
