import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from agent_col_agent_jobs import AgentJob
from agent_job_payloads import AgentJobPayload
from database import (
    MemoryClarificationSelectionError,
    MemoryProposalConflictError,
)
from memory_candidate_decisions import ClarifyDecision, ProfileCandidateDecision
from schemas import (
    AgentActionReceipt,
    MemoryClarificationChoice,
    MemoryClarificationReceipt,
    MemoryProposalReceiptV2,
    MemoryProposalV2,
    QueuedActionReceipt,
)
from trusted_memory_service import (
    NaturalMemoryCommand,
    NaturalMemoryProposalResult,
    SelectMemoryClarificationCommand,
)


NOW = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)


class RecordingMemoryService:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.error = error
        self.delay_seconds = delay_seconds
        self.commands: list[NaturalMemoryCommand] = []
        self.selection_commands: list[SelectMemoryClarificationCommand] = []
        self.preference_confirmation_calls: list[dict[str, object]] = []
        self.resource_mutations: list[str] = []

    async def handle_natural_memory_decision(self, command):
        self.commands.append(command)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        self.resource_mutations.append("memory_proposal")
        return NaturalMemoryProposalResult(
            status="pending",
            action=AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            ),
            proposal=MemoryProposalReceiptV2(
                proposal_id=(
                    "response_length--e82366f7699ee2e39bff6a68154e09b7"
                ),
                category="response_length",
                proposed_value="concise",
                expires_at=NOW + timedelta(hours=1),
            ),
        )

    async def select_memory_clarification(self, command):
        self.selection_commands.append(command)
        if self.error is not None:
            raise self.error
        return NaturalMemoryProposalResult(
            status="pending",
            action=AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            ),
            proposal=MemoryProposalReceiptV2(
                proposal_id=(
                    "response_length--clarified-proposal-1"
                ),
                category="response_length",
                proposed_value="detailed",
                expires_at=NOW + timedelta(hours=1),
            ),
        )

    async def open_preference_hypothesis_confirmation(self, **kwargs):
        self.preference_confirmation_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return MemoryClarificationReceipt(
            clarification_id="memory-clarification--preference-1",
            choices=[
                MemoryClarificationChoice(
                    candidate_index=0,
                    category_label="Response length",
                    value_label="concise",
                ),
                MemoryClarificationChoice(
                    candidate_index=1,
                    category_label="Do not save",
                    value_label="Keep this as feedback only",
                ),
            ],
            expires_at=NOW + timedelta(minutes=15),
        )


class RecordingAgentJobRepository:
    def __init__(self, *, job, payload) -> None:
        self.job = job
        self.payload = payload
        self.leased = []
        self.renewed = []
        self.renew_error: Exception | None = None
        self.events = []
        self.completed = []
        self.failed = []
        self.finalized = []
        self.reports = []

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
        if action_kind is not None and self.job.action_kind != action_kind:
            return None
        return self.job.model_copy(
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
        return self.job.model_copy(
            update={
                "status": "running",
                "updated_at": observed_at,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
            }
        )

    async def get_job_payload(self, *, user_id, workspace_id, job_id):
        assert user_id == self.job.user_id
        assert workspace_id == self.job.workspace_id
        assert job_id == self.job.job_id
        return self.payload

    async def append_event(self, *, user_id, workspace_id, event):
        self.events.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "event": event,
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
        return self.job.model_copy(
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
        return self.job.model_copy(
            update={
                "status": "failed",
                "updated_at": observed_at,
                "lease_owner": lease_owner,
                "failure_summary": failure,
            }
        )

    async def finalize_terminal_job(
        self,
        *,
        user_id,
        workspace_id,
        job_id,
        lease_owner,
        observed_at,
        status,
        result_refs,
        failure,
        event,
        report,
    ):
        self.finalized.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "job_id": job_id,
                "lease_owner": lease_owner,
                "observed_at": observed_at,
                "status": status,
                "result_refs": result_refs,
                "failure": failure,
                "event": event,
                "report": report,
            }
        )
        self.events.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "event": event,
            }
        )
        self.reports.append(report)
        return self.job.model_copy(
            update={
                "status": status,
                "updated_at": observed_at,
                "lease_owner": lease_owner,
                "result_refs": result_refs or {},
                "failure_summary": failure,
            }
        )

    async def create_report(self, report):
        self.reports.append(report)
        return report


class RecordingGovernedMemoryDatabase:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create_guarded_memory_proposal_v2(
        self,
        **kwargs,
    ) -> MemoryProposalV2:
        self.calls.append(kwargs)
        ids = kwargs["origin_ids"]
        return MemoryProposalV2(
            proposal_id=ids.proposal_id,
            category=kwargs["category"],
            proposed_value=kwargs["proposed_value"],
            expected_signal_id=None,
            status="pending",
            source_session_id=kwargs["session_id"],
            source_message_id=kwargs["source_message_id"],
            evidence_message_id=kwargs["evidence_message_id"],
            clarification_id=kwargs["clarification_id"],
            created_at=kwargs["observed_at"],
            expires_at=kwargs["observed_at"] + timedelta(hours=24),
        )


