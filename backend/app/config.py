from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DocuMind API"
    environment: str = "development"
    debug: bool = False
    cors_allowed_origins: str = ""
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=500, gt=0)
    chunk_size: int = Field(default=1200, gt=0)
    chunk_overlap: int = Field(default=180, ge=0)
    retrieval_limit: int = Field(default=5, gt=0)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_chat_model: str = "qwen2.5:3b"
    ollama_timeout_seconds: float = Field(default=300, gt=0, le=900)
    chroma_persist_directory: str = "./data/chroma"
    # Keep vectors from this embedding model separate from prior model indexes.
    chroma_collection_name: str = "document_chunks_nomic_embed_text"

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self

    model_config = SettingsConfigDict(env_prefix="DOCUMIND_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
