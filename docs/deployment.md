# Motif Deployment

## Current Blockers

- GitHub push from this Codex session was rejected by the approval prompt.
- Vercel production deployment is live.
- No Render API token or deploy hook URL is present in the environment.
- GitHub HTTPS push lacks credentials, and SSH push is not configured.

## Live Frontend

Production:

```text
https://frontend-fawn-beta-13.vercel.app
```

Deployment URL:

```text
https://motif-avc3hqdda-tanisha112.vercel.app
```

## Vercel Frontend

Run from the frontend directory:

```bash
cd frontend
PATH=/Users/tanishaprasad/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/tanishaprasad/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin:$PATH pnpm dlx vercel login
PATH=/Users/tanishaprasad/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/tanishaprasad/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin:$PATH pnpm dlx vercel deploy --prod --yes
```

Set this Vercel environment variable:

```text
NEXT_PUBLIC_API_URL=<Render backend URL>
```

## Render Backend

This repo includes `render.yaml` and `backend/Dockerfile`.

In Render:

1. Create a PostgreSQL database.
2. Create or connect a hosted Weaviate instance.
3. Create a Blueprint from `https://github.com/tprasad02/motif`.
4. Set these backend environment variables:

```text
DATABASE_URL=<Render Postgres internal/external connection string>
WEAVIATE_URL=<Hosted Weaviate URL>
MOTIF_COLLECTION=MotifChunk
EMBEDDING_PROVIDER=local
FRONTEND_ORIGIN=<Vercel frontend URL>
```

After backend deployment, ingest the public corpus against production:

```bash
DATABASE_URL="<Render DATABASE_URL>" \
WEAVIATE_URL="<Hosted WEAVIATE_URL>" \
.venv/bin/python -m ingestion.cli ingest --sources data/public_sources.csv --reset
```

If you create a Render deploy hook, trigger it with:

```bash
curl "$RENDER_DEPLOY_HOOK_URL"
```
