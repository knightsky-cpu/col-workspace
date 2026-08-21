from collections.abc import Awaitable
from typing import Protocol

from database import (
    MemoryEngineError,
    MemoryProposalConflictError,
    MemoryProposalExpiredError,
    MemoryProposalNotFoundError,
    MemoryProposalOriginConflictError,
    MemoryProposalStateError,
    MemorySignalAlreadyActiveError,
)
from memory_routing_evaluation import MemoryRoutingScenario
from schemas import (
    ActiveMemorySignal,
    CollaborationProfile,
    MemoryDecisionRequest,
)
from trusted_memory_service import (
    MemoryDecisionCommand,
    ProposeMemorySignalCommand,
    TrustedMemoryMutationResult,
    TrustedMemoryProposalResult,
)


class _DatabaseHandle(Protocol):
    def save_message(
        self,
        session_id: str,
        role: str,
        text: str,
    ) -> Awaitable[str]: ...

    def close(self) -> None: ...


class _MemoryServiceHandle(Protocol):
    def propose_memory_signal(
        self,
        command: ProposeMemorySignalCommand,
    ) -> Awaitable[TrustedMemoryProposalResult]: ...

    def decide_memory_proposal(
        self,
        command: MemoryDecisionCommand,
    ) -> Awaitable[TrustedMemoryMutationResult]: ...


_STATE_SETUP_EXCEPTIONS = (
    MemoryEngineError,
    MemoryProposalConflictError,
    MemoryProposalExpiredError,
    MemoryProposalNotFoundError,
    MemoryProposalOriginConflictError,
    MemoryProposalStateError,
    MemorySignalAlreadyActiveError,
    ValueError,
)


class MemoryRoutingStateError(RuntimeError):
    """Raised when a stateful evaluation precondition cannot be established."""


class MemoryRoutingStateManager:
    """Create trusted Firestore preconditions for stateful routing checks."""

    def __init__(
        self,
        *,
        database: _DatabaseHandle,
        memory_service: _MemoryServiceHandle,
    ) -> None:
        self._database = database
        self._memory_service = memory_service

    async def prepare(
        self,
        scenario: MemoryRoutingScenario,
        *,
        user_id: str,
        session_id: str,
    ) -> MemoryDecisionRequest | None:
        """Persist one real provenance chain and return target decision data."""
        setup = scenario.state_setup
        if scenario.execution_mode != "stateful" or setup is None:
            raise MemoryRoutingStateError(
                "Stateful routing setup is not configured."
            )
        setup_session_id = f"{session_id}-setup"
        try:
            source_message_id = await self._database.save_message(
                setup_session_id,
                "user",
                setup.proposal_source_message,
            )
            proposal_result = (
                await self._memory_service.propose_memory_signal(
                    ProposeMemorySignalCommand(
                        user_id=user_id,
                        session_id=setup_session_id,
                        source_message_id=source_message_id,
                        source_message_text=setup.proposal_source_message,
                        memory_decision_present=False,
                        category=setup.category,
                        proposed_value=setup.proposed_value,
                    )
                )
            )
            self._validate_proposal_result(
                proposal_result,
                scenario,
            )

            if scenario.state_precondition == (
                "active_identical_preference"
            ):
                approval_result = (
                    await self._memory_service.decide_memory_proposal(
                        MemoryDecisionCommand(
                            user_id=user_id,
                            proposal_id=(
                                proposal_result.proposal.proposal_id
                            ),
                            decision="approve",
                            confirmation_channel="memory_api",
                            confirmation_session_id=None,
                            confirmation_message_id=None,
                        )
                    )
                )
                self._validate_active_precondition(
                    approval_result,
                    proposal_result.proposal.proposal_id,
                    scenario,
                )
                return None

            if scenario.state_precondition == "structured_memory_decision":
                if setup.target_decision == "none":
                    raise MemoryRoutingStateError(
                        "Structured decision is not configured."
                    )
                return MemoryDecisionRequest(
                    proposal_id=proposal_result.proposal.proposal_id,
                    decision=setup.target_decision,
                )
            raise MemoryRoutingStateError(
                "Stateful routing precondition is unsupported."
            )
        except MemoryRoutingStateError:
            raise
        except _STATE_SETUP_EXCEPTIONS:
            raise MemoryRoutingStateError(
                "Stateful routing setup failed."
            ) from None

    def close(self) -> None:
        """Close the Firestore client owned by this evaluation manager."""
        self._database.close()

    @staticmethod
    def _validate_proposal_result(
        result: TrustedMemoryProposalResult,
        scenario: MemoryRoutingScenario,
    ) -> None:
        setup = scenario.state_setup
        if (
            setup is None
            or result.action.action_name != "propose_memory_signal"
            or result.action.status != "completed"
            or result.proposal.category != setup.category
            or result.proposal.proposed_value != setup.proposed_value
        ):
            raise MemoryRoutingStateError(
                "Stateful proposal setup did not match its contract."
            )

    @staticmethod
    def _validate_active_precondition(
        result: TrustedMemoryMutationResult,
        proposal_id: str,
        scenario: MemoryRoutingScenario,
    ) -> None:
        setup = scenario.state_setup
        if setup is None or result.action.action_name != (
            "approve_memory_signal"
        ):
            raise MemoryRoutingStateError(
                "Stateful approval setup did not match its contract."
            )
        active_signal = MemoryRoutingStateManager._active_signal(
            result.profile,
            setup.category,
        )
        if (
            active_signal is None
            or active_signal.signal_id != proposal_id
            or active_signal.value != setup.proposed_value
        ):
            raise MemoryRoutingStateError(
                "Stateful active-memory precondition was not established."
            )

    @staticmethod
    def _active_signal(
        profile: CollaborationProfile,
        category: str,
    ) -> ActiveMemorySignal | None:
        return profile.active_preferences.get(
            category
        ) or profile.identity_context.get(category)
