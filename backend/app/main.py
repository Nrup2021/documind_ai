import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.models import (
    ErrorResponse,
    HealthResponse,
    ValidationIssue,
)

logger = logging.getLogger(__name__)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
    )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health_check() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=app_settings.app_name,
            environment=app_settings.environment,
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
