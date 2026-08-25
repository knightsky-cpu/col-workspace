import asyncio
from dataclasses import dataclass, field

import pytest

from database import MemoryEngineError
from schemas import (
    ActiveMemorySignal,
    AdaptationReceipt,
    CollaborationProfile,
    SynthesisBlueprint,
)
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

    async def get_collaboration_profile(
        self,
        user_id: str,
    ) -> CollaborationProfile:
        if self.fail_on == "profile":
            assert self.error is not None
            raise self.error
        self.events.append(("collaboration_profile", user_id))
        return CollaborationProfile()

    async def get_chat_history(
        self,
        session_id: str,
        limit: int | None = None,
        *,
        user_id: str,
        project_id: str,
    ) -> list[dict[str, object]]:
        if self.fail_on == "history":
            assert self.error is not None
            raise self.error
        self.events.append(
            ("history", session_id, limit, user_id, project_id)
        )
        return self.history

    async def save_blueprint(
        self,
        project_id: str,
        session_id: str,
        user_id: str,
        model_name: str,
        schema_version: str,
        blueprint: dict[str, object],
        *,
        adaptations: tuple[AdaptationReceipt, ...] = (),
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
                adaptations,
            )
        )
        return "blueprint-1"


@dataclass
class FakeGovernedDatabase(FakeDatabase):
    collaboration_profile: CollaborationProfile = field(
        default_factory=CollaborationProfile
    )

    async def get_collaboration_profile(
        self,
        user_id: str,
    ) -> CollaborationProfile:
        self.events.append(("collaboration_profile", user_id))
        return self.collaboration_profile


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

    async def get_collaboration_profile(
        self,
        user_id: str,
    ) -> CollaborationProfile:
        self.events.append(("collaboration_profile", user_id))
        self.profile_started.set()
        await self.release_reads.wait()
        return CollaborationProfile()

    async def get_chat_history(
        self,
        session_id: str,
        limit: int | None = None,
        *,
        user_id: str,
        project_id: str,
    ) -> list[dict[str, object]]:
        self.events.append(
            ("history", session_id, limit, user_id, project_id)
        )
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
async def test_generate_blueprint_builds_context_without_persisting(
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
    command = SynthesisCommand(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        source_text="Build a study partner.",
    )

    generated = await service.generate_blueprint(command)

    assert generated is blueprint
    assert set(events[:2]) == {
        ("profile", "user-1"),
        ("history", "session-1", 20, "user-1", "project-1"),
    }
    assert events[2:] == [("generate",)]
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
async def test_governed_generation_projects_memory_and_derives_receipt(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_service import (
        SynthesisApplicationService,
        SynthesisCommand,
    )

    planning_signal = ActiveMemorySignal.model_validate(
        {
            "signal_id": "planning-granularity-signal-1",
            "category": "planning_granularity",
            "value": "micro_steps",
            "policy_version": "1.0",
            "source_event_id": (
                "planning-granularity-signal-1--approved"
            ),
            "approved_at": "2026-08-23T21:00:00Z",
        }
    )
    response_length_signal = ActiveMemorySignal.model_validate(
        {
            "signal_id": "response-length-signal-1",
            "category": "response_length",
            "value": "concise",
            "policy_version": "1.0",
            "source_event_id": "response-length-signal-1--approved",
            "approved_at": "2026-08-23T20:00:00Z",
        }
    )
    payload = blueprint.model_dump(mode="json")
    payload["personalization_trace"] = {
        "adaptations": [
            {
                "profile_key": "planning_granularity",
                "architecture_change": (
                    "The roadmap uses small sequential actions."
                ),
                "reason": "The approved preference requests micro-steps.",
            }
        ]
    }
    personalized_blueprint = SynthesisBlueprint.model_validate(payload)
    events: list[tuple[object, ...]] = []
    database = FakeGovernedDatabase(
        events,
        collaboration_profile=CollaborationProfile(
            memory_revision=7,
            active_preferences={
                "planning_granularity": planning_signal,
                "response_length": response_length_signal,
            },
        ),
    )
    generator = FakeBlueprintGenerator(events, personalized_blueprint)
    client = object()
    service = SynthesisApplicationService(
        client=client,
        database=database,
        governed_blueprint_generator=generator,
    )
    command = SynthesisCommand(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        source_text="Build a study partner.",
    )

    result = await service.generate_governed_blueprint(command)

    assert result.blueprint is personalized_blueprint
    assert [
        receipt.model_dump(mode="json")
        for receipt in result.adaptations
    ] == [
        {
            "signal_id": "planning-granularity-signal-1",
            "category": "planning_granularity",
            "value": "micro_steps",
            "source_event_id": (
                "planning-granularity-signal-1--approved"
            ),
            "status": "provided_to_model",
        }
    ]
    assert set(events[:2]) == {
        ("collaboration_profile", "user-1"),
        ("history", "session-1", 20, "user-1", "project-1"),
    }
    assert events[2:] == [("generate",)]
    assert generator.calls == [
        (
            client,
            {
                "planning_granularity": {
                    "value": "micro_steps",
                    "instruction": (
                        "Break complex plans into small sequential actions "
                        "with explicit verification."
                    ),
                }
            },
            [
                {"role": "user", "text": "Earlier question"},
                {"role": "model", "text": "Earlier answer"},
            ],
            "Build a study partner.",
        )
    ]
    assert not any(event[0] == "save" for event in events)


@pytest.mark.asyncio
async def test_governed_generation_allows_empty_memory_without_receipts(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_service import (
        SynthesisApplicationService,
        SynthesisCommand,
    )

    events: list[tuple[object, ...]] = []
    generator = FakeBlueprintGenerator(events, blueprint)
    service = SynthesisApplicationService(
        client=object(),
        database=FakeGovernedDatabase(events),
        governed_blueprint_generator=generator,
    )

    result = await service.generate_governed_blueprint(
        SynthesisCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            source_text="Build a study partner.",
        )
    )

    assert result.blueprint is blueprint
    assert result.adaptations == ()
    assert generator.calls[0][1] == {}
    assert not any(event[0] == "save" for event in events)


@pytest.mark.asyncio
async def test_governed_generation_rejects_duplicate_trace_category(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_personalization import SynthesisPersonalizationError
    from synthesis_service import (
        SynthesisApplicationService,
        SynthesisCommand,
    )

    signal = ActiveMemorySignal.model_validate(
        {
            "signal_id": "planning-granularity-signal-1",
            "category": "planning_granularity",
            "value": "tasks",
            "policy_version": "1.0",
            "source_event_id": (
                "planning-granularity-signal-1--approved"
            ),
            "approved_at": "2026-08-23T21:00:00Z",
        }
    )
    payload = blueprint.model_dump(mode="json")
    payload["personalization_trace"] = {
        "adaptations": [
            {
                "profile_key": "planning_granularity",
                "architecture_change": "The roadmap uses tasks.",
                "reason": "The preference requests tasks.",
            },
            {
                "profile_key": "planning_granularity",
                "architecture_change": "Tasks have clear outcomes.",
                "reason": "The preference requests reviewable tasks.",
            },
        ]
    }
    generated = SynthesisBlueprint.model_validate(payload)
    events: list[tuple[object, ...]] = []
    service = SynthesisApplicationService(
        client=object(),
        database=FakeGovernedDatabase(
            events,
            collaboration_profile=CollaborationProfile(
                active_preferences={"planning_granularity": signal}
            ),
        ),
        governed_blueprint_generator=FakeBlueprintGenerator(
            events,
            generated,
        ),
    )

    with pytest.raises(
        SynthesisEngineError,
        match="personalization validation failed",
    ) as error_info:
        await service.generate_governed_blueprint(
            SynthesisCommand(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                source_text="Build a study partner.",
            )
        )

    assert isinstance(error_info.value.__cause__, SynthesisPersonalizationError)
    assert not any(event[0] == "save" for event in events)


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
        governed_blueprint_generator=generator,
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
        ("collaboration_profile", "user-1"),
        ("history", "session-1", 20, "user-1", "project-1"),
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
            (),
        ),
    ]
    assert generator.calls == [
        (
            client,
            {},
            [
                {"role": "user", "text": "Earlier question"},
                {"role": "model", "text": "Earlier answer"},
            ],
            "Build a study partner.",
        )
    ]


@pytest.mark.asyncio
async def test_service_persists_only_governed_adaptation_receipts(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_service import (
        SynthesisApplicationService,
        SynthesisCommand,
    )

    signal = ActiveMemorySignal.model_validate(
        {
            "signal_id": "planning-granularity-signal-1",
            "category": "planning_granularity",
            "value": "micro_steps",
            "policy_version": "1.0",
            "source_event_id": "planning-granularity-signal-1--approved",
            "approved_at": "2026-08-23T21:00:00Z",
        }
    )
    payload = blueprint.model_dump(mode="json")
    payload["personalization_trace"] = {
        "adaptations": [
            {
                "profile_key": "planning_granularity",
                "architecture_change": "The roadmap uses micro-steps.",
                "reason": "The approved preference requests micro-steps.",
            }
        ]
    }
    governed_blueprint = SynthesisBlueprint.model_validate(payload)
    events: list[tuple[object, ...]] = []
    database = FakeGovernedDatabase(
        events,
        collaboration_profile=CollaborationProfile(
            active_preferences={"planning_granularity": signal}
        ),
    )
    legacy_generator = FakeBlueprintGenerator(events, blueprint)
    governed_generator = FakeBlueprintGenerator(events, governed_blueprint)
    service = SynthesisApplicationService(
        client=object(),
        database=database,
        blueprint_generator=legacy_generator,
        governed_blueprint_generator=governed_generator,
    )

    result = await service.synthesize(
        SynthesisCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            source_text="Build a study partner.",
        )
    )

    assert result.blueprint is governed_blueprint
    assert result.adaptations == (
        AdaptationReceipt(
            signal_id="planning-granularity-signal-1",
            category="planning_granularity",
            value="micro_steps",
            source_event_id="planning-granularity-signal-1--approved",
            status="provided_to_model",
        ),
    )
    assert legacy_generator.calls == []
    assert len(governed_generator.calls) == 1
    assert events[-1] == (
        "save",
        "project-1",
        "session-1",
        "user-1",
        "gemini-3.6-flash",
        "2.0",
        governed_blueprint.model_dump(mode="json"),
        result.adaptations,
    )


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
        governed_blueprint_generator=FakeBlueprintGenerator(
            events,
            blueprint,
        ),
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
        governed_blueprint_generator=FailingBlueprintGenerator(error),
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
        governed_blueprint_generator=FakeBlueprintGenerator(events, blueprint),
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