def make_command() -> NaturalMemoryCommand:
    return NaturalMemoryCommand(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_id="message-1",
        source_message_text="I prefer concise responses.",
        memory_decision_present=False,
        decision=ProfileCandidateDecision(
            kind="profile_candidate",
            category="response_length",
            canonical_value="concise",
            evidence_text="I prefer concise responses.",
        ),
        clarification_selection=None,
    )


def make_job(command: NaturalMemoryCommand) -> AgentJob:
    return AgentJob(
        job_id="memory-job-1",
        user_id=command.user_id,
        project_id=command.workspace_id,
        workspace_id=command.workspace_id,
        session_id=command.session_id,
        source_turn_id=command.source_message_id,
        source_message_id=command.source_message_id,
        action_kind="propose_memory_signal",
        status="queued",
        display_label="Memory request: response_length",
        agent_label="Memory Analyst",
        created_at=NOW,
        updated_at=NOW,
        idempotency_key="memory-proposal-1",
    )


def make_clarification_selection_job() -> AgentJob:
    return AgentJob(
        job_id="memory-clarification-selection-job-1",
        user_id="user-1",
        project_id="workspace-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_turn_id="message-2",
        source_message_id="message-2",
        action_kind="propose_memory_signal",
        status="queued",
        display_label="Memory clarification selection",
        agent_label="Memory Analyst",
        created_at=NOW,
        updated_at=NOW,
        idempotency_key="memory-clarification-selection-1",
    )


def make_clarification_selection_payload(job: AgentJob) -> AgentJobPayload:
    return AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "work_type": "memory_clarification_selection",
            "clarification_id": "memory-clarification--clarification-1",
            "selected_candidate_index": 0,
        },
    )


def exact_failed_user_requested_memory_payload(job: AgentJob) -> AgentJobPayload:
    return AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "decision": {
                "kind": "profile_candidate",
                "category": "user_requested_memory",
                "value": "Prefers pancakes on Saturday mornings for breakfast",
                "evidence_text": (
                    "Remember that I prefer pancakes on Saturday mornings "
                    "for breakfast."
                ),
            },
            "clarification_selection": None,
            "source_message_text": (
                "Remember that I prefer pancakes on Saturday mornings "
                "for breakfast."
            ),
            "memory_decision_present": False,
        },
    )


def raw_profile_candidate_payload(
    job: AgentJob,
    *,
    decision: dict[str, object],
    source_message_text: str,
) -> AgentJobPayload:
    return AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "decision": decision,
            "clarification_selection": None,
            "source_message_text": source_message_text,
            "memory_decision_present": False,
        },
    )


async def run_memory_worker_with_payload(
    payload: AgentJobPayload,
) -> tuple[AgentJob, RecordingMemoryService, RecordingAgentJobRepository]:
    from memory_proposal_job_worker import MemoryProposalJobWorker

    command = make_command()
    job = make_job(command)
    repository = RecordingAgentJobRepository(job=job, payload=payload)
    service = RecordingMemoryService()
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="memory-worker-1",
    )
    assert completed is not None
    return completed, service, repository


def test_memory_command_restores_persisted_value_alias_payload() -> None:
    from memory_proposal_job_worker import memory_command_from_payload

    command = make_command()
    job = make_job(command)

    restored = memory_command_from_payload(
        exact_failed_user_requested_memory_payload(job)
    )

    assert restored.decision.kind == "profile_candidate"
    assert restored.decision.category == "user_requested_memory"
    assert restored.decision.canonical_value == (
        "Prefers pancakes on Saturday mornings for breakfast"
    )
    assert restored.decision.evidence_text == (
        "Remember that I prefer pancakes on Saturday mornings for breakfast."
    )
    assert restored.source_message_text == (
        "Remember that I prefer pancakes on Saturday mornings for breakfast."
    )
    assert restored.memory_decision_present is False


@pytest.mark.asyncio
async def test_memory_worker_creates_proposal_from_standalone_value_alias_payload(
) -> None:
    from memory_proposal_job_worker import MemoryProposalJobWorker
    from trusted_memory_service import TrustedMemoryService

    command = make_command()
    job = make_job(command).model_copy(
        update={
            "job_id": "memory-job-c201d61827fb072d2a4c5138c94e6d88",
            "display_label": "Memory request: user_requested_memory",
            "idempotency_key": "memory-proposal-c201d61827fb072d2a4c5138c94e6d88",
        }
    )
    payload = exact_failed_user_requested_memory_payload(job)
    repository = RecordingAgentJobRepository(job=job, payload=payload)
    database = RecordingGovernedMemoryDatabase()
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=TrustedMemoryService(
            database=database,
            clock=lambda: NOW + timedelta(minutes=1),
        ),
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        lease_owner="memory-worker-1",
    )

    assert completed.status == "completed"
    assert repository.failed == []
    assert len(repository.finalized) == 1
    assert len(database.calls) == 1
    assert database.calls[0]["category"] == "user_requested_memory"
    assert database.calls[0]["proposed_value"] == (
        "Prefers pancakes on Saturday mornings for breakfast"
    )
    assert database.calls[0]["evidence_message_id"] == job.source_message_id
    assert "turn_lease" not in database.calls[0]
    assert repository.reports[0].status == "completed"
    assert repository.reports[0].title == "Memory proposal pending review"
    assert repository.reports[0].public_resource_label == (
        "Prefers pancakes on Saturday mornings for breakfast"
    )


