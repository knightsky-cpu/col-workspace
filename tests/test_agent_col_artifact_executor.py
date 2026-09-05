import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from agent_col_routing_v4 import AgentColRoutingDirective
from chat_turns import ChatTurnClaim, ChatTurnRequest, derive_chat_turn_ids
from schemas import (
    AdaptationReceipt,
    ArtifactReference,
    SingleFileArtifact,
    SynthesisBlueprint,
)


NOW = datetime(2026, 8, 23, 15, 0, tzinfo=UTC)
SOURCE_TEXT = (
    "Create a structured blueprint for a collaborative study partner with "
    "explicit approval, bounded memory, and verifiable milestones."
)


def blueprint() -> SynthesisBlueprint:
    return SynthesisBlueprint.model_validate(
        {
            "synthesized_conceptual_model": {
                "project_name": "Collaborative Study Partner",
                "core_value_proposition": (
                    "Turns learning goals into approved, verifiable plans."
                ),
                "in_scope": ["Collaborative planning"],
            },
            "personalization_trace": {},
            "architectural_decisions": [
                {
                    "component_name": "Approval boundary",
                    "proposed_solution": "Explicit structured decisions",
                    "rationale": "Keeps durable changes user-controlled.",
                    "alternatives": [
                        {
                            "option_name": "Inferred approval",
                            "tradeoff": "Lower friction but weaker control.",
                            "reason_not_selected": "Cannot prove consent.",
                        }
                    ],
                }
            ],
            "socratic_clarifying_questions": [
                {
                    "question_text": "Which learning goal comes first?",
                    "why_this_matters": "It determines the first milestone.",
                    "suggested_options": [
                        {"label": "Theory", "impact": "Start conceptually."},
                        {"label": "Practice", "impact": "Start hands-on."},
                    ],
                }
            ],
            "step_by_step_execution_roadmap": [
                {
                    "phase_name": "Foundation",
                    "objective": "Define the first learning goal.",
                    "expected_deliverable": "An approved milestone.",
                    "micro_tasks": [
                        {
                            "task_description": "Choose the first goal.",
                            "complexity_level": "Low",
                            "verification_steps": ["Record explicit approval."],
                        }
                    ],
                }
            ],
        }
    )


def artifact_directive() -> AgentColRoutingDirective:
    return AgentColRoutingDirective.model_validate(
        {
            "schema_version": "4.0",
            "route": "artifact",
            "artifact_intent": {
                "operation": "create_blueprint",
                "objective": "Create the requested structured blueprint.",
            },
        }
    )


def single_file_artifact_directive() -> AgentColRoutingDirective:
    return AgentColRoutingDirective.model_validate(
        {
            "schema_version": "4.0",
            "route": "artifact",
            "artifact_intent": {
                "operation": "create_single_file_artifact",
                "objective": "Create the requested password generator code artifact.",
                "artifact_family": "code",
                "format": "python",
                "filename": "password_generator.py",
            },
        }
    )


def initial_claim() -> ChatTurnClaim:
    return ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message=SOURCE_TEXT,
        ),
        ids=derive_chat_turn_ids("artifact-turn-1"),
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=120),
        resumed=False,
    )


def single_file_reference_for_claim(claim: ChatTurnClaim) -> ArtifactReference:
    return ArtifactReference(
        artifact_type="single_file_artifact",
        project_id=claim.request.project_id,
        artifact_id=f"artifact--{claim.ids.turn_id}",
        schema_version="1.0",
        display_label="Password Generator",
    )


def single_file_artifact() -> SingleFileArtifact:
    return SingleFileArtifact(
        artifact_family="code",
        format="python",
        filename="password_generator.py",
        content="import secrets\nprint(secrets.token_urlsafe(12))\n",
        summary="Password Generator",
    )


