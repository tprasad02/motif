# Motif

Motif is a retrieval-augmented close-reading app for psychologically rich films. It is built to answer a narrower and harder problem than a generic movie chatbot: when someone wants to think seriously about a film, Motif should ground the reading in curated criticism, interviews, screenplays, production notes, essays, and academic analysis instead of producing a smooth but unsupported opinion.

A user chooses a guided path, a film or pair of films, and a theme. The backend retrieves relevant source chunks, filters and reranks them, asks an LLM to produce a structured evidence plan, and displays a thesis with concrete film evidence.

## Project Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md): ingestion-to-answer system flow, retrieval, reranking, and debug mode.
- [DATASET.md](./DATASET.md): corpus strategy, source quality, source roles, chunk roles, and lens assignment.
- [EVALUATION.md](./EVALUATION.md): benchmark cases, metrics, failure modes, and improvements.
- [LIMITATIONS.md](./LIMITATIONS.md): honest scope limits, corpus limits, retrieval limits, and future work.

## Problem

Generic movie chatbots fail at this task in predictable ways:

- They summarize plot instead of reading form, performance, sound, structure, and recurring motifs.
- They blur together unsupported claims, fan theories, reviews, and general film knowledge.
- They rarely show whether the answer came from a screenplay, a director interview, criticism, or a weak source.
- They are too open-ended: a vague prompt can send retrieval toward generic fragments instead of useful evidence.

Motif solves this by narrowing the product contract. It does not try to answer every film question. It supports three workflows that can be evaluated and improved end to end.

## Guided Workflows

1. **Analyze a Film**
   - Select one film.
   - Select a supported theme.
   - Generate a close reading with a short thesis and four concrete pieces of film evidence.

2. **Compare Films**
   - Select two different films.
   - Select one dynamically suggested shared theme.
   - Generate a comparison where every evidence card discusses both films.

3. **Explore a Theme**
   - Select one theme.
   - Return ranked film cards from the film collection.
   - Each card gives short, non-spoiler context for why the theme is relevant.

The interface is button-driven on purpose. The selected workflow determines the backend contract, so the system does not have to guess whether the user wants analysis, comparison, or collection browsing. This makes retrieval testable and reduces the chance that vague text input breaks the pipeline.

The current answer format for film analysis is:
- A thesis
- Four evidence cards:
  - Scene
  - Character
  - Pattern
  - Counterreading

Each evidence card should point to something visible or audible in the film: a scene, image, sound cue, camera movement, edit, prop, repeated motif, performance choice, setting, or structural device.

## What Is Curated vs Dynamic

Motif is transparent about what is designed in advance and what is discovered at runtime.

| Area | Curated / configured | Dynamic |
| --- | --- | --- |
| Film collection | The active 18-film set is curated. | Theme mode ranks films dynamically from retrieved evidence. |
| Source corpus | Sources are manually selected and quality-tagged. | Retrieval selects chunks per workflow request. |
| Primary lens vocabulary | The public lens vocabulary is controlled: Memory, Identity, Control, etc. | Film-specific lens recommendations are scored from chunk tags, raw chunk text, source quality, source role, and chunk role. |
| Secondary angles | Known mappings exist for interpretable concepts such as Marriage or Surveillance. | Additional angles are extracted from corpus text with TF-IDF/ngram concept discovery and filtered back to supported primary lenses. |
| Pairings | No fixed list of “compare this with” buttons. | Suggested pairings are ranked from evidence strength under the same lens. |
| Answer structure | Thesis + four evidence-card jobs are fixed. | The content is generated from retrieved chunks and must attach chunk IDs internally. |

This balance is intentional. The app should feel guided and reliable, but the evidence selection should still be data-driven.

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

For more detail, see [DATASET.md](./DATASET.md).

## Project Structure

