# System Prompt and Persistent Test Suite Design

## Goal

Replace Agent_Col's short system instruction with the exact approved prompt
and establish a permanent, offline pytest suite for the FastAPI and Firestore
boundaries.

## Scope

This pass modifies the system prompt, adds reproducible runtime and development
dependency manifests, configures pytest, and creates persistent tests for
`main.py` and `database.py`.

This pass does not change endpoint paths, request or response schemas,
Firestore document structure, authentication, session ownership, deployment
configuration, or live Google Cloud resources.

## System Instruction

`SYSTEM_INSTRUCTION` in `main.py` will evaluate to this exact string:

```text
You are a collaborative partner for users, you learn about the users over time, provide feedback and ask questions to push development and goals, you are a helpful assistant that helps users with complex tasks by giving step by step instructions for complex tasks and offer insightful and meaningful feedback when users get stuck to help them progress.
```

The source will use adjacent parenthesized string literals to keep each line at
or below 88 characters without inserting or removing spaces from the runtime
value.

## Dependency Layout

`requirements.txt` will pin every directly used runtime package to the version
verified in the current Python 3.14 environment:

```text
fastapi==0.141.1
google-api-core==2.34.0
google-cloud-firestore==2.28.1
google-genai==2.18.1
pydantic==2.13.4
python-dotenv==1.2.3
uvicorn==0.52.4
```

`requirements-dev.txt` will include the runtime manifest and pin the testing
stack:

```text
-r requirements.txt
httpx==0.28.1
pytest==9.1.1
pytest-asyncio==1.4.0
```

Production installations can use `requirements.txt` without installing test
tools. Local development and CI use `requirements-dev.txt`.

## Pytest Configuration

`pytest.ini` will:

- restrict discovery to `tests`;
- use files named `test_*.py`;
- enable strict pytest-asyncio mode;
- add the repository root to the pytest import path so both console-script and
  module invocation collect identically;
- narrowly suppress the known `google-genai` Python 3.14 deprecation warning;
- show extra summary information for skipped, failed, and errored tests.

Every asynchronous test will carry an explicit `@pytest.mark.asyncio` marker.

## FastAPI Test Architecture

`tests/test_main.py` will use `httpx.AsyncClient` with its ASGI transport. Each
test that enters the application lifespan will replace the external
constructors used by `main.lifespan`:

- `main.MemoryEngine` returns an in-memory async fake;
- `main.genai.Client` returns a fake client with async chat behavior and close
  tracking;
- `GOOGLE_API_KEY` is set to a non-secret test value through pytest's
  `monkeypatch` fixture.

This preserves real FastAPI routing, JSON parsing, Pydantic validation,
response serialization, and lifespan entry/exit while preventing Firestore or
Gemini network access.

The endpoint suite will verify:

- `GET /` returns HTTP 200 and `{"status": "online"}`;
- valid `/api/chat` JSON returns the generated response;
- the exact approved system instruction reaches the GenAI chat configuration;
- profile context and stored chat history are converted into real GenAI SDK
  content types;
- the incoming user message is saved before generation and the model response
  is saved afterward;
- whitespace-only `session_id`, `user_id`, and `message` values each return
  HTTP 422;
- missing fields, malformed JSON, and non-JSON bodies return HTTP 422;
- `MemoryEngineError` and Gemini failures return sanitized HTTP 500 responses;
- startup initializes both clients and shutdown closes both clients.

Tests will assert observable HTTP responses and recorded fake-service events,
not merely the existence of mocks.

## Firestore Test Architecture

`tests/test_database.py` will inject a fake asynchronous Firestore client into
`MemoryEngine`. Firestore is the external boundary; no Application Default
Credentials, emulator, project, or network connection will be required.

The database suite will verify:

- `save_message` creates an auto-ID message reference and commits the parent
  session update plus message write in one async batch;
- both persisted timestamp fields use `firestore.SERVER_TIMESTAMP`;
- `get_chat_history` orders by `timestamp` ascending and preserves query order;
- `update_user_profile` calls `set(updates, merge=True)`;
- `get_user_profile` returns stored data or `{}` for a missing document;
- invalid identifiers, roles, text, and profile updates raise `ValueError`
  before any Firestore access;
- Firestore `GoogleAPIError` instances become `MemoryEngineError` with the
  original error retained as `__cause__`;
- error logs omit message text and profile content;
- `close()` delegates to the injected client.

## TDD Strategy

The exact prompt assertion is the production behavior change for this pass. It
will be written first and observed failing against the current short prompt,
then `main.py` will receive the minimal prompt replacement required for GREEN.

The FastAPI and Firestore behavior already exists. Tests covering that behavior
are characterization and regression coverage, not newly created RED-first
behavior. Their value will be checked through precise boundary assertions and
targeted mutation reasoning rather than falsely labeling first-run passes as
TDD.

## Verification

Focused development commands will run individual test files and named tests.
Final automated verification will run:

```bash
venv/bin/pytest -v
```

Additional checks will import both production modules, verify PEP 8 line
length, run `git diff --check`, and confirm no test contacts Firestore or
Gemini.

## Risks and Limitations

- Fakes can drift from third-party SDK behavior; tests will use real GenAI
  `types.Content`, `types.Part`, and `GenerateContentConfig` objects where those
  types cross the application boundary.
- Exact dependency pins improve reproducibility but require deliberate upgrade
  passes for security and compatibility updates.
- Offline tests do not prove Firestore IAM, database provisioning, quota,
  network availability, or live Gemini model availability.
- The new system prompt is intentionally long and repetitive because the user
  required exact text; this pass will not rewrite or optimize it.

## Acceptance Criteria

- `SYSTEM_INSTRUCTION` exactly equals the approved text.
- Runtime and development dependencies install from their separate manifests.
- Pytest discovers persistent tests only from `tests/`.
- Endpoint tests exercise real FastAPI request/response handling with offline
  service fakes.
- Database tests exercise all four public async operations, validation, error
  translation, and client cleanup offline.
- The complete pytest suite passes on macOS with Python 3.14.
- No API key, ADC credential, Firestore write, Gemini call, commit, or push is
  produced by the test run.