def test_build_artifact_source_text_uses_recent_context_for_reference_request(
) -> None:
    from agent_col_artifact_executor import build_artifact_source_text

    source_text = build_artifact_source_text(
        current_message="Turn that into a markdown artifact.",
        recent_user_messages=(
            "I need a simple Pomodoro timer with work sessions, short breaks, "
            "and a reset control.",
        ),
    )

    assert "[CURRENT_ARTIFACT_REQUEST]" in source_text
    assert "Turn that into a markdown artifact." in source_text
    assert "[RECENT_USER_CONTEXT]" in source_text
    assert "simple Pomodoro timer" in source_text


def test_build_artifact_source_text_uses_last_six_recent_context_messages(
) -> None:
    from agent_col_artifact_executor import build_artifact_source_text

    recent_messages = tuple(f"Context message {index}" for index in range(8))

    source_text = build_artifact_source_text(
        current_message="Turn that into a markdown artifact.",
        recent_user_messages=recent_messages,
    )

    assert "Context message 0" not in source_text
    assert "Context message 1" not in source_text
    for index in range(2, 8):
        assert f"Context message {index}" in source_text


def test_build_artifact_source_text_keeps_self_contained_request_single_source(
) -> None:
    from agent_col_artifact_executor import build_artifact_source_text

    source_text = build_artifact_source_text(
        current_message=(
            "Create a blueprint for a simple Pomodoro timer with a work "
            "interval, break interval, start button, pause button, and reset."
        ),
        recent_user_messages=(
            "Unrelated old request about a study tracker.",
        ),
    )

    assert source_text.startswith("Create a blueprint for a simple Pomodoro")
    assert "Unrelated old request" not in source_text


def test_artifact_executor_exposes_queue_without_chat_owned_execute() -> None:
    from agent_col_artifact_executor import AgentColArtifactExecutor

    assert hasattr(AgentColArtifactExecutor, "queue")
    assert not hasattr(AgentColArtifactExecutor, "execute")


@dataclass
class FakeSynthesisService:
    generated: SynthesisBlueprint
    adaptations: tuple[AdaptationReceipt, ...] = ()
    commands: list[object] = field(default_factory=list)
    persisted_blueprint_id: str = "blueprint-from-worker"
    delay_seconds: float = 0
    resource_mutations: list[str] = field(default_factory=list)

    async def generate_governed_blueprint(self, command: object) -> object:
        from synthesis_service import GovernedSynthesisGenerationResult

        self.commands.append(command)
        return GovernedSynthesisGenerationResult(
            blueprint=self.generated,
            adaptations=self.adaptations,
        )

    async def synthesize(self, command: object) -> object:
        from synthesis_service import SynthesisResult

        self.commands.append(command)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        self.resource_mutations.append("blueprint_artifact")
        return SynthesisResult(
            blueprint_id=self.persisted_blueprint_id,
            blueprint=self.generated,
            adaptations=self.adaptations,
        )


@dataclass
class FakeGenericArtifactGenerator:
    generated: SingleFileArtifact
    calls: list[tuple[object, object]] = field(default_factory=list)

    async def __call__(
        self,
        client: object,
        request: object,
    ) -> SingleFileArtifact:
        self.calls.append((client, request))
        return self.generated


