from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


NOW = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)


def test_agent_job_report_model_keeps_internal_ids_private() -> None:
    from agent_col_agent_jobs import AgentJobReport

    report = AgentJobReport(
        report_id="report-1",
        job_id="job-1",
        user_id="user-1",
        project_id="project-1",
        workspace_id="workspace-1",
        session_id="session-1",
        action_kind="propose_memory_signal",
        agent_label="Memory Analyst",
        status="completed",
        title="Memory proposal pending review",
        summary="A memory proposal was created and is pending your review.",
        public_resource_label="Prefers C over Python",
        created_at=NOW,
    )

    assert report.job_id == "job-1"
    assert report.session_id == "session-1"


@pytest.mark.parametrize(
    "metadata",
    (
        {"job_id": "job-1"},
        {"session_id": "session-1"},
        {"source_turn_id": "turn-1"},
        {"source_message_id": "message-1"},
        {"tool_payload": "private"},
        {"raw_prompt": "private"},
        {"owner_token": "private"},
    ),
)
def test_agent_job_report_rejects_private_public_metadata(
    metadata: dict[str, str],
) -> None:
    from agent_col_agent_jobs import AgentJobReport

    with pytest.raises(ValidationError):
        AgentJobReport(
            report_id="report-1",
            job_id="job-1",
            user_id="user-1",
            project_id="project-1",
            workspace_id="workspace-1",
            session_id="session-1",
            action_kind="propose_memory_signal",
            agent_label="Memory Analyst",
            status="completed",
            title="Memory proposal pending review",
            summary="A memory proposal was created and is pending your review.",
            public_resource_label="Prefers C over Python",
            public_metadata=metadata,
            created_at=NOW,
        )
