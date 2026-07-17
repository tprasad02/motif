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
```

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
chunks/vectors: 1,574
```

Local verification commands:

```bash
docker compose up -d postgres weaviate
.venv/bin/python -m ingestion.cli ingest --sources data/manual_sources.csv --reset
.venv/bin/python -m compileall backend/app ingestion evals
cd frontend && pnpm run build
```
