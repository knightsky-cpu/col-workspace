from datetime import UTC, datetime, timedelta

import pytest

from agent_col_agent_jobs import AgentJob
from agent_job_payloads import AgentJobPayload
from database import MemoryProposalConflictError
from memory_candidate_decisions import ProfileCandidateDecision
from memory_proposals import ProposalTurnLease
from schemas import AgentActionReceipt, MemoryProposalReceiptV2
from trusted_memory_service import (
    NaturalMemoryCommand,
    NaturalMemoryProposalResult,
)


NOW = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)


class RecordingMemoryService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.commands: list[NaturalMemoryCommand] = []

    async def handle_natural_memory_decision(self, command):
        self.commands.append(command)
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
                    "response_length--e82366f7699ee2e39bff6a68154e09b7"
                ),
                category="response_length",
                proposed_value="concise",
                expires_at=NOW + timedelta(hours=1),
            ),
        )


class RecordingAgentJobRepository:
    def __init__(self, *, job, payload) -> None:
        self.job = job
        self.payload = payload
        self.leased = []
        self.events = []
        self.completed = []
        self.failed = []
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

    async def create_report(self, report):
        self.reports.append(report)
        return report


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
        turn_lease=ProposalTurnLease(
            turn_id="a" * 64,
            owner_token="owner-1",
        ),
    )


def make_job(command: NaturalMemoryCommand) -> AgentJob:
    return AgentJob(
        job_id="memory-job-1",
        user_id=command.user_id,
        project_id=command.workspace_id,
        workspace_id=command.workspace_id,
        session_id=command.session_id,
        source_turn_id=command.turn_lease.turn_id,
        source_message_id=command.source_message_id,
        action_kind="propose_memory_signal",
        status="queued",
        display_label="Memory proposal: response_length",
        agent_label="Memory Analyst",
        created_at=NOW,
        updated_at=NOW,
        idempotency_key="memory-proposal-1",
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
    assert recorded.turn_lease is None
    assert repository.leased[0]["action_kind"] == "propose_memory_signal"
    assert [entry["event"].event_type for entry in repository.events] == [
        "started",
        "completed",
    ]
    assert repository.completed[0]["result_refs"] == {
        "proposal_id": "response_length--e82366f7699ee2e39bff6a68154e09b7"
    }
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
    assert recorded.turn_lease is None
    assert [entry["event"].event_type for entry in repository.events] == [
        "started",
        "failed",
    ]
    failure = repository.failed[0]["failure"]
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