@pytest.mark.asyncio
async def test_memory_worker_completes_queued_memory_proposal_from_private_payload(
) -> None:
    from memory_proposal_job_worker import (
        MemoryProposalJobWorker,
        memory_job_payload,
    )

    command = make_command()
    job = make_job(command)
    payload = memory_job_payload(command, job)
    assert "turn_lease" not in payload.payload
    assert "owner_token" not in str(payload.payload)
    repository = RecordingAgentJobRepository(job=job, payload=payload)
    service = RecordingMemoryService()
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="memory-worker-1",
    )

    assert completed.status == "completed"
    assert len(service.commands) == 1
    recorded = service.commands[0]
    assert recorded.user_id == command.user_id
    assert recorded.workspace_id == command.workspace_id
    assert recorded.session_id == command.session_id
    assert recorded.source_message_id == command.source_message_id
    assert recorded.source_message_text == command.source_message_text
    assert recorded.memory_decision_present == command.memory_decision_present
    assert recorded.decision == command.decision
    assert recorded.clarification_selection == command.clarification_selection
    assert repository.leased[0]["action_kind"] == "propose_memory_signal"
    assert len(repository.finalized) == 1
    assert repository.finalized[0]["status"] == "completed"
    assert repository.finalized[0]["result_refs"] == {
        "proposal_id": "response_length--e82366f7699ee2e39bff6a68154e09b7"
    }
    assert [entry["event"].event_type for entry in repository.events] == [
        "started",
        "completed",
    ]
    assert repository.completed == []
    assert repository.failed == []
    assert len(repository.reports) == 1
    report = repository.reports[0]
    assert report.status == "completed"
    assert report.agent_label == "Memory Analyst"
    assert report.title == "Memory proposal pending review"
    assert report.summary == (
        "A memory proposal was created and is pending your review."
    )
    assert report.public_resource_label == "concise"


@pytest.mark.asyncio
async def test_memory_worker_renews_lease_while_execution_remains_active(
) -> None:
    from memory_proposal_job_worker import (
        MemoryProposalJobWorker,
        memory_job_payload,
    )

    command = make_command()
    job = make_job(command)
    repository = RecordingAgentJobRepository(
        job=job,
        payload=memory_job_payload(command, job),
    )
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=RecordingMemoryService(delay_seconds=0.03),
        clock=lambda: NOW + timedelta(minutes=1),
        renewal_interval_seconds=0.001,
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="memory-worker-1",
    )
    renew_count = len(repository.renewed)
    await asyncio.sleep(0.01)

    assert completed.status == "completed"
    assert renew_count >= 1
    assert len(repository.renewed) == renew_count
    assert repository.renewed[0]["lease_owner"] == "memory-worker-1"


@pytest.mark.asyncio
async def test_memory_worker_renewal_failure_prevents_successful_completion(
) -> None:
    from agent_job_repository import AgentJobLeaseError
    from memory_proposal_job_worker import (
        MemoryProposalJobWorker,
        memory_job_payload,
    )

    command = make_command()
    job = make_job(command)
    repository = RecordingAgentJobRepository(
        job=job,
        payload=memory_job_payload(command, job),
    )
    memory_service = RecordingMemoryService(delay_seconds=0.03)
    repository.renew_error = AgentJobLeaseError("lost lease")
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=memory_service,
        clock=lambda: NOW + timedelta(minutes=1),
        renewal_interval_seconds=0.001,
    )

    with pytest.raises(AgentJobLeaseError):
        await worker.run_one(
            user_id="user-1",
            workspace_id="workspace-1",
            lease_owner="memory-worker-1",
        )

    assert repository.renewed
    assert repository.completed == []
    assert memory_service.resource_mutations == []


