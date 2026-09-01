from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from agent_col_agent_jobs import (
    AgentJob,
    AgentJobEvent,
    AgentJobFailure,
    transition_agent_job,
)


def fixed_time(second: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, 0, second, tzinfo=UTC)


def make_agent_job(**overrides: object) -> AgentJob:
    values: dict[str, object] = {
        "job_id": "job-create-artifact-1",
        "user_id": "user-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "session_id": "session-1",
        "source_turn_id": "turn-1",
        "source_message_id": "message-1",
        "action_kind": "create_artifact",
        "status": "queued",
        "display_label": "Create repo_helper.sh",
        "agent_label": "Artifact Agent",
        "created_at": fixed_time(),
        "updated_at": fixed_time(),
        "idempotency_key": "idem-create-artifact-1",
    }
    values.update(overrides)
    return AgentJob(**values)


@pytest.mark.parametrize(
    "status",
    ["queued", "running", "completed", "failed", "cancelled"],
)
def test_agent_job_accepts_public_lifecycle_statuses(status: str) -> None:
    job = make_agent_job(status=status)

    assert job.status == status


def test_agent_job_projects_to_existing_queued_action_receipt() -> None:
    job = make_agent_job(
        status="running",
        lease_owner="worker-private-token",
        lease_expires_at=fixed_time() + timedelta(seconds=30),
        result_refs={"artifact_id": "artifact-1"},
    )

    receipt = job.to_queued_action_receipt()

    assert receipt.model_dump(mode="json") == {
        "job_id": "job-create-artifact-1",
        "action_kind": "create_artifact",
        "status": "running",
        "display_label": "Create repo_helper.sh",
        "created_at": "2026-09-01T12:00:00Z",
        "agent_label": "Artifact Agent",
    }


def test_agent_job_preserves_owner_workspace_session_and_retry_linkage() -> None:
    retry = make_agent_job(
        job_id="job-create-artifact-retry-1",
        retry_of_job_id="job-create-artifact-1",
        attempt_count=2,
    )

    assert retry.user_id == "user-1"
    assert retry.project_id == "project-1"
    assert retry.workspace_id == "workspace-1"
    assert retry.session_id == "session-1"
    assert retry.retry_of_job_id == "job-create-artifact-1"
    assert retry.attempt_count == 2


def test_agent_job_rejects_private_prompt_or_raw_agent_fields() -> None:
    with pytest.raises(ValidationError):
        make_agent_job(prompt_body="internal prompt")

    with pytest.raises(ValidationError):
        make_agent_job(raw_agent_id="agent-private-1")


def test_terminal_agent_job_cannot_transition_to_new_status() -> None:
    completed = make_agent_job(status="completed", updated_at=fixed_time(5))

    with pytest.raises(ValueError, match="terminal"):
        transition_agent_job(
            completed,
            status="running",
            updated_at=fixed_time(10),
        )


def test_terminal_agent_job_cannot_be_mutated_under_same_status() -> None:
    completed = make_agent_job(status="completed", updated_at=fixed_time(5))

    with pytest.raises(ValueError, match="terminal"):
        transition_agent_job(
            completed,
            status="completed",
            updated_at=fixed_time(10),
            result_refs={"artifact_id": "artifact-2"},
        )


def test_agent_job_transition_updates_status_and_failure_summary() -> None:
    running = make_agent_job(status="running", updated_at=fixed_time(5))
    failure = AgentJobFailure(
        code="provider_timeout",
        summary="Artifact generation timed out.",
        retryable=True,
    )

    failed = transition_agent_job(
        running,
        status="failed",
        updated_at=fixed_time(10),
        failure=failure,
    )

    assert failed.status == "failed"
    assert failed.updated_at == fixed_time(10)
    assert failed.failure_summary == failure


def test_agent_job_transition_revalidates_updated_fields() -> None:
    queued = make_agent_job(created_at=fixed_time(10), updated_at=fixed_time(10))

    with pytest.raises(ValidationError):
        transition_agent_job(
            queued,
            status="running",
            updated_at=fixed_time(5),
        )


def test_agent_job_event_rejects_private_metadata_keys() -> None:
    with pytest.raises(ValidationError):
        AgentJobEvent(
            event_id="event-1",
            job_id="job-create-artifact-1",
            event_type="progress",
            message="Generating artifact.",
            created_at=fixed_time(),
            status="running",
            metadata={"tool_payload": {"secret": "value"}},
        )


def test_agent_job_event_public_projection_is_user_safe() -> None:
    event = AgentJobEvent(
        event_id="event-1",
        job_id="job-create-artifact-1",
        event_type="progress",
        message="Generating artifact.",
        created_at=fixed_time(),
        status="running",
        metadata={"step": "draft"},
    )

    assert event.to_public_dict() == {
        "event_id": "event-1",
        "job_id": "job-create-artifact-1",
        "event_type": "progress",
        "message": "Generating artifact.",
        "created_at": "2026-09-01T12:00:00Z",
        "status": "running",
        "metadata": {"step": "draft"},
    }
