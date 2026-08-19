# System Prompt and Persistent Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Agent_Col's system instruction with the exact approved text
and add a permanent, fully offline pytest suite for the FastAPI and Firestore
boundaries.

**Architecture:** Production and development dependencies are separated into
two pinned requirements files. FastAPI tests use `httpx.AsyncClient` with
in-memory service fakes at the Firestore and Gemini boundaries; database tests
inject mock async Firestore references directly into `MemoryEngine`.

**Tech Stack:** Python 3.14, FastAPI 0.141.1, Google GenAI 2.18.1,
google-cloud-firestore 2.28.1, pytest 9.1.1, pytest-asyncio 1.4.0,
httpx 0.28.1

**Spec:**
`docs/superpowers/specs/2026-08-19-system-prompt-and-persistent-tests-design.md`

## Global Constraints

- Preserve `/`, `/api/chat`, `ChatRequest`, and `ChatResponse` contracts.
- `SYSTEM_INSTRUCTION` must evaluate to the exact approved text.
- Keep every test offline; no ADC, Firestore emulator, Gemini request, or
  Google Cloud resource is allowed.
- Use real FastAPI routing and real Google GenAI content/config types in
  `tests/test_main.py`.
- Use injected Firestore mocks in `tests/test_database.py`.
- Use explicit `@pytest.mark.asyncio` markers with strict asyncio mode.
- Keep Python source at or below 88 characters per line.
- Do not modify `.env`, Firestore data, gcloud configuration, or IAM.
- Do not commit or push this pass until the user completes manual verification
  and explicitly authorizes a checkpoint.

---

### Task 1: Dependency manifests, pytest configuration, and prompt TDD

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/test_main.py`
- Modify: `main.py:15-18`

**Interfaces:**
- Consumes: existing `main.SYSTEM_INSTRUCTION`
- Produces: reproducible dependency installation, pytest discovery, and the
  exact detailed system instruction

- [ ] **Step 1: Create the pinned runtime manifest**

Create `requirements.txt` with exactly:

```text
fastapi==0.141.1
google-api-core==2.34.0
google-cloud-firestore==2.28.1
google-genai==2.18.1
pydantic==2.13.4
python-dotenv==1.2.3
uvicorn==0.52.4
```

- [ ] **Step 2: Create the pinned development manifest**

Create `requirements-dev.txt` with exactly:

```text
-r requirements.txt
httpx==0.28.1
pytest==9.1.1
pytest-asyncio==1.4.0
```

- [ ] **Step 3: Configure strict pytest discovery**

Create `pytest.ini` with exactly:

```ini
[pytest]
addopts = -ra
asyncio_mode = strict
filterwarnings =
    ignore:'_UnionGenericAlias' is deprecated and slated for removal in Python 3\.17:DeprecationWarning:google\.genai\.types
python_files = test_*.py
pythonpath = .
testpaths = tests
```

- [ ] **Step 4: Install the approved development dependencies**

Run:

```bash
venv/bin/pip install -r requirements-dev.txt
```

Expected: installation succeeds without dependency conflicts, and the existing
runtime packages remain on their pinned versions.

- [ ] **Step 5: Write the failing exact-prompt test**

Create `tests/test_main.py` with:

```python
import main


EXPECTED_SYSTEM_INSTRUCTION = (
    "You are a collaborative partner for users, you learn about the users "
    "over time, provide feedback and ask questions to push development and "
    "goals, you are a helpful assistant that helps users with complex tasks "
    "by giving step by step instructions for complex tasks and offer "
    "insightful and meaningful feedback when users get stuck to help them "
    "progress."
)


def test_system_instruction_uses_detailed_prompt() -> None:
    assert main.SYSTEM_INSTRUCTION == EXPECTED_SYSTEM_INSTRUCTION