@pytest.mark.asyncio
async def test_memory_worker_creates_queued_clarification_without_turn_lease(
) -> None:
    from memory_proposal_job_worker import (
        MemoryProposalJobWorker,
        memory_job_payload,
    )
    from trusted_memory_service import NaturalMemoryClarificationResult

    command = NaturalMemoryCommand(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_id="message-clarification-1",
        source_message_text=(
            "Remember either concise answers or practical examples."
        ),
        memory_decision_present=False,
        decision=ClarifyDecision(
            kind="clarify",
            candidates=[
                ProfileCandidateDecision(
                    kind="profile_candidate",
                    category="response_length",
                    canonical_value="concise",
                    evidence_text="concise answers",
                ),
                ProfileCandidateDecision(
                    kind="profile_candidate",
                    category="example_usage",
                    canonical_value="when_helpful",
                    evidence_text="practical examples",
                ),
            ],
        ),
        clarification_selection=None,
    )
    job = make_job(make_command()).model_copy(
        update={
            "job_id": "memory-clarification-job-1",
            "source_turn_id": command.source_message_id,
            "source_message_id": command.source_message_id,
            "display_label": "Memory clarification",
            "idempotency_key": "memory-clarification-1",
        }
    )
    repository = RecordingAgentJobRepository(
        job=job,
        payload=memory_job_payload(command, job),
    )
    service = RecordingMemoryService()
    clarification = MemoryClarificationReceipt(
        clarification_id="memory-clarification--clarification-1",
        choices=[
            MemoryClarificationChoice(
                candidate_index=0,
                category_label="Response length",
                value_label="concise",
            ),
            MemoryClarificationChoice(
                candidate_index=1,
                category_label="Example usage",
                value_label="when helpful",
            ),
        ],
        expires_at=NOW + timedelta(minutes=15),
    )

    async def create_clarification(
        restored: NaturalMemoryCommand,
    ) -> NaturalMemoryClarificationResult:
        service.commands.append(restored)
        return NaturalMemoryClarificationResult(
            status="clarification_required",
            clarification=clarification,
        )

    service.handle_natural_memory_decision = create_clarification
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        lease_owner="memory-worker-1",
    )

    assert completed.status == "completed"
    assert len(service.commands) == 1
    assert service.commands[0].decision == command.decision
    assert service.commands[0].source_message_id == command.source_message_id
    assert repository.finalized[0]["result_refs"] == {
        "clarification_id": clarification.clarification_id
    }
    assert repository.failed == []
    assert repository.reports[0].title == (
        "Memory clarification pending response"
    )


@pytest.mark.asyncio
async def test_memory_worker_creates_preference_confirmation_without_turn_lease(
) -> None:
    from preference_learning import PreferenceHypothesis
    from memory_proposal_job_worker import MemoryProposalJobWorker

    hypothesis = PreferenceHypothesis(
        hypothesis_id="pref-hyp--user-1--workspace-1--response_length",
        user_id="user-1",
        project_id="workspace-1",
        category="response_length",
        canonical_value="concise",
        evidence_count=2,
        contradiction_count=0,
        confidence=0.75,
        source_observation_ids=("pref-obs--turn-1", "pref-obs--turn-2"),
        first_observed_at=NOW - timedelta(minutes=5),
        last_observed_at=NOW,
    )
    job = make_job(make_command()).model_copy(
        update={
            "job_id": "memory-preference-confirmation-job-1",
            "source_turn_id": "message-preference-1",
            "source_message_id": "message-preference-1",
            "display_label": "Memory preference confirmation",
            "idempotency_key": "memory-preference-confirmation-1",
        }
    )
    payload = AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "work_type": "preference_hypothesis_confirmation",
            "hypothesis": hypothesis.model_dump(mode="json"),
        },
    )
    repository = RecordingAgentJobRepository(job=job, payload=payload)
    service = RecordingMemoryService()
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        lease_owner="memory-worker-1",
    )

    assert completed.status == "completed"
    assert service.preference_confirmation_calls == [
        {
            "user_id": "user-1",
            "project_id": "workspace-1",
            "session_id": "session-1",
            "source_message_id": "message-preference-1",
            "hypothesis": hypothesis,
            "confirmation_created_at": NOW,
        }
    ]
    assert repository.finalized[0]["result_refs"] == {
        "clarification_id": "memory-clarification--preference-1"
    }
    assert repository.failed == []
    assert repository.reports[0].title == (
        "Memory clarification pending response"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suppress_confirmation", "confirmation_expected"),
    [(False, True), (True, False)],
)
async def test_memory_worker_captures_preference_and_conditionally_queues_confirmation(
    suppress_confirmation: bool,
    confirmation_expected: bool,
) -> None:
    from memory_proposal_job_worker import MemoryProposalJobWorker
    from preference_learning import PreferenceHypothesis, PreferenceObservation
    from preference_learning_service import (
        PreferenceLearningCommand,
        PreferenceLearningResult,
    )

    command = PreferenceLearningCommand(
        user_id="user-1",
        project_id="workspace-1",
        session_id="session-1",
        turn_id="turn-preference-1",
        source_message_id="message-preference-1",
        user_message="Concise please.",
        model_response="Generated answer.",
    )
    observation = PreferenceObservation(
        observation_id="pref-obs--turn-preference-1",
        user_id=command.user_id,
        project_id=command.project_id,
        session_id=command.session_id,
        source_turn_id=command.turn_id,
        source_message_id=command.source_message_id,
        category="response_length",
        canonical_value="concise",
        evidence_kind="repeated_collaboration_preference",
        evidence_summary="User requested concise responses.",
        confidence_delta=0.35,
        created_at=NOW,
    )
    hypothesis = PreferenceHypothesis(
        hypothesis_id="pref-hyp--user-1--workspace-1--response_length",
        user_id="user-1",
        project_id="workspace-1",
        category="response_length",
        canonical_value="concise",
        evidence_count=2,
        contradiction_count=0,
        confidence=0.75,
        source_observation_ids=("pref-obs--turn-1", "pref-obs--turn-preference-1"),
        first_observed_at=NOW - timedelta(minutes=5),
        last_observed_at=NOW,
    )
    job = make_job(make_command()).model_copy(
        update={
            "job_id": "memory-preference-capture-job-1",
            "source_turn_id": command.turn_id,
            "source_message_id": command.source_message_id,
            "display_label": "Preference learning capture",
            "idempotency_key": "memory-preference-capture-1",
        }
    )
    payload = AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "work_type": "preference_learning_capture",
            "observation": observation.model_dump(mode="json"),
            "suppress_confirmation": suppress_confirmation,
        },
    )

    class RecordingPreferenceService:
        def __init__(self) -> None:
            self.commands = []

        async def capture_strict(self, captured_command):
            raise AssertionError("worker must not rerun preference extraction")

        async def capture_observation_strict(self, captured_observation):
            self.commands.append(captured_observation)
            return PreferenceLearningResult(
                hypothesis=hypothesis,
                surfaced_hypothesis=hypothesis,
            )

    preference_service = RecordingPreferenceService()
    confirmation_calls = []

    async def queue_confirmation(**kwargs):
        confirmation_calls.append(kwargs)
        return QueuedActionReceipt(
            job_id="memory-preference-confirmation-job-1",
            action_kind="propose_memory_signal",
            status="queued",
            display_label="Memory preference confirmation",
            created_at=NOW,
            agent_label="Memory Analyst",
        )

    repository = RecordingAgentJobRepository(job=job, payload=payload)
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=RecordingMemoryService(),
        preference_learning_service=preference_service,
        preference_confirmation_queue=queue_confirmation,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        lease_owner="memory-worker-1",
    )

    assert completed.status == "completed"
    assert preference_service.commands == [observation]
    expected_confirmation_call = {
        "user_id": command.user_id,
        "workspace_id": command.project_id,
        "session_id": command.session_id,
        "source_message_id": command.source_message_id,
        "hypothesis": hypothesis,
    }
    assert confirmation_calls == (
        [expected_confirmation_call] if confirmation_expected else []
    )
    expected_refs = {
        "observation_status": "captured",
        "hypothesis_id": hypothesis.hypothesis_id,
    }
    if confirmation_expected:
        expected_refs["confirmation_job_id"] = (
            "memory-preference-confirmation-job-1"
        )
    assert repository.finalized[0]["result_refs"] == expected_refs


