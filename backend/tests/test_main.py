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


def test_cors_allows_local_web_origins_in_development() -> None:
    client = TestClient(create_app(Settings(environment="development")))

    response = client.options(
        "/v1/documents",
        headers={
            "Origin": "http://127.0.0.1:8765",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://127.0.0.1:8765"
    )
    assert "POST" in response.headers["access-control-allow-methods"]


def test_cors_uses_configured_origins_outside_development() -> None:
    client = TestClient(
        create_app(
            Settings(
                environment="production",
                cors_allowed_origins="https://app.example.com",
            )
        )
    )

    allowed = client.options(
        "/v1/documents",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    disallowed = client.options(
        "/v1/documents",
        headers={
            "Origin": "http://localhost:8765",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert (
        allowed.headers["access-control-allow-origin"]
        == "https://app.example.com"
    )
    assert "access-control-allow-origin" not in disallowed.headers


def test_settings_read_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMIND_APP_NAME", "Configured API")
    monkeypatch.setenv("DOCUMIND_ENVIRONMENT", "staging")
    monkeypatch.setenv("DOCUMIND_DEBUG", "true")
    monkeypatch.setenv("DOCUMIND_OLLAMA_CHAT_MODEL", "test-chat-model")
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.app_name == "Configured API"
    assert settings.environment == "staging"
    assert settings.debug is True
    assert settings.ollama_chat_model == "test-chat-model"


def test_question_contract_validates_request_and_response() -> None:
    request = QuestionRequest(question="What is in this document?")
    response = QuestionResponse(
        outcome="answered",
        answer="A summary.",
        citations=[{"page_number": 2, "excerpt": "Supporting excerpt."}],
    )

    assert request.question == "What is in this document?"
    assert response.model_dump() == {
        "outcome": "answered",
        "answer": "A summary.",
        "citations": [{"page_number": 2, "excerpt": "Supporting excerpt."}],
    }


def test_validation_failure_uses_structured_error_response() -> None:
    application = create_app(Settings())

    @application.post("/test-question", response_model=QuestionResponse)
    def accept_question(request: QuestionRequest) -> QuestionResponse:
        return QuestionResponse(
            outcome="answered",
            answer=request.question,
            citations=[{"page_number": 1, "excerpt": "Evidence"}],
        )

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
