# DocuMind AI — proposed architecture

## Status boundary

Everything below is a proposed design. The inspected repository currently has
only the Flutter starter screen and test; none of these components or API
contracts have been implemented or verified.

## System shape

```text
Flutter Android app
  presentation (Riverpod + GoRouter)
       │ HTTPS / JSON + multipart PDF
       ▼
FastAPI modular monolith
  auth ─ documents ─ ingestion ─ questions
       │                    │
       │                    ├── PyMuPDF → page-aware chunks
       │                    ├── local embedding adapter
       │                    ├── Chroma persistent vector collection
       │                    └── Gemini answer generation
       ├── SQLite (users, document metadata, status)
       └── private PDF storage

Optional, separate admin/development integration:
FastAPI MCP client ── stdio ── official filesystem MCP server
                                 └── dedicated read-only fixture directory
```

Keep the backend a modular monolith. Define small ports at the model,
embedding, vector-store, and document-storage boundaries so tests can substitute
fakes; do not introduce a generic plugin framework or additional services.

## Proposed Flutter structure

See `implementation-plan.md` for milestone ordering. Feature UI depends on
feature domain contracts; network and persistence implementations sit behind
domain-facing repositories. Widgets do not call HTTP or model APIs directly.

## Proposed ingestion and question flows

1. The app sends a PDF with a bearer token. The API validates the token and
   writes to a generated private temporary path with size limits.
2. The API persists document metadata with `processing` state and returns
   `202 Accepted`. A small in-process FastAPI background task extracts page
   text, rejects unusable documents, chunks by page, embeds, and writes chunks
   with `owner_id`, `document_id`, and one-based `page_number` metadata.
3. The API marks the record `ready`, or records a safe failure code/message.
   A startup recovery check marks abandoned `processing` records as failed;
   in-process background work is intentionally not a durable queue.
4. The question endpoint first loads the document from SQLite constrained by
   the authenticated owner. It queries Chroma only for that authorized
   document's chunk IDs, applies a configurable relevance threshold, and
   passes only bounded excerpts to Gemini.
5. The model is instructed to answer only from supplied evidence and to abstain
   when evidence is inadequate. The backend validates the structured model
   response, intersects cited chunk IDs with the retrieved set, and constructs
   citation page numbers/excerpts from stored chunks—not model-invented
   metadata. If evidence or citations fail validation, return
   `insufficient_evidence` or a provider error, never fabricated citations.

Chroma metadata is useful for filtering but is not an authorization boundary:
ownership is enforced by the SQLite lookup and query construction before
vector retrieval. Retrieved PDF text is always untrusted data. The model gets
no tools; delimit and label excerpts as data, limit context, and test prompt
injection cases.

### Processing reliability boundary

FastAPI `BackgroundTasks` is acceptable only for a single-process MVP. It can
lose work on process exit and does not provide durable retries. Persist status
before scheduling, expose status polling, report failures, and recover stale
records on startup. Replace it with a durable queue only if reliability or
throughput requirements justify the added service and operational cost.

File, SQLite, and Chroma writes are not one atomic transaction. Use a
compensating cleanup path and tests for partial failures; never report `ready`
until all required extraction and indexing steps have succeeded. Document
deletion must be idempotent and remove vector entries and file data as well as
the metadata record.

## Proposed API

Prefix: `/v1`. JSON errors use a stable shape:

```json
{
  "error": {
    "code": "document_not_ready",
    "message": "This document is still being processed.",
    "request_id": "opaque-request-id",
    "details": {}
  }
}
```

Do not return internal stack traces, filesystem locations, prompts, or secrets.
All document endpoints require a bearer access token.

| Method and path | Purpose | Proposed result |
|---|---|---|
| `POST /v1/auth/register` | Create a local MVP account; hash passwords using a maintained password-hashing library. | `201 {user_id, access_token, token_type, expires_in}` |
| `POST /v1/auth/token` | Authenticate and issue a short-lived signed token. | `200 {user_id, access_token, token_type, expires_in}` |
| `POST /v1/documents` | Multipart PDF upload; validates limits and schedules ingestion. | `202 {document}` |
| `GET /v1/documents` | List only the caller's documents; bounded pagination. | `200 {items, next_cursor}` |
| `GET /v1/documents/{document_id}` | Read owned document metadata and processing status. | `200 {document}` |
| `DELETE /v1/documents/{document_id}` | Delete owned document, source, and chunks. | `204`; return the same not-found behavior for missing and non-owned IDs. |
| `POST /v1/documents/{document_id}/questions` | Ask about one owned, ready document. | `200 {answer, citations, outcome}` |
| `GET /health/live` | Process liveness only; no secrets or dependency details. | `200 {status}` |
| `GET /health/ready` | Readiness check for required local storage. | `200` or `503` |