@pytest.mark.asyncio
async def test_memory_worker_fails_preference_capture_safely() -> None:
    from memory_proposal_job_worker import MemoryProposalJobWorker
    from preference_learning import PreferenceObservation
    from preference_learning_service import PreferenceLearningCommand

    command = PreferenceLearningCommand(
        user_id="user-1",
        project_id="workspace-1",
        session_id="session-1",
        turn_id="turn-preference-1",
        source_message_id="message-preference-1",
        user_message="Concise please.",
        model_response="Generated answer.",
    )
    observation = PreferenceObservation(
        observation_id="pref-obs--turn-preference-1",
        user_id=command.user_id,
        project_id=command.project_id,
        session_id=command.session_id,
        source_turn_id=command.turn_id,
        source_message_id=command.source_message_id,
        category="response_length",
        canonical_value="concise",
        evidence_kind="repeated_collaboration_preference",
        evidence_summary="User requested concise responses.",
        confidence_delta=0.35,
        created_at=NOW,
    )
    job = make_job(make_command()).model_copy(
        update={
            "job_id": "memory-preference-capture-job-1",
            "source_turn_id": command.turn_id,
            "source_message_id": command.source_message_id,
            "display_label": "Preference learning capture",
            "idempotency_key": "memory-preference-capture-1",
        }
    )
    payload = AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "work_type": "preference_learning_capture",
            "observation": observation.model_dump(mode="json"),
            "suppress_confirmation": False,
        },
    )

    class FailingPreferenceService:
        async def capture_observation_strict(self, captured_observation):
            raise RuntimeError("private persistence failure")

    repository = RecordingAgentJobRepository(job=job, payload=payload)
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=RecordingMemoryService(),
        preference_learning_service=FailingPreferenceService(),
        preference_confirmation_queue=None,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    failed = await worker.run_one(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        lease_owner="memory-worker-1",
    )

    assert failed.status == "failed"
    assert repository.completed == []
    assert repository.finalized[0]["failure"].code == "preference_capture_failed"
    assert repository.finalized[0]["failure"].retryable is True
    assert "private persistence failure" not in repository.reports[0].summary

    class RecoveredPreferenceService:
        def __init__(self) -> None:
            self.observations = []

        async def capture_strict(self, captured_command):
            raise AssertionError("recovery must not rerun preference extraction")

        async def capture_observation_strict(self, captured_observation):
            from preference_learning_service import PreferenceLearningResult

            self.observations.append(captured_observation)
            return PreferenceLearningResult(observation=captured_observation)

    recovered_service = RecoveredPreferenceService()
    recovered_repository = RecordingAgentJobRepository(
        job=job,
        payload=payload,
    )
    recovered_worker = MemoryProposalJobWorker(
        agent_job_repository=recovered_repository,
        memory_service=RecordingMemoryService(),
        preference_learning_service=recovered_service,
        preference_confirmation_queue=None,
        clock=lambda: NOW + timedelta(minutes=2),
    )

    recovered = await recovered_worker.run_one(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        lease_owner="memory-worker-recovery",
    )

    assert recovered.status == "completed"
    assert recovered_service.observations == [observation]


