import pytest
from pydantic import ValidationError


CONTEXT_START = "[SERVER_VALIDATED_ROUTING_AND_EXPERT_RESULT]"
CONTEXT_END = "[/SERVER_VALIDATED_ROUTING_AND_EXPERT_RESULT]"


def completed_source_result():
    from source_expert import SourceExpertResult

    return SourceExpertResult.model_validate(
        {
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


def completed_research_result():
    from research_expert import ResearchExpertResult

    return ResearchExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "Research produced two grounded findings.",
            "payload": {
                "findings": [
                    {
                        "claim": "Python documentation describes Python.",
                        "evidence_summary": "The official documentation.",
                        "source_ids": ["source-1"],
                        "confidence": "high",
                    },
                    {
                        "claim": "PEP 8 documents Python style guidance.",
                        "evidence_summary": "The official PEP index.",
                        "source_ids": ["source-2"],
                        "confidence": "high",
                    },
                ],
                "sources": [
                    {
                        "source_id": "source-1",
                        "uri": "https://docs.python.org/3/",
                        "label": "Python documentation",
                    },
                    {
                        "source_id": "source-2",
                        "uri": "https://peps.python.org/pep-0008/",
                        "label": "PEP 8",
                    },
                ],
            },
            "evidence": {
                "source_ids": ["source-1", "source-2"],
                "grounded_finding_count": 2,
                "grounding_support_count": 2,
            },
        }
    )


def test_direct_and_clarify_contexts_accept_no_expert_effects() -> None:
    from agent_col_responder_context import AgentColResponderContext
    from agent_col_routing import AgentColRoutingDirective

    direct = AgentColResponderContext(
        routing_directive=AgentColRoutingDirective(route="direct")
    )
    clarify = AgentColResponderContext(
        routing_directive=AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which supplied page should I analyze?",
        )
    )

    assert direct.expert_result is None
    assert direct.actions == ()
    assert direct.citations == ()
    assert clarify.expert_result is None
    assert clarify.actions == ()
    assert clarify.citations == ()


@pytest.mark.parametrize(
    "extra_field",
    (
        "current_message",
        "message",
        "profile",
        "project_id",
        "session_id",
        "user_id",
        "turn_id",
        "idempotency_key",
    ),
)
def test_responder_context_rejects_unapproved_context_fields(
    extra_field: str,
) -> None:
    from agent_col_responder_context import AgentColResponderContext

    with pytest.raises(ValidationError):
        AgentColResponderContext.model_validate(
            {
                "routing_directive": {"route": "direct"},
                extra_field: "must-not-enter-model-context",
            }
        )


@pytest.mark.parametrize("route", ("direct", "clarify"))
def test_direct_and_clarify_contexts_reject_expert_receipts(
    route: str,
) -> None:
    from agent_col_responder_context import AgentColResponderContext

    routing_directive: dict[str, str] = {"route": route}
    if route == "clarify":
        routing_directive["clarifying_question"] = "Which source?"

    with pytest.raises(ValidationError):
        AgentColResponderContext.model_validate(
            {
                "routing_directive": routing_directive,
                "actions": [
                    {
                        "action_name": "url_context",
                        "status": "completed",
                    }
                ],
            }
        )


def test_source_and_research_contexts_accept_exact_derived_receipts() -> None:
    from agent_col_responder_context import AgentColResponderContext
    from agent_col_routing import AgentColRoutingDirective
    from research_expert import build_research_receipts
    from source_expert import build_source_receipts

    source_result = completed_source_result()
    source_receipts = build_source_receipts(source_result)
    source_context = AgentColResponderContext(
        routing_directive=AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Identify the documented purpose.",
                "selected_url_ids": ["url-1"],
            },
        ),
        expert_result=source_result,
        actions=source_receipts.actions,
        citations=source_receipts.citations,
    )

    research_result = completed_research_result()
    research_receipts = build_research_receipts(research_result)
    research_context = AgentColResponderContext(
        routing_directive=AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "What do the Python references establish?",
                "objective": "Summarize official public evidence.",
            },
        ),
        expert_result=research_result,
        actions=research_receipts.actions,
        citations=research_receipts.citations,
    )

    assert source_context.expert_result == source_result
    assert source_context.actions == source_receipts.actions
    assert source_context.citations == source_receipts.citations
    assert research_context.expert_result == research_result
    assert research_context.actions == research_receipts.actions
    assert research_context.citations == research_receipts.citations


@pytest.mark.parametrize(
    ("route", "result_factory"),
    (
        ("source", completed_research_result),
        ("research", completed_source_result),
    ),
)
def test_expert_context_rejects_route_capability_mismatch(
    route: str,
    result_factory,
) -> None:
    from agent_col_responder_context import AgentColResponderContext

    intent = (
        {
            "source_intent": {
                "objective": "Inspect the supplied page.",
                "selected_url_ids": ["url-1"],
            }
        }
        if route == "source"
        else {
            "research_intent": {
                "question": "What is current?",
                "objective": "Verify current public evidence.",
            }
        }
    )

    with pytest.raises(ValidationError):
        AgentColResponderContext.model_validate(
            {
                "routing_directive": {"route": route, **intent},
                "expert_result": result_factory().model_dump(mode="json"),
            }
        )


