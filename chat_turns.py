import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from schemas import (
    AgentActionReceipt,
    ChatResponse,
    MemoryDecisionRequest,
    MemoryProposalReceipt,
)


CHAT_TURN_SCHEMA_VERSION: Literal["1.0"] = "1.0"
CHAT_TURN_LEASE_DURATION = timedelta(seconds=120)
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class ChatTurnConflictError(RuntimeError):
    """Raised when one turn key is reused for a different request."""


class ChatTurnInProgressError(RuntimeError):
    """Raised when another owner holds an unexpired turn lease."""

    def __init__(self, retry_after_seconds: int) -> None:
        if (
            isinstance(retry_after_seconds, bool)
            or not isinstance(retry_after_seconds, int)
            or retry_after_seconds < 1
        ):
            raise ValueError(
                "retry_after_seconds must be a positive integer."
            )
        super().__init__("Chat turn is already in progress.")
        self.retry_after_seconds = retry_after_seconds


class ChatTurnOwnershipError(RuntimeError):
    """Raised when a worker no longer owns a chat turn lease."""


class ChatTurnStateError(RuntimeError):
    """Raised when durable chat-turn state is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class ChatTurnIds:
    turn_id: str
    user_message_id: str
    model_message_id: str


@dataclass(frozen=True, slots=True)
class ChatTurnRequest:
    project_id: str
    session_id: str
    user_id: str
    message: str
    memory_decision: MemoryDecisionRequest | None = None


@dataclass(frozen=True, slots=True)
class ChatTurnClaim:
    request: ChatTurnRequest
    ids: ChatTurnIds
    owner_token: str
    lease_expires_at: datetime
    resumed: bool
    precompleted_actions: tuple[AgentActionReceipt, ...] = ()
    precompleted_memory_proposals: tuple[MemoryProposalReceipt, ...] = ()


@dataclass(frozen=True, slots=True)
class ChatTurnReplay:
    response: ChatResponse


def validate_idempotency_key(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or _IDEMPOTENCY_KEY_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            "idempotency_key must be 1 through 128 ASCII letters, "
            "digits, underscores, or hyphens."
        )
    return value


def derive_chat_turn_ids(idempotency_key: str) -> ChatTurnIds:
    key = validate_idempotency_key(idempotency_key)
    turn_id = hashlib.sha256(key.encode("ascii")).hexdigest()
    return ChatTurnIds(
        turn_id=turn_id,
        user_message_id=f"turn--{turn_id}--user",
        model_message_id=f"turn--{turn_id}--model",
    )
