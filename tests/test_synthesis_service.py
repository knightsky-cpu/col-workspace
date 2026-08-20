import asyncio
from dataclasses import dataclass, field

import pytest

from database import MemoryEngineError
from schemas import SynthesisBlueprint
from synthesis import SynthesisEngineError


@pytest.fixture
def blueprint() -> SynthesisBlueprint:
    return SynthesisBlueprint.model_validate(
        {
            "synthesized_conceptual_model": {
                "project_name": "Study Partner",
                "core_value_proposition": "Turns rubrics into plans.",
                "in_scope": ["Planning"],
            },
            "personalization_trace": {},
            "architectural_decisions": [
                {
                    "component_name": "API",
                    "proposed_solution": "FastAPI",
                    "rationale": "Supports asynchronous services.",
                    "alternatives": [
                        {
                            "option_name": "Flask",
                            "tradeoff": "Synchronous by default.",
                            "reason_not_selected": "Does not match the stack.",
                        }
                    ],
                }
            ],
            "socratic_clarifying_questions": [
                {
                    "question_text": "Which client comes first?",
                    "why_this_matters": "It defines the API contract.",
                    "suggested_options": [
                        {"label": "Web", "impact": "Browser access."},
                        {"label": "CLI", "impact": "Terminal access."},
                    ],
                }
            ],
            "step_by_step_execution_roadmap": [
                {
                    "phase_name": "Phase 1",
                    "objective": "Define the API.",
                    "expected_deliverable": "A tested endpoint.",
                    "micro_tasks": [
                        {
                            "task_description": "Write the endpoint.",
                            "complexity_level": "Low",
                            "verification_steps": ["Run the API test."],
                        }
                    ],
                }
            ],
        }
    )


