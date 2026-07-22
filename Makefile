.PHONY: infra-up infra-down schema backend frontend build-backend-corpus ingest ingest-reset

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

build-backend-corpus:
	python -m ingestion.build_backend_corpus --sources data/manual_sources.csv --output-dir backend/app/corpus

ingest:
	python -m ingestion.cli ingest --sources data/manual_sources.csv

ingest-reset:
	python -m ingestion.cli ingest --sources data/manual_sources.csv --reset
