from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DocuMind API"
    environment: str = "development"
    debug: bool = False
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=500, gt=0)
    chunk_size: int = Field(default=1200, gt=0)
    chunk_overlap: int = Field(default=180, ge=0)
    retrieval_limit: int = Field(default=5, gt=0)
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chroma_persist_directory: str = "./data/chroma"
    chroma_collection_name: str = "document_chunks"
    tavily_api_key: str = ""
    mcp_timeout_seconds: float = Field(default=20, gt=0, le=120)

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self

    model_config = SettingsConfigDict(env_prefix="DOCUMIND_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
