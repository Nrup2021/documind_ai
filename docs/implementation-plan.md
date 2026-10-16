# DocuMind AI — implementation plan

## Status

The Flutter app shell for milestone 1 is implemented. The backend foundation
also includes synchronous PDF upload validation, PyMuPDF extraction,
page-aware chunking, OpenAI embeddings, persistent Chroma indexing, and
document-scoped passage retrieval. Authentication, document lifecycle and
ownership, answer generation, and later milestones remain proposed.

## Milestones

### 0. Resolve prerequisites and lock choices

- Install/select Python 3.12 for backend development; current shell Python is
  3.9.6. Confirm Android Studio's bundled JDK and `adb` or put them on PATH.
- Confirm the Gemini API account, selected model(s), billing/quotas, data
  handling, and budget before any live API call.
- Review PDF size/page caps and whether the proposed local filesystem MCP
  fixture integration meets the MCP requirement.
- Add backend package metadata/lockfile, then resolve compatible versions.
  Pin Flutter candidate dependencies and verify with `flutter pub get`.

**Exit:** toolchain and cost/data decisions are documented; clean dependency
resolution succeeds without adding unapproved paid services.

### 1. Flutter app shell and domain contracts

- Replace the counter starter with app bootstrap, theme, GoRouter routes, and
  Riverpod setup.
- Create auth, documents, and questions feature boundaries with repository
  contracts, typed entities, and a shared API error type.
- Build basic loading/empty/error states; configure API base URL per build
  environment. Do not include secrets in Dart assets or defines.

**Tests:** widget smoke tests, route tests, provider/repository unit tests, and
tests for API errors. **Exit:** Android debug build launches and tests pass.

### 2. Backend foundation and authorization

- Create FastAPI app, Pydantic schemas, settings validation, structured error
  mapping, SQLite schema, local user registration/login, password hashing, and
  short-lived signed bearer tokens.
- Add health routes and an authenticated principal dependency.
- Enforce document ownership in repository queries and verify identical
  not-found behavior for missing versus non-owned document IDs.

**Tests:** pytest for schema validation, password/token behavior, expiration,
unauthenticated requests, and cross-user access denial. **Exit:** API tests
prove a user's token cannot read or mutate another user's records.

### 3. Secure document upload and processing status

- [x] Add multipart upload validation, configurable byte/page limits, PyMuPDF
  extraction with page numbering, and API-level processing.
- [x] Add page-aware chunking, OpenAI embedding adapter, and persistent Chroma
  indexing/retrieval.
- [ ] Add generated storage paths, safe filename handling, and document status
  persistence.
- [ ] Add cleanup for partial failures and idempotent document deletion.
- [ ] Expose persisted processing state and recover abandoned jobs on service
  restart.

**Tests:** valid, renamed-non-PDF, malformed, empty, encrypted, oversize,
too-many-page, and cross-owner uploads; extraction/page metadata; status
transitions; Chroma failure compensation; deletion. **Exit:** files, SQLite,
and Chroma survive an application restart in local development, and a failed
index never appears ready. The current tests cover invalid PDF, empty text,
size limit, page metadata, and retrieval with fakes; persistent-store
integration and the other listed cases remain to be added.

### 4. Grounded question answering

- Add per-document retrieval, relevance threshold, bounded context, Gemini
  adapter, structured output validation, abstention behavior, and citations
  reconstructed from retrieved chunks.
- Use a deterministic fake model in tests; no real API key or paid request in
  normal CI.

**Tests:** relevant evidence, no relevant evidence, malformed model output,
invented citation IDs, Gemini timeout/rate limit, hostile instructions in PDF
text, and cross-document/cross-user retrieval isolation. **Exit:** answers
cite only retrieved page-aware excerpts or return an explicit abstention.

### 5. Connect Flutter flows end to end

- Implement login/register, PDF selection/upload, document list/status/delete,
  question composer, answer, citations, and actionable error states.
- Handle lifecycle/retries, pagination, progress, empty/loading states, and
  backend outages. Validate keyboard, scrolling, and narrow Android layouts.

