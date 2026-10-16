# DocuMind AI — implementation plan

## Status

The Flutter app shell and its Riverpod repositories, PDF upload/library, and
document-scoped chat are implemented against the existing FastAPI contracts.
The backend foundation also includes synchronous PDF upload validation,
PyMuPDF extraction, page-aware chunking, local Ollama embeddings, persistent
Chroma indexing, document-scoped passage retrieval, and locally generated
grounded answers with validated citations and abstention. Authentication,
server-side document lifecycle and ownership, relevance thresholds, and later
milestones remain proposed.

## Milestones

### 0. Resolve prerequisites and lock choices

- Install/select Python 3.12 for backend development; current shell Python is
  3.9.6. Confirm Android Studio's bundled JDK and `adb` or put them on PATH.
- Install Ollama and download the configured local embedding and answer models.
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
- [x] Add page-aware chunking, local Ollama embedding adapter, and persistent Chroma
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

- [x] Retrieve page-aware passages per document and send bounded evidence
  context to a local Ollama adapter.
- [x] Validate structured model output, require supporting excerpts from
  retrieved passages, construct page citations from retrieval metadata, and
  explicitly abstain when evidence is missing or insufficient.
- [ ] Add a configurable relevance threshold for retrieved passages.
- Use a deterministic fake model in tests; no real API key or paid request in
  normal CI.

**Tests:** relevant evidence and citation mapping, no retrieved evidence,
model abstention, malformed model output, invented citations, provider errors,
and local-model timeout, using a mocked model client. Prompt-injection text is
passed as quoted evidence, but dedicated adversarial prompt tests and
cross-document/cross-user authorization tests remain to be added. **Exit:**
answers cite only retrieved page-aware excerpts or return an explicit
abstention.

### 5. Connect Flutter flows end to end

- [x] Add Android PDF selection, multipart upload, byte progress, and safe
  backend error display.
- [x] Add a device-local library for successful uploads, client-observed
  processing/error states, retry, and document-scoped questions with citations.
- [ ] Add login/register and server-backed document list/status after those
  routes exist in FastAPI. The API now supports deleting indexed chunks but
  does not synchronize the server-side library.
- [x] Add empty/loading/error states and fake-repository widget and API
  contract tests.
- [ ] Validate keyboard, scrolling, and narrow Android layouts on a device.

**Tests:** Flutter repository contract tests use a local HTTP server and
widget tests use fake repositories; backend route contracts are covered by
pytest. A manual Android emulator/device smoke pass remains outstanding.

### 6. Dockerize the backend

- Add a minimal, non-root backend image with only runtime dependencies and a
  health check.
- Add local Compose configuration for FastAPI and persistent Chroma data.
- Configure the container to reach Ollama on the host without exposing
  Ollama's API to the network; document platform-specific host addresses.
- Keep secrets out of the image and logs; document environment configuration,
  persistence, backup, and reset behavior.

**Tests:** build the image, start the service, verify its health endpoint and
PDF/Q&A path with a fake or local model, and confirm Chroma data persists
across container restarts. **Exit:** a developer can run the backend with
Docker using documented setup and the existing local Ollama models.

### 7. GitHub Actions CI/CD

- Add pull-request and push workflows for Flutter formatting/analyze/tests,
  backend tests, and Docker image build.
- Use dependency caching and test fakes; CI must not need Ollama downloads,
  model/API credentials, or real PDFs.
- Add a controlled release/deployment workflow only after choosing a hosting
  target, secret management, and approval policy. Keep deployment credentials
  out of pull-request workflows.

**Tests:** workflows pass from a clean checkout, including Docker image build.
**Exit:** GitHub Actions validates changes automatically; release deployment
is enabled only after its target and operational policy are configured.

## Test strategy summary

| Layer | Approach | Required cases |
|---|---|---|
| Flutter unit | Test pure mapping/validation and repository behavior. | DTO-to-entity mapping, status/error mapping, upload validation. |
| Flutter widget | `flutter_test` with fake repositories/providers. | Loading, empty, processing, ready, failed, citations, retry, navigation. |
| Backend unit | pytest; inject fake embedding/model/vector adapters. | Chunk boundaries/page numbers, ownership filtering, state transitions, thresholds, error mapping. |
| Backend API | FastAPI test client + temporary SQLite/files/Chroma collection. | Auth, multipart validation, CRUD permissions, status polling, question response contract. |
| Backend integration | Local real PyMuPDF and Chroma; fake Ollama model client. | Parse/index/retrieve/delete/restart behavior, partial failures, cross-user isolation. |
| End-to-end | Android emulator/device + FastAPI and Ollama on the backend computer. | Upload a non-sensitive fixture PDF, verify page citation, explicit abstention, and backend errors. |
| Container | Docker/Compose; local data volume and local Ollama. | Image builds, health check, API smoke test, persistent Chroma volume across restart. |
| CI/CD | GitHub Actions; no production secrets in pull requests. | Formatting, lint/type checks, tests, Android debug build, backend image build; gated deploy after target selection. |

Do not assert that model output is grounded solely because a prompt requests
citations. Tests must verify returned citation IDs belong to retrieved chunks
and that page/excerpt values are reconstructed by the backend.

## Deployment approach

1. **Local development:** Flutter Android app points to a developer-run API
   and Ollama instance. Use non-sensitive sample PDFs; never commit
   credentials.
2. **Container:** run the backend with Docker and persist Chroma data in a
   named volume. Ollama remains a separate host service for local development.
3. **CI/CD:** validate Flutter, backend, and Docker image in GitHub Actions.
   Add a deployment job only after a host and secret policy are selected.
4. **Portfolio demo:** one Dockerized API instance with private persistent
   volumes for uploads, SQLite, and Chroma. Bind to localhost or deploy only
   after selecting a host and reviewing cost, TLS, authentication, backups,
   rate limits, retention, and data residency. A public demo needs a stronger
   abuse/rate-limit policy than the local MVP.
5. **Release:** build a signed Android artifact only after signing keys and
   release distribution are configured outside the repository. GitHub Actions
   release credentials must be narrowly scoped and stored as protected
   secrets.

Docker, Java, ADB, and GitHub CLI were not available on PATH during inspection;
container/build/emulator/remote GitHub deployment steps therefore require
tooling setup and were not verified.