```

- [ ] **Step 6: Run the prompt test and verify RED**

Run:

```bash
venv/bin/pytest tests/test_main.py::test_system_instruction_uses_detailed_prompt -v
```

Expected: one assertion failure showing the current short
`"You are Agent_Col..."` value differs from the approved detailed prompt.

- [ ] **Step 7: Replace only the production system instruction**

Replace `SYSTEM_INSTRUCTION` in `main.py` with:

```python
SYSTEM_INSTRUCTION = (
    "You are a collaborative partner for users, you learn about the users "
    "over time, provide feedback and ask questions to push development and "
    "goals, you are a helpful assistant that helps users with complex tasks "
    "by giving step by step instructions for complex tasks and offer "
    "insightful and meaningful feedback when users get stuck to help them "
    "progress."
)
```

- [ ] **Step 8: Run the prompt test and verify GREEN**

Run the same named pytest command. Expected: `1 passed`.

- [ ] **Step 9: Verify installed versions**

Run:

```bash
venv/bin/python -B -c \
  'from importlib.metadata import version; print(version("pytest")); print(version("pytest-asyncio")); print(version("httpx"))'
```

Expected output:

```text
9.1.1
1.4.0
0.28.1
```

- [ ] **Step 10: Inspect the scoped diff without committing**

Run:

```bash
git diff -- main.py requirements.txt requirements-dev.txt pytest.ini tests/test_main.py
git diff --check
```

Expected: only the approved prompt, dependency, configuration, and initial test
changes appear; whitespace validation passes.

---

### Task 2: Permanent FastAPI endpoint and lifecycle coverage

**Files:**
- Modify: `tests/test_main.py`
- Verify: `main.py`

**Interfaces:**
- Consumes: `main.app`, `main.MemoryEngine`, `main.genai.Client`,
  `main.MemoryEngineError`, and Google GenAI `types`
- Produces: offline HTTP-level regression coverage for startup, health,
  validation, chat orchestration, and failure responses

- [ ] **Step 1: Add complete external-service fakes**

Retain the prompt constant and test from Task 1. Replace the initial import
section with the imports below, then place the fake types after the prompt
test:

```python
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from google.genai import types

import main


@dataclass
class FakeMemoryEngine:
    events: list[tuple[Any, ...]]
    profile: dict[str, object] = field(
        default_factory=lambda: {"tone": "direct"}
    )
    history: list[dict[str, object]] = field(
        default_factory=lambda: [
            {"role": "user", "text": "Earlier question"},
            {"role": "model", "text": "Earlier answer"},
        ]
    )
    fail_on: str | None = None
    closed: bool = False

    async def get_user_profile(self, user_id: str) -> dict[str, object]:
        if self.fail_on == "profile":
            raise main.MemoryEngineError("profile read failed")
        self.events.append(("profile", user_id))
        return self.profile

    async def get_chat_history(
        self, session_id: str
    ) -> list[dict[str, object]]:
        if self.fail_on == "history":
            raise main.MemoryEngineError("history read failed")
        self.events.append(("history", session_id))
        return self.history

    async def save_message(
        self, session_id: str, role: str, text: str
    ) -> None:
        if self.fail_on == f"save_{role}":
            raise main.MemoryEngineError(f"{role} save failed")
        self.events.append(("save", session_id, role, text))

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeChat:
    events: list[tuple[Any, ...]]
    response_text: str | None = "Generated answer"
    error: Exception | None = None
    message: list[types.Part] | None = None

    async def send_message(
        self, message: list[types.Part]
    ) -> SimpleNamespace:
        self.message = message
        self.events.append(("gemini",))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.response_text)


@dataclass
class FakeChats:
    chat: FakeChat
    create_arguments: dict[str, object] = field(default_factory=dict)

    def create(self, **kwargs: object) -> FakeChat:
        self.create_arguments = kwargs
        return self.chat


@dataclass
class FakeAsyncGenAI:
    chats: FakeChats
    closed: bool = False

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class FakeGenAIClient:
    aio: FakeAsyncGenAI
    closed: bool = False

    def close(self) -> None:
        self.closed = True


@dataclass
class ServiceState:
    events: list[tuple[Any, ...]]
    database: FakeMemoryEngine
    chat: FakeChat
    chats: FakeChats
    genai_client: FakeGenAIClient
```

- [ ] **Step 2: Add isolated pytest fixtures**

Add:

```python
@pytest.fixture
def service_state(monkeypatch: pytest.MonkeyPatch) -> ServiceState:
    events: list[tuple[Any, ...]] = []
    database = FakeMemoryEngine(events)
    chat = FakeChat(events)
    chats = FakeChats(chat)
    genai_client = FakeGenAIClient(FakeAsyncGenAI(chats))
    state = ServiceState(events, database, chat, chats, genai_client)

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(main, "MemoryEngine", lambda: database)
    monkeypatch.setattr(main.genai, "Client", lambda: genai_client)
    return state