@pytest.mark.asyncio
async def test_memory_worker_reports_confirmation_enqueue_failure_after_capture(
) -> None:
    from memory_proposal_job_worker import MemoryProposalJobWorker
    from preference_learning import PreferenceHypothesis, PreferenceObservation
    from preference_learning_service import PreferenceLearningResult

    observation = PreferenceObservation(
        observation_id="pref-obs--turn-preference-retry",
        user_id="user-1",
        project_id="workspace-1",
        session_id="session-1",
        source_turn_id="turn-preference-retry",
        source_message_id="message-preference-retry",
        category="response_length",
        canonical_value="concise",
        evidence_kind="repeated_collaboration_preference",
        evidence_summary="User requested concise responses.",
        confidence_delta=0.35,
        created_at=NOW,
    )
    hypothesis = PreferenceHypothesis(
        hypothesis_id="pref-hyp--user-1--workspace-1--response_length",
        user_id="user-1",
        project_id="workspace-1",
        category="response_length",
        canonical_value="concise",
        evidence_count=2,
        contradiction_count=0,
        confidence=0.70,
        source_observation_ids=(
            "pref-obs--turn-1",
            observation.observation_id,
        ),
        first_observed_at=NOW - timedelta(minutes=5),
        last_observed_at=NOW,
    )
    job = AgentJob(
        job_id="memory-preference-capture-job-retry",
        user_id=observation.user_id,
        project_id=observation.project_id,
        workspace_id=observation.project_id,
        session_id=observation.session_id,
        source_turn_id=observation.source_turn_id,
        source_message_id=observation.source_message_id,
        action_kind="propose_memory_signal",
        status="queued",
        display_label="Preference learning capture",
        agent_label="Memory Analyst",
        created_at=NOW,
        updated_at=NOW,
        idempotency_key="memory-preference-capture-retry",
    )
    payload = AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "work_type": "preference_learning_capture",
            "observation": observation.model_dump(mode="json"),
            "suppress_confirmation": False,
        },
    )

    class IdempotentPreferenceService:
        def __init__(self) -> None:
            self.calls = []
            self.persisted_observation_ids = set()
            self.evidence_writes = 0

        async def capture_observation_strict(self, captured_observation):
            self.calls.append(captured_observation)
            if captured_observation.observation_id not in (
                self.persisted_observation_ids
            ):
                self.persisted_observation_ids.add(
                    captured_observation.observation_id
                )
                self.evidence_writes += 1
            return PreferenceLearningResult(
                observation=captured_observation,
                hypothesis=hypothesis,
                surfaced_hypothesis=hypothesis,
            )

    preference_service = IdempotentPreferenceService()
    confirmation_job_ids = set()
    confirmation_attempts = 0

    async def queue_confirmation(**kwargs):
        nonlocal confirmation_attempts
        confirmation_attempts += 1
        confirmation_job_ids.add("memory-preference-confirmation-job-retry")
        if confirmation_attempts == 1:
            raise RuntimeError("private confirmation queue failure")
        return QueuedActionReceipt(
            job_id="memory-preference-confirmation-job-retry",
            action_kind="propose_memory_signal",
            status="queued",
            display_label="Memory preference confirmation",
            created_at=NOW,
            agent_label="Memory Analyst",
        )

    first_repository = RecordingAgentJobRepository(job=job, payload=payload)
    first_worker = MemoryProposalJobWorker(
        agent_job_repository=first_repository,
        memory_service=RecordingMemoryService(),
        preference_learning_service=preference_service,
        preference_confirmation_queue=queue_confirmation,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    failed = await first_worker.run_one(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        lease_owner="memory-worker-first",
    )

    assert failed.status == "failed"
    assert first_repository.finalized[0]["failure"].code == (
        "preference_confirmation_enqueue_failed"
    )
    assert first_repository.finalized[0]["failure"].retryable is True
    assert "evidence was captured" in first_repository.reports[0].summary.lower()
    assert "private confirmation queue failure" not in (
        first_repository.reports[0].summary
    )

    retry_repository = RecordingAgentJobRepository(job=job, payload=payload)
    retry_worker = MemoryProposalJobWorker(
        agent_job_repository=retry_repository,
        memory_service=RecordingMemoryService(),
        preference_learning_service=preference_service,
        preference_confirmation_queue=queue_confirmation,
        clock=lambda: NOW + timedelta(minutes=2),
    )

    completed = await retry_worker.run_one(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        lease_owner="memory-worker-retry",
    )

    assert completed.status == "completed"
    assert preference_service.calls == [observation, observation]
    assert preference_service.evidence_writes == 1
    assert confirmation_attempts == 2
    assert confirmation_job_ids == {
        "memory-preference-confirmation-job-retry"
    }
    assert retry_repository.finalized[0]["result_refs"][
        "confirmation_job_id"
    ] == "memory-preference-confirmation-job-retry"


@pytest.mark.asyncio
async def test_memory_worker_completes_queued_clarification_selection_without_turn_lease(
) -> None:
    from memory_proposal_job_worker import MemoryProposalJobWorker

    job = make_clarification_selection_job()
    repository = RecordingAgentJobRepository(
        job=job,
        payload=make_clarification_selection_payload(job),
    )
    service = RecordingMemoryService()
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="memory-worker-1",
    )

    assert completed.status == "completed"
    assert service.commands == []
    assert service.selection_commands == [
        SelectMemoryClarificationCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-1",
            source_message_id="message-2",
            clarification_id="memory-clarification--clarification-1",
            selected_candidate_index=0,
        )
    ]
    assert repository.finalized[0]["result_refs"] == {
        "proposal_id": "response_length--clarified-proposal-1"
    }
    assert repository.failed == []
    assert repository.reports[0].status == "completed"
    assert repository.reports[0].title == "Memory proposal pending review"


