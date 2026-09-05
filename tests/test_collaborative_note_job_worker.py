import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from agent_col_agent_jobs import AgentJob
from agent_job_payloads import AgentJobPayload
from collaborative_note_candidates import NoteCandidateDecision
from collaborative_note_service import (
    CollaborativeNoteProposalResult,
    NaturalCollaborativeNoteCommand,
)
from database import MemoryProposalConflictError
from schemas import AgentActionReceipt, CollaborativeNoteProposal


NOW = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)


class RecordingCollaborativeNoteService:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.error = error
        self.delay_seconds = delay_seconds
        self.commands: list[NaturalCollaborativeNoteCommand] = []
        self.resource_mutations: list[str] = []

    async def create_natural_proposal(self, command):
        self.commands.append(command)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        self.resource_mutations.append("collaborative_note_proposal")
        return CollaborativeNoteProposalResult(
            action=AgentActionReceipt(
                action_name="propose_collaborative_note",
                status="completed",
            ),
            proposal=CollaborativeNoteProposal(
                proposal_id="note-proposal-1",
                note_kind="constraint",
                title="API version",
                body="Use API version 2.",
                source_session_id="session-1",
                source_message_ids=["message-1"],
                expected_note_id=None,
                expected_revision=None,
                policy_version="1.0",
                status="pending",
                created_at=NOW,
                expires_at=NOW + timedelta(hours=24),
            ),
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
        assert user_id == self.job.user_id
        assert workspace_id == self.job.workspace_id
        assert job_id == self.job.job_id
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


def make_command() -> NaturalCollaborativeNoteCommand:
    return NaturalCollaborativeNoteCommand(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_id="message-1",
        source_message_text=(
            "Agent Col, note that this workspace must use API version 2."
        ),
        memory_decision_present=False,
        collaborative_note_decision_present=False,
        artifact_feedback_decision_present=False,
        decision=NoteCandidateDecision(
            note_kind="constraint",
            title="API version",
            body="Use API version 2.",
            evidence_text="this workspace must use API version 2",
        ),
        observed_at=NOW,
    )


def make_job(command: NaturalCollaborativeNoteCommand) -> AgentJob:
    return AgentJob(
        job_id="note-job-1",
        user_id=command.user_id,
        project_id=command.workspace_id,
        workspace_id=command.workspace_id,
        session_id=command.session_id,
        source_turn_id=command.source_message_id,
        source_message_id=command.source_message_id,
        action_kind="propose_collaborative_note",
        status="queued",
        display_label="Workspace note: API version",
        agent_label="Note Curator",
        created_at=NOW,
        updated_at=NOW,
        idempotency_key="note-proposal-1",
    )


@pytest.mark.asyncio
async def test_note_worker_completes_queued_note_proposal_from_private_payload(
) -> None:
    from collaborative_note_job_worker import (
        CollaborativeNoteProposalJobWorker,
        note_job_payload,
    )

    command = make_command()
    job = make_job(command)
    payload = note_job_payload(command, job)
    assert "turn_lease" not in payload.payload
    assert "owner_token" not in str(payload.payload)
    repository = RecordingAgentJobRepository(job=job, payload=payload)
    service = RecordingCollaborativeNoteService()
    worker = CollaborativeNoteProposalJobWorker(
        agent_job_repository=repository,
        note_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="note-worker-1",
    )

    assert completed.status == "completed"
    assert len(service.commands) == 1
    recorded = service.commands[0]
    assert recorded.user_id == command.user_id
    assert recorded.workspace_id == command.workspace_id
    assert recorded.session_id == command.session_id
    assert recorded.source_message_id == command.source_message_id
    assert recorded.source_message_text == command.source_message_text
    assert recorded.decision == command.decision
    assert repository.leased[0]["action_kind"] == "propose_collaborative_note"
    assert [entry["event"].event_type for entry in repository.events] == [
        "started",
        "completed",
    ]
    assert repository.completed[0]["result_refs"] == {
        "proposal_id": "note-proposal-1"
    }
    assert repository.failed == []
    assert len(repository.reports) == 1
    report = repository.reports[0]
    assert report.status == "completed"
    assert report.agent_label == "Note Curator"
    assert report.title == "Workspace note proposal pending review"
    assert report.summary == (
        "A workspace note proposal was created and is pending your review."
    )
    assert report.public_resource_label == "API version"


@pytest.mark.asyncio
async def test_note_worker_renews_lease_while_execution_remains_active(
) -> None:
    from collaborative_note_job_worker import (
        CollaborativeNoteProposalJobWorker,
        note_job_payload,
    )

    command = make_command()
    job = make_job(command)
    repository = RecordingAgentJobRepository(
        job=job,
        payload=note_job_payload(command, job),
    )
    worker = CollaborativeNoteProposalJobWorker(
        agent_job_repository=repository,
        note_service=RecordingCollaborativeNoteService(delay_seconds=0.03),
        clock=lambda: NOW + timedelta(minutes=1),
        renewal_interval_seconds=0.001,
    )

    completed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="note-worker-1",
    )
    renew_count = len(repository.renewed)
    await asyncio.sleep(0.01)

    assert completed.status == "completed"
    assert renew_count >= 1
    assert len(repository.renewed) == renew_count
    assert repository.renewed[0]["lease_owner"] == "note-worker-1"


@pytest.mark.asyncio
async def test_note_worker_renewal_failure_prevents_successful_completion(
) -> None:
    from agent_job_repository import AgentJobLeaseError
    from collaborative_note_job_worker import (
        CollaborativeNoteProposalJobWorker,
        note_job_payload,
    )

    command = make_command()
    job = make_job(command)
    repository = RecordingAgentJobRepository(
        job=job,
        payload=note_job_payload(command, job),
    )
    note_service = RecordingCollaborativeNoteService(delay_seconds=0.03)
    repository.renew_error = AgentJobLeaseError("lost lease")
    worker = CollaborativeNoteProposalJobWorker(
        agent_job_repository=repository,
        note_service=note_service,
        clock=lambda: NOW + timedelta(minutes=1),
        renewal_interval_seconds=0.001,
    )

    with pytest.raises(AgentJobLeaseError):
        await worker.run_one(
            user_id="user-1",
            workspace_id="workspace-1",
            lease_owner="note-worker-1",
        )

    assert repository.renewed
    assert repository.completed == []
    assert note_service.resource_mutations == []


@pytest.mark.asyncio
async def test_note_worker_records_conflict_failure_without_private_details(
) -> None:
    from collaborative_note_job_worker import (
        CollaborativeNoteProposalJobWorker,
        note_job_payload,
    )

    command = make_command()
    job = make_job(command)
    repository = RecordingAgentJobRepository(
        job=job,
        payload=note_job_payload(command, job),
    )
    service = RecordingCollaborativeNoteService(
        error=MemoryProposalConflictError("private conflict detail")
    )
    worker = CollaborativeNoteProposalJobWorker(
        agent_job_repository=repository,
        note_service=service,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    failed = await worker.run_one(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="note-worker-1",
    )

    assert failed.status == "failed"
    assert len(service.commands) == 1
    assert [entry["event"].event_type for entry in repository.events] == [
        "started",
        "failed",
    ]
    failure = repository.failed[0]["failure"]
    assert failure.code == "collaborative_note_proposal_conflict"
    assert failure.summary == "Workspace note proposal could not be created."
    assert failure.retryable is False
    assert "private" not in str(failure)
    assert len(repository.reports) == 1
    report = repository.reports[0]
    assert report.status == "failed"
    assert report.title == "Workspace note proposal not created"
    assert report.summary == "Workspace note proposal could not be created."
