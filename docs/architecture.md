# DocuMind AI — proposed architecture

## Status boundary

The Flutter Android and web clients integrate the backend's synchronous PDF
upload and document-scoped question routes with Riverpod repositories. The
document library's metadata is stored locally on the device. The backend
implements a synchronous PDF-to-Chroma pipeline and a question route that
retrieves page-aware passages before generating grounded answers with a local
Ollama model.
Authentication, ownership metadata, server-side document listing/status,
deletion, and the remaining production lifecycle behavior below are still
proposed.

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
       │                    └── Ollama local answer generation
       ├── SQLite (users, document metadata, status)
       └── private PDF storage
```

Keep the backend a modular monolith. Define small ports at the model,
embedding, vector-store, and document-storage boundaries so tests can substitute
fakes; do not introduce a generic plugin framework or additional services.

## Proposed Flutter structure

See `implementation-plan.md` for milestone ordering. Feature UI depends on
feature domain contracts; network and persistence implementations sit behind
domain-facing repositories. Widgets do not call HTTP or model APIs directly.

The client uses `DOCUMIND_API_BASE_URL` to configure the API URL. By default,
web builds use `http://127.0.0.1:8000`, while Android builds use
`http://10.0.2.2:8000` to reach a development API on the host. The backend
allows local browser origins in development; deployed web origins must be
listed with `DOCUMIND_CORS_ALLOWED_ORIGINS`. Android's debug manifest permits
cleartext HTTP for local development; release builds should use an HTTPS URL.
No credentials or model keys are embedded in the app.

Implemented backend routes include `POST /v1/documents` with the multipart
field `file`, `DELETE /v1/documents/{document_id}`, and
`POST /v1/documents/{document_id}/questions` with `{"question": "..."}`.
Upload returns `document_id`, `page_count`, and `chunk_count`; questions return
`outcome`, `answer`, and `citations` containing `page_number` and `excerpt`.
Upload progress is client-side transfer progress; the backend processes the
upload synchronously and returns only after indexing.
There is no server-side document list or status polling, so completed document
metadata is persisted locally and the app does not claim server-side library
synchronization. A delete route removes indexed Chroma chunks by document ID;
the app removes local library metadata after that request succeeds.

## Proposed ingestion and question flows

1. The current Flutter client sends a PDF in the multipart field `file`.
   Authentication is not implemented on this route yet. The API validates
   upload size and PDF content before indexing.
2. The current API synchronously extracts page text, rejects unusable
   documents, chunks by page, embeds, and writes chunks with `document_id` and
   one-based `page_number` metadata. It returns a generated document ID after
   indexing completes; it does not persist document metadata or original PDFs.
3. The question endpoint embeds the question and retrieves ranked passages
   from Chroma filtered by the supplied document ID. The ID filter is not an
   authorization boundary because authentication and ownership checks are not
   yet implemented.
4. When passages exist, the backend passes bounded, page-preserving evidence
   to the local Ollama model. The model is instructed to answer only from that
   evidence and abstain when it is inadequate. The backend validates its
   structured response and each cited excerpt against the retrieved set, then
   constructs citation page numbers from retrieved passage metadata—not
   model-invented page numbers. No retrieved evidence returns an explicit
   abstention without calling the model; invalid citations and provider
   failures return structured errors, never fabricated citations.

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
| `POST /v1/documents/{document_id}/questions` | Retrieve evidence and generate a grounded answer (implemented; unauthenticated). | `200 {outcome, answer, citations}` |
| `GET /health/live` | Process liveness only; no secrets or dependency details. | `200 {status}` |
| `GET /health/ready` | Readiness check for required local storage. | `200` or `503` |

Implemented minimal routes are `POST /v1/documents` (synchronous extraction
and indexing) and `POST /v1/documents/{document_id}/questions` (retrieve
page-aware evidence and generate a grounded answer). They currently have no
authentication, and do not yet implement the broader table's ownership,
status, or lifecycle behavior.

### Main response models

- `User`: `id: UUID`, `email: normalized string`, `password_hash`, timestamps.
  Password hash is never serialized.
- `Document`: `id: UUID`, `owner_id: UUID`, `display_name`, `byte_size`,
  `page_count?`, `status: processing | ready | failed`, `failure_code?`,
  `created_at`, `updated_at`. Never serialize a storage path.
- `QuestionRequest`: `question: non-empty bounded string`.
- `Citation`: `page_number: positive integer`, `excerpt: supporting text from a
  retrieved passage`.
- `QuestionResponse`: `outcome: answered | insufficient_evidence`,
  `answer: string`, `citations: Citation[]`.
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
│   │   ├── infrastructure/           # SQLite, Chroma, Ollama adapters
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