@pytest.mark.asyncio
async def test_memory_worker_records_clarification_selection_conflict_failure(
) -> None:
    from memory_proposal_job_worker import MemoryProposalJobWorker

    job = make_clarification_selection_job()
    repository = RecordingAgentJobRepository(
        job=job,
        payload=make_clarification_selection_payload(job),
    )
    service = RecordingMemoryService(
        error=MemoryClarificationSelectionError("private stale selection")
    )
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    failed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="memory-worker-1",
    )

    assert failed.status == "failed"
    assert repository.completed == []
    assert repository.finalized[0]["failure"].code == "memory_proposal_conflict"
    assert "private stale selection" not in repository.finalized[0][
        "failure"
    ].summary
    assert repository.reports[0].status == "failed"


@pytest.mark.asyncio
async def test_memory_worker_records_conflict_failure_without_private_details(
) -> None:
    from memory_proposal_job_worker import (
        MemoryProposalJobWorker,
        memory_job_payload,
    )

    command = make_command()
    job = make_job(command)
    repository = RecordingAgentJobRepository(
        job=job,
        payload=memory_job_payload(command, job),
    )
    service = RecordingMemoryService(
        error=MemoryProposalConflictError("private conflict detail")
    )
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    failed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="memory-worker-1",
    )

    assert failed.status == "failed"
    assert len(service.commands) == 1
    recorded = service.commands[0]
    assert recorded.user_id == command.user_id
    assert recorded.workspace_id == command.workspace_id
    assert recorded.session_id == command.session_id
    assert recorded.source_message_id == command.source_message_id
    assert recorded.decision == command.decision
    assert [entry["event"].event_type for entry in repository.events] == [
        "started",
        "failed",
    ]
    failure = repository.finalized[0]["failure"]
    assert failure.code == "memory_proposal_conflict"
    assert failure.summary == (
        "A pending memory proposal already exists for this category."
    )
    assert failure.retryable is False
    assert "private" not in str(failure)
    assert len(repository.reports) == 1
    report = repository.reports[0]
    assert report.status == "failed"
    assert report.title == "Memory proposal not created"
    assert report.summary == (
        "A pending memory proposal already exists for this category."
    )


@pytest.mark.asyncio
async def test_memory_worker_normalizes_collaboration_preferences_candidate(
) -> None:
    from memory_proposal_job_worker import MemoryProposalJobWorker

    command = make_command()
    job = make_job(command)
    payload = AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "decision": {
                "kind": "profile_candidate",
                "category": "collaboration_preferences",
                "canonical_value": "Prefers assembly over C",
                "evidence_text": "remember that I prefer assembly over C",
            },
            "clarification_selection": None,
            "source_message_text": (
                "remember that I prefer assembly over C"
            ),
            "memory_decision_present": False,
        },
    )
    repository = RecordingAgentJobRepository(job=job, payload=payload)
    service = RecordingMemoryService()
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="memory-worker-1",
    )

    assert completed.status == "completed"
    assert len(service.commands) == 1
    recorded = service.commands[0]
    assert recorded.source_message_text == (
        "remember that I prefer assembly over C"
    )
    assert recorded.decision.kind == "profile_candidate"
    assert recorded.decision.category == "user_requested_memory"
    assert recorded.decision.canonical_value == "Prefers assembly over C"
    assert recorded.decision.evidence_text == (
        "remember that I prefer assembly over C"
    )


