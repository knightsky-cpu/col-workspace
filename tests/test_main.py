import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio

import main
from database import (
    MemoryEventCursorNotFoundError,
    MemorySignalConflictError,
    MemorySignalNotFoundError,
)
from schemas import (
    AgentActionReceipt,
    CollaborationProfile,
    MemoryEvent,
    MemoryProposal,
    SynthesisBlueprint,
)
from supervisor_runtime import (
    SupervisorRuntimeError,
    SupervisorTimeoutError,
    SupervisorTurnContext,
    SupervisorTurnResult,
)
from synthesis import SynthesisEngineError, SynthesisTimeoutError
from synthesis_service import (
    SynthesisCommand,
    SynthesisResult,
)
from trusted_memory_service import (
    DeleteMemorySignalCommand,
    InspectMemoryCommand,
    RevokeMemorySignalCommand,
    TrustedMemoryInspectionResult,
    TrustedMemoryMutationResult,
)


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
    "architectural_decisions": [
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

MEMORY_NOW = datetime(2026, 8, 20, 23, 0, tzinfo=UTC)


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
class FakeSynthesisApplicationService:
    events: list[tuple[Any, ...]]
    blueprint: SynthesisBlueprint
    error: Exception | None = None
    calls: list[SynthesisCommand] = field(default_factory=list)

    async def synthesize(
        self,
        command: SynthesisCommand,
    ) -> SynthesisResult:
        self.calls.append(command)
        self.events.append(("synthesis_service",))
        if self.error is not None:
            raise self.error
        return SynthesisResult(
            blueprint_id="blueprint-1",
            blueprint=self.blueprint,
        )


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
class FakeTrustedMemoryService:
    events: list[tuple[Any, ...]]
    result: TrustedMemoryInspectionResult
    error: Exception | None = None
    revoke_result: TrustedMemoryMutationResult | None = None
    delete_result: TrustedMemoryMutationResult | None = None
    calls: list[InspectMemoryCommand] = field(default_factory=list)
    revoke_calls: list[RevokeMemorySignalCommand] = field(
        default_factory=list
    )
    delete_calls: list[DeleteMemorySignalCommand] = field(
        default_factory=list
    )

    async def inspect_memory(
        self,
        command: InspectMemoryCommand,
    ) -> TrustedMemoryInspectionResult:
        self.calls.append(command)
        self.events.append(("memory_inspection",))
        if self.error is not None:
            raise self.error
        return self.result

    async def revoke_memory_signal(
        self,
        command: RevokeMemorySignalCommand,
    ) -> TrustedMemoryMutationResult:
        self.revoke_calls.append(command)
        self.events.append(("memory_revoke",))
        if self.error is not None:
            raise self.error
        if self.revoke_result is None:
            raise AssertionError("Missing fake revocation result.")
        return self.revoke_result

    async def delete_memory_signal(
        self,
        command: DeleteMemorySignalCommand,
    ) -> TrustedMemoryMutationResult:
        self.delete_calls.append(command)
        self.events.append(("memory_delete",))
        if self.error is not None:
            raise self.error
        if self.delete_result is None:
            raise AssertionError("Missing fake deletion result.")
        return self.delete_result


@dataclass
class ServiceState:
    events: list[tuple[Any, ...]]
    database: FakeMemoryEngine
    genai_client: FakeGenAIClient
    synthesis_service: FakeSynthesisApplicationService
    supervisor: FakeSupervisorRuntime
    memory_service: FakeTrustedMemoryService


@pytest.fixture
def service_state(monkeypatch: pytest.MonkeyPatch) -> ServiceState:
    events: list[tuple[Any, ...]] = []
    database = FakeMemoryEngine(events)
    genai_client = FakeGenAIClient(FakeAsyncGenAI())
    blueprint = SynthesisBlueprint.model_validate(VALID_BLUEPRINT_PAYLOAD)
    synthesis_service = FakeSynthesisApplicationService(events, blueprint)
    supervisor = FakeSupervisorRuntime(events)
    pending_proposal = MemoryProposal(
        proposal_id="example_usage--proposal-1",
        category="example_usage",
        proposed_value="always_practical",
        expected_signal_id=None,
        status="pending",
        source_session_id="source-session",
        source_message_id="source-message",
        created_at=MEMORY_NOW,
        expires_at=MEMORY_NOW + timedelta(hours=24),
    )
    approved_event = MemoryEvent(
        event_id="response_length--signal-1--approved",
        event_type="approved",
        signal_id="response_length--signal-1",
        category="response_length",
        value="concise",
        source_type="explicit_user_feedback",
        source_session_id="source-session",
        source_message_id="source-message",
        confirmation_channel="memory_api",
        confirmation_session_id=None,
        confirmation_message_id=None,
        related_signal_id=None,
        memory_revision=1,
        created_at=MEMORY_NOW,
    )
    memory_service = FakeTrustedMemoryService(
        events=events,
        result=TrustedMemoryInspectionResult(
            profile=CollaborationProfile(memory_revision=1),
            unresolved_proposals=(pending_proposal,),
            events=(approved_event,),
            next_event_id="response_length--signal-1--approved",
        ),
        revoke_result=TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="revoke_memory_signal",
                status="completed",
            ),
            profile=CollaborationProfile(memory_revision=2),
        ),
        delete_result=TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="delete_memory_signal",
                status="completed",
            ),
            profile=CollaborationProfile(memory_revision=3),
        ),
    )
    state = ServiceState(
        events,
        database,
        genai_client,
        synthesis_service,
        supervisor,
        memory_service,
    )

    def create_synthesis_service(**kwargs: object) -> object:
        assert kwargs == {
            "client": genai_client,
            "database": database,
        }
        return synthesis_service

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(main, "MemoryEngine", lambda: database)
    monkeypatch.setattr(main.genai, "Client", lambda: genai_client)
    monkeypatch.setattr(
        main,
        "SynthesisApplicationService",
        create_synthesis_service,
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
    monkeypatch.setattr(
        main,
        "TrustedMemoryService",
        lambda *, database: (
            memory_service
            if database is state.database
            else pytest.fail("Unexpected memory service database.")
        ),
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
async def test_memory_inspection_returns_typed_service_result(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/users/user-1/memory",
        params={
            "after_event_id": "response_length--cursor--approved",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "profile": {
            "memory_schema_version": "1.0",
            "memory_revision": 1,
            "identity_context": {},
            "active_preferences": {},
        },
        "unresolved_proposals": [
            {
                "proposal_id": "example_usage--proposal-1",
                "category": "example_usage",
                "proposed_value": "always_practical",
                "expected_signal_id": None,
                "policy_version": "1.0",
                "status": "pending",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "created_at": "2026-08-20T23:00:00Z",
                "expires_at": "2026-08-21T23:00:00Z",
            }
        ],
        "events": [
            {
                "event_id": "response_length--signal-1--approved",
                "event_type": "approved",
                "signal_id": "response_length--signal-1",
                "category": "response_length",
                "value": "concise",
                "policy_version": "1.0",
                "source_type": "explicit_user_feedback",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "confirmation_channel": "memory_api",
                "confirmation_session_id": None,
                "confirmation_message_id": None,
                "related_signal_id": None,
                "memory_revision": 1,
                "created_at": "2026-08-20T23:00:00Z",
            }
        ],
        "next_event_id": "response_length--signal-1--approved",
    }
    assert service_state.memory_service.calls == [
        InspectMemoryCommand(
            user_id="user-1",
            after_event_id="response_length--cursor--approved",
        )
    ]


@pytest.mark.asyncio
async def test_memory_inspection_maps_missing_user_cursor_to_not_found(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.memory_service.error = MemoryEventCursorNotFoundError(
        "private cursor detail"
    )

    response = await client.get(
        "/api/users/user-1/memory",
        params={"after_event_id": "response_length--missing--approved"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Memory event cursor was not found."
    }


@pytest.mark.asyncio
async def test_memory_inspection_translates_database_failure_safely(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_detail = "private-user private-memory-value"
    service_state.memory_service.error = main.MemoryEngineError(
        private_detail
    )

    response = await client.get("/api/users/private-user/memory")

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}
    assert "private-user" not in caplog.text
    assert "private-memory-value" not in caplog.text


@pytest.mark.parametrize(
    ("path", "params"),
    (
        (f"/api/users/{'u' * 129}/memory", None),
        (
            "/api/users/user-1/memory",
            {"after_event_id": "invalid/cursor"},
        ),
        (
            "/api/users/user-1/memory",
            {"after_event_id": "   "},
        ),
    ),
)
@pytest.mark.asyncio
async def test_memory_inspection_rejects_invalid_identifiers_before_service(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    path: str,
    params: dict[str, str] | None,
) -> None:
    response = await client.get(path, params=params)

    assert response.status_code == 422
    assert service_state.memory_service.calls == []


@pytest.mark.asyncio
async def test_revoke_memory_signal_returns_mutation_receipt(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/memory/signals/"
        "response_length--signal-1/revoke"
    )

    assert response.status_code == 200
    assert response.json() == {
        "action": {
            "action_name": "revoke_memory_signal",
            "status": "completed",
        },
        "profile": {
            "memory_schema_version": "1.0",
            "memory_revision": 2,
            "identity_context": {},
            "active_preferences": {},
        },
    }
    assert service_state.memory_service.revoke_calls == [
        RevokeMemorySignalCommand(
            user_id="user-1",
            signal_id="response_length--signal-1",
        )
    ]


@pytest.mark.asyncio
async def test_delete_memory_signal_returns_no_content(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.delete(
        "/api/users/user-1/memory/signals/response_length--signal-1"
    )

    assert response.status_code == 204
    assert response.content == b""
    assert service_state.memory_service.delete_calls == [
        DeleteMemorySignalCommand(
            user_id="user-1",
            signal_id="response_length--signal-1",
        )
    ]


@pytest.mark.asyncio
async def test_revoke_memory_signal_maps_unknown_signal_to_not_found(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.memory_service.error = MemorySignalNotFoundError(
        "private signal detail"
    )

    response = await client.post(
        "/api/users/user-1/memory/signals/"
        "response_length--missing/revoke"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Memory signal was not found."}


@pytest.mark.asyncio
async def test_revoke_memory_signal_maps_state_conflict(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.memory_service.error = MemorySignalConflictError(
        "private conflict detail"
    )

    response = await client.post(
        "/api/users/user-1/memory/signals/"
        "response_length--signal-1/revoke"
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Memory signal state conflicts with this request."
    }


@pytest.mark.parametrize(
    ("method", "path"),
    (
        (
            "POST",
            f"/api/users/{'u' * 129}/memory/signals/"
            "response_length--signal-1/revoke",
        ),
        (
            "POST",
            "/api/users/user-1/memory/signals/"
            f"response_length--{'s' * 129}/revoke",
        ),
        (
            "DELETE",
            f"/api/users/{'u' * 129}/memory/signals/"
            "response_length--signal-1",
        ),
        (
            "DELETE",
            "/api/users/user-1/memory/signals/"
            f"response_length--{'s' * 129}",
        ),
    ),
)
@pytest.mark.asyncio
async def test_memory_mutations_reject_invalid_identifiers_before_service(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    method: str,
    path: str,
) -> None:
    response = await client.request(method, path)

    assert response.status_code == 422
    assert service_state.memory_service.revoke_calls == []
    assert service_state.memory_service.delete_calls == []


@pytest.mark.parametrize(
    ("method", "path"),
    (
        (
            "POST",
            "/api/users/user-1/memory/signals/unknown--signal/revoke",
        ),
        (
            "DELETE",
            "/api/users/user-1/memory/signals/unknown--signal",
        ),
    ),
)
@pytest.mark.asyncio
async def test_memory_mutations_map_invalid_governed_category(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    method: str,
    path: str,
) -> None:
    service_state.memory_service.error = ValueError(
        "private invalid category detail"
    )

    response = await client.request(method, path)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Memory signal identifier is invalid."
    }


@pytest.mark.parametrize(
    ("method", "path"),
    (
        (
            "POST",
            "/api/users/private-user/memory/signals/"
            "response_length--private-signal/revoke",
        ),
        (
            "DELETE",
            "/api/users/private-user/memory/signals/"
            "response_length--private-signal",
        ),
    ),
)
@pytest.mark.asyncio
async def test_memory_mutations_translate_database_failure_safely(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
    method: str,
    path: str,
) -> None:
    service_state.memory_service.error = main.MemoryEngineError(
        "private-user private-signal private-memory-value"
    )

    response = await client.request(method, path)

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}
    assert "private-user" not in caplog.text
    assert "private-signal" not in caplog.text
    assert "private-memory-value" not in caplog.text


@pytest.mark.asyncio
async def test_lifespan_exposes_supervisor_runtime(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert main.app.state.supervisor is service_state.supervisor


@pytest.mark.asyncio
async def test_lifespan_exposes_synthesis_application_service(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert (
            main.app.state.synthesis_service
            is service_state.synthesis_service
        )


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
    assert service_state.events == [("synthesis_service",)]
    assert service_state.synthesis_service.calls == [
        SynthesisCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            source_text="Build a study partner.",
        )
    ]


@pytest.mark.asyncio
async def test_synthesize_translates_service_database_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.synthesis_service.error = main.MemoryEngineError(
        "database failed"
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

    assert response.status_code == 500
    assert response.text == '{"detail":"Database operation failed."}'
    assert service_state.events == [("synthesis_service",)]


@pytest.mark.asyncio
async def test_synthesize_translates_generation_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.synthesis_service.error = SynthesisEngineError(
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
    assert service_state.events == [("synthesis_service",)]


@pytest.mark.asyncio
async def test_synthesize_translates_generation_timeout(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.synthesis_service.error = SynthesisTimeoutError(
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
    assert service_state.events == [("synthesis_service",)]


@pytest.mark.asyncio
async def test_synthesize_does_not_log_private_database_failure_data(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_state.synthesis_service.error = main.MemoryEngineError(
        "private-project private-session private-user private brainstorm"
    )

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
    assert service_state.events == [("synthesis_service",)]
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
