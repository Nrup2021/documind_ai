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

## Planned next milestones

1. **Dockerize the backend:** create a secure backend image and local Compose
   setup, configure persistent storage for Chroma, and document how the
   container reaches Ollama on the host.
2. **GitHub Actions CI/CD:** run Flutter and backend checks on pushes and pull
   requests, then build and validate the Docker image. Add deployment only
   after choosing a hosting target and defining its secrets and release policy.

## Development checks

Format and verify Flutter changes with:

```sh
dart format .
flutter analyze
flutter test
```

For backend configuration, API details, and real-phone networking, see the
[backend README](./backend/README.md).