@pytest.mark.parametrize("route", ("source", "research"))
def test_selected_expert_route_requires_a_result(route: str) -> None:
    from agent_col_responder_context import AgentColResponderContext

    intent = (
        {
            "source_intent": {
                "objective": "Inspect the supplied page.",
                "selected_url_ids": ["url-1"],
            }
        }
        if route == "source"
        else {
            "research_intent": {
                "question": "What is current?",
                "objective": "Verify current public evidence.",
            }
        }
    )

    with pytest.raises(ValidationError):
        AgentColResponderContext.model_validate(
            {"routing_directive": {"route": route, **intent}}
        )


def test_completed_expert_context_rejects_changed_receipts() -> None:
    from agent_col_responder_context import AgentColResponderContext
    from agent_col_routing import AgentColRoutingDirective
    from research_expert import build_research_receipts
    from schemas import AgentActionReceipt, CitationReference

    result = completed_research_result()
    receipts = build_research_receipts(result)
    directive = AgentColRoutingDirective(
        route="research",
        research_intent={
            "question": "What do the Python references establish?",
            "objective": "Summarize official public evidence.",
        },
    )
    mutations = (
        {"actions": (), "citations": receipts.citations},
        {
            "actions": (
                AgentActionReceipt(
                    action_name="url_context",
                    status="completed",
                ),
            ),
            "citations": receipts.citations,
        },
        {
            "actions": receipts.actions,
            "citations": tuple(reversed(receipts.citations)),
        },
        {
            "actions": receipts.actions,
            "citations": (
                CitationReference(
                    uri="https://example.com/",
                    label="Altered citation",
                ),
            ),
        },
        {
            "actions": receipts.actions * 2,
            "citations": receipts.citations,
        },
        {
            "actions": receipts.actions,
            "citations": receipts.citations
            + tuple(
                CitationReference(
                    uri=f"https://example.com/source-{index}",
                    label=f"Unexpected source {index}",
                )
                for index in range(11)
            ),
        },
    )

    for mutation in mutations:
        with pytest.raises(ValidationError):
            AgentColResponderContext(
                routing_directive=directive,
                expert_result=result,
                **mutation,
            )


def test_noncompleted_expert_context_carries_no_receipts() -> None:
    from agent_col_responder_context import AgentColResponderContext
    from agent_col_routing import AgentColRoutingDirective
    from expert_contracts import ExpertStatus
    from schemas import AgentActionReceipt
    from source_expert import SourceExpertResult

    result = SourceExpertResult(status=ExpertStatus.TIMED_OUT)
    directive = AgentColRoutingDirective(
        route="source",
        source_intent={
            "objective": "Inspect the supplied page.",
            "selected_url_ids": ["url-1"],
        },
    )

    context = AgentColResponderContext(
        routing_directive=directive,
        expert_result=result,
    )

    assert context.actions == ()
    assert context.citations == ()
    with pytest.raises(ValidationError):
        AgentColResponderContext(
            routing_directive=directive,
            expert_result=result,
            actions=(
                AgentActionReceipt(
                    action_name="url_context",
                    status="completed",
                ),
            ),
        )


def test_responder_model_context_contains_only_validated_payload() -> None:
    import json

    from agent_col_responder_context import (
        AgentColResponderContext,
        build_agent_col_responder_model_context,
    )
    from agent_col_routing import AgentColRoutingDirective

    context = AgentColResponderContext(
        routing_directive=AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which supplied page should I analyze?",
        )
    )

    content = build_agent_col_responder_model_context(context)

    assert content.role == "user"
    assert content.parts is not None
    assert len(content.parts) == 1
    text = content.parts[0].text
    assert isinstance(text, str)
    payload_text = text.split(CONTEXT_START, 1)[1].split(
        CONTEXT_END,
        1,
    )[0]
    assert json.loads(payload_text) == context.model_dump(mode="json")
    assert set(json.loads(payload_text)) == {
        "routing_directive",
        "expert_result",
        "actions",
        "citations",
    }
    for forbidden_field in (
        "current_message",
        "profile",
        "project_id",
        "session_id",
        "user_id",
        "turn_id",
        "idempotency_key",
        "credential",
    ):
        assert forbidden_field not in payload_text


def test_responder_model_context_states_authority_and_trust_boundaries(
) -> None:
    from agent_col_responder_context import (
        AgentColResponderContext,
        build_agent_col_responder_model_context,
    )
    from agent_col_routing import AgentColRoutingDirective

    content = build_agent_col_responder_model_context(
        AgentColResponderContext(
            routing_directive=AgentColRoutingDirective(route="direct")
        )
    )

    assert content.parts is not None
    text = content.parts[0].text
    assert isinstance(text, str)
    normalized = " ".join(text.split()).lower()
    for required_rule in (
        "authoritative",
        "do not reroute",
        "untrusted evidence",
        "do not call an expert",
        "do not fabricate",
        "do not change",
    ):
        assert required_rule in normalized
