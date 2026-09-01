from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, Self, TypeAlias

from pydantic import ConfigDict, Field, field_validator, model_validator

from schemas import (
    DisplayLabelStr,
    IdentifierStr,
    QueuedActionReceipt,
    StrictModel,
)


AgentJobStatus: TypeAlias = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]
AgentJobKind: TypeAlias = Literal[
    "create_artifact",
    "propose_collaborative_note",
    "propose_memory_signal",
    "retrieve_chat_context",
]
AgentJobEventType: TypeAlias = Literal[
    "queued",
    "started",
    "progress",
    "completed",
    "failed",
    "cancelled",
]

TERMINAL_AGENT_JOB_STATUSES: frozenset[AgentJobStatus] = frozenset(
    {"completed", "failed", "cancelled"}
)
_RECEIPT_ACTION_KINDS = frozenset(
    {"create_artifact", "propose_collaborative_note", "propose_memory_signal"}
)
_PRIVATE_METADATA_KEYS = frozenset(
    {
        "credentials",
        "internal_prompt",
        "model_reasoning",
        "private_context",
        "prompt",
        "prompt_body",
        "raw_agent_id",
        "raw_prompt",
        "service_account",
        "tool_payload",
    }
)


class AgentJobFailure(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: IdentifierStr
    summary: DisplayLabelStr
    retryable: bool = False


class AgentJob(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: IdentifierStr
    user_id: IdentifierStr
    project_id: IdentifierStr
    workspace_id: IdentifierStr
    session_id: IdentifierStr
    source_turn_id: IdentifierStr
    source_message_id: IdentifierStr
    action_kind: AgentJobKind
    status: AgentJobStatus
    display_label: DisplayLabelStr
    agent_label: DisplayLabelStr
    created_at: datetime
    updated_at: datetime
    idempotency_key: IdentifierStr
    attempt_count: int = Field(default=1, ge=1)
    lease_owner: IdentifierStr | None = None
    lease_expires_at: datetime | None = None
    result_refs: dict[str, IdentifierStr] = Field(default_factory=dict)
    failure_summary: AgentJobFailure | None = None
    retry_of_job_id: IdentifierStr | None = None

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at.")
        return self

    def to_queued_action_receipt(self) -> QueuedActionReceipt:
        if self.action_kind not in _RECEIPT_ACTION_KINDS:
            raise ValueError(
                f"{self.action_kind!r} cannot be projected as a queued action."
            )
        return QueuedActionReceipt(
            job_id=self.job_id,
            action_kind=self.action_kind,
            status=self.status,
            display_label=self.display_label,
            created_at=self.created_at,
            agent_label=self.agent_label,
        )


class AgentJobSnapshot(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job: AgentJob
    events: tuple[AgentJobEvent, ...] = ()


class AgentJobEvent(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: IdentifierStr
    job_id: IdentifierStr
    event_type: AgentJobEventType
    message: DisplayLabelStr
    created_at: datetime
    status: AgentJobStatus
    public_visibility: bool = True
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_public_metadata(cls, value: object) -> object:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("metadata must be an object.")
        _reject_private_metadata_keys(value)
        return value

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json",
            exclude={"public_visibility"},
            exclude_none=True,
        )


def transition_agent_job(
    job: AgentJob,
    *,
    status: AgentJobStatus,
    updated_at: datetime,
    lease_owner: str | None = None,
    lease_expires_at: datetime | None = None,
    result_refs: dict[str, str] | None = None,
    failure: AgentJobFailure | None = None,
) -> AgentJob:
    if job.status in TERMINAL_AGENT_JOB_STATUSES:
        raise ValueError("Cannot transition a terminal AgentJob.")

    updates: dict[str, object] = {
        "status": status,
        "updated_at": updated_at,
    }
    if lease_owner is not None:
        updates["lease_owner"] = lease_owner
    if lease_expires_at is not None:
        updates["lease_expires_at"] = lease_expires_at
    if result_refs is not None:
        updates["result_refs"] = result_refs
    if failure is not None:
        updates["failure_summary"] = failure

    data = job.model_dump(mode="python")
    data.update(updates)
    return AgentJob.model_validate(data)


def _reject_private_metadata_keys(value: Mapping[object, object]) -> None:
    for key, child in value.items():
        if isinstance(key, str) and key.lower() in _PRIVATE_METADATA_KEYS:
            raise ValueError(f"metadata key {key!r} is not public-safe.")
        if isinstance(child, Mapping):
            _reject_private_metadata_keys(child)
