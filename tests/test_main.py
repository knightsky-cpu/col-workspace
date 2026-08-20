import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio

import main
from schemas import SynthesisBlueprint
from supervisor_runtime import (
    SupervisorRuntimeError,
    SupervisorTimeoutError,
    SupervisorTurnContext,
    SupervisorTurnResult,
)
from synthesis import SynthesisEngineError, SynthesisTimeoutError


VALID_BLUEPRINT_PAYLOAD = {
    "synthesized_conceptual_model": {
        "project_name": "Study Partner",
        "core_value_proposition": "Turns rubrics into executable plans.",
        "in_scope": ["Planning"],
        "out_of_scope": ["Automatic deployment"],
        "assumptions": ["The user reviews each milestone"],
    },
    "personalization_trace": {
        "adaptations": [
            {
                "profile_key": "experience_level",
                "architecture_change": "Adds smaller implementation steps.",
                "reason": "Supports an early-career developer.",
            }
        ]
    },
    "architectural_decisions_and_feedback": [
        {
            "component_name": "API",
            "proposed_solution": "FastAPI",
            "rationale": "Matches the existing asynchronous backend.",
            "alternatives": [
                {
                    "option_name": "Flask",
                    "tradeoff": "Simpler but synchronous by default.",
                    "reason_not_selected": (
                        "Would diverge from the backend."
                    ),
                }
            ],
        }
    ],
    "socratic_clarifying_questions": [
        {
            "question_text": "Which client should be supported first?",
            "why_this_matters": "It determines the first API contract.",
            "suggested_options": [
                {
                    "label": "Web",
                    "impact": "Reuses the existing FastAPI host.",
                },
                {
                    "label": "CLI",
                    "impact": "Optimizes for terminal workflows.",
                },
            ],
        }
    ],
    "step_by_step_execution_roadmap": [
        {
            "phase_name": "Phase 1: Contract",
            "objective": "Define the public request and response.",
            "expected_deliverable": "A tested Pydantic contract.",
            "micro_tasks": [
                {
                    "task_description": "Write the request model.",
                    "complexity_level": "Low",
                    "verification_steps": ["Run the schema tests."],
                }
            ],
        }
    ],
    "diagnostic_warnings": [],
}


