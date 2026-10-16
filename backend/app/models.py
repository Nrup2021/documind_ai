from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)

    @field_validator("question")
    @classmethod
    def reject_blank_question(cls, question: str) -> str:
        question = question.strip()
        if not question:
            raise ValueError("Question must not be blank")
        return question


class AnswerCitation(BaseModel):
    page_number: int = Field(gt=0)
    excerpt: str = Field(min_length=1)


class QuestionResponse(BaseModel):
    outcome: Literal["answered", "insufficient_evidence"]
    answer: str
    citations: List[AnswerCitation] = Field(default_factory=list)


class DocumentUploadResponse(BaseModel):
    document_id: str
    page_count: int
    chunk_count: int


class RetrievedPassage(BaseModel):
    text: str
    page_number: int
    distance: Optional[float] = None


class RetrievalResponse(BaseModel):
    document_id: str
    passages: List[RetrievedPassage] = Field(default_factory=list)


class ResearchSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def reject_blank_query(cls, query: str) -> str:
        query = query.strip()
        if not query:
            raise ValueError("Query must not be blank")
        return query


class ResearchSearchResponse(BaseModel):
    content: str


class ValidationIssue(BaseModel):
    location: List[Union[str, int]]
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[List[ValidationIssue]] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
