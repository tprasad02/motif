from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://motif:motif@localhost:5432/motif"
    weaviate_url: str = "http://localhost:8080"
    motif_collection: str = "MotifChunk"
    embedding_provider: str = "local"
    openai_api_key: str | None = None
    frontend_origin: str = "http://localhost:3000"

    class Config:
        env_file = "../.env"
        env_file_encoding = "utf-8"


settings = Settings()
