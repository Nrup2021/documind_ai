import httpx
import pytest

from app.ollama_client import OllamaClient, OllamaError


def make_client(handler, *, timeout_seconds=5):
    return OllamaClient(
        "http://localhost:11434/",
        timeout_seconds,
        transport=httpx.MockTransport(handler),
    )


def test_embed_posts_batch_and_returns_numeric_vectors() -> None:
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]},
        )

    vectors = make_client(handler).embed("nomic-embed-text", ["one", "two"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert str(requests[0].url) == "http://localhost:11434/api/embed"
    assert requests[0].read() == (
        b'{"model":"nomic-embed-text","input":["one","two"],"truncate":false}'
    )


def test_embed_rejects_wrong_number_of_vectors() -> None:
    client = make_client(
        lambda _request: httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})
    )

    with pytest.raises(OllamaError) as error:
        client.embed("nomic-embed-text", ["one", "two"])

    assert error.value.code == "ollama_invalid_response"


def test_chat_sends_grounding_prompt_and_json_schema() -> None:
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"message": {"content": '{"answer":"ok"}'}},
        )

    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    response = make_client(handler).chat(
        model="qwen2.5:3b",
        system_prompt="Use only evidence.",
        user_prompt="Question and evidence",
        response_schema=schema,
    )

    assert response == '{"answer":"ok"}'
    assert str(requests[0].url) == "http://localhost:11434/api/chat"
    body = requests[0].read().decode()
    assert '"stream":false' in body
    assert '"format":{"type":"object"' in body
    assert "Use only evidence." in body
    assert "Question and evidence" in body


def test_missing_model_returns_actionable_error() -> None:
    client = make_client(
        lambda _request: httpx.Response(
            404,
            json={"error": "model not found"},
        )
    )

    with pytest.raises(OllamaError) as error:
        client.embed("nomic-embed-text", ["one"])

    assert error.value.code == "ollama_model_unavailable"
    assert error.value.status_code == 503
    assert "ollama pull" in str(error.value)


def test_local_server_connection_failure_is_actionable() -> None:
    def handler(_request):
        raise httpx.ConnectError("private connection detail")

    client = make_client(handler)

    with pytest.raises(OllamaError) as error:
        client.embed("nomic-embed-text", ["one"])

    assert error.value.code == "ollama_unavailable"
    assert error.value.status_code == 503
    assert "private connection detail" not in str(error.value)
