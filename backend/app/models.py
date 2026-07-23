from __future__ import annotations
from typing import Any, Literal
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ChunkingStrategy = Literal[
    "fixed_token",
    "sentence",
    "paragraph",
    "heading",
    "semantic",
]

EvaluationStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
]

# helper functions
def utc_now() -> datetime:
    return datetime.now(timezone.utc)

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
    theme_films: list[dict[str, object]] = Field(default_factory=list)
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

# Evaluation Models
# ---------------------------------------------------------------------------
# Input model matching chunks.jsonl
# ---------------------------------------------------------------------------

# ============================================================
# Input model
# ============================================================

class InputChunk(BaseModel):
    """
    One line from chunks.jsonl.

    Expected format:
    {
        "chunk_id": "b934539726424a99c670791bae313308",
        "text": "Chunk text"
    }
    """

    chunk_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    film_slug: str | None = None
    source_key: str | None = None
    source_type: str | None = None
    source_role: str | None = None
    chunk_role: str | None = None
    lens_tags: list[str] = Field(default_factory=list)


# ============================================================
# OpenAI structured-output models
# ============================================================

class GeneratedQuestion(BaseModel):
    question: str = Field(
        description=(
            "A substantive question answerable completely from the target chunk."
        )
    )
    answer: str = Field(
        description=(
            "A concise answer supported completely by the target chunk."
        )
    )


class ChunkLLMEvaluation(BaseModel):
    score: int = Field(
        ge=1,
        le=5,
        description="Overall chunk quality score from 1 to 5.",
    )

    reason: str = Field(
        max_length=200,
        description=(
            "A short reason for the score, using one concise sentence."
        ),
    )

    suggestion: str = Field(
        max_length=200,
        description=(
            "One short, actionable suggestion for improving the chunk."
        ),
    )


# ============================================================
# Evaluation output models
# ============================================================

class DeterministicEvaluation(BaseModel):
    character_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    token_count: int = Field(ge=0)

    starts_with_lowercase: bool
    starts_with_continuation_word: bool
    starts_with_closing_punctuation: bool
    ends_with_terminal_punctuation: bool
    contains_incomplete_trailing_clause: bool

    previous_chunk_similarity: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    next_chunk_similarity: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )

    below_min_tokens: bool
    above_max_tokens: bool
    near_empty: bool
    boilerplate_or_reference_junk: bool = False
    likely_plot_summary: bool = False


class ChunkEvaluationResult(BaseModel):
    chunk_id: str
    chunk_index: int = Field(ge=0)

    text: str
    content_hash: str

    deterministic: DeterministicEvaluation
    llm: ChunkLLMEvaluation | None = None

    error: str | None = None

class EvaluationDocument(BaseModel):
    id: UUID = Field(default_factory=uuid4)

    source_key: str = Field(min_length=1)
    film_slug: str | None = None

    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    source_type: str = Field(min_length=1)

    file_path: str = Field(min_length=1)
    raw_text: str = Field(min_length=1)

    content_hash: str = Field(min_length=1)
    character_count: int = Field(ge=0)
    token_count: int = Field(ge=0)

    created_at: datetime = Field(default_factory=utc_now)


class EvaluationSummary(BaseModel):
    model: str

    chunk_count: int
    successful_count: int
    failed_count: int

    total_characters: int
    total_tokens: int

    average_tokens: float
    median_tokens: float
    token_standard_deviation: float
    minimum_tokens: int
    maximum_tokens: int

    below_min_token_rate: float
    above_max_token_rate: float
    invalid_start_rate: float
    invalid_ending_rate: float

    average_adjacent_similarity: float | None

    average_score: float | None
    bad_chunk_rate: float = 0.0
    strong_chunk_rate: float = 0.0
    boilerplate_or_reference_junk_rate: float = 0.0
    likely_plot_summary_rate: float = 0.0


class EvaluationOutput(BaseModel):
    input_file: str
    evaluated_at: datetime
    minimum_tokens: int | None
    maximum_tokens: int | None

    summary: EvaluationSummary
    chunks: list[ChunkEvaluationResult]
