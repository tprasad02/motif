# Motif

Motif is a film close-reading app for psychological movies. It helps a user analyze one film, compare two films, or explore a theme across a curated film collection.

A user chooses a workflow, film, and theme. The backend retrieves relevant criticism, interviews, essays, screenplays, production materials, and other curated documents from the local corpus, then that evidence is used to generate a concise reading.

## What The App Does

Motif currently supports three guided workflows:

1. **Analyze a Film**
   - Select one film.
   - Select a recommended theme.
   - Generate a close reading with a short thesis and four concrete pieces of film evidence.

2. **Compare Films**
   - Select two different films.
   - Select one shared theme.
   - Generate a comparison grounded in both films.

3. **Explore a Theme**
   - Select one theme.
   - Return ranked film cards from the film collection.
   - Each card gives brief context for why that film is relevant.

The current answer format for film analysis is:
- A thesis
- Four evidence cards:
  - Scene
  - Character
  - Pattern
  - Counterreading

Each evidence card should point to something visible or audible in the film: a scene, image, sound cue, camera movement, edit, prop, repeated motif, performance choice, setting, or structural device.

## Film Corpus

The active corpus contains 18 films:

- The Shawshank Redemption
- Fight Club
- One Flew Over the Cuckoo's Nest
- Se7en
- The Silence of the Lambs
- The Prestige
- Memento
- Taxi Driver
- Shutter Island
- Black Swan
- The Sixth Sense
- Prisoners
- Gone Girl
- Requiem for a Dream
- Donnie Darko
- The Machinist
- Mulholland Drive
- The Truman Show

The corpus is manually curated. Source metadata lives in:

```text
data/manual_sources.csv
data/seed_films.csv
```

Manual documents live in:

```text
data/manual/
data/manual_extracted/
```

The backend also has a checked-in JSONL corpus for app/runtime use:

```text
backend/app/corpus/chunks.jsonl
backend/app/corpus/sources.jsonl
```

## Architecture

```text
frontend/        Next.js UI
backend/         FastAPI API and RAG answer generation
ingestion/       Corpus extraction, cleaning, chunking, embedding, and storage
evals/           Corpus and retrieval checks
infra/           PostgreSQL schema
notebooks/       Manual retrieval experiments
data/            Manual corpus metadata and source files
```

Core services:

- **FastAPI** serves `/answer`, `/retrieve`, `/health`, and workflow endpoints.
- **PostgreSQL** stores film/source/document/chunk metadata and supports BM25/full-text retrieval.
- **Weaviate** stores vectors for chunk retrieval.
- **Next.js** provides the guided film-analysis interface.
- **LLM provider** writes the final answer from retrieved context.

The intended flow is:

```text
button selections
→ structured request
→ metadata-filtered retrieval
→ vector + BM25 retrieval
→ merge + dedupe
→ reranking
→ prompt construction
→ LLM answer
→ frontend display
```

## Debug Mode

The public UI hides retrieval internals so Motif feels like a clean close-reading tool, not a search dashboard.

For development and portfolio review, open either:

```text
http://localhost:3000/debug
http://localhost:3000/?debug=1
```

Debug mode shows the retrieved chunks used by the answer pipeline, including:

- source title
- source role
- rerank score
- vector and BM25 scores
- chunk role
- why the chunk was selected
- which evidence card used the chunk, when the model attached chunk IDs

This makes the RAG path inspectable without exposing source mechanics to normal users.

## Current Metrics Snapshot

Latest generated files:

```text
evals/Reports/metrics_summary.json
evals/Reports/metrics_trials.csv
```

| Metric | Current value | Notes |
| --- | ---: | --- |
| Films | 18 | Active curated film collection |
| Documents | 140 | Checked-in source records in `backend/app/corpus/sources.jsonl` |
| Chunks | 2,427 | Checked-in retrieval units in `backend/app/corpus/chunks.jsonl` |
| Eval cases | 50 | 12 analyze, 30 compare, 8 theme |
| Trials per retrieval case | 3 | 150 retrieval trials total |
| Film retrieval accuracy | 1.000 | Average film match rate for analyze and compare retrieval |
| Lens retrieval accuracy | 0.965 | Average theme/lens match rate across retrieval trials |
| Comparison balance | 100.0% | Comparison cases retrieved enough material from both films |
| Retrieval pass rate | 100.0% | Pass rate across all retrieval trials |
| Average response latency | 20.022s | OpenAI-backed generation on 5 benchmark cases x 3 trials |

