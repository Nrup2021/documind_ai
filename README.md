# DocuMind

DocuMind is a Flutter app foundation for exploring a personal document library
and document-focused chat, with a separate Python backend foundation.

## Current scope

- Riverpod app bootstrap and GoRouter navigation.
- Responsive library and chat shell with presentation-only empty states.
- FastAPI backend with health and typed API contracts.
- PDF extraction, page-aware chunking, local Ollama embeddings, persistent
  Chroma indexing, and document-scoped passage retrieval with locally
  generated grounded answers.
- Authentication and server-side document lifecycle management are not
  implemented yet.

## Tech stack

| Area | Technology | Purpose |
| --- | --- | --- |
| Mobile and web app | Flutter, Dart, Material | Shared application UI for Android and web. |
| App state and navigation | Riverpod, GoRouter | State management and route navigation. |
| Backend API | Python, FastAPI, Pydantic, Uvicorn | REST endpoints, request/response validation, and local development server. |
| PDF processing | PyMuPDF | Extract text and page numbers from uploaded PDFs. |
| Embeddings and answer generation | Ollama with `nomic-embed-text` and `qwen2.5:3b` | Generate document/query embeddings and grounded answers locally on the backend computer. |
| Retrieval and vector storage | ChromaDB | Persist document chunk embeddings and retrieve relevant passages for a question. |
| App networking and file selection | Dio, `file_picker` | Send API requests and select PDFs. |
| Local app preferences | `shared_preferences` | Store the client-side document library metadata. |
| Testing | Flutter `flutter_test`, Python `pytest` | Test client UI/logic and backend behavior. |

For document Q&A, the backend follows a retrieval-augmented generation (RAG)
flow: it extracts and chunks PDF text, embeds and stores those chunks, retrieves
relevant passages for a question, then asks the local answer model to respond
using that evidence. The backend validates citations against the retrieved
passages. Ollama runs on the computer hosting FastAPI; the Flutter app talks
to FastAPI, not directly to Ollama.

## Run the app locally

PDF embeddings and answers run on the computer hosting the FastAPI backend.
Hosted model API keys and Ollama account sign-in are not required for the
local PDF question-answering flow.

### 1. Install and start Ollama

