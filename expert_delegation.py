import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import secrets
import time

from expert_contracts import ExpertCapability


class ExpertDelegationDenialReason(StrEnum):
    """Internal reason a specialist delegation was denied."""

    ATTEMPT_BUDGET_EXHAUSTED = "attempt_budget_exhausted"
    CAPABILITY_ALREADY_CLAIMED = "capability_already_claimed"
    INVALID_CAPABILITY = "invalid_capability"
    INVALID_DEPTH = "invalid_depth"
    INSUFFICIENT_TIME_REMAINING = "insufficient_time_remaining"
    TURN_NOT_REGISTERED = "turn_not_registered"


class ExpertDelegationDeniedError(RuntimeError):
    """Safe failure raised when an invocation cannot claim an expert."""

    def __init__(self, reason: ExpertDelegationDenialReason) -> None:
        self.reason = reason
        super().__init__("Expert delegation denied.")


@dataclass(frozen=True, slots=True)
class ExpertDelegationClaim:
    """Immutable receipt for one invocation-scoped expert attempt."""

    capability: ExpertCapability
    attempt_number: int


class ExpertDelegationBudget:
    """Atomically bounds specialist attempts within one supervisor turn."""

    _MAX_ATTEMPTS = 2

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._claims: list[ExpertDelegationClaim] = []

    async def claim(
        self,
        capability: ExpertCapability,
        *,
        depth: int,
    ) -> ExpertDelegationClaim:
        """Claim one specialist attempt or fail without exposing inputs."""
        if not isinstance(capability, ExpertCapability):
            raise ExpertDelegationDeniedError(
                ExpertDelegationDenialReason.INVALID_CAPABILITY
            )
        if type(depth) is not int or depth != 1:
            raise ExpertDelegationDeniedError(
                ExpertDelegationDenialReason.INVALID_DEPTH
            )
        async with self._lock:
            if any(
                claim.capability is capability for claim in self._claims
            ):
                raise ExpertDelegationDeniedError(
                    ExpertDelegationDenialReason.CAPABILITY_ALREADY_CLAIMED
                )
            if len(self._claims) >= self._MAX_ATTEMPTS:
                raise ExpertDelegationDeniedError(
                    ExpertDelegationDenialReason.ATTEMPT_BUDGET_EXHAUSTED
                )

            claim = ExpertDelegationClaim(
                capability=capability,
                attempt_number=len(self._claims) + 1,
            )
            self._claims.append(claim)
            return claim


@dataclass(frozen=True, slots=True)
class _RegisteredTurn:
    budget: ExpertDelegationBudget
    deadline: float


class ExpertDelegationRegistry:
    """Resolve server-owned turn tokens to invocation-scoped budgets."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._lock = asyncio.Lock()
        self._turns: dict[str, _RegisteredTurn] = {}

    def register_turn(
        self,
        *,
        budget: ExpertDelegationBudget,
        deadline: float,
    ) -> str:
        token = secrets.token_urlsafe(32)
        self._turns[token] = _RegisteredTurn(
            budget=budget,
            deadline=deadline,
        )
        return token

    async def claim(
        self,
        token: str,
        capability: ExpertCapability,
        *,
        depth: int,
        minimum_remaining_seconds: float,
    ) -> ExpertDelegationClaim:
        async with self._lock:
            turn = self._turns.get(token)
            if turn is None:
                raise ExpertDelegationDeniedError(
                    ExpertDelegationDenialReason.TURN_NOT_REGISTERED
                )
            if turn.deadline - self._clock() < minimum_remaining_seconds:
                raise ExpertDelegationDeniedError(
                    ExpertDelegationDenialReason.INSUFFICIENT_TIME_REMAINING
                )
            return await turn.budget.claim(capability, depth=depth)

    def release_turn(self, token: str) -> None:
        self._turns.pop(token, None)
