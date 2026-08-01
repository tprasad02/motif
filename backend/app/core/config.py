from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://motif:motif@localhost:5432/motif"
    weaviate_url: str = "http://localhost:8080"
    motif_collection: str = "MotifChunk"
    embedding_provider: str = "local"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    frontend_origin: str = "http://localhost:3000"
    next_public_api_url: str = "http://localhost:8000"  # Default value
    tmdb_api_key: str | None = None
    next_public_tmdb_api_key: str | None = None
    use_runtime_databases: bool = True
    class Config:
        env_file = (".env", "backend/.env", "../.env")
        env_file_encoding = "utf-8"


settings = Settings()
