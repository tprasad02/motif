CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE source_type AS ENUM (
  'review',
  'interview',
  'essay',
  'academic',
  'screenplay',
  'production_notes',
  'festival_qa',
  'educational_essay',
  'video_essay_transcript',
  'director_commentary',
  'cast_interview',
  'craft_article',
  'film_history',
  'book_excerpt',
  'other'
);

CREATE TYPE document_status AS ENUM (
  'pending',
  'ingested',
  'failed'
);

CREATE TABLE IF NOT EXISTS films (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  release_year INTEGER,
  director TEXT,
  country TEXT,
  synopsis TEXT,
  themes TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  film_id UUID NOT NULL REFERENCES films(id) ON DELETE CASCADE,
  source_key TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  author TEXT,
  publisher TEXT,
  source_type source_type NOT NULL,
  url TEXT,
  license_note TEXT,
  publication_date DATE,
  credibility_score NUMERIC(3,2) NOT NULL DEFAULT 0.70,
  quality_score TEXT NOT NULL DEFAULT 'medium',
  source_role TEXT NOT NULL DEFAULT 'criticism',
  lens_tags TEXT[] NOT NULL DEFAULT '{}',
  is_primary BOOLEAN NOT NULL DEFAULT false,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  local_path TEXT,
  content_hash TEXT,
  raw_text TEXT,
  cleaned_text TEXT,
  token_count INTEGER,
  status document_status NOT NULL DEFAULT 'pending',
  error_message TEXT,
  ingested_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  film_id UUID NOT NULL REFERENCES films(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  start_char INTEGER,
  end_char INTEGER,
  section_title TEXT,
  chunk_role TEXT NOT NULL DEFAULT 'interpretive_claim',
  embedding_model TEXT,
  lens_tags TEXT[] NOT NULL DEFAULT '{}',
  weaviate_uuid UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS film_relations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  film_id UUID NOT NULL REFERENCES films(id) ON DELETE CASCADE,
  related_film_id UUID NOT NULL REFERENCES films(id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  rationale TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (film_id, related_film_id, relation_type)
);

CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ============================================================
-- Evaluation runs
-- ============================================================

CREATE TABLE chunk_evaluation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    input_file TEXT,

    model TEXT NOT NULL,

    minimum_tokens INTEGER
        CHECK (
            minimum_tokens IS NULL
            OR minimum_tokens >= 0
        ),

    maximum_tokens INTEGER
        CHECK (
            maximum_tokens IS NULL
            OR maximum_tokens >= 1
        ),

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'running',
                'completed',
                'failed'
            )
        ),

    total_chunks INTEGER
        CHECK (
            total_chunks IS NULL
            OR total_chunks >= 0
        ),

    successful_chunks INTEGER
        CHECK (
            successful_chunks IS NULL
            OR successful_chunks >= 0
        ),

    failed_chunks INTEGER
        CHECK (
            failed_chunks IS NULL
            OR failed_chunks >= 0
        ),

    evaluator_version TEXT NOT NULL DEFAULT '1.0',

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_chunk_evaluation_token_range
        CHECK (
            minimum_tokens IS NULL
            OR maximum_tokens IS NULL
            OR minimum_tokens <= maximum_tokens
        ),

    CONSTRAINT ck_chunk_evaluation_run_timestamps
        CHECK (
            started_at IS NULL
            OR completed_at IS NULL
            OR started_at <= completed_at
        )
);

CREATE INDEX ix_chunk_evaluation_runs_status
    ON chunk_evaluation_runs (status);

CREATE INDEX ix_chunk_evaluation_runs_created_at
    ON chunk_evaluation_runs (created_at);

CREATE INDEX ix_chunk_evaluation_runs_model
    ON chunk_evaluation_runs (model);


-- ============================================================
-- Chunks evaluated during a run
-- ============================================================

CREATE TABLE evaluated_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    evaluation_run_id UUID NOT NULL
        REFERENCES chunk_evaluation_runs (id)
        ON DELETE CASCADE,

    external_chunk_id TEXT NOT NULL,

    chunk_index INTEGER NOT NULL
        CHECK (chunk_index >= 0),

    text TEXT NOT NULL
        CHECK (length(text) > 0),

    content_hash TEXT NOT NULL,

    character_count INTEGER NOT NULL
        CHECK (character_count >= 0),

    word_count INTEGER NOT NULL
        CHECK (word_count >= 0),

    token_count INTEGER NOT NULL
        CHECK (token_count >= 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_evaluated_chunk_external_id
        UNIQUE (
            evaluation_run_id,
            external_chunk_id
        ),

    CONSTRAINT uq_evaluated_chunk_index
        UNIQUE (
            evaluation_run_id,
            chunk_index
        )
);

CREATE INDEX ix_evaluated_chunks_run
    ON evaluated_chunks (evaluation_run_id);

CREATE INDEX ix_evaluated_chunks_external_id
    ON evaluated_chunks (external_chunk_id);

CREATE INDEX ix_evaluated_chunks_content_hash
    ON evaluated_chunks (content_hash);


-- ============================================================
-- Per-chunk evaluation results
-- ============================================================