```text
motif/
├── README.md                  Project overview, setup, metrics, and portfolio narrative
├── ARCHITECTURE.md            System flow, retrieval, reranking, and debug mode
├── DATASET.md                 Corpus strategy, source roles, quality, and lens assignment
├── EVALUATION.md              Evaluation methodology, metrics, failures, and improvements
├── LIMITATIONS.md             Scope boundaries and known limitations
├── backend/                   FastAPI app and RAG services
│   ├── app/
│   │   ├── main.py            API routes
│   │   ├── models.py          Pydantic request/response models
│   │   ├── film_config.py     Film metadata, primary lenses, lens expansion helpers
│   │   ├── core/              Runtime configuration
│   │   ├── corpus/            Checked-in JSONL corpus used by the app
│   │   ├── db/                PostgreSQL helpers
│   │   └── services/          Retrieval, recommendations, embeddings, and answer generation
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                  Next.js guided UI
│   ├── app/
│   │   ├── page.tsx           Main workflow interface
│   │   ├── debug/             Hidden debug route
│   │   ├── filmConfig.ts      Frontend film metadata fallback
│   │   └── styles.css         UI styling
│   ├── package.json
│   └── vercel.json
├── ingestion/                 Source extraction, cleaning, chunking, embeddings, and storage
├── evals/                     Corpus, chunk, retrieval, answer, and aggregate metrics scripts
│   ├── Reports/               Current evaluation outputs only
│   └── benchmark_cases.json   Main benchmark suite
├── data/                      Manual corpus metadata and extracted/manual source files
│   ├── manual/                Manually supplied PDFs/texts/spreadsheet
│   ├── manual_extracted/      Extracted text used for ingestion
│   ├── manual_sources.csv     Source metadata
│   └── seed_films.csv         Film metadata
├── infra/
│   └── postgres/              PostgreSQL schema
├── notebooks/                 Manual retrieval exploration
├── docker-compose.yml         Local PostgreSQL and Weaviate
├── render.yaml                Render backend deployment config
└── Makefile                   Convenience commands
```

## System Design

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

For a deeper system walkthrough, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Retrieval And Reranking

Motif uses hybrid retrieval:

- **Vector search** finds semantically similar chunks.
- **BM25 search** finds exact keyword/theme matches through PostgreSQL full-text search.
- **Merge + dedupe** combines vector and BM25 candidates.
- **Reranking** re-scores candidates using query overlap, vector score, BM25 score, source quality, source role, chunk role, lens match, and junk/front-matter penalties.
- **Balancing** prevents comparison mode from retrieving only one of the two selected films.

The reranker prefers chunks that look useful for film analysis: scene evidence, formal observations, creator commentary, scholarship, and high-quality source material. It penalizes plot summary, front matter, references, and low-quality sources.

## Side-by-Side Retrieval Comparison

Example path: `Analyze a Film → Memento → Memory`.

| Retrieval mode | What surfaced | What it showed |
| --- | --- | --- |
| Vector-only | Interview transcript, academic article, craft article | Semantically relevant, but some top chunks included intros/front matter or broad discussion. |
| BM25-only | Explicit hits for `memory`, `Leonard`, `tattoo`, `photograph` | Strong for exact evidence words, especially screenplay details, but brittle when the query is too syntactically specific. |
| Hybrid + reranked | Academic formal observation, screenplay tattoo/room scene, production note on reverse Polaroid | Better mix of interpretation, scene evidence, and production/formal context. |

Representative hybrid top results:

| Rank | Source role | Chunk role | Why useful |
| ---: | --- | --- | --- |
| 1 | scholarship | formal observation | Academic argument about Memento's memory structure. |
| 2 | screenplay | scene evidence | Tattoo/phone scene evidence connected to Leonard's memory system. |
| 3 | scholarship | interpretive claim | Critical framing for unreliable memory and narration. |
| 4 | screenplay | scene evidence | Room/handwriting confusion as concrete memory evidence. |
| 5 | production context | formal observation | Reverse Polaroid opening as formal memory device. |

## LLM Generation

The LLM is not asked to “write an essay” from scratch. The backend first retrieves 8-12 chunks, then asks the model for a private structured evidence plan:

```text
thesis
evidence_1: Scene
evidence_2: Character
evidence_3: Pattern
evidence_4: Counterreading
```

The public UI renders the thesis and four cards. Debug mode can show which retrieved chunk IDs the model attached to each card.

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

