import importlib

import pytest


def load_smoke_module():
    try:
        return importlib.import_module("smoke_test_agent_col_routing_v4")
    except ModuleNotFoundError:
        pytest.fail("smoke_test_agent_col_routing_v4 has not been implemented")


def test_v4_smoke_input_exposes_only_bounded_artifact_authority() -> None:
    module = load_smoke_module()

    routing_input = module.build_artifact_routing_input()

    assert routing_input.artifact_creation_available is True
    assert routing_input.structured_decision_present is False
    assert routing_input.available_capabilities == (
        "source",
        "research",
        "computation",
        "requirements_verification",
    )
    assert "complete brief" in routing_input.current_message


@pytest.mark.asyncio
async def test_v4_smoke_reports_artifact_route_without_prompt_content() -> None:
    module = load_smoke_module()
    from agent_col_routing_v4 import AgentColRoutingDirective

    async def request(_routing_input: object) -> object:
        return AgentColRoutingDirective(
            route="artifact",
            artifact_intent={
                "operation": "create_blueprint",
                "objective": "Create the requested structured blueprint.",
            },
        )

    output: list[str] = []
    exit_code = await module.run_artifact_routing_compatibility(
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 0
    assert output == [
        "agent-col-routing-v4 route=artifact "
        "operation=create_blueprint pass"
    ]
    assert "study partner" not in output[0]


@pytest.mark.asyncio
async def test_v4_smoke_reports_route_mismatch() -> None:
    module = load_smoke_module()
    from agent_col_routing_v4 import AgentColRoutingDirective

    async def request(_routing_input: object) -> object:
        return AgentColRoutingDirective(
            route="clarify",
            clarifying_question="What material should the blueprint use?",
        )

    output: list[str] = []
    exit_code = await module.run_artifact_routing_compatibility(
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 1
    assert output == [
        "agent-col-routing-v4 expected=artifact actual=clarify route_mismatch"
    ]


@pytest.mark.asyncio
async def test_v4_smoke_reports_content_safe_provider_failure() -> None:
    module = load_smoke_module()
    from agent_col_routing_provider_v4 import AgentColRoutingV4ProviderError

    async def request(_routing_input: object) -> object:
        raise AgentColRoutingV4ProviderError("private-provider-content")

    output: list[str] = []
    exit_code = await module.run_artifact_routing_compatibility(
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["agent-col-routing-v4 provider_error"]
    assert "private" not in output[0]


@pytest.mark.asyncio
async def test_v4_smoke_subclassifies_route_payload_output_failure() -> None:
    module = load_smoke_module()
    from agent_col_routing_provider_v4 import (
        AgentColRoutingV4InvalidOutputReason,
        AgentColRoutingV4ProviderOutputError,
        AgentColRoutingV4SchemaFailureReason,
    )

    async def request(_routing_input: object) -> object:
        raise AgentColRoutingV4ProviderOutputError(
            AgentColRoutingV4InvalidOutputReason.SCHEMA_VALIDATION_FAILED,
            schema_failure_reason=(
                AgentColRoutingV4SchemaFailureReason.ROUTE_PAYLOAD_MISMATCH
            ),
        )

    output: list[str] = []
    exit_code = await module.run_artifact_routing_compatibility(
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        "agent-col-routing-v4 "
        "model_output_error:route_payload_mismatch"
    ]
