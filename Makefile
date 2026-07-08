.PHONY: infra-up infra-down schema backend frontend ingest

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

ingest:
	python -m ingestion.cli ingest --sources data/seed_sources.csv

