# DocuMind backend

This directory contains a FastAPI service with PDF ingestion and passage
retrieval. It validates upload size, extracts page text with PyMuPDF, preserves
one-based page numbers in text chunks, embeds with OpenAI, and stores/retrieves
vectors in a persistent local Chroma collection. It also provides `GET
/health` and typed API contracts.

Authentication, document metadata/lifecycle management, answer generation,
Gemini, and MCP integrations are not implemented. The document and question
routes are therefore a local development foundation, not a production-ready
multi-user service.

## Requirements

- Python 3.9 or newer
- `venv` and `pip`

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

Set `DOCUMIND_OPENAI_API_KEY` on the backend process before using the document
routes. The key is never sent by the client. The current default upload limit is
25 MiB and the page limit is 500; both are configurable. Upload is synchronous:
it returns only after extraction, embedding, and indexing succeed.

```sh
curl -F "file=@report.pdf;type=application/pdf" \
  http://127.0.0.1:8000/v1/documents
```

The response contains `document_id`, `page_count`, and `chunk_count`. Retrieve
the nearest passages for a question using that ID:

```sh
curl -H "Content-Type: application/json" \
  -d '{"question":"What are the main findings?"}' \
  http://127.0.0.1:8000/v1/documents/DOCUMENT_ID/questions
```

Each returned passage includes its one-based source `page_number` and Chroma
distance. Chroma is filtered by the requested document ID, but the API has no
authentication or document ownership checks yet. Do not expose it to untrusted
clients.

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
| `DOCUMIND_RETRIEVAL_LIMIT` | `5` | Maximum passages returned per question |
| `DOCUMIND_OPENAI_API_KEY` | unset | Server-side key used for embeddings |
| `DOCUMIND_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `DOCUMIND_CHROMA_PERSIST_DIRECTORY` | `./data/chroma` | Local persistent Chroma data directory |
| `DOCUMIND_CHROMA_COLLECTION_NAME` | `document_chunks` | Chroma collection |

For example, set `DOCUMIND_ENVIRONMENT=local` before starting Uvicorn.

## Model and pricing assumptions

The embedding adapter uses OpenAI's supported `text-embedding-3-small` model.
OpenAI's [published standard API pricing](https://developers.openai.com/api/docs/pricing)
checked on 2026-10-16 lists **$0.02 per million input tokens**. This is an
estimate based on the provider's current list price, not a quote or guarantee;
prices, discounts, taxes, quotas, and account eligibility can change. Each
uploaded page chunk and each question uses embedding input tokens. No
answer-generation model is called by this pipeline. Chroma is self-hosted and
has no per-request vendor API price here, but local compute, disk, backups, and
deployment are not free. Review current provider pricing and billing before
enabling live calls.

## Tests

Install the development dependencies as above, then run from `backend`:

```sh
python -m pytest
```

The tests cover health status, the OpenAPI health response schema, Pydantic
question contracts, structured errors, PDF validation and size limits, empty
extracted text, page-aware chunks, and document-scoped passage retrieval. Tests
use fake embedding/vector adapters and do not make paid API requests.