class RecordingAgentJobRepository:
    def __init__(self) -> None:
        self.enqueued = []
        self.enqueued_payloads = []
        self.events = []
        self.leased = []
        self.renewed = []
        self.renew_error: Exception | None = None
        self.completed = []
        self.failed = []
        self.reports = []

    async def enqueue_job(self, job):
        self.enqueued.append(job)
        return job

    async def enqueue_job_with_payload(self, job, payload):
        self.enqueued.append(job)
        self.enqueued_payloads.append(payload)
        return job

    async def lease_next_queued_job(
        self,
        *,
        user_id,
        workspace_id,
        lease_owner,
        lease_expires_at,
        observed_at,
        action_kind=None,
    ):
        self.leased.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
                "observed_at": observed_at,
                "action_kind": action_kind,
            }
        )
        if not self.enqueued:
            return None
        job = self.enqueued[-1]
        if action_kind is not None and job.action_kind != action_kind:
            return None
        return job.model_copy(
            update={
                "status": "running",
                "updated_at": observed_at,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
            }
        )

    async def renew_job_lease(
        self,
        *,
        user_id,
        workspace_id,
        job_id,
        lease_owner,
        lease_expires_at,
        observed_at,
    ):
        self.renewed.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "job_id": job_id,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
                "observed_at": observed_at,
            }
        )
        if self.renew_error is not None:
            raise self.renew_error
        job = self.enqueued[-1]
        return job.model_copy(
            update={
                "status": "running",
                "updated_at": observed_at,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
            }
        )

    async def get_job_payload(self, *, user_id, workspace_id, job_id):
        assert user_id == self.enqueued[-1].user_id
        assert workspace_id == self.enqueued[-1].workspace_id
        assert job_id == self.enqueued[-1].job_id
        return self.enqueued_payloads[-1]

    async def append_event(self, *, user_id, workspace_id, event):
        self.events.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "event": event,
            }
        )
        return event

    async def lease_queued_job(
        self,
        *,
        user_id,
        workspace_id,
        job_id,
        lease_owner,
        lease_expires_at,
        observed_at,
    ):
        self.leased.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "job_id": job_id,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
                "observed_at": observed_at,
            }
        )
        job = self.enqueued[-1]
        return job.model_copy(
            update={
                "status": "running",
                "updated_at": observed_at,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
            }
        )

    async def complete_job(
        self,
        *,
        user_id,
        workspace_id,
        job_id,
        lease_owner,
        observed_at,
        result_refs,
    ):
        self.completed.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "job_id": job_id,
                "lease_owner": lease_owner,
                "observed_at": observed_at,
                "result_refs": result_refs,
            }
        )
        job = self.enqueued[-1]
        return job.model_copy(
            update={
                "status": "completed",
                "updated_at": observed_at,
                "lease_owner": lease_owner,
                "result_refs": result_refs,
            }
        )

    async def fail_job(
        self,
        *,
        user_id,
        workspace_id,
        job_id,
        lease_owner,
        observed_at,
        failure,
    ):
        self.failed.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "job_id": job_id,
                "lease_owner": lease_owner,
                "observed_at": observed_at,
                "failure": failure,
            }
        )
        job = self.enqueued[-1]
        return job.model_copy(
            update={
                "status": "failed",
                "updated_at": observed_at,
                "lease_owner": lease_owner,
                "failure_summary": failure,
            }
        )

    async def create_report(self, report):
        self.reports.append(report)
        return report


@dataclass
class RecordingGenericArtifactCreationService:
    reference: ArtifactReference
    commands: list[object] = field(default_factory=list)

    async def create_artifact(self, command: object) -> object:
        from generic_artifact_creation_service import (
            GenericArtifactCreationResult,
        )

        self.commands.append(command)
        return GenericArtifactCreationResult(
            reference=self.reference,
            artifact=SingleFileArtifact.model_validate(command.artifact),
        )


