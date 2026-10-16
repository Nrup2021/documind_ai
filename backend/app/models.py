from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10_000)


class QuestionResponse(BaseModel):
    answer: str
    sources: List[str] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    location: List[Union[str, int]]
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[List[ValidationIssue]] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