@pytest_asyncio.fixture
async def client(service_state: ServiceState):
    async with main.lifespan(main.app):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as test_client:
            yield test_client
```

The `client` fixture intentionally has no return annotation that depends on
pytest's generator fixture internals. Ruff is not part of this pass.

- [ ] **Step 3: Add health and valid-chat behavior tests**

Add:

```python
@pytest.mark.asyncio
async def test_health_check(client: httpx.AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "online"}


@pytest.mark.asyncio
async def test_chat_uses_context_and_persists_both_messages(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"response": "Generated answer"}
    assert set(service_state.events[:2]) == {
        ("profile", "user-1"),
        ("history", "session-1"),
    }
    assert service_state.events[2:] == [
        ("save", "session-1", "user", "New question"),
        ("gemini",),
        ("save", "session-1", "model", "Generated answer"),
    ]

    arguments = service_state.chats.create_arguments
    assert arguments["model"] == "gemini-3.6-flash"
    assert arguments["config"].system_instruction == (
        EXPECTED_SYSTEM_INSTRUCTION
    )

    history = arguments["history"]
    assert all(isinstance(item, types.Content) for item in history)
    assert [item.role for item in history] == ["user", "model"]
    assert [item.parts[0].text for item in history] == [
        "Earlier question",
        "Earlier answer",
    ]
    assert service_state.chat.message is not None
    assert '"tone": "direct"' in service_state.chat.message[0].text
    assert service_state.chat.message[-1].text == "New question"
```

- [ ] **Step 4: Add request-validation tests**

Add:

```python
@pytest.mark.parametrize("field", ("session_id", "user_id", "message"))
@pytest.mark.asyncio
async def test_chat_rejects_whitespace_only_fields(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    field: str,
) -> None:
    payload = {
        "session_id": "session-1",
        "user_id": "user-1",
        "message": "hello",
    }
    payload[field] = " \t "

    response = await client.post("/api/chat", json=payload)

    assert response.status_code == 422
    assert service_state.events == []


@pytest.mark.parametrize(
    "request_arguments",
    (
        {"json": {"session_id": "session-1", "message": "hello"}},
        {
            "content": "{",
            "headers": {"content-type": "application/json"},
        },
        {
            "content": "not-json",
            "headers": {"content-type": "text/plain"},
        },
    ),
)
@pytest.mark.asyncio
async def test_chat_rejects_invalid_json_payloads(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    request_arguments: dict[str, object],
) -> None:
    response = await client.post("/api/chat", **request_arguments)

    assert response.status_code == 422
    assert service_state.events == []
