from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence
from uuid import uuid4

import fitz

from app.config import Settings
from app.ollama_client import OllamaClient, OllamaError


class PipelineError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    id: str
    page_number: int
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    page_number: int
    text: str
    distance: Optional[float] = None


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        ...


class VectorStore(Protocol):
    def add(
        self,
        document_id: str,
        chunks: Sequence[TextChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        ...

    def query(
        self,
        document_id: str,
        embedding: Sequence[float],
        limit: int,
    ) -> List[RetrievedChunk]:
        ...

    def delete(self, document_id: str) -> None:
        ...


def extract_pdf_pages(payload: bytes, max_pages: int) -> List[PageText]:
    try:
        document = fitz.open(stream=payload, filetype="pdf")
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise PipelineError("invalid_pdf", "The uploaded file is not a valid PDF.", 400) from exc

    with document:
        if document.is_encrypted:
            raise PipelineError(
                "encrypted_pdf", "Password-protected PDFs are not supported.", 422
            )
        if document.page_count == 0:
            raise PipelineError("empty_pdf", "The PDF contains no pages.", 422)
        if document.page_count > max_pages:
            raise PipelineError(
                "page_limit_exceeded",
                "The PDF exceeds the maximum page count.",
                413,
            )

        pages = [
            PageText(page_number=index + 1, text=page.get_text("text").strip())
            for index, page in enumerate(document)
        ]

    if not any(page.text for page in pages):
        raise PipelineError(
            "empty_pdf_text",
            "No extractable text was found in the PDF.",
            422,
        )
    return pages


def chunk_pages(
    pages: Sequence[PageText], chunk_size: int, chunk_overlap: int
) -> List[TextChunk]:
    if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("Chunk size must be positive and overlap smaller than size.")

    chunks: List[TextChunk] = []
    for page in pages:
        text = " ".join(page.text.split())
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + chunk_size // 2, end)
                if boundary > start:
                    end = boundary

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    TextChunk(
                        id=str(uuid4()),
                        page_number=page.page_number,
                        text=chunk_text,
                    )
                )
            if end >= len(text):
                break

            next_start = max(start + 1, end - chunk_overlap)
            boundary = text.find(" ", next_start, end)
            start = boundary + 1 if boundary >= 0 else next_start
    return chunks


class OllamaEmbeddingProvider:
    def __init__(
        self,
        settings: Settings,
        client: Optional[EmbeddingProvider] = None,
    ) -> None:
        self._client = client or OllamaClient(
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
        self._model = settings.ollama_embedding_model

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        try:
            return self._client.embed(self._model, texts)
        except OllamaError as exc:
            raise PipelineError(exc.code, str(exc), exc.status_code) from exc


class ChromaVectorStore:
    def __init__(self, persist_directory: str, collection_name: str) -> None:
        import chromadb

        self._chromadb = chromadb
        self._collection = chromadb.PersistentClient(
            path=persist_directory,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        ).get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        document_id: str,
        chunks: Sequence[TextChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        try:
            self._collection.add(
                ids=[chunk.id for chunk in chunks],
                documents=[chunk.text for chunk in chunks],
                embeddings=[list(embedding) for embedding in embeddings],
                metadatas=[
                    {"document_id": document_id, "page_number": chunk.page_number}
                    for chunk in chunks
                ],
            )
        except self._chromadb.errors.ChromaError as exc:
            raise PipelineError(
                "vector_store_error", "The document could not be indexed.", 502
            ) from exc

    def query(
        self,
        document_id: str,
        embedding: Sequence[float],
        limit: int,
    ) -> List[RetrievedChunk]:
        try:
            result = self._collection.query(
                query_embeddings=[list(embedding)],
                n_results=limit,
                where={"document_id": document_id},
                include=["documents", "metadatas", "distances"],
            )
        except self._chromadb.errors.ChromaError as exc:
            raise PipelineError(
                "vector_store_error", "Passage retrieval failed.", 502
            ) from exc

        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]
        return [
            RetrievedChunk(
                page_number=int(metadata["page_number"]),
                text=text,
                distance=float(distance),
            )
            for text, metadata, distance in zip(documents, metadatas, distances)
        ]

    def delete(self, document_id: str) -> None:
        try:
            self._collection.delete(where={"document_id": document_id})
        except self._chromadb.errors.ChromaError as exc:
            raise PipelineError(
                "vector_store_error", "The document could not be removed.", 502
            ) from exc


class DocumentPipeline:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    @classmethod
    def from_settings(cls, settings: Settings) -> "DocumentPipeline":
        return cls(
            embedder=OllamaEmbeddingProvider(settings),
            vector_store=ChromaVectorStore(
                persist_directory=settings.chroma_persist_directory,
                collection_name=settings.chroma_collection_name,
            ),
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    def ingest(
        self, document_id: str, payload: bytes, max_pages: int
    ) -> tuple[int, int]:
        pages = extract_pdf_pages(payload, max_pages)
        chunks = chunk_pages(pages, self._chunk_size, self._chunk_overlap)

        embeddings: List[List[float]] = []
        batch_size = 64
        for start in range(0, len(chunks), batch_size):
            embeddings.extend(
                self._embedder.embed(
                    [chunk.text for chunk in chunks[start : start + batch_size]]
                )
            )
        if len(embeddings) != len(chunks):
            raise PipelineError(
                "embedding_provider_error",
                "The embedding provider returned an incomplete result.",
                502,
            )

        self._vector_store.add(document_id, chunks, embeddings)
        return len(pages), len(chunks)

    def retrieve(
        self, document_id: str, question: str, limit: int
    ) -> List[RetrievedChunk]:
        embeddings = self._embedder.embed([question])
        if len(embeddings) != 1:
            raise PipelineError(
                "embedding_provider_error",
                "The embedding provider returned an incomplete result.",
                502,
            )
        return self._vector_store.query(document_id, embeddings[0], limit)

    def delete_document(self, document_id: str) -> None:
        self._vector_store.delete(document_id)
