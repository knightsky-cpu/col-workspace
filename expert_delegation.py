import asyncio
from dataclasses import dataclass
from enum import StrEnum

from expert_contracts import ExpertCapability


class ExpertDelegationDenialReason(StrEnum):
    """Internal reason a specialist delegation was denied."""

    ATTEMPT_BUDGET_EXHAUSTED = "attempt_budget_exhausted"
    CAPABILITY_ALREADY_CLAIMED = "capability_already_claimed"
    INVALID_CAPABILITY = "invalid_capability"
    INVALID_DEPTH = "invalid_depth"


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
