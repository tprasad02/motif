# Motif

Motif is a retrieval-augmented close-reading app for psychologically rich films. It is built to answer a narrower and harder problem than a generic movie chatbot: when someone wants to think seriously about a film, Motif should ground the reading in curated criticism, interviews, screenplays, production notes, essays, and academic analysis instead of producing a smooth but unsupported opinion.

## Project Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md): system flow, retrieval, reranking, and debug mode.
- [DATASET.md](./DATASET.md): corpus strategy, source roles, quality, and lens assignment.
- [EVALUATION.md](./EVALUATION.md): benchmark cases, metrics, failures, and improvements.
- [evals/RAG_METRICS.md](./evals/RAG_METRICS.md): relevance-judgment rubric and ranking metrics.
- [LIMITATIONS.md](./LIMITATIONS.md): scope boundaries and future work.

## Problem

Generic movie chatbots fail at this task in predictable ways:

- They summarize plot instead of reading form, performance, sound, structure, and recurring motifs.
- They blur together unsupported claims, fan theories, reviews, and general film knowledge.
- They rarely show whether the answer came from a screenplay, a director interview, criticism, or a weak source.
- They are too open-ended: a vague prompt can send retrieval toward generic fragments instead of useful evidence.

Motif solves this by narrowing the product contract. It does not try to answer every film question. It supports three workflows that can be evaluated and improved end to end.

## Demo

[Motif demo video](./docs/assets/motif-demo.mp4)

Comparison workflow screenshots:

<img src="./docs/assets/motif-title-page.png" alt="Motif homepage" width="760">

<img src="./docs/assets/motif-film-selection.png" alt="Motif film selection" width="760">

<img src="./docs/assets/motif-select-lens.png" alt="Motif lens selection" width="760">

<img src="./docs/assets/motif-comparison-thesis.png" alt="Motif comparison thesis" width="760">

<img src="./docs/assets/motif-evidence-cards.png" alt="Motif evidence cards" width="760">

## What It Does

Motif supports three workflows:

1. **Analyze a Film**
   Select one film and one supported theme. Motif returns a short thesis and four evidence cards: Scene, Character, Pattern, and Counterreading.

2. **Compare Films**
   Select two films and one shared theme. Motif returns a comparison where each evidence card discusses both films.

3. **Explore a Theme**
   Select one theme. Motif returns ranked film cards from the collection with short non-spoiler context.

The button-driven flow keeps each request structured:

```text
workflow selection
→ film/theme selection
→ metadata-filtered retrieval
→ vector + BM25 search
→ merge + rerank
→ LLM evidence plan
→ thesis and evidence cards
```

## Corpus

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

Source metadata lives in:

```text
data/manual_sources.csv
data/seed_films.csv
```

Runtime corpus files live in:

```text
backend/app/corpus/chunks.jsonl
backend/app/corpus/sources.jsonl
```

## Retrieval

Motif uses hybrid retrieval:

- **Vector search** finds semantically related chunks.
- **BM25** finds exact keyword and theme matches using PostgreSQL full-text search.
- **Reranking** combines retrieval scores with source quality, source role, chunk role, theme match, and penalties for low-value text.
- **Comparison balancing** requires both selected films to appear in the retrieved evidence.

The reranker favors scene evidence, formal observations, creator commentary, criticism, scholarship, and production context. It downranks plot summary, references, front matter, and noisy chunks.

## Answer Format

Analyze and compare workflows return:

- **Thesis**: one short, film-bound claim.
- **Scene**: one sequence that directly supports the thesis.
- **Character**: behavior, performance, relationship, or psychological trajectory.
- **Pattern**: recurring image, sound, line, motif, edit, structure, or formal device.
- **Counterreading**: evidence that complicates the thesis.

The app hides citations in the public UI. Debug mode shows retrieval details for development and review.

## Debug Mode

Open:

```text
http://localhost:3000/debug
http://localhost:3000/?debug=1
```

Debug mode shows retrieved chunks, source title, source role, rerank score, vector/BM25 scores, chunk role, selection reason, and which evidence card used each chunk when available.

## Metrics Snapshot

One reproducible evaluation suite writes:

```text
evals/Reports/corpus_coverage.csv
evals/Reports/retrieval_quality_results.json
evals/Reports/rag_ranking_metrics.json
evals/Reports/answer_quality_results.json
evals/final_metrics/metrics_summary.json
evals/final_metrics/metrics_trials.csv
evals/final_metrics/metrics_case_summary.csv
evals/final_metrics/evaluation_manifest.json
```

| Metric | Historical snapshot |
| --- | ---: |
| Films | 18 |
| Documents | 140 |
| Chunks | 2,427 |
| Eval cases | 50 (pre-expansion) |
| Trials per retrieval case | 3 |
| Retrieval guardrails | 100.0% (pre-expansion) |
| Judgment-backed ranking metrics | Not yet assessed |
| Answer checked cases | 50 |
| Answer validity / quality | Legacy — regenerate |
| LLM-judged answer cases | 41 |
| Faithfulness / answer relevance | Legacy — regenerate |
| Average response latency | 12.486s |

