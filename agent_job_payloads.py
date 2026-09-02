from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent_col_agent_jobs import AgentJobKind
from schemas import IdentifierStr, StrictModel


class AgentJobPayload(StrictModel):
    """Private backend work payload for an AgentJob."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    job_id: IdentifierStr
    user_id: IdentifierStr
    project_id: IdentifierStr
    workspace_id: IdentifierStr
    session_id: IdentifierStr
    source_turn_id: IdentifierStr
    source_message_id: IdentifierStr
    action_kind: AgentJobKind
    created_at: datetime
    payload: dict[str, object] = Field(min_length=1)

    @field_validator("payload")
    @classmethod
    def validate_payload_is_json_safe(
        cls,
        value: dict[str, object],
    ) -> dict[str, object]:
        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must be JSON-serializable.") from exc
        return value

    @model_validator(mode="after")
    def validate_created_at(self) -> Self:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware.")
        return self
