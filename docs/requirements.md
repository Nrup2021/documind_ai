# DocuMind AI — requirements

## Status and scope

This is a planning document, not a claim that all proposed features exist. The
repository now contains a Flutter foundation with Riverpod, GoRouter, and
presentation-only document-library and chat screens. It has no backend,
authentication, document upload, RAG pipeline, MCP integration, Docker
configuration, or CI workflow.

**Proposed MVP:** one Flutter Android client, one modular FastAPI service, and
one local persistent data store. Users authenticate, upload PDFs, see ingestion
status, and ask questions about documents they own. Answers include citations
constructed from retrieved page-aware excerpts. This is not a multi-tenant
production service; it is a small, single-deployment portfolio MVP with
server-side ownership checks.

## User stories and acceptance criteria

1. **Choose and upload a PDF**
   - The user can select one local PDF using Android's system file picker and
     see the selected filename, size, and upload progress.
   - The backend checks the authenticated user, size and page limits, PDF
     signature, and successful parsing. It stores files under generated IDs,
     not client-provided paths or filenames.
   - Invalid, encrypted, empty-text, oversized, or malformed PDFs receive a
     useful error. The UI does not display a failed upload as successful.
2. **Browse documents and processing state**
   - The user sees only their own documents, with filename, upload time, page
     count when known, and `processing`, `ready`, or `failed` state.
   - The client can refresh state after app restart. A failed record provides
     a safe, user-readable reason and can be deleted/retried.
3. **Ask a question**
   - A question can be submitted only for a document owned by the caller and
     in `ready` state.
   - The backend retrieves relevant chunks only from that document, generates
     an answer with Gemini, and returns page numbers and excerpts sourced from
     those retrieved chunks.
   - If evidence is insufficient, the API returns an explicit
     `insufficient_evidence` result rather than a confident-looking guess.
4. **Handle errors and data lifecycle**
   - Authentication, network, upload, parsing, indexing, model, and
     insufficient-evidence errors are distinguishable and actionable.
   - Deleting a document removes its metadata, source file, and vector entries;
     retries and partial failures are observable and do not grant access.
5. **Keep secrets and authorization server-side**
   - The Gemini key, JWT signing key, and MCP process configuration never ship
     in the Flutter app.
   - Every document read, delete, status lookup, and question operation checks
     ownership using the authenticated principal. A client-supplied document
     or owner ID is never treated as authorization.

## Proposed constraints and quality requirements

The following are initial, configurable MVP defaults—not measured limits:

- PDF upload: 25 MiB maximum; 500 pages maximum; accept PDF only. Validate
  actual content and parser outcome, not just extension or MIME header.
- Questions: non-empty, bounded request (for example, 2,000 characters).
- Chunking: preserve page boundaries and one-based source page numbers.
- Store original PDFs in a private backend data directory; never expose a
  filesystem path in the API.
- Keep SQLite metadata, Chroma's persistent local collection, and uploaded
  files on durable, access-controlled storage. This local persistence is for a
  single service instance, not horizontal scaling.
- Do not log PDF text, access tokens, API keys, or complete model prompts.
  Return a request ID and stable error code for support/debugging.
- Retrieved text is untrusted. It may contain instructions or hostile prompt
  injection. Treat it only as quoted evidence; do not execute instructions
  from it, and do not give the answer model tools or filesystem access.
- Set timeouts and bounded retries for Gemini. Do not silently convert provider
  or indexing failures into empty answers.

## Proposed dependency choices

Versions below were checked against package metadata on 2026-10-16 and are
candidates, not dependencies installed in this repository:

| Area | Candidate | Compatibility / rationale |
|---|---|---|
| Flutter state | `flutter_riverpod 3.4.3` | Requires Dart `^3.12.0`; the inspected toolchain is Dart 3.13.5. |
| Flutter navigation | `go_router 18.1.0` | Requires Dart `^3.12.0` and Flutter `>=3.44.0`; the inspected toolchain is Flutter 3.47.7. |
| Android PDF selection | `file_picker 13.1.0` | Requires Dart `>=3.10.0` and Flutter `>=3.38.0`; use native picker and filter for PDF, then validate on the server. |
| Backend API/schema | FastAPI with Pydantic 2 | Typed request/response validation and OpenAPI; use a supported Python runtime. |
| PDF extraction | PyMuPDF (`pymupdf`) | Page-oriented extraction suitable for preserving page citations. |
| RAG store | Chroma (`chromadb`) | Persisted local vector collection; SQLite remains the source of truth for ownership and document metadata. |
| Local embeddings | Sentence Transformers with `sentence-transformers/all-MiniLM-L6-v2` | Avoids a separate paid embedding API; model download, license, quality, and deployment size must be checked before adoption. |
| Answer generation | Google's maintained `google-genai` Python SDK | Use the Gemini Developer API from the backend only. Model IDs, quotas, pricing, and regional/data handling must be verified at implementation time. |
| MCP client | Official MCP Python SDK (`mcp`) | Compatible MCP client; use a Python version supported by the selected SDK. |
| Backend tests | pytest, HTTPX test client, and fakes for external/model boundaries | Deterministic tests without making paid Gemini requests. |

Before implementation, resolve and lock mutually compatible Python package
versions in the project's lockfile; do not use unbounded production
dependencies. The machine currently reports Python 3.9.6, which is too old for
the proposed MCP Python SDK baseline and is not a suitable new backend target.
Use Python 3.12 for local/CI/container backend work, subject to confirming
package support and wheels. Flutter candidates above meet the inspected local
SDK constraints, but still need resolution through `flutter pub get`.

Gemini use can incur charges and sends the question plus selected document
excerpts to Google's API. Confirm account billing, model availability, data
handling, and a per-request budget before enabling live calls. No paid hosting,
managed database, or paid vector service is proposed.

## Explicitly out of scope for the MVP

- iOS/web/desktop product support, collaborative sharing, teams, and
  organization-level roles.
- OCR for scanned PDFs, arbitrary file formats, and password-protected PDF
  decryption. Return a clear unsupported/unreadable-document error instead.
- Background job infrastructure, distributed workers, microservices,
  Kubernetes, multi-agent orchestration, and horizontal scaling.
- Exposing MCP tools to the mobile client or using MCP as the RAG/vector
  database.
- Production identity-provider integrations, billing, analytics, and
  multi-region backup. Add only after requirements and cost are reviewed.

## Inspected environment (facts)

- Flutter 3.47.7 and Dart 3.13.5 are available; Python 3.9.6 is on PATH.
- Node.js 24.11.1 and npm 11.6.2 are available.
- Docker, GitHub CLI (`gh`), Java, and `adb` were not available on the shell
  PATH during inspection. Android Studio may bundle a JDK/ADB, but that was not
  verified from this shell.
- The working tree was clean on branch `main`. The existing Android Gradle
  scaffold uses Java 17 settings; an Android build was not run.
