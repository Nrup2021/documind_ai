# DocuMind backend

This directory contains a FastAPI service with PDF ingestion and passage
retrieval. It validates upload size, extracts page text with PyMuPDF, preserves
one-based page numbers in text chunks, embeds with OpenAI, and stores/retrieves
vectors in a persistent local Chroma collection. It also provides `GET
/health`, typed API contracts, and optional web research through Tavily's MCP
server.

Authentication and document metadata/lifecycle management are not implemented.
The question route retrieves page-aware evidence and generates a grounded
answer with Gemini. The document and question routes are a local development
foundation, not a production-ready multi-user service. Web research is a
separate optional route; PDF ingestion and RAG do not depend on MCP.

## Requirements

- Python 3.10 or newer (required by the official MCP Python client SDK)
- `venv` and `pip`
- Node.js 20 or newer and npm/npx (required to run Tavily's stdio MCP server)

## Set up a virtual environment

From the repository root:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

On Windows, activate the environment with
`.venv\Scripts\activate` instead of the `source` command.

## Run the API

With the virtual environment active and the current directory set to `backend`:

```sh
uvicorn app.main:app --reload
```

The health endpoint is available at `http://127.0.0.1:8000/health`; interactive
API documentation is at `http://127.0.0.1:8000/docs`.

## PDF API

Set `DOCUMIND_OPENAI_API_KEY` on the backend process before uploading documents,
and `DOCUMIND_GEMINI_API_KEY` before asking questions about documents with
retrieved passages. Both keys are used only by the backend and are never sent by
the Flutter client. The current default upload limit is 25 MiB and the page
limit is 500; both are configurable. Upload is synchronous: it returns only
after extraction, embedding, and indexing succeed.

```sh
curl -F "file=@report.pdf;type=application/pdf" \
  http://127.0.0.1:8000/v1/documents
```

The response contains `document_id`, `page_count`, and `chunk_count`. Ask a
question using that ID:

```sh
curl -H "Content-Type: application/json" \
  -d '{"question":"What are the main findings?"}' \
  http://127.0.0.1:8000/v1/documents/DOCUMENT_ID/questions
```

The question endpoint retrieves passages from that document before calling
Gemini. An answered response includes `outcome: "answered"`, an answer, and
`citations` with one-based source `page_number` values and exact supporting
`excerpt` text drawn from retrieved passages. If no passages are found or the
model reports that they do not support an answer, it returns
`outcome: "insufficient_evidence"` with an explicit abstention and no
citations. Model-provided citations are validated against the retrieved
passages; invented pages or excerpts are rejected as an upstream response
error. Gemini calls use a configurable timeout and report provider failures
without returning provider details.

Chroma is filtered by the requested document ID, but the API has no
authentication or document ownership checks yet. Do not expose it to untrusted
clients.

## Optional MCP web research

Set `DOCUMIND_TAVILY_API_KEY` on the backend process to enable the separate
`POST /v1/research/search` endpoint:

```sh
curl -H "Content-Type: application/json" \
  -d '{"query":"Recent approaches to document question answering"}' \
  http://127.0.0.1:8000/v1/research/search
```

The backend launches Tavily's maintained `tavily-mcp@0.2.22` package over
stdio using the official MCP Python client (`mcp==2.3.0`). Each request
discovers the server's tools, validates the `tavily_search` input schema, and
invokes only that search tool with the validated query. Although the server
also advertises extraction, crawling, mapping, and research tools, the backend
does not call or expose them. The backend caps each search at five results and
bounds query length, response size, and request time. The API key is passed
only to the child process via the SDK's restricted environment; the subprocess
also runs from an isolated temporary working directory so it cannot load a
backend `.env` file. The key is not placed in a URL or returned to clients.

Web search is disabled when the API key is unset and reports a structured
`503` error. MCP startup, tool, and timeout failures are reported separately
from the document pipeline. Search queries and results are sent to/received
from Tavily and should be treated as external, untrusted data. The subprocess
runs as the backend OS user, so deploy the backend with an appropriately
restricted user/container and review the pinned npm package before upgrading.
The direct package is pinned, but its npm dependencies use version ranges and
are resolved by `npx`; for reproducible production deployments, bake a reviewed
dependency tree into the deployment image. Do not include private document
contents in a search query. The MCP endpoint does not read from or write to the
RAG store.

## Configuration

Configuration is read from environment variables using the `DOCUMIND_` prefix:

| Variable | Default | Description |
| --- | --- | --- |
| `DOCUMIND_APP_NAME` | `DocuMind API` | FastAPI title and health response service name |
| `DOCUMIND_ENVIRONMENT` | `development` | Environment name returned by the health endpoint |
| `DOCUMIND_DEBUG` | `false` | FastAPI debug mode |
| `DOCUMIND_MAX_UPLOAD_BYTES` | `26214400` | Maximum PDF upload size in bytes |
| `DOCUMIND_MAX_PDF_PAGES` | `500` | Maximum number of PDF pages |
| `DOCUMIND_CHUNK_SIZE` | `1200` | Approximate maximum chunk length in characters |
| `DOCUMIND_CHUNK_OVERLAP` | `180` | Approximate overlap in characters between same-page chunks |
| `DOCUMIND_RETRIEVAL_LIMIT` | `5` | Maximum passages supplied as evidence per question |
| `DOCUMIND_OPENAI_API_KEY` | unset | Server-side key used for embeddings |
| `DOCUMIND_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `DOCUMIND_GEMINI_API_KEY` | unset | Server-side key used for grounded answer generation |
| `DOCUMIND_GEMINI_MODEL` | `gemini-2.5-flash` | Gemini answer-generation model |
| `DOCUMIND_GEMINI_TIMEOUT_SECONDS` | `30` | Gemini request timeout (maximum 120 seconds) |
| `DOCUMIND_CHROMA_PERSIST_DIRECTORY` | `./data/chroma` | Local persistent Chroma data directory |
| `DOCUMIND_CHROMA_COLLECTION_NAME` | `document_chunks` | Chroma collection |
| `DOCUMIND_TAVILY_API_KEY` | unset | Enables Tavily MCP web research; stored only on the backend |
| `DOCUMIND_MCP_TIMEOUT_SECONDS` | `20` | Total time limit for MCP startup, discovery, and invocation (maximum 120) |

For example, set `DOCUMIND_ENVIRONMENT=local` before starting Uvicorn.

## Model and pricing assumptions

The embedding adapter uses OpenAI's supported `text-embedding-3-small` model.
OpenAI's [published standard API pricing](https://developers.openai.com/api/docs/pricing)
checked on 2026-10-16 lists **$0.02 per million input tokens**. This is an
estimate based on the provider's current list price, not a quote or guarantee;
prices, discounts, taxes, quotas, and account eligibility can change. Each
uploaded page chunk and each question uses embedding input tokens. No
answer-generation price is specified here; Gemini receives retrieved passages
and questions when answering. Chroma is self-hosted and has no per-request
vendor API price here, but local compute, disk, backups, and deployment are not
free. Review current provider pricing, data handling, and billing before
enabling live calls.

## Tests

Install the development dependencies as above, then run from `backend`:

```sh
python -m pytest
```

The tests cover health status, the OpenAPI health response schema, Pydantic
question contracts, structured errors, PDF validation and size limits, empty
extracted text, page-aware chunks, document-scoped passage retrieval followed
by answer generation, Gemini response/citation validation and errors using a
mock model client, and MCP tool discovery/invocation using a mock MCP client.
Tests do not make paid API requests.