CREATE TABLE chunk_evaluation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    evaluated_chunk_id UUID NOT NULL
        REFERENCES evaluated_chunks (id)
        ON DELETE CASCADE,

    -- --------------------------------------------------------
    -- Deterministic results
    -- --------------------------------------------------------

    starts_with_lowercase BOOLEAN NOT NULL,

    starts_with_continuation_word BOOLEAN NOT NULL,

    starts_with_closing_punctuation BOOLEAN NOT NULL,

    ends_with_terminal_punctuation BOOLEAN NOT NULL,

    contains_incomplete_trailing_clause BOOLEAN NOT NULL,

    previous_chunk_similarity DOUBLE PRECISION
        CHECK (
            previous_chunk_similarity IS NULL
            OR previous_chunk_similarity BETWEEN 0 AND 1
        ),

    next_chunk_similarity DOUBLE PRECISION
        CHECK (
            next_chunk_similarity IS NULL
            OR next_chunk_similarity BETWEEN 0 AND 1
        ),

    below_min_tokens BOOLEAN NOT NULL,

    above_max_tokens BOOLEAN NOT NULL,

    near_empty BOOLEAN NOT NULL,

    -- --------------------------------------------------------
    -- LLM scores
    -- --------------------------------------------------------

    coherence SMALLINT
        CHECK (
            coherence IS NULL
            OR coherence BETWEEN 1 AND 5
        ),

    completeness SMALLINT
        CHECK (
            completeness IS NULL
            OR completeness BETWEEN 1 AND 5
        ),

    boundary_quality SMALLINT
        CHECK (
            boundary_quality IS NULL
            OR boundary_quality BETWEEN 1 AND 5
        ),

    atomicity SMALLINT
        CHECK (
            atomicity IS NULL
            OR atomicity BETWEEN 1 AND 5
        ),

    reference_clarity SMALLINT
        CHECK (
            reference_clarity IS NULL
            OR reference_clarity BETWEEN 1 AND 5
        ),

    requires_previous_chunk BOOLEAN,

    requires_next_chunk BOOLEAN,

    boundary_problem TEXT,

    improvement_suggestion TEXT,

    explanation TEXT,

    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_chunk_evaluation_result
        UNIQUE (evaluated_chunk_id),

    CONSTRAINT ck_complete_llm_score_group
        CHECK (
            (
                coherence IS NULL
                AND completeness IS NULL
                AND boundary_quality IS NULL
                AND atomicity IS NULL
                AND reference_clarity IS NULL
            )
            OR
            (
                coherence IS NOT NULL
                AND completeness IS NOT NULL
                AND boundary_quality IS NOT NULL
                AND atomicity IS NOT NULL
                AND reference_clarity IS NOT NULL
            )
        )
);

CREATE INDEX ix_chunk_evaluation_results_chunk
    ON chunk_evaluation_results (evaluated_chunk_id);

CREATE INDEX ix_chunk_evaluation_results_coherence
    ON chunk_evaluation_results (coherence);

CREATE INDEX ix_chunk_evaluation_results_boundary_quality
    ON chunk_evaluation_results (boundary_quality);


-- ============================================================
-- Questions generated by the evaluator
-- ============================================================

CREATE TABLE chunk_generated_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    chunk_evaluation_result_id UUID NOT NULL
        REFERENCES chunk_evaluation_results (id)
        ON DELETE CASCADE,

    question_index SMALLINT NOT NULL
        CHECK (
            question_index BETWEEN 0 AND 1
        ),

    question TEXT NOT NULL
        CHECK (length(question) > 0),

    answer TEXT NOT NULL
        CHECK (length(answer) > 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_chunk_generated_question_index
        UNIQUE (
            chunk_evaluation_result_id,
            question_index
        )
);

CREATE TABLE IF NOT EXISTS evaluation_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  source_key TEXT NOT NULL,
  film_slug TEXT,

  title TEXT,
  author TEXT,
  publisher TEXT,
  source_type source_type NOT NULL,

  file_path TEXT NOT NULL,
  raw_text TEXT NOT NULL,

  content_hash TEXT NOT NULL,

  character_count INTEGER NOT NULL
    CHECK (character_count >= 0),

  token_count INTEGER NOT NULL
    CHECK (token_count >= 0),

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT fk_evaluation_documents_source
    FOREIGN KEY (source_key)
    REFERENCES sources(source_key)
    ON DELETE CASCADE,

  CONSTRAINT fk_evaluation_documents_film
    FOREIGN KEY (film_slug)
    REFERENCES films(slug)
    ON DELETE SET NULL,

  CONSTRAINT uq_evaluation_documents_source_hash
    UNIQUE (source_key, content_hash),

  CONSTRAINT chk_evaluation_documents_raw_text
    CHECK (length(raw_text) >= 1),

  CONSTRAINT chk_evaluation_documents_file_path
    CHECK (length(file_path) >= 1)
);


CREATE INDEX IF NOT EXISTS idx_sources_film_id ON sources(film_id);
CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_source_id ON documents(source_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_source_hash ON documents(source_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_film_id ON chunks(film_id);
CREATE INDEX IF NOT EXISTS idx_chunks_source_id ON chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_text_fts ON chunks USING GIN (to_tsvector('english', text));
CREATE INDEX IF NOT EXISTS idx_films_director ON films(director);
CREATE INDEX IF NOT EXISTS idx_films_release_year ON films(release_year);
CREATE INDEX IF NOT EXISTS idx_films_themes ON films USING GIN (themes);
CREATE INDEX IF NOT EXISTS idx_sources_author ON sources(author);
CREATE INDEX IF NOT EXISTS idx_sources_quality ON sources(quality_score);
CREATE INDEX IF NOT EXISTS idx_sources_role ON sources(source_role);
CREATE INDEX IF NOT EXISTS idx_sources_lens_tags ON sources USING GIN (lens_tags);
CREATE INDEX IF NOT EXISTS idx_chunks_lens_tags ON chunks USING GIN (lens_tags);
CREATE INDEX IF NOT EXISTS idx_chunks_role ON chunks(chunk_role);

-- ============================================================
-- Evaluation indexes
-- ============================================================

CREATE INDEX ix_chunk_generated_questions_result
    ON chunk_generated_questions (
        chunk_evaluation_result_id
    );