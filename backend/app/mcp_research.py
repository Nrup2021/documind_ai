import asyncio
import logging
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager, AsyncGenerator, Optional, Protocol

from app.config import Settings

logger = logging.getLogger(__name__)

TAVILY_MCP_PACKAGE = "tavily-mcp@0.2.22"
TAVILY_SEARCH_TOOL = "tavily_search"
MAX_SEARCH_RESULTS = 5
MAX_SEARCH_CONTENT_CHARS = 20_000


class MCPIntegrationError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class MCPToolDefinition(Protocol):
    name: str
    input_schema: Mapping[str, Any]


class MCPToolList(Protocol):
    tools: Sequence[MCPToolDefinition]


class MCPCallResult(Protocol):
    is_error: bool
    content: Sequence[object]


class MCPClient(Protocol):
    async def list_tools(self) -> MCPToolList:
        ...

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> MCPCallResult:
        ...


class MCPClientFactory(Protocol):
    def __call__(self, api_key: str) -> AsyncContextManager[MCPClient]:
        ...


class ResearchProvider(Protocol):
    async def search(self, query: str) -> str:
        ...


class TavilyResearchProvider:
    def __init__(
        self,
        settings: Settings,
        client_factory: Optional[MCPClientFactory] = None,
    ) -> None:
        self._api_key = settings.tavily_api_key
        self._timeout_seconds = settings.mcp_timeout_seconds
        self._client_factory = client_factory or self._create_client

    async def search(self, query: str) -> str:
        if not self._api_key:
            raise MCPIntegrationError(
                "mcp_not_configured",
                "Web search is not configured on this server.",
                503,
            )

        try:
            return await asyncio.wait_for(
                self._search_with_mcp(query),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning("MCP web search timed out")
            raise MCPIntegrationError(
                "mcp_timeout",
                "Web search did not complete before the timeout.",
                504,
            ) from exc
        except MCPIntegrationError:
            raise
        except Exception as exc:
            logger.exception("MCP web search failed")
            raise MCPIntegrationError(
                "mcp_server_error",
                "The web search service could not complete the request.",
                502,
            ) from exc

    async def _search_with_mcp(self, query: str) -> str:
        async with self._client_factory(self._api_key) as client:
            tool_list = await client.list_tools()
            search_tool = next(
                (tool for tool in tool_list.tools if tool.name == TAVILY_SEARCH_TOOL),
                None,
            )
            if search_tool is None or not self._accepts_query(search_tool.input_schema):
                raise MCPIntegrationError(
                    "mcp_tool_unavailable",
                    "The configured MCP server does not provide the expected search tool.",
                    502,
                )

            result = await client.call_tool(
                TAVILY_SEARCH_TOOL,
                {"query": query, "max_results": MAX_SEARCH_RESULTS},
            )
            if result.is_error:
                raise MCPIntegrationError(
                    "mcp_tool_error",
                    "The web search service reported a tool error.",
                    502,
                )

            text_blocks = [
                text
                for block in result.content
                if getattr(block, "type", None) == "text"
                and isinstance((text := getattr(block, "text", None)), str)
            ]
            content = "\n".join(text_blocks).strip()
            if not content:
                raise MCPIntegrationError(
                    "mcp_empty_result",
                    "The web search service returned no text results.",
                    502,
                )
            return content[:MAX_SEARCH_CONTENT_CHARS]

    @staticmethod
    def _accepts_query(input_schema: Mapping[str, Any]) -> bool:
        properties = input_schema.get("properties")
        required = input_schema.get("required")
        if not isinstance(properties, Mapping):
            return False

        query_schema = properties.get("query")
        max_results_schema = properties.get("max_results")
        return (
            input_schema.get("type") == "object"
            and isinstance(query_schema, Mapping)
            and query_schema.get("type") == "string"
            and isinstance(max_results_schema, Mapping)
            and max_results_schema.get("type") in ("number", "integer")
            and isinstance(required, list)
            and "query" in required
        )

    @staticmethod
    @asynccontextmanager
    async def _create_client(api_key: str) -> AsyncGenerator[MCPClient, None]:
        try:
            from mcp import Client, StdioServerParameters
        except ImportError as exc:
            raise MCPIntegrationError(
                "mcp_sdk_unavailable",
                "The MCP client SDK is not installed on this server.",
                503,
            ) from exc

        with tempfile.TemporaryDirectory(prefix="documind-mcp-") as working_directory:
            server = StdioServerParameters(
                command="npx",
                args=["--yes", TAVILY_MCP_PACKAGE],
                env={"TAVILY_API_KEY": api_key},
                cwd=working_directory,
            )
            async with Client(server) as client:
                yield client
