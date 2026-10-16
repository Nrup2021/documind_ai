import logging
import math
from typing import Any, Mapping, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self._post(
            "/api/embed",
            # Reject overlong input instead of silently embedding truncated PDF
            # text, which could make saved citations point to missing evidence.
            {"model": model, "input": list(texts), "truncate": False},
        )
        embeddings = response.get("embeddings")
        if (
            not isinstance(embeddings, list)
            or len(embeddings) != len(texts)
            or any(
                not isinstance(embedding, list)
                or not embedding
                or any(
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    for value in embedding
                )
                for embedding in embeddings
            )
            or len({len(embedding) for embedding in embeddings}) != 1
        ):
            raise OllamaError(
                "ollama_invalid_response",
                "The local embedding model returned invalid embeddings.",
                502,
            )
        return [
            [float(value) for value in embedding]
            for embedding in embeddings
        ]

    def chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
    ) -> str:
        response = self._post(
            "/api/chat",
            {
                "model": model,
                "stream": False,
                "format": response_schema,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        message = response.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaError(
                "ollama_invalid_response",
                "The local answer model returned an empty response.",
                502,
            )
        return content

    def _post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(f"{self._base_url}{path}", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            logger.warning("Ollama request timed out")
            raise OllamaError(
                "ollama_timeout",
                "The local model did not respond before the timeout.",
                504,
            ) from exc
        except httpx.ConnectError as exc:
            logger.warning("Could not connect to the local Ollama server")
            raise OllamaError(
                "ollama_unavailable",
                "The local model server is unavailable. Start Ollama and check its configured address.",
                503,
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.warning("Ollama returned HTTP %s for %s", status_code, path)
            if status_code == 404:
                raise OllamaError(
                    "ollama_model_unavailable",
                    "The configured local model is missing. Download it with the corresponding `ollama pull` command.",
                    503,
                ) from exc
            raise OllamaError(
                "ollama_provider_error",
                "The local model server could not process the request.",
                502,
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("Ollama request failed: %s", type(exc).__name__)
            raise OllamaError(
                "ollama_unavailable",
                "The local model server could not be reached. Check its configured address.",
                503,
            ) from exc
        except ValueError as exc:
            logger.warning("Ollama returned invalid JSON for %s", path)
            raise OllamaError(
                "ollama_invalid_response",
                "The local model server returned an invalid response.",
                502,
            ) from exc

        if not isinstance(body, dict):
            raise OllamaError(
                "ollama_invalid_response",
                "The local model server returned an invalid response.",
                502,
            )
        return body
