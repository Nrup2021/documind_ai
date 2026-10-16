import json
import logging
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.config import Settings
from app.documents import RetrievedChunk
from app.models import AnswerCitation, QuestionResponse
from app.ollama_client import OllamaClient, OllamaError

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_ANSWER = (
    "The available document passages do not provide enough evidence to answer "
    "this question."
)

DOCUMENT_ANSWER_SYSTEM_PROMPT = (
    Path(__file__).parent / "prompts" / "document_answer_system.txt"
).read_text(encoding="utf-8").strip()

OLLAMA_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "sufficient_evidence": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "passage_index": {"type": "integer"},
                    "excerpt": {"type": "string"},
                },
                "required": ["passage_index", "excerpt"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["sufficient_evidence", "answer", "citations"],
    "additionalProperties": False,
}


class AnswerGenerationError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AnswerProvider(Protocol):
    def answer(
        self, question: str, passages: Sequence[RetrievedChunk]
    ) -> QuestionResponse:
        ...


class OllamaChatClient(Protocol):
    def chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
    ) -> str:
        ...


class _DraftCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    passage_index: int = Field(ge=0)
    excerpt: str = Field(min_length=1)


class _DraftAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sufficient_evidence: bool
    answer: str = Field(min_length=1)
    citations: list[_DraftCitation]

    @field_validator("answer")
    @classmethod
    def reject_blank_answer(cls, answer: str) -> str:
        answer = answer.strip()
        if not answer:
            raise ValueError("Answer must not be blank")
        return answer


class OllamaAnswerProvider:
    def __init__(
        self,
        settings: Settings,
        client: Optional[OllamaChatClient] = None,
    ) -> None:
        self._model = settings.ollama_chat_model
        self._client = client or OllamaClient(
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        )

    def answer(
        self, question: str, passages: Sequence[RetrievedChunk]
    ) -> QuestionResponse:
        if not passages:
            return self._insufficient_evidence()

        try:
            raw_text = self._client.chat(
                model=self._model,
                system_prompt=DOCUMENT_ANSWER_SYSTEM_PROMPT,
                user_prompt=self._user_prompt(question, passages),
                response_schema=OLLAMA_RESPONSE_SCHEMA,
            )
        except OllamaError as exc:
            raise AnswerGenerationError(exc.code, str(exc), exc.status_code) from exc
        except Exception as exc:
            logger.exception("Ollama answer generation failed")
            raise AnswerGenerationError(
                "ollama_provider_error",
                "The local answer model could not complete the request.",
                502,
            ) from exc

        try:
            if not raw_text.strip():
                raise ValueError("Ollama returned an empty response.")
            draft = _DraftAnswer.model_validate_json(raw_text, strict=True)
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            logger.warning("Ollama returned an invalid structured answer")
            raise AnswerGenerationError(
                "ollama_invalid_response",
                "The local answer model returned an invalid response.",
                502,
            ) from exc

        if not draft.sufficient_evidence:
            return self._insufficient_evidence()
        if not draft.citations:
            raise self._invalid_response()

        citations: list[AnswerCitation] = []
        seen = set()
        for citation in draft.citations:
            # Treat model-generated citations as untrusted; accept only exact
            # excerpts from passages actually retrieved for this question.
            if citation.passage_index >= len(passages):
                raise self._invalid_citation()
            passage = passages[citation.passage_index]
            if citation.excerpt not in passage.text:
                raise self._invalid_citation()
            citation_key = (passage.page_number, citation.excerpt)
            if citation_key not in seen:
                citations.append(
                    AnswerCitation(
                        page_number=passage.page_number,
                        excerpt=citation.excerpt,
                    )
                )
                seen.add(citation_key)

        return QuestionResponse(
            outcome="answered",
            answer=draft.answer,
            citations=citations,
        )

    @staticmethod
    def _user_prompt(question: str, passages: Sequence[RetrievedChunk]) -> str:
        evidence = [
            {"passage_index": index, "text": passage.text}
            for index, passage in enumerate(passages)
        ]
        return (
            f"Question: {json.dumps(question, ensure_ascii=True)}\n"
            f"Evidence: {json.dumps(evidence, ensure_ascii=True)}"
        )

    @staticmethod
    def _insufficient_evidence() -> QuestionResponse:
        return QuestionResponse(
            outcome="insufficient_evidence",
            answer=INSUFFICIENT_EVIDENCE_ANSWER,
            citations=[],
        )

    @staticmethod
    def _invalid_response() -> AnswerGenerationError:
        return AnswerGenerationError(
            "ollama_invalid_response",
            "The local answer model returned an answer without citations.",
            502,
        )

    @staticmethod
    def _invalid_citation() -> AnswerGenerationError:
        return AnswerGenerationError(
            "ollama_invalid_response",
            "The local answer model returned an unsupported citation.",
            502,
        )
