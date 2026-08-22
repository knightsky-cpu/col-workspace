import importlib

import pytest
from pydantic import ValidationError

from agent_col_routing_v2 import AgentColRoutingDirective
from computational_expert import (
    ComputationExpertInput,
    ComputationExpertResult,
    build_computation_receipts,
    normalize_computation_events,
    project_computation_responder_result,
)
from expert_contracts import ExpertStatus
from google.adk.events import Event
from google.genai import types
from research_expert import ResearchExpertResult, build_research_receipts
from source_expert import SourceExpertResult, build_source_receipts


def load_context_v2():
    try:
        return importlib.import_module("agent_col_responder_context_v2")
    except ModuleNotFoundError:
        pytest.fail("agent_col_responder_context_v2 has not been implemented")


def completed_computation_result():
    request = ComputationExpertInput.model_validate(
        {
            "objective": "Calculate the mean.",
            "inputs": {
                "series": [{"name": "values", "values": [1, 2, 3]}],
                "expression": None,
            },
            "required_precision": {
                "mode": "decimal_places",
                "digits": 2,
            },
        }
    )
    full = normalize_computation_events(
        request,
        (
            Event(
                author="computational_expert",
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            executable_code=types.ExecutableCode(
                                language=types.Language.PYTHON,
                                code="print('RAW_CODE_MARKER')",
                            )
                        ),
                        types.Part(
                            code_execution_result=types.CodeExecutionResult(
                                outcome=types.Outcome.OUTCOME_OK,
                                output="RAW_OUTPUT_MARKER\n",
                            )
                        ),
                        types.Part.from_text(
                            text="The arithmetic mean is 2.00."
                        ),
                    ],
                ),
            ),
        ),
    )
    return project_computation_responder_result(full)


def completed_source_result() -> SourceExpertResult:
    return SourceExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "One grounded source statement.",
            "payload": {
                "documents": [
                    {
                        "source_id": "source-1",
                        "url": "https://example.com/",
                        "retrieval_status": "retrieved",
                        "evidence_summary": "Example evidence.",
                    }
                ],
                "facts": [
                    {"text": "Example evidence.", "source_ids": ["source-1"]}
                ],
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


def completed_research_result() -> ResearchExpertResult:
    return ResearchExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "One grounded research finding.",
            "payload": {
                "findings": [
                    {
                        "claim": "Python publishes release details.",
                        "evidence_summary": "Official downloads page.",
                        "source_ids": ["source-1"],
                        "confidence": "high",
                    }
                ],
                "sources": [
                    {
                        "source_id": "source-1",
                        "uri": "https://www.python.org/downloads/",
                        "label": "Python downloads",
                    }
                ],
            },
            "evidence": {
                "source_ids": ["source-1"],
                "grounded_finding_count": 1,
                "grounding_support_count": 1,
            },
        }
    )


@pytest.mark.parametrize(
    "directive",
    (
        AgentColRoutingDirective(route="direct"),
        AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which values should I calculate?",
        ),
    ),
)
def test_v2_context_keeps_direct_and_clarify_isolated(directive) -> None:
    context_v2 = load_context_v2()

    context = context_v2.AgentColResponderContextV2(
        routing_directive=directive
    )

    assert context.expert_result is None
    assert context.actions == ()
    assert context.citations == ()


@pytest.mark.parametrize(
    ("route", "result", "receipt_builder"),
    (
        ("source", completed_source_result(), build_source_receipts),
        ("research", completed_research_result(), build_research_receipts),
    ),
)
def test_v2_context_preserves_source_and_research_receipt_parity(
    route,
    result,
    receipt_builder,
) -> None:
    context_v2 = load_context_v2()
    directive = (
        AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Analyze the page.",
                "selected_url_ids": ["url-1"],
            },
        )
        if route == "source"
        else AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "What is current?",
                "objective": "Verify the answer.",
            },
        )
    )
    receipts = receipt_builder(result)

    context = context_v2.AgentColResponderContextV2(
        routing_directive=directive,
        expert_result=result,
        actions=receipts.actions,
        citations=receipts.citations,
    )

    assert context.expert_result == result
    assert context.actions == receipts.actions
    assert context.citations == receipts.citations


def computation_directive() -> AgentColRoutingDirective:
    return AgentColRoutingDirective(
        route="computation",
        computation_intent={
            "objective": "Calculate the mean.",
            "series_inputs": [
                {
                    "name": "values",
                    "numeric_ids": ["number-1", "number-2", "number-3"],
                }
            ],
            "precision": {
                "mode": "decimal_places",
                "digits_numeric_id": "number-4",
            },
        },
    )


def test_v2_context_requires_exact_computation_receipt_and_no_citations(
) -> None:
    context_v2 = load_context_v2()
    result = completed_computation_result()
    receipts = build_computation_receipts(result)

    context = context_v2.AgentColResponderContextV2(
        routing_directive=computation_directive(),
        expert_result=result,
        actions=receipts.actions,
        citations=receipts.citations,
    )

    assert context.actions[0].action_name == "run_computation"
    assert context.citations == ()

    with pytest.raises(ValidationError):
        context_v2.AgentColResponderContextV2(
            routing_directive=computation_directive(),
            expert_result=result,
            actions=(),
        )


@pytest.mark.parametrize(
    "status",
    tuple(status for status in ExpertStatus if status is not ExpertStatus.COMPLETED),
)
def test_v2_context_accepts_contentless_computation_failures_without_receipts(
    status: ExpertStatus,
) -> None:
    context_v2 = load_context_v2()
    from computational_expert import ComputationResponderResult

    context = context_v2.AgentColResponderContextV2(
        routing_directive=computation_directive(),
        expert_result=ComputationResponderResult(status=status),
    )

    assert context.expert_result is not None
    assert context.expert_result.status is status
    assert context.actions == ()
    assert context.citations == ()


def test_v2_responder_serialization_contains_only_bounded_computation_context(
) -> None:
    context_v2 = load_context_v2()
    result = completed_computation_result()
    receipts = build_computation_receipts(result)
    context = context_v2.AgentColResponderContextV2(
        routing_directive=computation_directive(),
        expert_result=result,
        actions=receipts.actions,
    )

    rendered = context_v2.build_agent_col_responder_v2_model_context(context)
    text = rendered.parts[0].text

    assert "The arithmetic mean is 2.00." in text
    assert '"execution_verified":true' in text
    for excluded in (
        "RAW_CODE_MARKER",
        "RAW_OUTPUT_MARKER",
        "execution_runs",
        "CURRENT_MESSAGE_MARKER",
        "PROFILE_MARKER",
        "PROJECT_ID_MARKER",
        "SESSION_ID_MARKER",
        "USER_ID_MARKER",
        "IDEMPOTENCY_KEY_MARKER",
        "CREDENTIAL_MARKER",
    ):
        assert excluded not in text