@pytest.mark.asyncio
async def test_artifact_executor_queues_single_file_work_without_generation(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
    )

    claim = initial_claim()
    generated = single_file_artifact()
    repository = RecordingAgentJobRepository()
    dispatched_jobs = []
    generic_generator = FakeGenericArtifactGenerator(generated)
    executor = AgentColArtifactExecutor(
        synthesis_service=FakeSynthesisService(blueprint()),
        generic_artifact_generator=generic_generator,
        genai_client=object(),
        agent_job_repository=repository,
        artifact_job_dispatcher=dispatched_jobs.append,
    )

    result = await executor.queue(
        AgentColArtifactExecutionCommand(
            claim=claim,
            routing_directive=single_file_artifact_directive(),
            observed_at=NOW,
            source_text="Create a Python password generator.",
        )
    )

    assert result.claim is claim
    assert result.actions == ()
    assert result.artifacts == ()
    assert len(result.queued_actions) == 1
    assert result.queued_actions[0].action_kind == "create_artifact"
    assert result.queued_actions[0].status == "queued"
    assert result.queued_actions[0].display_label == (
        "Artifact: password_generator.py"
    )
    assert len(repository.enqueued) == 1
    assert dispatched_jobs == repository.enqueued
    assert len(repository.enqueued_payloads) == 1
    payload = repository.enqueued_payloads[0]
    assert payload.action_kind == "create_artifact"
    assert payload.source_turn_id == claim.ids.turn_id
    assert payload.source_message_id == claim.ids.user_message_id
    assert payload.payload["source_text"] == "Create a Python password generator."
    assert "owner_token" not in str(payload.payload)
    assert "turn_lease" not in str(payload.payload)
    assert [entry["event"].event_type for entry in repository.events] == [
        "queued",
    ]
    assert generic_generator.calls == []


@pytest.mark.asyncio
async def test_artifact_worker_creates_single_file_artifact_from_private_payload(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactCreationJobWorker,
        AgentColArtifactExecutionCommand,
        _artifact_job,
        artifact_job_payload,
    )

    claim = initial_claim()
    generated = single_file_artifact()
    artifact = single_file_reference_for_claim(claim)
    repository = RecordingAgentJobRepository()
    command = AgentColArtifactExecutionCommand(
        claim=claim,
        routing_directive=single_file_artifact_directive(),
        observed_at=NOW,
        source_text="Create a Python password generator.",
    )
    command_job = _artifact_job(command)
    job = await repository.enqueue_job_with_payload(
        command_job,
        artifact_job_payload(command, command_job),
    )
    generic_generator = FakeGenericArtifactGenerator(generated)
    artifact_creator = RecordingGenericArtifactCreationService(artifact)
    worker = AgentColArtifactCreationJobWorker(
        agent_job_repository=repository,
        synthesis_service=FakeSynthesisService(blueprint()),
        generic_artifact_generator=generic_generator,
        generic_artifact_creator=artifact_creator,
        genai_client=object(),
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="agent-col",
        lease_owner="artifact-worker-1",
    )

    assert completed is not None
    assert completed.status == "completed"
    assert repository.leased[0]["action_kind"] == "create_artifact"
    assert len(generic_generator.calls) == 1
    assert len(artifact_creator.commands) == 1
    creation_command = artifact_creator.commands[0]
    assert creation_command.project_id == "agent-col"
    assert creation_command.session_id == "session-1"
    assert creation_command.user_id == "user-1"
    assert creation_command.originating_turn_id == claim.ids.turn_id
    assert creation_command.artifact == generated.model_dump(mode="json")
    assert repository.completed[0]["result_refs"] == {
        "artifact_id": artifact.artifact_id
    }
    assert [entry["event"].event_type for entry in repository.events] == [
        "started",
        "completed",
    ]
    assert len(repository.reports) == 1
    report = repository.reports[0]
    assert report.status == "completed"
    assert report.agent_label == "Artifact Builder"
    assert report.title == "Artifact created"
    assert report.summary == "The requested artifact was created."
    assert report.public_resource_label == "Password Generator"
    assert job.action_kind == "create_artifact"


