from typing import cast

from google.adk.events import Event

from expert_contracts import ExpertCapability, ExpertStatus
from expert_delegation import ExpertDelegationBudget
from research_expert import (
    ResearchExpertReceipts,
    build_research_receipts,
    normalize_research_event,
    normalize_research_failure,
)


class ResearchExpertRuntimeError(RuntimeError):
    """Safe failure raised for an unusable Research Expert attempt."""

    def __init__(self, status: ExpertStatus) -> None:
        self.status = status
        super().__init__("Research Expert execution failed.")


class ResearchExpertTurnTracker:
    """Validate Research Expert attempts and receipts within one turn."""

    def __init__(
        self,
        *,
        budget: ExpertDelegationBudget | None = None,
    ) -> None:
        self._budget = budget or ExpertDelegationBudget()
        self._claims = 0
        self._results = 0
        self._receipts = ResearchExpertReceipts()

    async def observe(self, event: Event | object) -> None:
        """Observe one ADK event before the runner requests the next event."""
        get_function_calls = getattr(event, "get_function_calls", None)
        function_calls = (
            get_function_calls() if callable(get_function_calls) else ()
        )
        for function_call in function_calls:
            if function_call.name != "research_expert":
                continue
            depth = (
                1
                if getattr(event, "author", None) == "Agent_Col"
                else 2
            )
            await self._budget.claim(
                ExpertCapability.RESEARCH,
                depth=depth,
            )
            self._claims += 1

        if getattr(event, "author", None) != "research_expert":
            return
        error_code = getattr(event, "error_code", None)
        if error_code is not None:
            self._require_pending_claim()
            result = normalize_research_failure(
                self._failure_status(error_code)
            )
            self._results += 1
            raise ResearchExpertRuntimeError(result.status)
        if getattr(event, "output", None) is None:
            return
        self._require_pending_claim()
        result = normalize_research_event(cast(Event, event))
        self._results += 1
        if result.status is not ExpertStatus.COMPLETED:
            raise ResearchExpertRuntimeError(result.status)
        self._receipts = build_research_receipts(result)

    def _require_pending_claim(self) -> None:
        if self._results >= self._claims:
            raise ResearchExpertRuntimeError(ExpertStatus.INVALID_OUTPUT)

    @staticmethod
    def _failure_status(error_code: str) -> ExpertStatus:
        if error_code == "ValidationError":
            return ExpertStatus.REJECTED_INPUT
        if error_code == "NodeTimeoutError":
            return ExpertStatus.TIMED_OUT
        return ExpertStatus.UNAVAILABLE

    def finalize(self) -> ResearchExpertReceipts:
        """Return server-derived receipts after the runner finishes."""
        if self._results != self._claims:
            raise ResearchExpertRuntimeError(ExpertStatus.INVALID_OUTPUT)
        return self._receipts