To run the full benchmark latency suite, remove `--latency-case-limit`:

```bash
python -m evals.build_metrics_summary --trials 3
```

For the practical snapshot used above:

```bash
python -m evals.build_metrics_summary --trials 3 --latency-case-limit 5
```

## Requirements

Install these before setup:

- Python 3.12 or newer
- Docker Desktop
- Node.js 20 or newer
- pnpm
- PostgreSQL client tools, optional but useful for `psql`

The project has been tested locally with the bundled Node runtime in this environment, but a normal Node 20+ install should work.

## Environment Variables

Create a root `.env` file:

```bash
cp .env.example .env
```

Default `.env.example`:

```env
DATABASE_URL=postgresql://motif:motif@localhost:5432/motif
WEAVIATE_URL=http://localhost:8080
EMBEDDING_PROVIDER=local
OPENAI_API_KEY=
MOTIF_COLLECTION=MotifChunk
NEXT_PUBLIC_API_URL=http://localhost:8000
FRONTEND_ORIGIN=http://localhost:3000
```

Important local Docker note: `docker-compose.yml` maps PostgreSQL to host port `5433`.

If you use the included Docker Postgres service, set this in `.env`:

```env
DATABASE_URL=postgresql://motif:motif@localhost:5433/motif
```

Default local database credentials:

```text
database: motif
username: motif
password: motif
host: localhost
port: 5433
```

For LLM-backed answers, set:

```env
OPENAI_API_KEY=your_openai_key
```

If no OpenAI key is available, answer generation returns an error instead of a fake reading. The real app experience requires `OPENAI_API_KEY`.

## First-Time Setup

From the repo root:

```bash
cd motif
```

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install backend and ingestion dependencies:

```bash
pip install -r backend/requirements.txt
pip install -r ingestion/requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
pnpm install
cd ..
```

Start infrastructure:

```bash
docker compose up -d postgres weaviate
```

Confirm the containers are running:

```bash
docker compose ps
```

## Database Setup

The PostgreSQL schema is mounted into the Docker container at startup from:

```text
infra/postgres/001_schema.sql
```

If you need to apply it manually:

```bash
psql "postgresql://motif:motif@localhost:5433/motif" -f infra/postgres/001_schema.sql
```

## Corpus Ingestion

Use this when the manual source files or `data/manual_sources.csv` change.

Make sure the Python environment is active:

```bash
source .venv/bin/activate
```

Run a full reset ingestion:

```bash
DATABASE_URL=postgresql://motif:motif@localhost:5433/motif \
WEAVIATE_URL=http://localhost:8080 \
python -m ingestion.cli ingest --sources data/manual_sources.csv --reset
```

This will:

- Load film metadata.
- Load source metadata.
- Extract text from local files or URLs listed in `data/manual_sources.csv`.
- Clean the text.
- Chunk the documents.
- Generate embeddings.
- Store metadata and chunks in PostgreSQL.
- Store vectors in Weaviate.

To ingest without clearing existing stores:

```bash
python -m ingestion.cli ingest --sources data/manual_sources.csv
```

To rebuild the checked-in backend corpus JSONL files:

```bash
python -m ingestion.build_backend_corpus \
  --sources data/manual_sources.csv \
  --output-dir backend/app/corpus
```

## Running Locally

You need the backend and frontend running at the same time.

Terminal 1: start Docker services.

```bash
cd motif
docker compose up -d postgres weaviate
```

Terminal 2: start the backend (From project root).

```bash
source ../.venv/bin/activate
DATABASE_URL=postgresql://motif:motif@localhost:5433/motif \
WEAVIATE_URL=http://localhost:8080 \
uvicorn app.main:app --reload --port 8000
```

Backend health check:

