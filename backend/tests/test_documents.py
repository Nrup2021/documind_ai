from typing import List, Optional, Sequence

import fitz
from fastapi.testclient import TestClient

from app.config import Settings
from app.documents import (
    ChromaVectorStore,
    DocumentPipeline,
    OllamaEmbeddingProvider,
    PageText,
    PipelineError,
    RetrievedChunk,
    TextChunk,
    chunk_pages,
    extract_pdf_pages,
)
from app.main import create_app
from app.models import AnswerCitation, QuestionResponse
from app.ollama_client import OllamaError


def make_pdf(*page_texts: str) -> bytes:
    document = fitz.open()
    for page_text in page_texts:
        page = document.new_page()
        if page_text:
            page.insert_text((72, 72), page_text)
    payload = document.tobytes()
    document.close()
    return payload


class FakeEmbedder:
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [[float(len(text)), 1.0] for text in texts]


def test_ollama_embedding_provider_uses_injected_local_client() -> None:
    class FakeOllamaClient:
        def embed(self, model, texts):
            assert model == "test-embedding-model"
            assert list(texts) == ["document text"]
            return [[0.25, 0.75]]

    provider = OllamaEmbeddingProvider(
        Settings(ollama_embedding_model="test-embedding-model"),
        client=FakeOllamaClient(),
    )

    assert provider.embed(["document text"]) == [[0.25, 0.75]]


def test_ollama_embedding_provider_preserves_local_service_errors() -> None:
    class FailingOllamaClient:
        def embed(self, _model, _texts):
            raise OllamaError("ollama_unavailable", "Start local Ollama.", 503)

    provider = OllamaEmbeddingProvider(
        Settings(),
        client=FailingOllamaClient(),
    )

    try:
        provider.embed(["document text"])
    except PipelineError as error:
        assert error.code == "ollama_unavailable"
        assert error.status_code == 503
        assert str(error) == "Start local Ollama."
    else:
        raise AssertionError("Expected a local model error to be translated.")