@pytest.mark.asyncio
async def test_artifact_worker_creates_blueprint_artifact_from_private_payload(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactCreationJobWorker,
        AgentColArtifactExecutionCommand,
        _artifact_job,
        artifact_job_payload,
    )
    from synthesis_service import SynthesisCommand

    claim = initial_claim()
    generated = blueprint()
    synthesis_service = FakeSynthesisService(generated)
    repository = RecordingAgentJobRepository()
    command = AgentColArtifactExecutionCommand(
        claim=claim,
        routing_directive=artifact_directive(),
        observed_at=NOW,
        source_text="Create a study partner blueprint.",
    )
    job = _artifact_job(command)
    await repository.enqueue_job_with_payload(
        job,
        artifact_job_payload(command, job),
    )
    worker = AgentColArtifactCreationJobWorker(
        agent_job_repository=repository,
        synthesis_service=synthesis_service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="agent-col",
        lease_owner="artifact-worker-1",
    )

    assert completed is not None
    assert completed.status == "completed"
    assert synthesis_service.commands == [
        SynthesisCommand(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            source_text="Create a study partner blueprint.",
        )
    ]
    assert repository.completed[0]["result_refs"] == {
        "artifact_id": "blueprint-from-worker"
    }
    assert [entry["event"].event_type for entry in repository.events] == [
        "started",
        "completed",
    ]
    assert len(repository.reports) == 1
    report = repository.reports[0]
    assert report.status == "completed"
    assert report.agent_label == "Artifact Builder"
    assert report.title == "Artifact created"
    assert report.summary == "The requested artifact was created."
    assert report.public_resource_label == "Collaborative Study Partner"


@pytest.mark.asyncio
async def test_artifact_worker_renews_lease_while_execution_remains_active(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactCreationJobWorker,
        AgentColArtifactExecutionCommand,
        _artifact_job,
        artifact_job_payload,
    )

    claim = initial_claim()
    repository = RecordingAgentJobRepository()
    command = AgentColArtifactExecutionCommand(
        claim=claim,
        routing_directive=artifact_directive(),
        observed_at=NOW,
        source_text="Create a study partner blueprint.",
    )
    command_job = _artifact_job(command)
    job = await repository.enqueue_job_with_payload(
        command_job,
        artifact_job_payload(command, command_job),
    )
    worker = AgentColArtifactCreationJobWorker(
        agent_job_repository=repository,
        synthesis_service=FakeSynthesisService(blueprint(), delay_seconds=0.03),
        clock=lambda: NOW + timedelta(minutes=1),
        renewal_interval_seconds=0.001,
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="agent-col",
        lease_owner="artifact-worker-1",
    )
    renew_count = len(repository.renewed)
    await asyncio.sleep(0.01)

    assert completed is not None
    assert completed.status == "completed"
    assert renew_count >= 1
    assert len(repository.renewed) == renew_count
    assert {
        entry["job_id"] for entry in repository.renewed
    } == {job.job_id}
    assert {
        entry["lease_owner"] for entry in repository.renewed
    } == {"artifact-worker-1"}


@pytest.mark.asyncio
async def test_artifact_worker_renewal_failure_prevents_successful_completion(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactCreationJobWorker,
        AgentColArtifactExecutionCommand,
        _artifact_job,
        artifact_job_payload,
    )
    from agent_job_repository import AgentJobLeaseError

    claim = initial_claim()
    repository = RecordingAgentJobRepository()
    repository.renew_error = AgentJobLeaseError("lease lost")
    command = AgentColArtifactExecutionCommand(
        claim=claim,
        routing_directive=artifact_directive(),
        observed_at=NOW,
        source_text="Create a study partner blueprint.",
    )
    command_job = _artifact_job(command)
    await repository.enqueue_job_with_payload(
        command_job,
        artifact_job_payload(command, command_job),
    )
    synthesis_service = FakeSynthesisService(
        blueprint(),
        delay_seconds=0.03,
    )
    worker = AgentColArtifactCreationJobWorker(
        agent_job_repository=repository,
        synthesis_service=synthesis_service,
        clock=lambda: NOW + timedelta(minutes=1),
        renewal_interval_seconds=0.001,
    )

    with pytest.raises(AgentJobLeaseError):
        await worker.run_one(
            user_id="user-1",
            workspace_id="agent-col",
            lease_owner="artifact-worker-1",
        )

    assert repository.renewed
    assert repository.completed == []
    assert synthesis_service.resource_mutations == []
