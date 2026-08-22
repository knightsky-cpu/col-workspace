import time
from types import SimpleNamespace

import pytest

from expert_contracts import ExpertStatus
from source_expert import SourceExpertResult
from source_expert_service import SourceExpertServiceError


def completed_source_result() -> SourceExpertResult:
    return SourceExpertResult.model_validate(
        {
            "capability": "source",
            "status": "completed",
            "summary": "Source analysis produced one grounded statement.",
            "payload": {
                "documents": [
                    {
                        "source_id": "source-1",
                        "url": "https://example.com/",
                        "retrieval_status": "retrieved",
                        "evidence_summary": (
                            "Example Domain is reserved for documentation."
                        ),
                    }
                ],
                "facts": [
                    {
                        "text": (
                            "Example Domain is reserved for documentation."
                        ),
                        "source_ids": ["source-1"],
                    }
                ],
                "requirements": [],
                "constraints": [],
                "assumptions": [],
                "open_questions": [],
                "sources": [
                    {
                        "source_id": "source-1",
                        "uri": "https://example.com/",
                        "label": "Example Domain",
                    }
                ],
            },
            "evidence": {
                "source_ids": ["source-1"],
                "grounded_statement_count": 1,
                "grounding_support_count": 1,
            },
        }
    )


class RecordingSourceService:
    def __init__(
        self,
        result: SourceExpertResult,
        *,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def registered_tool(service: RecordingSourceService):
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationRegistry,
    )
    from source_expert_tool import create_source_expert_tool

    registry = ExpertDelegationRegistry()
    token = registry.register_turn(
        budget=ExpertDelegationBudget(),
        deadline=time.monotonic() + 90,
    )
    return (
        create_source_expert_tool(
            source_service=service,
            delegation_registry=registry,
        ),
        token,
    )


def test_source_tool_description_exposes_multi_url_comparison_scope() -> None:
    service = RecordingSourceService(completed_source_result())
    tool, _token = registered_tool(service)

    assert "one to three" in tool.description
    assert "compare" in tool.description


@pytest.mark.asyncio
async def test_source_tool_claims_and_returns_validated_completed_result(
) -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationRegistry,
    )
    from source_expert_tool import (
        CompletedSourceExpertToolResponse,
        create_source_expert_tool,
        parse_source_expert_tool_response,
    )

    service = RecordingSourceService(completed_source_result())
    registry = ExpertDelegationRegistry()
    token = registry.register_turn(
        budget=ExpertDelegationBudget(),
        deadline=time.monotonic() + 90,
    )
    tool = create_source_expert_tool(
        source_service=service,
        delegation_registry=registry,
    )

    raw_response = await tool.run_async(
        args={
            "objective": "  Identify the documented purpose.  ",
            "urls": ["https://example.com/"],
            "constraints": ["  Use only the supplied source.  "],
        },
        tool_context=SimpleNamespace(
            state={"expert_delegation_token": token}
        ),
    )
    parsed = parse_source_expert_tool_response(raw_response)

    assert isinstance(parsed, CompletedSourceExpertToolResponse)
    assert parsed.result.status is ExpertStatus.COMPLETED
    assert parsed.result.payload is not None
    assert parsed.result.payload.facts[0].text == (
        "Example Domain is reserved for documentation."
    )
    assert service.requests[0].objective == (
        "Identify the documented purpose."
    )
    assert service.requests[0].constraints == (
        "Use only the supplied source.",
    )


@pytest.mark.filterwarnings(
    "ignore:\\[EXPERIMENTAL\\].*JSON_SCHEMA_FOR_FUNC_DECL.*:UserWarning"
)
def test_source_tool_exposes_only_bounded_task_fields_to_model() -> None:
    from google.adk.tools import FunctionTool

    service = RecordingSourceService(completed_source_result())
    tool, _ = registered_tool(service)

    declaration = tool._get_declaration()

    assert isinstance(tool, FunctionTool)
    assert tool.name == "analyze_source"
    assert declaration is not None
    schema = declaration.parameters_json_schema
    assert schema is not None
    assert set(schema["properties"]) == {
        "objective",
        "urls",
        "constraints",
    }
    assert schema["required"] == ["objective", "urls", "constraints"]
    assert "expert_delegation_token" not in declaration.model_dump_json()


