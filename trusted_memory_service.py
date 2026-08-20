import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from database import MemoryEngine
from memory_policy import (
    MEMORY_CATEGORY_ORDER,
    ConfirmationChannel,
    MemoryCategory,
    MemoryDecision,
)
from schemas import (
    AgentActionReceipt,
    CollaborationProfile,
    MemoryEvent,
    MemoryProposal,
)


@dataclass(frozen=True, slots=True)
class MemoryDecisionCommand:
    """Describe one explicit decision about a pending memory proposal."""

    user_id: str
    proposal_id: str
    decision: MemoryDecision
    confirmation_channel: ConfirmationChannel
    confirmation_session_id: str | None
    confirmation_message_id: str | None


@dataclass(frozen=True, slots=True)
class RevokeMemorySignalCommand:
    """Describe one explicit request to stop using a memory signal."""

    user_id: str
    signal_id: str


@dataclass(frozen=True, slots=True)
class DeleteMemorySignalCommand:
    """Describe one explicit hard-deletion request for a memory signal."""

    user_id: str
    signal_id: str


@dataclass(frozen=True, slots=True)
class InspectMemoryCommand:
    """Describe one bounded governed-memory inspection request."""

    user_id: str
    after_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class TrustedMemoryMutationResult:
    """Return a completed deterministic memory action and profile."""

    action: AgentActionReceipt
    profile: CollaborationProfile


@dataclass(frozen=True, slots=True)
class TrustedMemoryInspectionResult:
    """Return a bounded governed-memory inspection page."""

    profile: CollaborationProfile
    unresolved_proposals: tuple[MemoryProposal, ...]
    events: tuple[MemoryEvent, ...]
    next_event_id: str | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TrustedMemoryService:
    """Coordinate deterministic governed-memory persistence operations."""

    def __init__(
        self,
        *,
        database: MemoryEngine,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._database = database
        self._clock = clock

    async def inspect_memory(
        self,
        command: InspectMemoryCommand,
    ) -> TrustedMemoryInspectionResult:
        """Load one bounded page of governed collaboration memory."""
        result = await self._database.get_memory_inspection(
            command.user_id,
            observed_at=self._clock(),
            after_event_id=command.after_event_id,
        )
        return TrustedMemoryInspectionResult(
            profile=result.profile,
            unresolved_proposals=result.unresolved_proposals,
            events=result.events,
            next_event_id=result.next_event_id,
        )

    async def decide_memory_proposal(
        self,
        command: MemoryDecisionCommand,
    ) -> TrustedMemoryMutationResult:
        """Apply one structured approval or rejection decision."""
        self._validate_confirmation(command)
        category = self._category_from_identifier(command.proposal_id)
        observed_at = self._clock()
        if command.decision == "approve":
            result = await self._database.approve_memory_proposal(
                command.user_id,
                category,
                command.proposal_id,
                confirmation_channel=command.confirmation_channel,
                confirmation_session_id=command.confirmation_session_id,
                confirmation_message_id=command.confirmation_message_id,
                observed_at=observed_at,
            )
            action_name = "approve_memory_signal"
        elif command.decision == "reject":
            result = await self._database.reject_memory_proposal(
                command.user_id,
                category,
                command.proposal_id,
                observed_at=observed_at,
            )
            action_name = "reject_memory_signal"
        else:
            raise ValueError("Unsupported memory decision.")
        return TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name=action_name,
                status="completed",
            ),
            profile=result.profile,
        )

    async def revoke_memory_signal(
        self,
        command: RevokeMemorySignalCommand,
    ) -> TrustedMemoryMutationResult:
        """Revoke one active memory signal through the memory API."""
        category = self._category_from_identifier(command.signal_id)
        result = await self._database.revoke_memory_signal(
            command.user_id,
            category,
            command.signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=self._clock(),
        )
        return TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="revoke_memory_signal",
                status="completed",
            ),
            profile=result.profile,
        )

    async def delete_memory_signal(
        self,
        command: DeleteMemorySignalCommand,
    ) -> TrustedMemoryMutationResult:
        """Hard-delete one signal's bounded memory artifacts."""
        category = self._category_from_identifier(command.signal_id)
        result = await self._database.delete_memory_signal(
            command.user_id,
            category,
            command.signal_id,
        )
        return TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="delete_memory_signal",
                status="completed",
            ),
            profile=result.profile,
        )

    @staticmethod
    def _category_from_identifier(identifier: object) -> MemoryCategory:
        if not isinstance(identifier, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            identifier,
        ) is None:
            raise ValueError("Memory identifier must be valid.")
        for category in MEMORY_CATEGORY_ORDER:
            if identifier.startswith(f"{category}--"):
                return cast(MemoryCategory, category)
        raise ValueError("Memory identifier has no governed category.")

    @staticmethod
    def _validate_confirmation(command: MemoryDecisionCommand) -> None:
        if command.confirmation_channel == "chat_decision":
            for field_name, value in (
                (
                    "confirmation_session_id",
                    command.confirmation_session_id,
                ),
                (
                    "confirmation_message_id",
                    command.confirmation_message_id,
                ),
            ):
                if not isinstance(value, str) or re.fullmatch(
                    r"[A-Za-z0-9_-]{1,128}",
                    value,
                ) is None:
                    raise ValueError(
                        f"{field_name} must be a valid identifier."
                    )
            return
        if command.confirmation_channel == "memory_api":
            if (
                command.confirmation_session_id is not None
                or command.confirmation_message_id is not None
            ):
                raise ValueError(
                    "Memory API confirmation IDs must be omitted."
                )
            return
        raise ValueError("confirmation_channel is invalid.")