Those checked-in values predate the complete judgment-backed suite and are not
current claims. The aggregate report now contains both operational guardrails
and standard ranked-retrieval metrics, without collapsing them into one score.
The current benchmark contains 100 cases; do not call a guardrail pass rate
“accuracy.”

Run the complete evaluation suite:

```bash
python -m evals.run_evaluation --trials 3 --latency-case-limit 5
```

First create and assess the relevance pool if `evals/relevance_judgments.csv`
has not been completed:

```bash
python -m evals.rag_metrics --write-annotation-pool evals/Reports/relevance_pool.csv --pool-k 30
```

See [EVALUATION.md](./EVALUATION.md) for each layer, what it measures, and how
to interpret the combined report.

## Project Structure

```text
motif/
├── README.md
├── ARCHITECTURE.md
├── DATASET.md
├── EVALUATION.md
├── LIMITATIONS.md
├── backend/                 FastAPI app and retrieval/answer services
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── film_config.py
│   │   ├── core/
│   │   ├── corpus/
│   │   ├── db/
│   │   └── services/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                Next.js guided UI
│   ├── app/
│   ├── package.json
│   └── vercel.json
├── ingestion/               Extraction, cleaning, chunking, and corpus build scripts
├── evals/                   Unified corpus, retrieval, ranking, answer, and aggregate evaluation suite
├── data/                    Manual source metadata and extracted files
├── infra/postgres/          PostgreSQL schema
├── notebooks/               Manual retrieval checks
├── docs/assets/             README demo video and screenshots
├── docker-compose.yml
├── render.yaml
└── Makefile
```

## Requirements

- Python 3.12 or newer
- Docker Desktop
- Node.js 20 or newer
- pnpm
- PostgreSQL client tools, optional

## Environment Variables

Create a root `.env` file:

```bash
cp .env.example .env
```

Default values:

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

For local Docker Postgres, use port `5433`:

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

Set `OPENAI_API_KEY` for generated readings. If no key is available, the backend returns a clear configuration error unless an exact cached reading already exists.

Generated Analyze/Compare readings are cached in:

```text
backend/app/corpus/answer_cache.json
```

Set `TMDB_API_KEY` for poster shelves. The frontend uses an internal `/api/posters` route so the key stays server-side. Motif includes TMDb attribution in the UI.

## First-Time Setup

Create and activate a Python environment:

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

Start local infrastructure:

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

Rebuild the checked-in runtime corpus:

```bash
python -m ingestion.build_backend_corpus \
  --sources data/manual_sources.csv \
  --output-dir backend/app/corpus
```

## Running Locally

Start Docker services:

```bash
docker compose up -d postgres weaviate
```

Start the backend from the repo root:

```bash
source .venv/bin/activate
PYTHONPATH=backend \
DATABASE_URL=postgresql://motif:motif@localhost:5433/motif \
WEAVIATE_URL=http://localhost:8080 \
uvicorn app.main:app --reload --port 8000
```

Health check:

```text
http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Start the frontend:

```bash
cd frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm run dev
```

Open:

```text
http://localhost:3000
```

## Build Checks

Backend/eval compile check:

```bash
python -m compileall backend/app ingestion evals
```

Frontend build:

```bash
cd frontend
pnpm run build
```

Vercel preview build:

```bash
npx vercel pull --yes --environment preview
npx vercel build
```

## Deployment

### Render Backend

`render.yaml` configures the FastAPI backend.

Required Render variables:

```env
FRONTEND_ORIGIN=https://your-vercel-app.vercel.app
OPENAI_API_KEY=...
USE_RUNTIME_DATABASES=false
```

For the deployed demo, `USE_RUNTIME_DATABASES=false` lets the backend use the checked-in JSONL corpus instead of runtime Postgres/Weaviate.

### Vercel Frontend

Required Vercel variables:

```env
NEXT_PUBLIC_API_URL=https://your-render-backend-url
TMDB_API_KEY=...
```

## API

### Health

```http
GET /health
```

### Retrieve

```http
POST /retrieve
```

Returns retrieved chunks and coverage information for debugging/evaluation.

### Answer

```http
POST /answer
```

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

## Evaluation

Run all corpus, retrieval, ranking, answer, and aggregate checks together:

```bash
python -m evals.run_evaluation --trials 3 --latency-case-limit 5
```

The run publishes an artifact manifest and one aggregate summary. Full
methodology, metric definitions, and annotation requirements are in
[EVALUATION.md](./EVALUATION.md).

## Limitations

- Motif is strongest on supported film/theme combinations in the curated corpus.
- Source quality affects answer depth.
- The public UI hides citations; debug mode exposes retrieval details.
- It is not designed for arbitrary open-ended film questions.
