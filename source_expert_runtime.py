from expert_contracts import ExpertStatus
from source_expert import (
    SourceExpertReceipts,
    build_source_receipts,
)
from source_expert_tool import (
    CompletedSourceExpertToolResponse,
    SourceExpertToolResponseError,
    parse_source_expert_tool_response,
)


class SourceExpertRuntimeError(RuntimeError):
    """Safe failure raised for an unusable Source Expert response."""

    def __init__(self, status: ExpertStatus) -> None:
        self.status = status
        super().__init__("Source Expert execution failed.")


class SourceExpertTurnTracker:
    """Validate Source FunctionTool responses and derive public receipts."""

    def __init__(self) -> None:
        self._response_observed = False
        self._receipts = SourceExpertReceipts()

    def observe(self, event: object) -> None:
        """Observe one ADK event without trusting model-authored prose."""
        get_function_responses = getattr(
            event,
            "get_function_responses",
            None,
        )
        function_responses = (
            get_function_responses()
            if callable(get_function_responses)
            else ()
        )
        for function_response in function_responses:
            if function_response.name != "analyze_source":
                continue
            if self._response_observed:
                raise SourceExpertRuntimeError(
                    ExpertStatus.INVALID_OUTPUT
                )
            self._response_observed = True
            try:
                parsed = parse_source_expert_tool_response(
                    function_response.response
                )
            except SourceExpertToolResponseError as exc:
                raise SourceExpertRuntimeError(
                    ExpertStatus.INVALID_OUTPUT
                ) from exc
            if isinstance(parsed, CompletedSourceExpertToolResponse):
                self._receipts = build_source_receipts(parsed.result)

    def finalize(self) -> SourceExpertReceipts:
        """Return only server-validated Source action and citation receipts."""
        return self._receipts
