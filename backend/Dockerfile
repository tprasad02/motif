FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend
ENV HF_HOME=/opt/huggingface

WORKDIR /app

COPY requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# The application loads this model with local_files_only=True. Download it
# during the image build so Render can serve embeddings without a runtime fetch.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY . /app/backend

# Render runs without a vector database. Precompute the committed corpus once
# in the image so the first reader request does not have to embed it.
RUN PYTHONPATH=/app/backend python -c "from app.services.retrieval import precompute_file_chunk_vectors; precompute_file_chunk_vectors()"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
