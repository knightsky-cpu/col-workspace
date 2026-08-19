from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from google.genai import types

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