Do not add a public MCP tool-execution endpoint. If an MCP demonstration is
included, keep it behind an explicit development/admin boundary and expose only
fixed, reviewed operations.

### Main response models

- `User`: `id: UUID`, `email: normalized string`, `password_hash`, timestamps.
  Password hash is never serialized.
- `Document`: `id: UUID`, `owner_id: UUID`, `display_name`, `byte_size`,
  `page_count?`, `status: processing | ready | failed`, `failure_code?`,
  `created_at`, `updated_at`. Never serialize a storage path.
- `QuestionRequest`: `question: non-empty bounded string`.
- `Citation`: `page_number: positive integer`, `excerpt: bounded string`,
  `chunk_id: opaque identifier`.
- `QuestionResponse`: `outcome: answered | insufficient_evidence`,
  `answer: string` (empty only for explicit abstention), `citations: Citation[]`.
- `ErrorResponse`: `code`, safe `message`, `request_id`, and optional
  field-level `details`.

SQLite is authoritative for users, document ownership, document status, and
metadata. Chroma stores chunk text plus only the minimum metadata needed for
retrieval (opaque owner/document/chunk IDs and page number). Uploaded bytes
belong in a private filesystem volume, not SQLite.

## Proposed repository layout

```text
.
├── android/                         # Existing Flutter platform scaffold
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   └── implementation-plan.md
├── lib/
│   ├── app/                          # App bootstrap, theme, router, providers
│   ├── core/                         # Shared HTTP, errors, config, primitives
│   └── features/
│       ├── auth/
│       │   ├── data/                 # API DTOs and repository implementation
│       │   ├── domain/               # Entities and repository contract
│       │   └── presentation/         # Screens, widgets, Riverpod providers
│       ├── documents/                # Upload, list, status, delete
│       └── questions/                # Ask, answer, citations
├── test/                             # Flutter unit/widget tests
├── backend/
│   ├── pyproject.toml                # Python package/dependency declaration
│   ├── uv.lock                       # Exact resolved backend dependencies
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py                   # FastAPI composition and lifespan
│   │   ├── api/v1/                   # Routers and HTTP schemas
│   │   ├── core/                     # Settings, auth, errors, logging
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── documents/
│   │   │   └── questions/
│   │   ├── infrastructure/           # SQLite, Chroma, Gemini, MCP adapters
│   │   └── workers/                  # In-process ingestion task
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/
├── .github/workflows/                # CI and release workflows
├── .env.example                      # Names/placeholders only; no secrets
├── .gitignore                        # Ignore env, uploads, DB, vector data
└── docker-compose.yml                # Local API + persistent data volumes
```

Do not create every directory up front. Add only the modules needed by each
milestone, and keep fixtures free of real/private PDFs.

## MCP server recommendation

**Proposed existing server:** the official
[`@modelcontextprotocol/server-filesystem`](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
server, consumed by the backend through the official
[Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk).

- **Tools/capabilities:** filesystem read/write, directory listing and
  creation/deletion, move, search, and metadata operations; access is limited
  to configured directories or MCP Roots.
- **Transport:** launch the Node server as a local `stdio` subprocess from the
  Python MCP client. The Python SDK documents client support for stdio and
  Streamable HTTP; the filesystem server's local process integration is the
  simplest no-hosted-service option. This requires Node/npm, which were present
  in the inspected shell.
- **MVP role:** a small, optional development/admin integration over a
  dedicated fixture directory, not the PDF ingestion path, user upload store,
  question-answer path, or vector database. A compatible client should
  discover tools, validate arguments, and invoke only fixed, explicitly
  allow-listed read/list operations. Do not expose a generic call-tool API to
  the app.
- **Limitations:** it is a filesystem utility, not a PDF processor, document
  authorization system, embedding service, or vector search server. It cannot
  replace PyMuPDF, Chroma, SQLite, or backend ownership checks. It adds a Node
  runtime and another process to supervise.
- **Security:** the server can mutate files and directories. A client-side
  allow-list is not an access-control boundary. Give it a dedicated fixture
  root with OS/container-level read-only permissions; never give it the upload
  directory, repository secrets, home directory, or arbitrary client-supplied
  paths. Treat tool output as untrusted; bound calls and output size; validate
  schemas and timeouts; do not forward secrets. Leave integration disabled by
  default outside local development until its deployment and authentication
  boundary is reviewed.
- **Vector capability verification:** the documented filesystem tools do not
  provide vector search. No MCP vector capability is assumed or required.

This is a recommendation for review, not an installed or connected server. If
the intended MCP server is an existing one you already operate, its name,
transport, tool catalog, authentication, and data-access scope should be
verified before substituting it.
