import importlib

import pytest
from pydantic import ValidationError

from agent_col_routing_v3 import AgentColRoutingDirective
from computational_expert import (
    ComputationResponderResult,
    build_computation_receipts,
)
from expert_contracts import ExpertStatus
from research_expert import ResearchExpertResult, build_research_receipts
from requirements_verification import (
    RequirementAssessment,
    RequirementStatusCounts,
    RequirementsVerificationEvidence,
    RequirementsVerificationPayload,
    RequirementsVerificationResult,
    SubjectEvidence,
    build_requirements_verification_receipts,
)
from source_expert import SourceExpertResult, build_source_receipts


def load_context_v3():
    try:
        return importlib.import_module("agent_col_responder_context_v3")
    except ModuleNotFoundError:
        pytest.fail("agent_col_responder_context_v3 has not been implemented")


def verification_directive() -> AgentColRoutingDirective:
    return AgentColRoutingDirective(
        route="requirements_verification",
        requirements_verification_intent={
            "objective": "Assess every requirement.",
            "requirement_block_ids": ["block-1"],
            "subject_block_ids": ["block-2"],
        },
    )


def completed_verification_result() -> RequirementsVerificationResult:
    evidence = SubjectEvidence(
        subject_block_id="SUBJECT-001",
        excerpt="includes one practical example",
        explanation="The supplied subject directly addresses the requirement.",
    )
    return RequirementsVerificationResult(
        status=ExpertStatus.COMPLETED,
        summary="Requirements verification completed for 1 requirements.",
        limitations=("Only supplied material was assessed.",),
        payload=RequirementsVerificationPayload(
            assessments=(
                RequirementAssessment(
                    requirement_id="REQ-001",
                    requirement_text="Include one practical example.",
                    status="covered",
                    evidence=(evidence,),
                ),
            ),
            counts=RequirementStatusCounts(
                covered=1,
                partial=0,
                missing=0,
                contradictory=0,
                unsupported=0,
            ),
            overall_limitations=("Only supplied material was assessed.",),
        ),
        evidence=RequirementsVerificationEvidence(
            requirement_count=1,
            assessed_requirement_count=1,
            validated_evidence_count=1,
            referenced_subject_block_ids=("SUBJECT-001",),
        ),
    )


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


def failed_research_invalid_output_result() -> ResearchExpertResult:
    return ResearchExpertResult(
        status=ExpertStatus.INVALID_OUTPUT,
        invalid_output_reason="missing_grounding_metadata",
    )


def completed_computation_result() -> ComputationResponderResult:
    return ComputationResponderResult.model_validate(
        {
            "status": "completed",
            "summary": "One verified computation.",
            "payload": {
                "method": "Provider-executed Python computation.",
                "inputs_used": {
                    "series": [{"name": "values", "values": [1, 2, 3]}],
                    "expression": None,
                },
                "result": "The arithmetic mean is 2.00.",
            },
            "evidence": {
                "execution_verified": True,
                "execution_count": 1,
                "successful_execution_count": 1,
                "code_character_count": 10,
                "output_character_count": 5,
            },
        }
    )


@pytest.mark.parametrize(
    "directive",
    (
        AgentColRoutingDirective(route="direct"),
        AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which subject should I assess?",
        ),
    ),
)
def test_v3_context_keeps_direct_and_clarify_isolated(directive) -> None:
    context_v3 = load_context_v3()

    context = context_v3.AgentColResponderContextV3(
        routing_directive=directive
    )

    assert context.expert_result is None
    assert context.actions == ()
    assert context.citations == ()


def test_v3_context_requires_exact_verification_receipt_and_no_citations(
) -> None:
    context_v3 = load_context_v3()
    result = completed_verification_result()
    receipts = build_requirements_verification_receipts(result)

    context = context_v3.AgentColResponderContextV3(
        routing_directive=verification_directive(),
        expert_result=result,
        actions=receipts.actions,
        citations=receipts.citations,
    )

    assert context.expert_result == result
    assert context.actions[0].model_dump() == {
        "action_name": "verify_requirements",
        "status": "completed",
    }
    assert context.citations == ()

    with pytest.raises(ValidationError):
        context_v3.AgentColResponderContextV3(
            routing_directive=verification_directive(),
            expert_result=result,
            actions=(),
        )


@pytest.mark.parametrize(
    ("directive", "result", "receipt_builder"),
    (
        (
            AgentColRoutingDirective(
                route="source",
                source_intent={
                    "objective": "Analyze the supplied page.",
                    "selected_url_ids": ["url-1"],
                },
            ),
            completed_source_result(),
            build_source_receipts,
        ),
        (
            AgentColRoutingDirective(
                route="research",
                research_intent={
                    "question": "What is current?",
                    "objective": "Verify with public evidence.",
                },
            ),
            completed_research_result(),
            build_research_receipts,
        ),
        (
            AgentColRoutingDirective(
                route="computation",
                computation_intent={
                    "objective": "Calculate the mean.",
                    "series_inputs": [
                        {
                            "name": "values",
                            "numeric_ids": [
                                "number-1",
                                "number-2",
                                "number-3",
                            ],
                        }
                    ],
                },
            ),
            completed_computation_result(),
            build_computation_receipts,
        ),
    ),
)
def test_v3_context_preserves_existing_expert_receipt_parity(
    directive,
    result,
    receipt_builder,
) -> None:
    context_v3 = load_context_v3()
    receipts = receipt_builder(result)

    context = context_v3.AgentColResponderContextV3(
        routing_directive=directive,
        expert_result=result,
        actions=receipts.actions,
        citations=receipts.citations,
    )

    assert context.expert_result == result
    assert context.actions == receipts.actions
    assert context.citations == receipts.citations


def test_v3_responder_serialization_contains_only_bounded_verification_context(
) -> None:
    context_v3 = load_context_v3()
    result = completed_verification_result()
    receipts = build_requirements_verification_receipts(result)
    context = context_v3.AgentColResponderContextV3(
        routing_directive=verification_directive(),
        expert_result=result,
        actions=receipts.actions,
    )

    rendered = context_v3.build_agent_col_responder_v3_model_context(context)
    assert rendered.parts is not None
    text = rendered.parts[0].text
    assert text is not None
    assert '"requirement_id":"REQ-001"' in text
    assert '"status":"covered"' in text
    assert '"validated_evidence_count":1' in text
    assert '"action_name":"verify_requirements"' in text
    assert "evidence-backed assessment, not a certification" in text
    for excluded in (
        "CURRENT_MESSAGE_MARKER",
        "PROFILE_MARKER",
        "HISTORY_MARKER",
        "PROJECT_ID_MARKER",
        "SESSION_ID_MARKER",
        "USER_ID_MARKER",
        "IDEMPOTENCY_KEY_MARKER",
        "CREDENTIAL_MARKER",
        "PROVIDER_PAYLOAD_MARKER",
    ):
        assert excluded not in text


def test_v3_responder_context_marks_failed_expert_as_non_authoritative(
) -> None:
    context_v3 = load_context_v3()
    result = failed_research_invalid_output_result()
    context = context_v3.AgentColResponderContextV3(
        routing_directive=AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "What is the current stable Python release?",
                "objective": "Verify with public evidence.",
            },
        ),
        expert_result=result,
        actions=(),
        citations=(),
    )

    rendered = context_v3.build_agent_col_responder_v3_model_context(context)
    assert rendered.parts is not None
    text = rendered.parts[0].text
    assert text is not None
    assert '"invalid_output_reason":"missing_grounding_metadata"' in text
    assert "Failed expert results are non-authoritative" in text
    assert "do not replace failed expert evidence with fallback facts" in text
