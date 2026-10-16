import logging
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.documents import DocumentPipeline, PipelineError
from app.mcp_research import (
    MCPIntegrationError,
    ResearchProvider,
    TavilyResearchProvider,
)
from app.models import (
    DocumentUploadResponse,
    ErrorResponse,
    HealthResponse,
    QuestionRequest,
    ResearchSearchRequest,
    ResearchSearchResponse,
    RetrievedPassage,
    RetrievalResponse,
    ValidationIssue,
)

logger = logging.getLogger(__name__)


def create_app(
    settings: Optional[Settings] = None,
    pipeline: Optional[DocumentPipeline] = None,
    research_provider: Optional[ResearchProvider] = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
    )
    application.state.document_pipeline = pipeline
    application.state.research_provider = (
        research_provider
        if research_provider is not None
        else TavilyResearchProvider(app_settings)
    )

    def get_pipeline() -> DocumentPipeline:
        if application.state.document_pipeline is None:
            application.state.document_pipeline = DocumentPipeline.from_settings(
                app_settings
            )
        return application.state.document_pipeline

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health_check() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=app_settings.app_name,
            environment=app_settings.environment,
        )

    @application.post(
        "/v1/documents",
        response_model=DocumentUploadResponse,
        status_code=201,
        tags=["documents"],
    )
    async def upload_document(file: UploadFile = File(...)) -> DocumentUploadResponse:
        payload = await file.read(app_settings.max_upload_bytes + 1)
        if len(payload) > app_settings.max_upload_bytes:
            raise PipelineError(
                "upload_too_large",
                "The uploaded file exceeds the maximum size.",
                413,
            )
        if not payload:
            raise PipelineError("empty_upload", "The uploaded file is empty.", 400)

        document_id = str(uuid4())
        page_count, chunk_count = get_pipeline().ingest(
            document_id=document_id,
            payload=payload,
            max_pages=app_settings.max_pdf_pages,
        )
        return DocumentUploadResponse(
            document_id=document_id,
            page_count=page_count,
            chunk_count=chunk_count,
        )

    @application.post(
        "/v1/documents/{document_id}/questions",
        response_model=RetrievalResponse,
        tags=["documents"],
    )
    def retrieve_passages(
        document_id: str, request: QuestionRequest
    ) -> RetrievalResponse:
        passages = get_pipeline().retrieve(
            document_id=document_id,
            question=request.question,
            limit=app_settings.retrieval_limit,
        )
        return RetrievalResponse(
            document_id=document_id,
            passages=[
                RetrievedPassage(
                    text=passage.text,
                    page_number=passage.page_number,
                    distance=passage.distance,
                )
                for passage in passages
            ],
        )

    @application.post(
        "/v1/research/search",
        response_model=ResearchSearchResponse,
        tags=["research"],
    )
    async def search_web(request: ResearchSearchRequest) -> ResearchSearchResponse:
        content = await application.state.research_provider.search(request.query)
        return ResearchSearchResponse(content=content)

    @application.exception_handler(PipelineError)
    async def pipeline_error_handler(
        _request: Request, exc: PipelineError
    ) -> JSONResponse:
        response = ErrorResponse(
            error={
                "code": exc.code,
                "message": str(exc),
            }
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(exclude_none=True),
        )

    @application.exception_handler(MCPIntegrationError)
    async def mcp_error_handler(
        _request: Request, exc: MCPIntegrationError
    ) -> JSONResponse:
        response = ErrorResponse(
            error={
                "code": exc.code,
                "message": str(exc),
            }
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(exclude_none=True),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        response = ErrorResponse(
            error={
                "code": "validation_error",
                "message": "Request validation failed",
                "details": [
                    ValidationIssue(
                        location=list(issue["loc"]),
                        message=issue["msg"],
                    )
                    for issue in exc.errors()
                ],
            }
        )
        return JSONResponse(status_code=422, content=response.model_dump())

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        response = ErrorResponse(
            error={
                "code": "http_error",
                "message": str(exc.detail),
            }
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(exclude_none=True),
            headers=exc.headers,
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled request error")
        response = ErrorResponse(
            error={
                "code": "internal_server_error",
                "message": "An unexpected error occurred",
            }
        )
        return JSONResponse(
            status_code=500,
            content=response.model_dump(exclude_none=True),
        )

    return application


app = create_app()