## One Case Study: Memento + Memory

Initial problem: early versions of Motif sometimes produced generic “memory is unreliable” prose or pasted retrieved fragments into the answer. The output looked like a search summary, not film analysis.

Fixes:

- Changed the answer format from an essay to a thesis plus four fixed evidence cards.
- Added chunk roles such as `scene_evidence`, `formal_observation`, `creator_commentary`, `interpretive_claim`, and `plot_summary`.
- Added source roles such as `creator_voice`, `criticism`, `scholarship`, `screenplay`, and `production_context`.
- Added source quality filtering so weak or noisy sources do not dominate retrieval.
- Added hybrid retrieval and reranking so screenplay evidence, creator commentary, and criticism can work together.
- Added answer-quality evals that check thesis specificity, distinct evidence cards, concrete film details, anti-plot-summary behavior, generic-language avoidance, and groundedness.

Result: the Memento + Memory path now retrieves a stronger mix of scholarship, screenplay evidence, production context, creator commentary, and formal observations. The answer is forced to make one specific claim and support it with four concrete cards rather than drifting into a broad essay.

## Current Metrics Snapshot

Latest generated files:

```text
evals/Reports/metrics_summary.json
evals/Reports/metrics_trials.csv
evals/Reports/metrics_case_summary.csv
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
| Answer checked cases | 50 | Pulled from the latest answer-quality report |
| Answer pass rate | 100.0% | Includes deterministic checks for theme cards |
| LLM-judged answer cases | 41 | Numeric answer-quality scores for generated analyze/compare readings |
| Average answer-quality score | 4.854 / 5 | Average across LLM-judged answer cases |
| Average response latency | 12.486s | OpenAI-backed generation on 5 benchmark cases x 3 trials |

To run the full benchmark latency suite, remove `--latency-case-limit`:

```bash
python -m evals.build_metrics_summary --trials 3
```

For the practical snapshot used above:

```bash
python -m evals.build_metrics_summary --trials 3 --latency-case-limit 5
```

The metrics files intentionally avoid answer text, retrieved text, and long source excerpts. Use `metrics_trials.csv` for per-trial retrieval/latency rows, `metrics_case_summary.csv` for one row per benchmark case, and `metrics_summary.json` for portfolio-level aggregate numbers.

For the full evaluation methodology, see [EVALUATION.md](./EVALUATION.md).

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
TMDB_API_KEY=
USE_RUNTIME_DATABASES=true
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

If no OpenAI key is available, answer generation returns an error instead of a fake reading unless an exact generated reading already exists in the checked-in answer cache. The real app experience requires `OPENAI_API_KEY`; the cache is a demo safety net, not the primary generation path.

Successful generated Analyze/Compare readings are cached by structured request in:

```text
backend/app/corpus/answer_cache.json
```

Before recording or demoing, run the strongest demo paths once with a valid OpenAI key, then commit the updated cache file if you want those exact readings to remain available when the OpenAI key is unavailable. Cached readings are keyed by workflow, selected film(s), lens, and optional angle.

For poster shelves, set a TMDb API key:

```env
TMDB_API_KEY=your_tmdb_key
```

The frontend reads poster data through its internal `/api/posters` route, which keeps the key server-side, caches poster URLs, and falls back to text cards if TMDb is unavailable. Motif displays a small TMDb logo in the featured shelf for attribution. In Vercel, add `TMDB_API_KEY` as a frontend project environment variable.

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
Or alternatively, if port `3000` is occupied:

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
FRONTEND_ORIGIN=https://your-vercel-app.vercel.app
OPENAI_API_KEY=...
USE_RUNTIME_DATABASES=false
```

For the portfolio demo deployment, `USE_RUNTIME_DATABASES=false` is recommended. The backend then uses the checked-in JSONL corpus in `backend/app/corpus/` and does not depend on Render Postgres or Weaviate at runtime. Keep `DATABASE_URL` and `WEAVIATE_URL` for local ingestion/evaluation workflows, but they are not required for the deployed demo when this flag is false.

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
