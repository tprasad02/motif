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