@pytest.mark.asyncio
async def test_memory_worker_normalizes_communication_style_candidate(
) -> None:
    command = make_command()
    job = make_job(command)
    payload = raw_profile_candidate_payload(
        job,
        decision={
            "kind": "profile_candidate",
            "category": "communication_style",
            "value": "Prefers direct answers with concise tradeoffs",
            "evidence_text": (
                "Remember that I prefer direct answers with concise tradeoffs."
            ),
        },
        source_message_text=(
            "Remember that I prefer direct answers with concise tradeoffs."
        ),
    )

    completed, service, repository = await run_memory_worker_with_payload(
        payload
    )

    assert completed.status == "completed"
    assert repository.failed == []
    assert len(service.commands) == 1
    recorded = service.commands[0]
    assert recorded.decision.kind == "profile_candidate"
    assert recorded.decision.category == "user_requested_memory"
    assert recorded.decision.canonical_value == (
        "Prefers direct answers with concise tradeoffs"
    )
    assert recorded.decision.evidence_text == (
        "Remember that I prefer direct answers with concise tradeoffs."
    )


@pytest.mark.asyncio
async def test_memory_worker_unwraps_single_nested_profile_candidate(
) -> None:
    command = make_command()
    job = make_job(command)
    payload = raw_profile_candidate_payload(
        job,
        decision={
            "kind": "profile_candidate",
            "candidate": {
                "kind": "profile_candidate",
                "category": "communication_style",
                "canonical_value": "Prefers terse code review summaries",
                "evidence_text": (
                    "Remember that I prefer terse code review summaries."
                ),
            },
        },
        source_message_text=(
            "Remember that I prefer terse code review summaries."
        ),
    )

    completed, service, repository = await run_memory_worker_with_payload(
        payload
    )

    assert completed.status == "completed"
    assert repository.failed == []
    assert len(service.commands) == 1
    recorded = service.commands[0]
    assert recorded.decision.kind == "profile_candidate"
    assert recorded.decision.category == "user_requested_memory"
    assert recorded.decision.canonical_value == (
        "Prefers terse code review summaries"
    )
    assert recorded.decision.evidence_text == (
        "Remember that I prefer terse code review summaries."
    )


@pytest.mark.parametrize(
    ("decision", "source_message_text"),
    (
        (
            {
                "kind": "profile_candidate",
                "category": "response_length",
                "candidate": {
                    "kind": "profile_candidate",
                    "category": "communication_style",
                    "canonical_value": "Prefers concise answers",
                    "evidence_text": "Remember that I prefer concise answers.",
                },
            },
            "Remember that I prefer concise answers.",
        ),
        (
            {
                "kind": "profile_candidate",
                "candidate": {
                    "kind": "profile_candidate",
                    "category": "communication_style",
                    "canonical_value": "Prefers concise answers",
                },
            },
            "Remember that I prefer concise answers.",
        ),
        (
            {
                "candidate": {
                    "kind": "profile_candidate",
                    "category": "communication_style",
                    "canonical_value": "Prefers concise answers",
                    "evidence_text": "Remember that I prefer concise answers.",
                },
            },
            "Remember that I prefer concise answers.",
        ),
    ),
)
@pytest.mark.asyncio
async def test_memory_worker_rejects_invalid_nested_candidate_shapes(
    decision: dict[str, object],
    source_message_text: str,
) -> None:
    command = make_command()
    job = make_job(command)
    payload = raw_profile_candidate_payload(
        job,
        decision=decision,
        source_message_text=source_message_text,
    )

    completed, service, repository = await run_memory_worker_with_payload(
        payload
    )

    assert completed.status == "failed"
    assert service.commands == []
    assert len(repository.finalized) == 1
    failure = repository.finalized[0]["failure"]
    assert failure.code == "invalid_memory_candidate"
    assert failure.retryable is False


@pytest.mark.asyncio
async def test_memory_worker_rejects_normalized_candidate_without_exact_evidence(
) -> None:
    from memory_proposal_job_worker import MemoryProposalJobWorker
    from trusted_memory_service import TrustedMemoryService

    command = make_command()
    job = make_job(command)
    payload = raw_profile_candidate_payload(
        job,
        decision={
            "kind": "profile_candidate",
            "candidate": {
                "kind": "profile_candidate",
                "category": "communication_style",
                "canonical_value": "Prefers concise answers",
                "evidence_text": "Different source text.",
            },
        },
        source_message_text="Remember that I prefer concise answers.",
    )
    repository = RecordingAgentJobRepository(job=job, payload=payload)
    database = RecordingGovernedMemoryDatabase()
    worker = MemoryProposalJobWorker(
        agent_job_repository=repository,
        memory_service=TrustedMemoryService(
            database=database,
            clock=lambda: NOW + timedelta(minutes=1),
        ),
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="memory-worker-1",
    )

    assert completed is not None
    assert completed.status == "failed"
    assert database.calls == []
    failure = repository.finalized[0]["failure"]
    assert failure.code == "invalid_memory_candidate"
    assert failure.retryable is False
