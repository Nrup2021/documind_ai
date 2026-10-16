# DocuMind backend

This directory contains a FastAPI service with PDF ingestion and passage
retrieval. It validates upload size, extracts page text with PyMuPDF, preserves
one-based page numbers in text chunks, creates embeddings and grounded answers
with local Ollama models, and stores/retrieves vectors in a persistent local
Chroma collection. It also provides `GET /health`, typed API contracts, and
structured API errors.

Authentication and document metadata/lifecycle management are not implemented.
The question route retrieves page-aware evidence and generates a grounded
answer locally. The document and question routes are a local development
foundation, not a production-ready multi-user service.

## Requirements

- Flutter SDK and a supported target (Chrome or an Android emulator) to run
  the client; see the root README for the complete start-to-finish walkthrough.
- Python 3.9 or newer
- `venv` and `pip`
- [Ollama](https://ollama.com/download) running on the computer hosting FastAPI

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

Download the default local models once:

```sh
ollama pull nomic-embed-text
ollama pull qwen2.5:3b
```

Ollama must be running while using PDF upload and question answering. The model
downloads use disk space and inference uses the backend computer's memory and
CPU/GPU, but the app makes no OpenAI or Gemini API calls.

## Run the API

With the virtual environment active and the current directory set to `backend`:

```sh
uvicorn app.main:app --reload
```

The health endpoint is available at `http://127.0.0.1:8000/health`; interactive
API documentation is at `http://127.0.0.1:8000/docs`.
In development, the API allows local browser origins such as Flutter's
`localhost` or `127.0.0.1` web server. For a deployed web client, set
`DOCUMIND_CORS_ALLOWED_ORIGINS` to a comma-separated list of exact origins
(for example, `https://app.example.com`).
An Android emulator reaches the computer hosting FastAPI at `10.0.2.2`.
For a real phone on the same Wi-Fi, stop the default backend process and
restart it listening on the computer's network interfaces:

```sh
uvicorn app.main:app --reload --host 0.0.0.0
```

Then launch Flutter with the computer's current LAN IP:

```sh
flutter run -d <phone-device-id> \
  --dart-define=DOCUMIND_API_BASE_URL=http://192.168.1.10:8000
```

Replace `192.168.1.10` with the computer's LAN IP and use the device ID from
`flutter devices`. The phone and computer must be on the same Wi-Fi, and the
computer's firewall must permit incoming connections to port 8000. Binding to
`0.0.0.0` exposes the development API to the local network; use only on a
trusted network and stop this server when finished.
A phone using cellular data cannot reach a private LAN address; it needs a
reachable VPN or a secured, deployed API endpoint. Do not expose this
unauthenticated development API directly to the public internet.

The default Flutter settings already use `127.0.0.1:8000` for web and
`10.0.2.2:8000` for the Android emulator; no override is needed for those
targets.

## PDF API

The backend uses the local Ollama models for both PDF embeddings and answer
generation; no OpenAI or Gemini keys are needed. The current default upload
limit is 25 MiB and the page limit is 500; both are configurable. Upload is
synchronous: it returns only after extraction, embedding, and indexing
succeed.

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

The question endpoint retrieves passages from that document before asking the
local Ollama chat model. An answered response includes `outcome: "answered"`,
an answer, and
`citations` with one-based source `page_number` values and exact supporting
`excerpt` text drawn from retrieved passages. If no passages are found or the
model reports that they do not support an answer, it returns
`outcome: "insufficient_evidence"` with an explicit abstention and no
citations. Model-provided citations are validated against the retrieved
passages; invented pages or excerpts are rejected as an upstream response
error. Ollama calls use a configurable timeout and return actionable local
server/model errors without exposing provider details.

Chroma is filtered by the requested document ID, but the API has no
authentication or document ownership checks yet. Do not expose it to untrusted
clients.

Remove an indexed document and its Chroma chunks with:

```sh
curl -X DELETE http://127.0.0.1:8000/v1/documents/DOCUMENT_ID
```

A successful deletion returns `204 No Content`. The current service does not
store original PDFs on the backend; the app removes its local library record
after the backend confirms deletion. This route does not provide
authentication or document ownership checks.

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
| `DOCUMIND_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama server URL as seen by FastAPI |
| `DOCUMIND_OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Local model used to embed document chunks and questions |
| `DOCUMIND_OLLAMA_CHAT_MODEL` | `qwen2.5:3b` | Local model used for grounded answer generation |
| `DOCUMIND_OLLAMA_TIMEOUT_SECONDS` | `300` | Local model request timeout (maximum 900 seconds) |
| `DOCUMIND_CHROMA_PERSIST_DIRECTORY` | `./data/chroma` | Local persistent Chroma data directory |
| `DOCUMIND_CHROMA_COLLECTION_NAME` | `document_chunks_nomic_embed_text` | Chroma collection for vectors from the configured embedding model |

For example, set `DOCUMIND_ENVIRONMENT=local` before starting Uvicorn.

## Local-model and index notes

The default Ollama models are configurable and run on the backend computer.
They do not charge per API request, but require model downloads, local disk,
memory, and compute. The backend sends extracted PDF text only to the local
Ollama service. It does not send document data to OpenAI or Gemini.

Chroma embeddings are model-specific. This configuration uses a separate
`document_chunks_nomic_embed_text` collection so it does not mix with earlier
OpenAI vectors. After changing the embedding model, use a new Chroma collection
name and upload the PDFs again; old vectors cannot be reused with a different
embedding model. If the app already contains documents indexed with the old
model, clear its local app data (or reinstall it), then select those PDFs again
to index them with the new model.

## Tests

Install the development dependencies as above, then run from `backend`:

```sh
python -m pytest
```

The tests cover health status, the OpenAPI health response schema, Pydantic
question contracts, structured errors, PDF validation and size limits, empty
extracted text, page-aware chunks, document-scoped passage retrieval followed
by answer generation, Ollama request handling and citation validation using
mock clients. Tests do not make external model API requests.
