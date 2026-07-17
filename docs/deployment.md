# Motif Deployment

## Frontend: Vercel

The frontend lives in `frontend/`.

Required Vercel settings:

```text
Root Directory: frontend
Install Command: pnpm install
Build Command: pnpm run build
Output: Next.js default
```

Required environment variable:

```text
NEXT_PUBLIC_API_URL=<deployed backend URL>
```

The Vercel project config is `frontend/vercel.json`.

## Backend: Render

The backend deploys from `render.yaml` using `backend/Dockerfile`.

Required Render environment variables:

```text
DATABASE_URL=<Render/Postgres connection string>
WEAVIATE_URL=<Weaviate URL>
MOTIF_COLLECTION=MotifChunk
EMBEDDING_PROVIDER=local
FRONTEND_ORIGIN=<Vercel frontend URL>
OPENAI_API_KEY=<optional OpenAI key>
OPENAI_MODEL=gpt-4o-mini
PUTER_AUTH_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InYyIn0.eyJ0IjoidCIsInYiOiIyIiwidG9rZW5fdWlkIjoiZGZmNzY0ZjUtODM0OC00ZWZlLWI1YzYtNTZjNzhjNGEwMjdmIiwidXUiOiJGa21ReTdTcFJYZWdwUEFsUjMrRndRPT0iLCJzdSI6Ilk2U2NEZVp1VGVtYXk5TXFSMGxSTEE9PSIsImFpIjoiRmttUXk3U3BSWGVncFBBbFIzK0Z3UT09IiwiZnVsbF9hY2Nlc3MiOnRydWUsImlhdCI6MTc4NDMyMDAyMH0.1IMTFu0cq7yUeEZ40ePhJfYZhfK2b3KlsFmnu8x3SQA
PUTER_MODEL=gpt-5.4-nano
```

Use either `OPENAI_API_KEY` or `PUTER_AUTH_TOKEN` for LLM-backed answers. If neither is set, the backend falls back to a deterministic local synthesis for development only.

Health check:

```text
/health
```

## Production Ingestion

After deploying backend infrastructure, ingest the manual corpus into the production Postgres and Weaviate services:

```bash
DATABASE_URL="<production database url>" \
WEAVIATE_URL="<production weaviate url>" \
.venv/bin/python -m ingestion.cli ingest --sources data/manual_sources.csv --reset
```

## Current Local Verification

Local corpus state after ingestion:

```text
films: 18
sources/documents: 142
chunks/vectors: 1,317
```

Local verification commands:

```bash
docker compose up -d postgres weaviate
.venv/bin/python -m ingestion.cli ingest --sources data/manual_sources.csv --reset
.venv/bin/python -m compileall backend/app ingestion evals
cd frontend && pnpm run build
```