@pytest.mark.asyncio
async def test_source_tool_rejects_invalid_url_and_consumes_attempt() -> None:
    from source_expert_tool import (
        FailedSourceExpertToolResponse,
        parse_source_expert_tool_response,
    )

    service = RecordingSourceService(completed_source_result())
    tool, token = registered_tool(service)
    context = SimpleNamespace(
        state={"expert_delegation_token": token}
    )

    first = parse_source_expert_tool_response(
        await tool.run_async(
            args={
                "objective": "Inspect the source.",
                "urls": ["http://127.0.0.1/private"],
                "constraints": [],
            },
            tool_context=context,
        )
    )
    second = parse_source_expert_tool_response(
        await tool.run_async(
            args={
                "objective": "Inspect the source.",
                "urls": ["https://example.com/"],
                "constraints": [],
            },
            tool_context=context,
        )
    )

    assert isinstance(first, FailedSourceExpertToolResponse)
    assert first.status is ExpertStatus.REJECTED_INPUT
    assert isinstance(second, FailedSourceExpertToolResponse)
    assert second.status is ExpertStatus.REJECTED_INPUT
    assert service.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    (
        {},
        {"expert_delegation_token": None},
        {"expert_delegation_token": "not-a-server-token"},
    ),
)
async def test_source_tool_fails_safely_for_invalid_server_context(
    state: dict[str, object],
) -> None:
    from source_expert_tool import (
        FailedSourceExpertToolResponse,
        parse_source_expert_tool_response,
    )

    service = RecordingSourceService(completed_source_result())
    tool, _ = registered_tool(service)

    parsed = parse_source_expert_tool_response(
        await tool.run_async(
            args={
                "objective": "Inspect the source.",
                "urls": ["https://example.com/"],
                "constraints": [],
            },
            tool_context=SimpleNamespace(state=state),
        )
    )

    assert isinstance(parsed, FailedSourceExpertToolResponse)
    assert parsed.status is ExpertStatus.UNAVAILABLE
    assert parsed.message == "Source analysis could not be completed."
    assert service.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "service_status",
    (
        ExpertStatus.TIMED_OUT,
        ExpertStatus.UNAVAILABLE,
        ExpertStatus.INVALID_OUTPUT,
    ),
)
async def test_source_tool_contains_service_failures(
    service_status: ExpertStatus,
) -> None:
    from source_expert_tool import (
        FailedSourceExpertToolResponse,
        parse_source_expert_tool_response,
    )

    service = RecordingSourceService(
        completed_source_result(),
        error=SourceExpertServiceError(service_status),
    )
    tool, token = registered_tool(service)

    parsed = parse_source_expert_tool_response(
        await tool.run_async(
            args={
                "objective": "Inspect the source.",
                "urls": ["https://example.com/"],
                "constraints": [],
            },
            tool_context=SimpleNamespace(
                state={"expert_delegation_token": token}
            ),
        )
    )

    assert isinstance(parsed, FailedSourceExpertToolResponse)
    assert parsed.status is service_status
    assert parsed.message == "Source analysis could not be completed."


@pytest.mark.asyncio
async def test_source_tool_rejects_noncompleted_service_result() -> None:
    from source_expert_tool import (
        FailedSourceExpertToolResponse,
        parse_source_expert_tool_response,
    )

    service = RecordingSourceService(
        SourceExpertResult(status=ExpertStatus.INVALID_OUTPUT)
    )
    tool, token = registered_tool(service)

    parsed = parse_source_expert_tool_response(
        await tool.run_async(
            args={
                "objective": "Inspect the source.",
                "urls": ["https://example.com/"],
                "constraints": [],
            },
            tool_context=SimpleNamespace(
                state={"expert_delegation_token": token}
            ),
        )
    )

    assert isinstance(parsed, FailedSourceExpertToolResponse)
    assert parsed.status is ExpertStatus.INVALID_OUTPUT


@pytest.mark.parametrize(
    "invalid_response",
    (
        {
            "status": "unavailable",
            "message": "Source analysis could not be completed.",
            "private_detail": "must-not-survive",
        },
        {
            "status": "completed",
            "result": {
                "capability": "source",
                "status": "completed",
            },
        },
        {
            "status": "completed",
            "result": {
                "capability": "source",
                "status": "invalid_output",
            },
        },
        {"status": "fabricated"},
        "private-response",
    ),
)
def test_source_tool_parser_rejects_malformed_envelopes(
    invalid_response: object,
) -> None:
    from source_expert_tool import (
        SourceExpertToolResponseError,
        parse_source_expert_tool_response,
    )

    with pytest.raises(SourceExpertToolResponseError) as exc_info:
        parse_source_expert_tool_response(invalid_response)

    assert str(exc_info.value) == "Source Expert tool response is invalid."
