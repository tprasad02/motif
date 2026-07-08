import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://motif:motif@localhost:5432/motif")
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
MOTIF_COLLECTION = os.getenv("MOTIF_COLLECTION", "MotifChunk")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")

