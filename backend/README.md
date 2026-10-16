# DocuMind backend

This directory contains the standalone FastAPI service foundation. It currently
provides `GET /health`, typed health and error responses, and Pydantic question
request/response contracts for future API work. Question answering,
document-processing, Gemini, and MCP integrations are not implemented.

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

## Configuration

Configuration is read from environment variables using the `DOCUMIND_` prefix:

| Variable | Default | Description |
| --- | --- | --- |
| `DOCUMIND_APP_NAME` | `DocuMind API` | FastAPI title and health response service name |
| `DOCUMIND_ENVIRONMENT` | `development` | Environment name returned by the health endpoint |
| `DOCUMIND_DEBUG` | `false` | FastAPI debug mode |

For example, set `DOCUMIND_ENVIRONMENT=local` before starting Uvicorn.

## Tests

Install the development dependencies as above, then run from `backend`:

```sh
python -m pytest
```

The tests cover health status, the OpenAPI health response schema, Pydantic
question contracts, and the structured error format.