@dataclass
class FakeMemoryEngine:
    events: list[tuple[Any, ...]]
    profile: dict[str, object] = field(
        default_factory=lambda: {"experience_level": "early-career"}
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
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        if self.fail_on == "history":
            raise main.MemoryEngineError("history read failed")
        self.events.append(("history", session_id, limit))
        return self.history

    async def save_message(
        self, session_id: str, role: str, text: str
    ) -> None:
        if self.fail_on == f"save_{role}":
            raise main.MemoryEngineError(f"{role} save failed")
        self.events.append(("save", session_id, role, text))

    async def save_blueprint(
        self,
        project_id: str,
        session_id: str,
        user_id: str,
        model_name: str,
        blueprint: dict[str, object],
    ) -> str:
        if self.fail_on == "save_blueprint":
            raise main.MemoryEngineError("blueprint save failed")
        self.events.append(
            (
                "save_blueprint",
                project_id,
                session_id,
                user_id,
                model_name,
                blueprint,
            )
        )
        return "blueprint-1"

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeAsyncGenAI:
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
class FakeSynthesis:
    events: list[tuple[Any, ...]]
    blueprint: SynthesisBlueprint
    error: Exception | None = None
    call_arguments: tuple[
        object,
        dict[str, object],
        list[dict[str, object]],
        str,
    ] | None = None

    async def __call__(
        self,
        client: object,
        profile: dict[str, object],
        history: list[dict[str, object]],
        source_text: str,
    ) -> SynthesisBlueprint:
        self.call_arguments = (
            client,
            profile,
            history,
            source_text,
        )
        self.events.append(("synthesize",))
        if self.error is not None:
            raise self.error
        return self.blueprint


@dataclass
class FakeSupervisorRuntime:
    events: list[tuple[Any, ...]]
    response_text: str = "Generated answer"
    error: Exception | None = None
    calls: list[SupervisorTurnContext] = field(default_factory=list)

    async def run_turn(
        self,
        context: SupervisorTurnContext,
    ) -> SupervisorTurnResult:
        self.calls.append(context)
        self.events.append(("supervisor",))
        if self.error is not None:
            raise self.error
        return SupervisorTurnResult(response=self.response_text)


@dataclass
class ServiceState:
    events: list[tuple[Any, ...]]
    database: FakeMemoryEngine
    genai_client: FakeGenAIClient
    synthesis: FakeSynthesis
    supervisor: FakeSupervisorRuntime


@pytest.fixture
def service_state(monkeypatch: pytest.MonkeyPatch) -> ServiceState:
    events: list[tuple[Any, ...]] = []
    database = FakeMemoryEngine(events)
    genai_client = FakeGenAIClient(FakeAsyncGenAI())
    blueprint = SynthesisBlueprint.model_validate(VALID_BLUEPRINT_PAYLOAD)
    synthesis = FakeSynthesis(events, blueprint)
    supervisor = FakeSupervisorRuntime(events)
    state = ServiceState(
        events,
        database,
        genai_client,
        synthesis,
        supervisor,
    )

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(main, "MemoryEngine", lambda: database)
    monkeypatch.setattr(main.genai, "Client", lambda: genai_client)
    monkeypatch.setattr(
        main,
        "generate_blueprint",
        synthesis,
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "create_supervisor_app",
        lambda: object(),
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "SupervisorRuntime",
        SimpleNamespace(from_app=lambda app: supervisor),
        raising=False,
    )
    return state


@pytest_asyncio.fixture
async def client(service_state: ServiceState):
    async with main.lifespan(main.app):
        transport = httpx.ASGITransport(
            app=main.app,
            raise_app_exceptions=False,
        )
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
async def test_lifespan_exposes_supervisor_runtime(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert main.app.state.supervisor is service_state.supervisor


@pytest.mark.asyncio
async def test_lifespan_closes_resources_if_supervisor_construction_fails(
    service_state: ServiceState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_error = RuntimeError("supervisor construction failed")

    def fail_construction(app: object) -> object:
        raise construction_error

    monkeypatch.setattr(
        main,
        "SupervisorRuntime",
        SimpleNamespace(from_app=fail_construction),
    )

    with pytest.raises(RuntimeError) as caught:
        async with main.lifespan(main.app):
            pass

    assert caught.value is construction_error
    assert service_state.database.closed
    assert service_state.genai_client.aio.closed
    assert service_state.genai_client.closed


@pytest.mark.asyncio
async def test_synthesize_returns_and_persists_blueprint(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "Build a study partner.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "blueprint_id": "blueprint-1",
        "blueprint": VALID_BLUEPRINT_PAYLOAD,
    }
    assert set(service_state.events[:2]) == {
        ("profile", "user-1"),
        ("history", "session-1", 20),
    }
    assert service_state.events[2:] == [
        ("synthesize",),
        (
            "save_blueprint",
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            VALID_BLUEPRINT_PAYLOAD,
        ),
    ]
    assert service_state.synthesis.call_arguments == (
        service_state.genai_client,
        {"experience_level": "early-career"},
        [
            {"role": "user", "text": "Earlier question"},
            {"role": "model", "text": "Earlier answer"},
        ],
        "Build a study partner.",
    )


@pytest.mark.asyncio
async def test_synthesize_starts_context_reads_concurrently(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    profile_started = asyncio.Event()
    history_started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_profile(user_id: str) -> dict[str, object]:
        assert user_id == "user-1"
        profile_started.set()
        await release.wait()
        return {}

    async def blocked_history(
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-1"
        assert limit == 20
        history_started.set()
        await release.wait()
        return []

    service_state.database.get_user_profile = blocked_profile
    service_state.database.get_chat_history = blocked_history
    request_task = asyncio.create_task(
        client.post(
            "/api/synthesize",
            json={
                "project_id": "project-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "source_text": "Build a study partner.",
            },
        )
    )

    await asyncio.wait_for(profile_started.wait(), timeout=1)
    both_reads_started = True
    try:
        await asyncio.wait_for(history_started.wait(), timeout=1)
    except TimeoutError:
        both_reads_started = False
    finally:
        assert ("synthesize",) not in service_state.events
        release.set()
        response = await request_task

    assert both_reads_started
    assert response.status_code == 200


@pytest.mark.parametrize("failure_point", ("profile", "history"))
@pytest.mark.asyncio
async def test_synthesize_translates_context_database_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    failure_point: str,
) -> None:
    service_state.database.fail_on = failure_point

    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "private brainstorm",
        },
    )

    assert response.status_code == 500
    assert response.text == '{"detail":"Database operation failed."}'
    assert ("synthesize",) not in service_state.events
    assert not any(
        event[0] == "save_blueprint"
        for event in service_state.events
    )


@pytest.mark.asyncio
async def test_synthesize_translates_generation_failure_without_writing(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.synthesis.error = SynthesisEngineError(
        "generation failed"
    )

    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "private brainstorm",
        },
    )

    assert response.status_code == 502
    assert response.text == '{"detail":"Blueprint generation failed."}'
    assert not any(
        event[0] == "save_blueprint"
        for event in service_state.events
    )


@pytest.mark.asyncio
async def test_synthesize_translates_generation_timeout_without_writing(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.synthesis.error = SynthesisTimeoutError(
        "generation timed out"
    )

    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "private brainstorm",
        },
    )

    assert response.status_code == 504
    assert response.text == '{"detail":"Blueprint generation timed out."}'
    assert not any(
        event[0] == "save_blueprint"
        for event in service_state.events
    )