@dataclass
class FakeDatabase:
    events: list[tuple[object, ...]]
    profile: dict[str, object] = field(
        default_factory=lambda: {"experience_level": "student"}
    )
    history: list[dict[str, object]] = field(
        default_factory=lambda: [
            {"role": "user", "text": "Earlier question"},
            {"role": "model", "text": "Earlier answer"},
        ]
    )
    fail_on: str | None = None
    error: MemoryEngineError | None = None

    async def get_user_profile(self, user_id: str) -> dict[str, object]:
        if self.fail_on == "profile":
            assert self.error is not None
            raise self.error
        self.events.append(("profile", user_id))
        return self.profile

    async def get_chat_history(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        if self.fail_on == "history":
            assert self.error is not None
            raise self.error
        self.events.append(("history", session_id, limit))
        return self.history

    async def save_blueprint(
        self,
        project_id: str,
        session_id: str,
        user_id: str,
        model_name: str,
        schema_version: str,
        blueprint: dict[str, object],
    ) -> str:
        if self.fail_on == "save":
            assert self.error is not None
            raise self.error
        self.events.append(
            (
                "save",
                project_id,
                session_id,
                user_id,
                model_name,
                schema_version,
                blueprint,
            )
        )
        return "blueprint-1"


@dataclass
class FakeBlueprintGenerator:
    events: list[tuple[object, ...]]
    blueprint: SynthesisBlueprint
    calls: list[tuple[object, ...]] = field(default_factory=list)

    async def __call__(
        self,
        client: object,
        profile: dict[str, object],
        history: list[dict[str, object]],
        source_text: str,
    ) -> SynthesisBlueprint:
        self.calls.append((client, profile, history, source_text))
        self.events.append(("generate",))
        return self.blueprint


@dataclass
class BlockingDatabase(FakeDatabase):
    profile_started: asyncio.Event = field(default_factory=asyncio.Event)
    history_started: asyncio.Event = field(default_factory=asyncio.Event)
    release_reads: asyncio.Event = field(default_factory=asyncio.Event)

    async def get_user_profile(self, user_id: str) -> dict[str, object]:
        self.events.append(("profile", user_id))
        self.profile_started.set()
        await self.release_reads.wait()
        return self.profile

    async def get_chat_history(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        self.events.append(("history", session_id, limit))
        self.history_started.set()
        await self.release_reads.wait()
        return self.history


@dataclass
class FailingBlueprintGenerator:
    error: SynthesisEngineError

    async def __call__(
        self,
        client: object,
        profile: dict[str, object],
        history: list[dict[str, object]],
        source_text: str,
    ) -> SynthesisBlueprint:
        raise self.error


@pytest.mark.asyncio
async def test_service_generates_and_persists_project_blueprint(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_service import (
        SynthesisApplicationService,
        SynthesisCommand,
    )

    events: list[tuple[object, ...]] = []
    client = object()
    database = FakeDatabase(events)
    generator = FakeBlueprintGenerator(events, blueprint)
    service = SynthesisApplicationService(
        client=client,
        database=database,
        blueprint_generator=generator,
    )

    result = await service.synthesize(
        SynthesisCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            source_text="Build a study partner.",
        )
    )

    assert result.blueprint_id == "blueprint-1"
    assert result.blueprint is blueprint
    assert set(events[:2]) == {
        ("profile", "user-1"),
        ("history", "session-1", 20),
    }
    assert events[2:] == [
        ("generate",),
        (
            "save",
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            blueprint.model_dump(mode="json"),
        ),
    ]
    assert generator.calls == [
        (
            client,
            {"experience_level": "student"},
            [
                {"role": "user", "text": "Earlier question"},
                {"role": "model", "text": "Earlier answer"},
            ],
            "Build a study partner.",
        )
    ]


@pytest.mark.asyncio
async def test_service_loads_profile_and_history_concurrently(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_service import (
        SynthesisApplicationService,
        SynthesisCommand,
    )

    events: list[tuple[object, ...]] = []
    database = BlockingDatabase(events)
    service = SynthesisApplicationService(
        client=object(),
        database=database,
        blueprint_generator=FakeBlueprintGenerator(events, blueprint),
    )

    task = asyncio.create_task(
        service.synthesize(
            SynthesisCommand(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                source_text="Build a study partner.",
            )
        )
    )
    try:
        await asyncio.wait_for(
            asyncio.gather(
                database.profile_started.wait(),
                database.history_started.wait(),
            ),
            timeout=1,
        )
        assert not task.done()
        assert ("generate",) not in events
        database.release_reads.set()

        result = await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert result.blueprint_id == "blueprint-1"


@pytest.mark.asyncio
async def test_service_preserves_synthesis_errors_without_persisting(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_service import (
        SynthesisApplicationService,
        SynthesisCommand,
    )

    events: list[tuple[object, ...]] = []
    error = SynthesisEngineError("generation failed")
    service = SynthesisApplicationService(
        client=object(),
        database=FakeDatabase(events),
        blueprint_generator=FailingBlueprintGenerator(error),
    )

    with pytest.raises(SynthesisEngineError) as error_info:
        await service.synthesize(
            SynthesisCommand(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                source_text="Build a study partner.",
            )
        )

    assert error_info.value is error
    assert not any(event[0] == "save" for event in events)


@pytest.mark.parametrize("failure_point", ("profile", "history", "save"))
@pytest.mark.asyncio
async def test_service_preserves_database_errors(
    blueprint: SynthesisBlueprint,
    failure_point: str,
) -> None:
    from synthesis_service import (
        SynthesisApplicationService,
        SynthesisCommand,
    )

    events: list[tuple[object, ...]] = []
    error = MemoryEngineError("database failed")
    database = FakeDatabase(
        events,
        fail_on=failure_point,
        error=error,
    )
    service = SynthesisApplicationService(
        client=object(),
        database=database,
        blueprint_generator=FakeBlueprintGenerator(events, blueprint),
    )

    with pytest.raises(MemoryEngineError) as error_info:
        await service.synthesize(
            SynthesisCommand(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                source_text="Build a study partner.",
            )
        )

    assert error_info.value is error
    assert not any(event[0] == "save" for event in events)