Install [Ollama](https://ollama.com/download) for your operating system and
open the Ollama app. In a new terminal (the working directory does not matter),
download the default models once:

```sh
ollama pull nomic-embed-text
ollama pull qwen2.5:3b
ollama list
```

Keep Ollama running while using the app. Model downloads take disk space;
inference uses the computer's memory and CPU/GPU.

### 2. Set up and start FastAPI

Open a second terminal and create the backend environment (one-time setup):

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

For later runs, activate the existing environment and start the server:

```sh
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Keep this terminal running. Check that the API is available at
<http://127.0.0.1:8000/health>; interactive API documentation is at
<http://127.0.0.1:8000/docs>.

On Windows, activate the environment with `.venv\Scripts\activate` instead of
`source .venv/bin/activate`.

### 3. Set up and start Flutter

Open a third terminal at the repository root:

```sh
flutter pub get
flutter devices
```

Start the browser app:

```sh
flutter run -d chrome
```

Or start the Android emulator app using the device ID printed by
`flutter devices`:

```sh
flutter run -d <device-id>
```

The web app connects to `127.0.0.1:8000`; the Android emulator uses
`10.0.2.2:8000` to reach the computer hosting FastAPI. For a real phone on the
same Wi-Fi, configure the API base URL to use the computer's LAN IP; see the
[backend setup guide](./backend/README.md#run-the-api).

### 4. Upload and ask

In DocuMind, select and upload a PDF. Wait for processing to finish, then ask a
question about that document. After changing the embedding model, upload the
PDF again so it can be indexed with the new model.

## Production CI/CD plan

> **Status:** This is the target implementation guide, not a description of
> automation that is already installed. The repository currently has no
> GitHub Actions workflows or configured app flavors. In particular,
> `android/app/build.gradle.kts` signs release builds with the debug signing
> configuration. Do not distribute a release build until production signing
> has been configured and verified.

The recommended pipeline uses GitHub Actions for continuous integration and
release orchestration. It validates Flutter and backend changes on pull
requests and development branches. Only a push to `master` may publish a
production release: Android is uploaded to the Google Play **Internal
testing** track, and signed Android and iOS artifacts are attached to a
GitHub Release. The iOS IPA is an archive artifact; it is not uploaded to
App Store Connect or TestFlight by this policy.

### 1. Use explicit branch roles

| Branch | Purpose | Expected automation |
| --- | --- | --- |
| `dev` | Integration branch for completed feature work. Feature branches merge here by pull request. | Run CI and produce non-production validation builds; never publish production artifacts. |
| `main` | Stabilization/release-candidate branch. Promote tested commits from `dev` by pull request. | Run CI and release-candidate checks; never publish production artifacts. |
| `master` | Production release branch. Promote an approved, tested commit from `main` by pull request. | Run release CI and publish only after every required check succeeds. |
| `feature/*`, `fix/*` | Short-lived work branches. | Pull requests into `dev` run the same quality gates; no release credentials are available. |

Protect `dev`, `main`, and `master` in GitHub repository rulesets:

1. Require pull requests and at least one review; require CODEOWNER review for
   workflow, signing, and release configuration.
2. Require the CI status checks to pass, resolve review conversations, and
   block force pushes and branch deletion.
3. Limit the protected `production` environment to the `master` branch and
   designated maintainers. Keep review/approval before merge; do not add a
   post-merge environment approval if a master push must publish automatically.
4. Merge with a consistent strategy and promote the tested commit forward
   (`dev` → `main` → `master`) so the production branch contains the changes
   validated on the release candidate.

`main` and `master` have distinct roles here: `main` is the release-candidate
branch; `master` alone is the production publishing branch. Do not enable
publishing for tags, pull requests, `dev`, or `main`.

### 2. Define environment flavors and variants

Add matching Android product flavors and iOS Xcode schemes/configurations for
three environments. A flavor chooses environment-specific app identity and
configuration; a build type/configuration chooses debug or optimized release
compilation. Together they form variants such as `devDebug`,
`stagingRelease`, and `productionRelease`.

| Environment | Intended use | API endpoint | Distribution |
| --- | --- | --- | --- |
| `dev` | Developer integration and automated checks | Development API URL | Local installs or CI validation artifacts |
| `staging` | Release-candidate acceptance testing | Staging API URL | Restricted QA distribution |
| `production` | Public production release | Production API URL over HTTPS | Master-only production release |

For Android, add `dev`, `staging`, and `production` product flavors in
`android/app/build.gradle.kts`, use distinct application ID suffixes for
non-production apps (for example `.dev` and `.staging`), and keep the
production application ID stable. Add environment-specific app names/icons if
needed. Configure release signing independently of the debug key.

For iOS, create shared Xcode schemes and build configurations for the same
environments, with distinct bundle identifiers for dev/staging and the
existing production identifier for production. Commit shared schemes and
non-secret build settings so CI and developer machines build the same
variants.

The app currently reads `DOCUMIND_API_BASE_URL` with `--dart-define` and
otherwise defaults to loopback/emulator addresses. Every CI build must pass
the correct environment URL; a production build must never use a local
development default. The URL is configuration, not a secret. Do not put API
keys, signing credentials, or other secrets in `--dart-define`: values
compiled into a client can be extracted from the app.

Once flavors and schemes are implemented, use the matching flavor/scheme
commands (for example `flutter build appbundle --flavor production` for
Android and `flutter build ipa --flavor production` for iOS). Verify the
exact commands against the committed Gradle and Xcode configuration before
enabling the workflow.

### 3. Run continuous integration on every change

Create a pull-request workflow (for example,
`.github/workflows/ci.yml`) and a push trigger for `dev`, `main`, and
`master`. CI should be read-only and should not receive release credentials.
Use pinned GitHub Actions, least-privilege token permissions, dependency
caching, and a concurrency group that cancels superseded runs for the same
branch/PR.

Recommended checks:

1. Check out the commit and install the Flutter SDK version pinned by the
   repository/toolchain policy. Pin the Python version used by the backend.
2. Run `flutter pub get`, `dart format --output=none --set-exit-if-changed .`,
   `flutter analyze`, and `flutter test`.
3. Set up Python in `backend`, install `requirements-dev.txt`, and run
   `python -m pytest`.
4. Build unsigned/non-production validation variants for the supported
   platforms. Do not use production credentials for pull-request builds.
5. Retain test reports and validation artifacts for a defined, limited period;
   publish test results as job summaries without leaking environment values.
6. Enable secret scanning and dependency/security update alerts. Add the
   organization's SAST and dependency-audit checks as required gates; fail the
   PR for newly introduced critical/high findings according to the
   organization's vulnerability policy. Pin third-party Actions to full
   commit SHAs.

The current README development checks can be used to run the Flutter
commands locally. Backend tests use `python -m pytest` from `backend`.

### 4. Make the backend safe to release independently

CI can run the backend tests now, but that is not backend production
deployment. The current backend README explicitly describes the service as a
local-development foundation: authentication and document ownership checks
are not implemented, and Ollama/Chroma use local services and storage. Do
not expose this API to the public internet or claim a production backend
release until the following have been designed and verified:

- Authentication, authorization, per-user document isolation, and secure
  document lifecycle behavior.
- A supported deployment target, durable/private vector storage, backup and
  restore, and a managed inference strategy for embeddings and answer
  generation.
- Production TLS, secret/configuration management, rate and resource limits,
  observability/alerting, health/readiness checks, and an incident/rollback
  procedure.
- Integration and security testing against that deployment environment.

When those prerequisites are met, add backend image build, vulnerability
scanning, and environment-gated deployment as a separate workflow. Do not
couple mobile publication to an unready backend deployment.

### 5. Configure production signing and upload credentials

Create a protected GitHub Environment named `production`. Store credentials
there rather than in source control, workflow YAML, repository-wide variables,
or developer `.env` files. Restrict the environment to `master`. To preserve
automatic publishing on master pushes, approvals and required checks happen
before merge through branch protection; do not configure a manual
post-merge deployment approval.

| Platform/service | Required setup |
| --- | --- |
| Android signing | Enroll in Google Play App Signing so Google manages the app-signing key; use a production upload keystore for CI uploads and securely back it up. Add the keystore (base64-encoded if passed as a GitHub secret), keystore password, key alias, and key password as environment secrets. Configure Gradle to load them only for production release builds. Never commit the keystore or generated properties file. |
| Google Play | Grant a dedicated service account the minimum Play Console permissions needed for the app and Internal testing track. Prefer keyless/workload identity federation when supported by the chosen upload action; otherwise store its JSON key as a protected environment secret and rotate it. |
| iOS signing | Use a protected Apple distribution certificate/private key and provisioning profile for the production bundle ID. Prefer a managed signing solution such as Fastlane Match with an encrypted certificate repository and a separate decryption secret. Keep all signing material out of the repository and job logs. |
| GitHub Release | Grant only the release job `contents: write`; keep CI jobs at read-only permissions. Restrict the release environment and branch rules so only approved `master` commits can publish. |

Limit secret exposure to the one protected publishing job, mask derived
credentials, avoid printing environment variables, and use short-lived
credentials where available. Rotate credentials after suspected exposure and
maintain an offline backup/recovery plan for signing keys. Losing the Android
upload key or Apple signing access can block future releases.

### 6. Publish only from a push to `master`

Create a separate release workflow (for example,
`.github/workflows/release.yml`) with a push trigger restricted to
`master`. It must also have an explicit branch guard before any release
credential is accessed. Do not add `pull_request`, `workflow_dispatch`, or
tag triggers to its publishing job if the policy is “automatic upload only
when a commit is pushed to master.”

The master release sequence should be:

1. Run the complete required CI checks on the exact pushed commit.
2. Enter the protected `production` environment automatically after the
   branch and workflow guards pass.
3. Read the app version from the repository and supply a unique, monotonically
   increasing build number. Keep Android `versionCode` and iOS build number
   increasing for every uploaded build; a retry that reuses an already
   uploaded number must not publish a duplicate.
4. Build the signed production Android App Bundle (AAB) and signed iOS IPA
   using the production API URL and production flavor/scheme.
5. Validate that artifacts exist, are signed with the expected identities,
   target the production application/bundle IDs, and contain no development
   endpoint. Generate checksums and preserve build/test metadata.
6. Upload the AAB to the Google Play Internal testing track. This is an
   automated upload, not an automatic public rollout; promote to a wider track
   only through an explicitly approved Play Console release process.
7. Create a versioned GitHub Release for the same commit and attach the signed
   Android artifact(s), signed iOS IPA, checksums, and concise release notes.
   Keep the repository private or restrict release access if the artifacts
   are confidential.

An App Store-distribution IPA generally cannot be installed directly from a
GitHub Release. It is retained there as a signed build artifact only. If iOS
test distribution or public iOS release is required later, add a separately
approved TestFlight/App Store Connect upload and release gate.

Use the same immutable build outputs for validation and distribution wherever
possible; do not rebuild a different binary after it passes validation.
Record the commit SHA, app version/build number, workflow run, signing
identity, and artifact checksums in the release notes or attached provenance.
Retain release artifacts according to an explicit retention policy.

### 7. Prepare release notes and recovery

Use a versioned tag/release title such as `v1.2.0` and include the commit
identifier, user-visible changes, known issues, and artifact checksums.
`pubspec.yaml` provides the app version (`version: name+build`); define who
updates the semantic version and ensure each Play/App Store upload receives a
new build number.

If validation fails, stop before upload and fix forward through the protected
branch flow. If Google Play accepts an unintended build, halt promotion and
publish a corrected higher build number. GitHub Release assets are immutable
release records; publish a corrected version/build rather than silently
replacing a distributed binary. Document who can approve emergency releases
and how signing credentials are recovered.

### 8. Roll out in safe stages

Implement in this order:

1. Confirm final application IDs, bundle IDs, environment API URLs, and
   ownership of Play Console and Apple Developer accounts.
2. Add flavors/schemes and test each variant locally, including API endpoint
   selection and app identity.
3. Replace Android debug release signing with protected production signing;
   establish and test key backup/recovery.
4. Add CI checks without release secrets and make them required in branch
   protection.
5. Add protected environments and signing/upload credentials; test the
   publishing workflow against a non-production app/track first.
6. Enable the production release workflow and verify a master commit produces
   one matching Play Internal release and GitHub Release.
7. Keep public rollout and backend deployment separately gated until their
   production-readiness requirements are met.

### Current production-readiness blockers

- No CI/CD workflow or flavor/scheme matrix is configured yet.
- Android release currently uses the debug signing key.
- The app's fallback API URL is for local development; production must inject
  a secured HTTPS backend URL.
- The backend currently lacks authentication/authorization and production
  hosting/storage/inference setup.
- Google Play and Apple account ownership, final IDs, distribution policy,
  and release approvers must be confirmed before publishing credentials are
  configured.

## Development checks

Format and verify Flutter changes with:

```sh
dart format .
flutter analyze
flutter test
```

For backend configuration, API details, and real-phone networking, see the
[backend README](./backend/README.md).
