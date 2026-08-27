import json
import re
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from schemas import IdentifierStr, StrictModel


WORKING_STATE_CONTEXT_START = "[SERVER_VALIDATED_WORKING_STATE]"
WORKING_STATE_CONTEXT_END = "[/SERVER_VALIDATED_WORKING_STATE]"
WORKING_STATE_CONTEXT_MAX_CHARS = 5_000

WorkingStateText200 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
WorkingStateText240 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
]
WorkingStateText300 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
WorkingStateText400 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=400),
]
WorkingStateText500 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]

WorkingStateStatus = Literal["active", "empty"]
WorkingStateConfidence = Literal["low", "medium", "high"]
WorkingStateClarificationStatus = Literal["none", "useful", "blocking"]
WorkingStateBlockingStatus = Literal["not_blocking", "useful", "blocking"]


class WorkingStateQuestion(StrictModel):
    question: WorkingStateText240
    why_it_matters: WorkingStateText300
    blocking_status: WorkingStateBlockingStatus


class WorkingStateSnapshot(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    status: WorkingStateStatus = "active"
    authority: Literal["non_authoritative"] = "non_authoritative"
    user_id: IdentifierStr
    project_id: IdentifierStr
    session_id: IdentifierStr
    source_message_id: IdentifierStr | None = None
    request_summary: WorkingStateText200
    current_goal: WorkingStateText300
    intent_hypothesis: WorkingStateText500
    active_constraints: tuple[WorkingStateText240, ...] = Field(
        default_factory=tuple,
        max_length=6,
    )
    unresolved_questions: tuple[WorkingStateQuestion, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
    clarification_status: WorkingStateClarificationStatus
    next_step_hypothesis: WorkingStateText400
    confidence: WorkingStateConfidence
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def require_empty_state_to_have_no_working_detail(self) -> Self:
        if self.status == "empty" and (
            self.active_constraints or self.unresolved_questions
        ):
            raise ValueError("Empty working state cannot include details.")
        return self


def build_working_state_context(snapshot: WorkingStateSnapshot) -> str:
    if not isinstance(snapshot, WorkingStateSnapshot):
        raise TypeError("snapshot must be a WorkingStateSnapshot.")
    state_json = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)
    context = "\n".join(
        (
            WORKING_STATE_CONTEXT_START,
            (
                "This block is hidden internal working state. It is "
                "non-authoritative and may be stale. Use it only as Agent "
                "Col's current collaboration hypothesis. Current user "
                "messages, approved memory, workspace notes, persisted "
                "artifacts, and higher-priority instructions override it."
            ),
            state_json,
            WORKING_STATE_CONTEXT_END,
        )
    )
    if len(context) > WORKING_STATE_CONTEXT_MAX_CHARS:
        raise ValueError("Working state context exceeds the maximum length.")
    return context


def should_update_working_state(message: str, *, route: str | None = None) -> bool:
    if not isinstance(message, str):
        raise TypeError("message must be a string.")
    normalized = re.sub(r"\s+", " ", message).strip().lower()
    if not normalized:
        return False
    if route in {
        "artifact",
        "clarify",
        "source",
        "research",
        "requirements_verification",
    }:
        return True
    collaborative_markers = (
        "i want",
        "i need",
        "plan",
        "strategy",
        "proposal",
        "approach",
        "deploy",
        "artifact",
        "create",
        "make",
        "write",
        "clarify",
        "not sure",
        "unsure",
        "probably",
        "maybe",
        "actually",
        "what i meant",
        "instead",
        "change",
        "revise",
        "continue",
        "what did we decide",
        "where were we",
    )
    return any(marker in normalized for marker in collaborative_markers)