@pytest.mark.asyncio
async def test_synthesize_translates_blueprint_database_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_state.database.fail_on = "save_blueprint"

    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "private-project",
            "session_id": "private-session",
            "user_id": "private-user",
            "source_text": "private brainstorm",
        },
    )

    assert response.status_code == 500
    assert response.text == '{"detail":"Database operation failed."}'
    assert service_state.events[-1] == ("synthesize",)
    assert "private-project" not in caplog.text
    assert "private-session" not in caplog.text
    assert "private-user" not in caplog.text
    assert "private brainstorm" not in caplog.text
    assert "Turns rubrics into executable plans." not in caplog.text


@pytest.mark.parametrize(
    "payload",
    (
        {
            "project_id": " ",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "bad/id",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": " ",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": "bad/id",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": " ",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": " ",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x" * 10_001,
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x",
            "unexpected": True,
        },
    ),
)
@pytest.mark.asyncio
async def test_synthesize_rejects_invalid_request_before_service_access(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    payload: dict[str, object],
) -> None:
    response = await client.post("/api/synthesize", json=payload)

    assert response.status_code == 422
    assert service_state.events == []


@pytest.mark.parametrize(
    "request_arguments",
    (
        {
            "json": {
                "project_id": "project-1",
                "session_id": "session-1",
                "user_id": "user-1",
            }
        },
        {
            "content": "{",
            "headers": {"content-type": "application/json"},
        },
    ),
)
@pytest.mark.asyncio
async def test_synthesize_rejects_incomplete_or_malformed_json(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    request_arguments: dict[str, object],
) -> None:
    response = await client.post(
        "/api/synthesize",
        **request_arguments,
    )

    assert response.status_code == 422
    assert service_state.events == []


