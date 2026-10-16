import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.mcp_research import (
    MAX_SEARCH_CONTENT_CHARS,
    MAX_SEARCH_RESULTS,
    MCPIntegrationError,
    TavilyResearchProvider,
)


def make_search_tool(input_schema=None):
    return SimpleNamespace(
        name="tavily_search",
        input_schema=input_schema
        or {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "number"},
            },
            "required": ["query"],
        },
    )


class MockMCPClient:
    def __init__(self, *, tools=None, result=None, list_tools=None) -> None:
        self.tools = tools if tools is not None else [make_search_tool()]
        self.result = result or SimpleNamespace(
            is_error=False,
            content=[SimpleNamespace(type="text", text="Search result")],
        )
        self.list_tools_call = list_tools
        self.call_tool_arguments = None
        self.exited = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        self.exited = True

    async def list_tools(self):
        if self.list_tools_call is not None:
            await self.list_tools_call()
        return SimpleNamespace(tools=self.tools)

    async def call_tool(self, name, arguments):
        self.call_tool_arguments = (name, arguments)
        return self.result


class FakeDocumentPipeline:
    def retrieve(self, *, document_id, question, limit):
        return []


def make_provider(client, *, api_key="test-key", timeout_seconds=1):
    return TavilyResearchProvider(
        Settings(
            tavily_api_key=api_key,
            mcp_timeout_seconds=timeout_seconds,
        ),
        client_factory=lambda _api_key: client,
    )


def test_search_discovers_and_invokes_only_the_allowlisted_tool() -> None:
    client = MockMCPClient(
        tools=[
            SimpleNamespace(name="tavily_extract", input_schema={}),
            make_search_tool(),
        ]
    )
    provider = make_provider(client)

    content = asyncio.run(provider.search("  document AI research  "))

    assert content == "Search result"
    assert client.call_tool_arguments == (
        "tavily_search",
        {
            "query": "  document AI research  ",
            "max_results": MAX_SEARCH_RESULTS,
        },
    )
    assert client.exited


def test_search_rejects_unexpected_tool_schema_before_invocation() -> None:
    client = MockMCPClient(
        tools=[
            make_search_tool(
                {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                }
            )
        ]
    )
    provider = make_provider(client)

    with pytest.raises(MCPIntegrationError) as error:
        asyncio.run(provider.search("query"))

    assert error.value.code == "mcp_tool_unavailable"
    assert client.call_tool_arguments is None
    assert client.exited


def test_search_reports_tool_errors() -> None:
    client = MockMCPClient(
        result=SimpleNamespace(is_error=True, content=[])
    )
    provider = make_provider(client)

    with pytest.raises(MCPIntegrationError) as error:
        asyncio.run(provider.search("query"))

    assert error.value.code == "mcp_tool_error"
    assert client.exited


def test_search_bounds_result_content_size() -> None:
    client = MockMCPClient(
        result=SimpleNamespace(
            is_error=False,
            content=[
                SimpleNamespace(
                    type="text",
                    text="x" * (MAX_SEARCH_CONTENT_CHARS + 1),
                )
            ],
        )
    )

    content = asyncio.run(make_provider(client).search("query"))

    assert len(content) == MAX_SEARCH_CONTENT_CHARS


def test_search_timeout_closes_mcp_client() -> None:
    async def slow_discovery():
        await asyncio.sleep(0.1)

    client = MockMCPClient(list_tools=slow_discovery)
    provider = make_provider(client, timeout_seconds=0.01)

    with pytest.raises(MCPIntegrationError) as error:
        asyncio.run(provider.search("query"))

    assert error.value.code == "mcp_timeout"
    assert client.exited


def test_search_requires_api_key_without_starting_client() -> None:
    def fail_if_started(_api_key):
        raise AssertionError("MCP client must not start without an API key")

    provider = TavilyResearchProvider(
        Settings(tavily_api_key=""),
        client_factory=fail_if_started,
    )

    with pytest.raises(MCPIntegrationError) as error:
        asyncio.run(provider.search("query"))

    assert error.value.code == "mcp_not_configured"


def test_stdio_server_receives_limited_environment_and_isolated_cwd(monkeypatch):
    captured = {}

    class FakeServerParameters:
        def __init__(self, **values):
            self.values = values

    class FakeSDKClient:
        def __init__(self, server):
            captured["server"] = server

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
            pass

    monkeypatch.setitem(
        sys.modules,
        "mcp",
        SimpleNamespace(
            Client=FakeSDKClient,
            StdioServerParameters=FakeServerParameters,
        ),
    )
    client_context = TavilyResearchProvider._create_client("test-key")

    async def inspect_server_parameters():
        async with client_context:
            params = captured["server"].values
            working_directory = Path(params["cwd"])
            assert working_directory.is_dir()
            assert not (working_directory / ".env").exists()
            assert params["env"] == {"TAVILY_API_KEY": "test-key"}
            assert params["command"] == "npx"
            assert params["args"] == ["--yes", "tavily-mcp@0.2.22"]
            return working_directory

    working_directory = asyncio.run(inspect_server_parameters())

    assert not working_directory.exists()


def test_search_endpoint_uses_mcp_and_keeps_rag_routes_independent() -> None:
    mcp_client = MockMCPClient()
    provider = make_provider(mcp_client)
    client = TestClient(
        create_app(
            Settings(),
            pipeline=FakeDocumentPipeline(),
            research_provider=provider,
        )
    )

    response = client.post(
        "/v1/research/search",
        json={"query": "How does retrieval augmented generation work?"},
    )
    rag_response = client.post(
        "/v1/documents/not-indexed/questions",
        json={"question": "What does it say?"},
    )

    assert response.status_code == 200
    assert response.json() == {"content": "Search result"}
    assert mcp_client.call_tool_arguments == (
        "tavily_search",
        {
            "query": "How does retrieval augmented generation work?",
            "max_results": MAX_SEARCH_RESULTS,
        },
    )
    assert rag_response.status_code == 200
    assert rag_response.json() == {
        "document_id": "not-indexed",
        "passages": [],
    }


def test_search_endpoint_validates_query() -> None:
    client = TestClient(create_app(Settings()))

    response = client.post("/v1/research/search", json={"query": "  "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_search_endpoint_rejects_oversized_query() -> None:
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/v1/research/search",
        json={"query": "x" * 501},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_search_endpoint_reports_unconfigured_mcp() -> None:
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/v1/research/search",
        json={"query": "A public web query"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "mcp_not_configured"
