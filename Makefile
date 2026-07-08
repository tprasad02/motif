.PHONY: infra-up infra-down schema backend frontend build-public-corpus ingest

infra-up:
	docker compose up -d postgres weaviate

infra-down:
	docker compose down

schema:
	psql "$$DATABASE_URL" -f infra/postgres/001_schema.sql

backend:
	cd backend && uvicorn app.main:app --reload

frontend:
	cd frontend && npm run dev

build-public-corpus:
	python -m ingestion.build_public_corpus

ingest:
	python -m ingestion.cli ingest --sources data/public_sources.csv

ingest-reset:
	python -m ingestion.cli ingest --sources data/public_sources.csv --reset