```

- [ ] **Step 5: Add sanitized error-response tests**

Add:

```python
@pytest.mark.parametrize(
    "failure_point",
    ("profile", "history", "save_user", "save_model"),
)
@pytest.mark.asyncio
async def test_chat_translates_database_failures(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    failure_point: str,
) -> None:
    service_state.database.fail_on = failure_point

    response = await client.post(
        "/api/chat",
        json={
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "private message",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}


@pytest.mark.asyncio
async def test_chat_translates_gemini_failures_without_logging_payload(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_message = "private prompt text"
    service_state.chat.error = RuntimeError(
        f"provider echoed {private_message}"
    )

    response = await client.post(
        "/api/chat",
        json={
            "session_id": "private-session",
            "user_id": "private-user",
            "message": private_message,
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Gemini API request failed."}
    assert private_message not in caplog.text
    assert "private-session" not in caplog.text
    assert "private-user" not in caplog.text
    assert not any(
        event[0] == "save" and event[2] == "model"
        for event in service_state.events
    )
```

- [ ] **Step 6: Add lifecycle cleanup coverage**

Add:

```python
@pytest.mark.asyncio
async def test_lifespan_closes_both_clients(
    service_state: ServiceState,
) -> None:
    assert not service_state.database.closed
    assert not service_state.genai_client.aio.closed
    assert not service_state.genai_client.closed

    async with main.lifespan(main.app):
        assert not service_state.database.closed

    assert service_state.database.closed
    assert service_state.genai_client.aio.closed
    assert service_state.genai_client.closed
```

- [ ] **Step 7: Run the complete FastAPI test file**

Run:

```bash
venv/bin/pytest tests/test_main.py -v
```

Expected: all endpoint, validation, error, prompt, and lifecycle cases pass.
These are characterization tests except for the RED/GREEN prompt test recorded
in Task 1.

- [ ] **Step 8: Inspect the scoped diff without committing**

Run:

```bash
git diff -- tests/test_main.py main.py
git diff --check
```

Expected: no production behavior changed beyond the approved prompt.

---

### Task 3: Permanent offline Firestore coverage

**Files:**
- Create: `tests/test_database.py`
- Verify: `database.py`

**Interfaces:**
- Consumes: `MemoryEngine`, `MemoryEngineError`, Firestore server timestamp and
  query direction sentinels
- Produces: offline regression coverage for all public database methods,
  validation, error translation, safe logs, and cleanup

- [ ] **Step 1: Create Firestore test helpers and atomic-save coverage**

Create `tests/test_database.py` with:

```python
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

from database import MemoryEngine, MemoryEngineError


@pytest.mark.asyncio
async def test_save_message_commits_parent_and_message_atomically() -> None:
    client = MagicMock()
    sessions = MagicMock()
    session = MagicMock()
    messages = MagicMock()
    message = MagicMock()
    batch = MagicMock()
    batch.commit = AsyncMock(return_value=[])

    client.collection.return_value = sessions
    sessions.document.return_value = session
    session.collection.return_value = messages
    messages.document.return_value = message
    client.batch.return_value = batch

    engine = MemoryEngine(client=client)
    await engine.save_message("session-1", "user", "hello")

    client.collection.assert_called_once_with("sessions")
    sessions.document.assert_called_once_with("session-1")
    session.collection.assert_called_once_with("messages")
    messages.document.assert_called_once_with()
    assert batch.set.call_args_list == [
        call(
            session,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            message,
            {
                "role": "user",
                "text": "hello",
                "timestamp": firestore.SERVER_TIMESTAMP,
            },
        ),
    ]
    batch.commit.assert_awaited_once_with()
```

- [ ] **Step 2: Add ordered-history coverage**

Append:

```python
async def snapshot_stream():
    yield SimpleNamespace(
        to_dict=lambda: {"role": "user", "text": "first"}
    )
    yield SimpleNamespace(
        to_dict=lambda: {"role": "model", "text": "second"}
    )


@pytest.mark.asyncio
async def test_get_chat_history_orders_by_timestamp() -> None:
    client = MagicMock()
    sessions = MagicMock()
    session = MagicMock()
    messages = MagicMock()
    query = MagicMock()

    client.collection.return_value = sessions
    sessions.document.return_value = session
    session.collection.return_value = messages
    messages.order_by.return_value = query
    query.stream.return_value = snapshot_stream()

    engine = MemoryEngine(client=client)
    history = await engine.get_chat_history("session-1")

    messages.order_by.assert_called_once_with(
        "timestamp",
        direction=firestore.Query.ASCENDING,
    )
    assert history == [
        {"role": "user", "text": "first"},
        {"role": "model", "text": "second"},
    ]
```

- [ ] **Step 3: Add profile merge and read coverage**

Append:

```python
@pytest.mark.asyncio
async def test_update_user_profile_merges_fields() -> None:
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    user.set = AsyncMock()
    client.collection.return_value = users
    users.document.return_value = user

    engine = MemoryEngine(client=client)
    await engine.update_user_profile("user-1", {"tone": "direct"})

    client.collection.assert_called_once_with("users")
    users.document.assert_called_once_with("user-1")
    user.set.assert_awaited_once_with({"tone": "direct"}, merge=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exists", "stored", "expected"),
    (
        (True, {"tone": "direct"}, {"tone": "direct"}),
        (False, None, {}),
    ),
)
async def test_get_user_profile_handles_existing_and_missing_documents(
    exists: bool,
    stored: dict[str, object] | None,
    expected: dict[str, object],
) -> None:
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    snapshot = SimpleNamespace(
        exists=exists,
        to_dict=lambda: stored,
    )
    user.get = AsyncMock(return_value=snapshot)
    client.collection.return_value = users
    users.document.return_value = user

    engine = MemoryEngine(client=client)
    assert await engine.get_user_profile("user-1") == expected
```

- [ ] **Step 4: Add strict validation coverage**

Append:

```python
@pytest.mark.asyncio
async def test_invalid_inputs_fail_before_firestore_access() -> None:
    client = MagicMock()
    engine = MemoryEngine(client=client)
    invalid_calls = (
        (engine.save_message, ("", "user", "text")),
        (engine.save_message, ("session", " ", "text")),
        (engine.save_message, ("session", "user", " ")),
        (engine.get_chat_history, (" ",)),
        (engine.update_user_profile, ("", {"tone": "direct"})),
        (engine.update_user_profile, ("user", {})),
        (engine.get_user_profile, ("",)),
    )

    for operation, arguments in invalid_calls:
        with pytest.raises(ValueError):
            await operation(*arguments)

    client.collection.assert_not_called()
```

- [ ] **Step 5: Add error translation and safe-log coverage**

Append:

```python
@pytest.mark.asyncio
async def test_firestore_errors_preserve_cause_and_hide_profile_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_value = "private profile content"
    firestore_error = ServiceUnavailable("backend unavailable")
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    user.set = AsyncMock(side_effect=firestore_error)
    client.collection.return_value = users
    users.document.return_value = user
    engine = MemoryEngine(client=client)
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await engine.update_user_profile(
            "private-user-id",
            {"note": private_value},
        )

    assert caught.value.__cause__ is firestore_error
    assert private_value not in caplog.text
    assert "private-user-id" not in caplog.text
```

- [ ] **Step 6: Add client-close coverage**

Append:

```python
def test_close_delegates_to_client() -> None:
    client = MagicMock()

    MemoryEngine(client=client).close()

    client.close.assert_called_once_with()
```

- [ ] **Step 7: Run the complete database test file**

Run:

```bash
venv/bin/pytest tests/test_database.py -v
```

Expected: every async database boundary test passes without credentials,
emulator access, network calls, or warnings.

- [ ] **Step 8: Inspect the scoped diff without committing**

Run:

```bash
git diff -- tests/test_database.py database.py
git diff --check
```

Expected: `database.py` remains unchanged and only persistent offline tests are
added.

---

### Task 4: Complete suite and handoff verification

**Files:**
- Verify: `main.py`
- Verify: `database.py`
- Verify: `requirements.txt`
- Verify: `requirements-dev.txt`
- Verify: `pytest.ini`
- Verify: `tests/test_main.py`
- Verify: `tests/test_database.py`

**Interfaces:**
- Consumes: all artifacts from Tasks 1-3
- Produces: evidence-backed implementation report pending manual acceptance

- [ ] **Step 1: Run the complete persistent suite**

Run:

```bash
venv/bin/pytest -v
```

Expected: all collected tests pass, no test is skipped, and output contains no
unexpected warnings or errors.

- [ ] **Step 2: Verify imports and exact prompt value**

Run:

```bash
venv/bin/python -B - <<'PY'
import database
import main

expected = (
    "You are a collaborative partner for users, you learn about the users "
    "over time, provide feedback and ask questions to push development and "
    "goals, you are a helpful assistant that helps users with complex tasks "
    "by giving step by step instructions for complex tasks and offer "
    "insightful and meaningful feedback when users get stuck to help them "
    "progress."
)
assert main.SYSTEM_INSTRUCTION == expected
print("production_imports=pass")
print("system_instruction=pass")
PY
```

- [ ] **Step 3: Verify PEP 8 line length**

Run:

```bash
awk 'length($0) > 88 { print FNR ":" length($0) ":" FILENAME; failed=1 } END { exit failed }' main.py database.py tests/test_main.py tests/test_database.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Verify repository scope and ignored secrets**

Run:

```bash
git status --short
git diff --check
git check-ignore -v .env venv __pycache__
```

Expected: only the approved spec, plan, dependency manifests, pytest config,
tests, and `main.py` prompt are changed or untracked. `.env`, `venv`, and
`__pycache__` remain ignored.

- [ ] **Step 5: Produce the implementation-pass report**

Report:

- status as **implemented, pending manual verification**;
- exact files changed;
- prompt RED/GREEN evidence;
- characterization-test results without calling them new TDD;
- complete pytest count and command;
- dependency installation result;
- offline boundary and remaining live-service limitations;
- manual command `venv/bin/pytest -v` for user acceptance;
- no commit or push performed.

- [ ] **Step 6: Stop for manual acceptance**

Do not commit, push, or begin another pass. Wait for the user to run the suite
and explicitly approve the checkpoint.