@pytest.mark.asyncio
async def test_chat_uses_context_and_persists_both_messages(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "response": "Generated answer",
        "actions": [],
        "artifacts": [],
        "citations": [],
    }
    assert set(service_state.events[:2]) == {
        ("profile", "user-1"),
        ("history", "session-1", 20),
    }
    assert service_state.events[2:] == [
        ("save", "session-1", "user", "New question"),
        ("supervisor",),
        ("save", "session-1", "model", "Generated answer"),
    ]

    assert len(service_state.supervisor.calls) == 1
    context = service_state.supervisor.calls[0]
    assert context.project_id == "project-1"
    assert context.session_id == "session-1"
    assert context.user_id == "user-1"
    assert context.message == "New question"
    assert len(context.model_input_context) == 1
    context_content = context.model_input_context[0]
    assert context_content.role == "user"
    context_text = context_content.parts[0].text
    assert "[USER_PROFILE_DATA]" in context_text
    assert '"experience_level": "early-career"' in context_text
    assert "[SESSION_HISTORY_DATA]" in context_text
    assert context_text.index("Earlier question") < context_text.index(
        "Earlier answer"
    )
    assert "New question" not in context_text


@pytest.mark.parametrize(
    "field",
    ("project_id", "session_id", "user_id", "message"),
)
@pytest.mark.asyncio
async def test_chat_rejects_whitespace_only_fields(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    field: str,
) -> None:
    payload = {
        "project_id": "project-1",
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
        {
            "json": {
                "project_id": "project-1",
                "session_id": "session-1",
                "message": "hello",
            }
        },
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
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "private message",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}


@pytest.mark.asyncio
async def test_chat_translates_supervisor_failure_without_model_write(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_message = "private prompt text"
    service_state.supervisor.error = SupervisorRuntimeError(
        f"provider echoed {private_message}"
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "private-project",
            "session_id": "private-session",
            "user_id": "private-user",
            "message": private_message,
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Agent_Col response failed."}
    assert private_message not in caplog.text
    assert "private-project" not in caplog.text
    assert "private-session" not in caplog.text
    assert "private-user" not in caplog.text
    assert (
        "save",
        "private-session",
        "user",
        private_message,
    ) in service_state.events
    assert not any(
        event[0] == "save" and event[2] == "model"
        for event in service_state.events
    )


@pytest.mark.asyncio
async def test_chat_translates_supervisor_timeout_without_model_write(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.supervisor.error = SupervisorTimeoutError(
        "turn timed out"
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Hello",
        },
    )

    assert response.status_code == 504
    assert response.json() == {"detail": "Agent_Col response timed out."}
    assert (
        "save",
        "session-1",
        "user",
        "Hello",
    ) in service_state.events
    assert not any(
        event[0] == "save" and event[2] == "model"
        for event in service_state.events
    )


@pytest.mark.asyncio
async def test_chat_starts_context_reads_concurrently(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    profile_started = asyncio.Event()
    history_started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_profile(user_id: str) -> dict[str, object]:
        assert user_id == "user-1"
        profile_started.set()
        await release.wait()
        return {}

    async def blocked_history(
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-1"
        assert limit == 20
        history_started.set()
        await release.wait()
        return []

    service_state.database.get_user_profile = blocked_profile
    service_state.database.get_chat_history = blocked_history
    request_task = asyncio.create_task(
        client.post(
            "/api/chat",
            json={
                "project_id": "project-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "message": "Hello",
            },
        )
    )

    await asyncio.wait_for(profile_started.wait(), timeout=1)
    both_reads_started = True
    try:
        await asyncio.wait_for(history_started.wait(), timeout=1)
    except TimeoutError:
        both_reads_started = False
    finally:
        assert ("supervisor",) not in service_state.events
        release.set()
        response = await request_task

    assert both_reads_started
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_rejects_invalid_stored_history_before_writes(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.history = [
        {"role": "tool", "text": "untrusted content"}
    ]

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Hello",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Chat history is invalid."}
    assert not any(event[0] == "save" for event in service_state.events)
    assert ("supervisor",) not in service_state.events


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