class FakeVectorStore:
    def __init__(self) -> None:
        self.documents = {}

    def add(
        self,
        document_id: str,
        chunks: Sequence[TextChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        self.documents[document_id] = list(chunks)

    def query(
        self,
        document_id: str,
        embedding: Sequence[float],
        limit: int,
    ) -> List[RetrievedChunk]:
        return [
            RetrievedChunk(
                page_number=chunk.page_number,
                text=chunk.text,
                distance=0.1,
            )
            for chunk in self.documents.get(document_id, [])[:limit]
        ]

    def delete(self, document_id: str) -> None:
        self.documents.pop(document_id, None)


class FakeAnswerProvider:
    def answer(self, question, passages):
        if not passages:
            return QuestionResponse(
                outcome="insufficient_evidence",
                answer="The available document passages do not provide enough "
                "evidence to answer this question.",
            )
        return QuestionResponse(
            outcome="answered",
            answer="The relevant passage is on page one.",
            citations=[
                AnswerCitation(
                    page_number=passages[0].page_number,
                    excerpt=passages[0].text,
                )
            ],
        )


def make_test_client(
    settings: Optional[Settings] = None,
) -> tuple[TestClient, FakeVectorStore]:
    vector_store = FakeVectorStore()
    pipeline = DocumentPipeline(
        embedder=FakeEmbedder(),
        vector_store=vector_store,
        chunk_size=1200,
        chunk_overlap=180,
    )
    return TestClient(
        create_app(settings or Settings(), pipeline, answer_provider=FakeAnswerProvider())
    ), vector_store


def test_invalid_pdf_upload_returns_structured_error() -> None:
    client, _ = make_test_client()

    response = client.post(
        "/v1/documents",
        files={"file": ("invalid.pdf", b"not a PDF", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_pdf"


def test_pdf_with_no_extractable_text_is_rejected() -> None:
    client, _ = make_test_client()

    response = client.post(
        "/v1/documents",
        files={"file": ("blank.pdf", make_pdf(""), "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_pdf_text"


def test_upload_enforces_configured_size_limit() -> None:
    client, _ = make_test_client(Settings(max_upload_bytes=32))

    response = client.post(
        "/v1/documents",
        files={"file": ("large.pdf", make_pdf("some text"), "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"


def test_extraction_and_chunking_preserve_one_based_page_metadata() -> None:
    pages = extract_pdf_pages(make_pdf("first page", "second page"), max_pages=10)
    chunks = chunk_pages(pages, chunk_size=7, chunk_overlap=2)

    assert [page.page_number for page in pages] == [1, 2]
    assert {chunk.page_number for chunk in chunks if "first" in chunk.text} == {1}
    assert {chunk.page_number for chunk in chunks if "second" in chunk.text} == {2}


def test_question_retrieves_page_aware_passages_from_requested_document() -> None:
    client, vector_store = make_test_client()
    upload = client.post(
        "/v1/documents",
        files={
            "file": (
                "notes.pdf",
                make_pdf("The relevant passage is on page one.", "Another page."),
                "application/pdf",
            )
        },
    )
    document_id = upload.json()["document_id"]

    response = client.post(
        f"/v1/documents/{document_id}/questions",
        json={"question": "Where is the relevant passage?"},
    )

    assert upload.status_code == 201
    assert upload.json()["page_count"] == 2
    assert upload.json()["chunk_count"] == 2
    assert document_id in vector_store.documents
    assert response.status_code == 200
    assert response.json() == {
        "outcome": "answered",
        "answer": "The relevant passage is on page one.",
        "citations": [
            {"page_number": 1, "excerpt": "The relevant passage is on page one."}
        ],
    }


def test_retrieval_does_not_return_another_documents_chunks() -> None:
    client, _ = make_test_client()

    response = client.post(
        "/v1/documents/not-indexed/questions",
        json={"question": "What does it say?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "outcome": "insufficient_evidence",
        "answer": (
            "The available document passages do not provide enough evidence to "
            "answer this question."
        ),
        "citations": [],
    }


def test_delete_document_removes_its_indexed_chunks() -> None:
    client, vector_store = make_test_client()
    upload = client.post(
        "/v1/documents",
        files={
            "file": (
                "notes.pdf",
                make_pdf("The document contains searchable content."),
                "application/pdf",
            )
        },
    )
    document_id = upload.json()["document_id"]

    response = client.delete(f"/v1/documents/{document_id}")
    question = client.post(
        f"/v1/documents/{document_id}/questions",
        json={"question": "What does it say?"},
    )

    assert response.status_code == 204
    assert document_id not in vector_store.documents
    assert question.json()["outcome"] == "insufficient_evidence"


def test_chroma_returns_nearest_matching_document_chunk(tmp_path) -> None:
    store = ChromaVectorStore(str(tmp_path), "retrieval_test")
    store.add(
        "document-a",
        [
            TextChunk("relevant", 2, "relevant passage"),
            TextChunk("irrelevant", 3, "unrelated material"),
        ],
        [[1.0, 0.0], [0.0, 1.0]],
    )

    passages = store.query("document-a", [1.0, 0.0], limit=1)
    other_document = store.query("document-b", [1.0, 0.0], limit=1)

    assert passages == [RetrievedChunk(2, "relevant passage", 0.0)]
    assert other_document == []

    store.delete("document-a")

    assert store.query("document-a", [1.0, 0.0], limit=1) == []


def test_chunk_pages_rejects_invalid_overlap() -> None:
    try:
        chunk_pages([PageText(page_number=1, text="text")], 10, 10)
    except ValueError as exc:
        assert str(exc) == "Chunk size must be positive and overlap smaller than size."
    else:
        raise AssertionError("Expected invalid chunk configuration to be rejected.")


def test_chunking_does_not_drop_unbroken_text() -> None:
    text = "x" * 2500

    chunks = chunk_pages([PageText(page_number=1, text=text)], 1000, 100)

    assert all(len(chunk.text) <= 1000 for chunk in chunks)
    reconstructed = chunks[0].text + "".join(
        chunk.text[100:] for chunk in chunks[1:]
    )
    assert reconstructed == text