**Tests:** Flutter unit/widget tests with fake repositories; API integration
tests with local backend; manual Android emulator/device smoke pass for file
picker, upload, polling, Q&A, logout, and error cases. **Exit:** an Android
user can complete the complete flow without embedding any privileged secret.

### 6. MCP integration and safe developer workflow

- Add a Python MCP client adapter behind an explicit configuration flag.
- Start the official filesystem MCP server only against a dedicated fixture
  directory; client-allow-list fixed read/list tools and apply process, path,
  timeout, and output limits.
- Add integration tests with a controlled fixture and verify disallowed tools,
  paths, and malformed arguments are rejected. Do not connect it to uploaded
  PDFs or RAG.

**Exit:** a reviewer can see a working compatible MCP client/server exchange,
and the integration has no access to user files or secrets. If this does not
add portfolio value, revisit the exact requirement before widening its role.

### 7. CI, container, and local deployment

- Add GitHub Actions for Flutter formatting/analyze/tests and Python lint,
  typing, and pytest; build the Android debug APK. Cache dependencies safely
  and use fakes so CI does not need Gemini credentials.
- Add a non-root backend container, health checks, `.env.example`, and local
  Compose configuration with persistent volumes for SQLite, Chroma, and
  uploads. Keep secrets out of the image and logs.
- Document backup/restore and reset procedures. Do not make reset scripts
  destructive without explicit operator confirmation.

**Tests:** CI from a clean checkout; backend container health/readiness; volume
persistence across restart; local end-to-end walkthrough. **Exit:** CI is green
and a developer can reproduce the flow from documented setup.

## Test strategy summary

| Layer | Approach | Required cases |
|---|---|---|
| Flutter unit | Test pure mapping/validation and repository behavior. | DTO-to-entity mapping, status/error mapping, upload validation. |
| Flutter widget | `flutter_test` with fake repositories/providers. | Loading, empty, processing, ready, failed, citations, retry, navigation. |
| Backend unit | pytest; inject fake embedding/model/vector adapters. | Chunk boundaries/page numbers, ownership filtering, state transitions, thresholds, error mapping. |
| Backend API | FastAPI test client + temporary SQLite/files/Chroma collection. | Auth, multipart validation, CRUD permissions, status polling, question response contract. |
| Backend integration | Local real PyMuPDF and Chroma; fake Gemini. | Parse/index/retrieve/delete/restart behavior, partial failures, cross-user isolation. |
| MCP | Local stdio server, isolated fixture root, deterministic test data. | Tool discovery, schema validation, allowed calls only, path escapes and writes rejected. |
| End-to-end | Android emulator/device + local backend; Gemini only in a separate opt-in smoke test. | Upload a non-sensitive fixture PDF, verify page citation, explicit abstention, and backend errors. |
| CI | GitHub Actions; no production secrets. | Formatting, lint/type checks, tests, Android debug build, backend image build. |

Do not assert that model output is grounded solely because a prompt requests
citations. Tests must verify returned citation IDs belong to retrieved chunks
and that page/excerpt values are reconstructed by the backend.

## Deployment approach

1. **Local development:** Flutter Android app points to a developer-run API.
   Use non-sensitive sample PDFs and a local `.env` ignored by Git. Gemini
   calls are opt-in after billing and data-handling review.
2. **CI:** run unit/integration tests with fake Gemini and temporary storage;
   do not store Gemini or MCP credentials in pull-request workflows.
3. **Portfolio demo:** one Dockerized API instance with private persistent
   volumes for uploads, SQLite, and Chroma. Bind to localhost or deploy only
   after selecting a host and reviewing cost, TLS, authentication, backups,
   rate limits, retention, and data residency. A public demo needs a stronger
   abuse/rate-limit policy than the local MVP.
4. **Release:** build a signed Android artifact only after signing keys and
   release distribution are configured outside the repository. GitHub Actions
   release credentials must be narrowly scoped and stored as protected
   secrets.

Docker, Java, ADB, and GitHub CLI were not available on PATH during inspection;
container/build/emulator/remote GitHub deployment steps therefore require
tooling setup and were not verified.
