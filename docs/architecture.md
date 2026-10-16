# DocuMind AI — proposed architecture

## Status boundary

The Flutter foundation is in place with Riverpod, GoRouter, and
document-library/chat presentation routes. The backend currently implements a
synchronous PDF-to-Chroma pipeline and question-based passage retrieval.
Authentication, ownership metadata, answer generation, and the remaining
production lifecycle behavior below are still proposed.

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
2. The current API synchronously extracts page text, rejects unusable
   documents, chunks by page, embeds, and writes chunks with `document_id` and
   one-based `page_number` metadata. It returns a generated document ID after
   indexing completes; it does not persist document metadata or original PDFs.
3. The current question endpoint embeds the question and retrieves ranked
   passages from Chroma filtered by the supplied document ID. The ID filter
   is not an authorization boundary because authentication and ownership checks
   are not yet implemented.
4. A future question endpoint should load the document from SQLite constrained
   by the authenticated owner, apply a configurable relevance threshold, and
   pass only bounded excerpts to an answer model.
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

The current processing path runs inline with the upload request. It is suitable
only as a minimal development pipeline; there is no persisted status record or
durable job queue.

For a future asynchronous implementation, persist status before scheduling,
expose status polling, report failures, and recover stale records on startup.
Replace in-process background work with a durable queue only if reliability or
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
Future protected document endpoints require a bearer access token; the two
implemented minimal routes currently have no authentication.

| Method and path | Purpose | Proposed result |
|---|---|---|
| `POST /v1/auth/register` | Create a local MVP account; hash passwords using a maintained password-hashing library. | `201 {user_id, access_token, token_type, expires_in}` |
| `POST /v1/auth/token` | Authenticate and issue a short-lived signed token. | `200 {user_id, access_token, token_type, expires_in}` |
| `POST /v1/documents` | Multipart PDF upload; validates limits and synchronously indexes content. | `201 {document_id, page_count, chunk_count}` |
| `GET /v1/documents` | List only the caller's documents; bounded pagination. | `200 {items, next_cursor}` |
| `GET /v1/documents/{document_id}` | Read owned document metadata and processing status. | `200 {document}` |
| `DELETE /v1/documents/{document_id}` | Delete owned document, source, and chunks. | `204`; return the same not-found behavior for missing and non-owned IDs. |
| `POST /v1/documents/{document_id}/questions` | Retrieve page-aware passages for one document (implemented; unauthenticated). | `200 {document_id, passages}` |
| `GET /health/live` | Process liveness only; no secrets or dependency details. | `200 {status}` |
| `GET /health/ready` | Readiness check for required local storage. | `200` or `503` |

Implemented minimal routes are `POST /v1/documents` (synchronous extraction
and indexing) and `POST /v1/documents/{document_id}/questions` (retrieve
page-aware passages without generating an answer). They currently have no
authentication, and do not yet implement the broader table's ownership,
status, or lifecycle behavior.

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
