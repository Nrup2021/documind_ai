from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.models import QuestionRequest, QuestionResponse


def test_health_endpoint_returns_service_status() -> None:
    client = TestClient(
        create_app(
            Settings(
                app_name="Test DocuMind API",
                environment="test",
            )
        )
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Test DocuMind API",
        "environment": "test",
    }


def test_health_endpoint_is_documented_with_response_schema() -> None:
    client = TestClient(create_app(Settings()))

    schema = client.get("/openapi.json").json()

    assert schema["paths"]["/health"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]["$ref"].endswith("/HealthResponse")


def test_settings_read_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMIND_APP_NAME", "Configured API")
    monkeypatch.setenv("DOCUMIND_ENVIRONMENT", "staging")
    monkeypatch.setenv("DOCUMIND_DEBUG", "true")
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.app_name == "Configured API"
    assert settings.environment == "staging"
    assert settings.debug is True


def test_question_contract_validates_request_and_response() -> None:
    request = QuestionRequest(question="What is in this document?")
    response = QuestionResponse(answer="A summary.", sources=["doc-1"])

    assert request.question == "What is in this document?"
    assert response.model_dump() == {
        "answer": "A summary.",
        "sources": ["doc-1"],
    }


def test_validation_failure_uses_structured_error_response() -> None:
    application = create_app(Settings())

    @application.post("/test-question", response_model=QuestionResponse)
    def accept_question(request: QuestionRequest) -> QuestionResponse:
        return QuestionResponse(answer=request.question)

    response = TestClient(application).post(
        "/test-question",
        json={"question": ""},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed",
            "details": [
                {
                    "location": ["body", "question"],
                    "message": "String should have at least 1 character",
                }
            ],
        }
    }


def test_unknown_route_uses_structured_error_response() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "http_error",
            "message": "Not Found",
        }
    }


def test_unexpected_error_uses_generic_structured_error_response() -> None:
    application = create_app(Settings())

    @application.get("/test-error")
    def raise_error() -> None:
        raise RuntimeError("sensitive internal detail")

    client = TestClient(application, raise_server_exceptions=False)
    response = client.get("/test-error")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "An unexpected error occurred",
        }
    }