```text
http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Terminal 3: start the frontend.

```bash
cd motif/frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm run dev
```
Or alternaitively if the port 3000 is occupied

```bash
pnpm run dev -- -p <available_port_number>
```

Open:

```text
http://localhost:3000
```

## Production-Style Local Frontend Build

To test the Next.js build:

```bash
cd motif/frontend
pnpm run build
```

To run the production build locally:

```bash
pnpm run start
```

Open:

```text
http://localhost:3000
```

## Vercel Build Test

From the repo root:

```bash
npx vercel pull --yes --environment preview
npx vercel build
```

This creates local Vercel output at:

```text
.vercel/output
```

## Render Backend Deployment

The backend deployment config is:

```text
render.yaml
```

Render should run the FastAPI backend from the `backend/` directory.

Required Render environment variables:

```env
DATABASE_URL=...
WEAVIATE_URL=...
FRONTEND_ORIGIN=https://your-vercel-app.vercel.app
OPENAI_API_KEY=...
```

The deployed frontend must have:

```env
NEXT_PUBLIC_API_URL=https://your-render-backend-url
```

## API Endpoints

### Health

```http
GET /health
```

Returns:

```json
{"status":"ok"}
```

### Retrieve

```http
POST /retrieve
```

Runs retrieval and returns chunks with coverage information. This is mainly for debugging and evaluation.

### Answer

```http
POST /answer
```

Primary app endpoint. Accepts structured workflow input.

Analyze one film:

```json
{
  "mode": "analyze_film",
  "film_a": "memento",
  "lens": "Memory",
  "top_k": 12
}
```

Compare two films:

```json
{
  "mode": "compare_films",
  "film_a": "memento",
  "film_b": "shutter-island",
  "lens": "Guilt",
  "top_k": 12
}
```

Explore a theme:

```json
{
  "mode": "explore_theme",
  "lens": "Reality vs Illusion",
  "top_k": 12
}
```

## Evaluation And Verification

Verify corpus coverage:

```bash
python -m evals.verify_corpus --sources data/manual_sources.csv --min-per-film 4
```

Test retrieval quality:

```bash
DATABASE_URL=postgresql://motif:motif@localhost:5433/motif \
WEAVIATE_URL=http://localhost:8080 \
python -m evals.test_retrieval_quality
```

Compile backend, ingestion, and eval code:

```bash
python -m compileall backend/app ingestion evals
```

Build frontend:

```bash
cd frontend
pnpm run build
```

## Common Issues

### PostgreSQL password fails in pgAdmin

If using Docker, the credentials are:

```text
host: localhost
port: 5433
database: motif
username: motif
password: motif
```

### Backend cannot connect to PostgreSQL

Check that `.env` uses port `5433` for local Docker:

```env
DATABASE_URL=postgresql://motif:motif@localhost:5433/motif
```

Then restart the backend.

### Frontend says load failed

Check that the backend is running:

```text
http://localhost:8000/health
```

Check that the frontend can see the backend URL:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Restart the frontend after changing frontend environment variables.

### Answers are generic

Likely causes:

- LLM key is missing, so the backend is using fallback output.
- Corpus has not been ingested into PostgreSQL/Weaviate.
- The selected film/theme combination has weak source coverage.
- Retrieval is returning low-value chunks.

Run:

```bash
python -m evals.test_retrieval_quality
```

and inspect retrieved chunks through the debug path before changing prompts.

## Current Limitations

- The corpus is manually curated and depends on the quality of uploaded/source documents.
- Some films have stronger source coverage than others.
- The frontend intentionally hides citations and retrieval details from regular users.
- Debug and evaluation flows should be used by developers to inspect source grounding.
- The app is optimized for guided workflows, not arbitrary open-ended movie questions.

## Development Notes

- Keep the active film list in sync between:
  - `backend/app/film_config.py`
  - `frontend/app/filmConfig.ts`
  - `data/seed_films.csv`
- Keep source metadata in `data/manual_sources.csv`.
- Avoid adding scraped junk or generic plot summaries to the corpus.
- Prefer high-quality interviews, screenplays, production notes, educational essays, academic analysis, and video essay transcripts.
- Smaller high-quality source coverage is better than a larger noisy corpus.
