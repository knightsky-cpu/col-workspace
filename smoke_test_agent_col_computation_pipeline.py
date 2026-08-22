"""Run one fixed live routing-v2 computation pipeline verification."""

import asyncio
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from agent_col_expert_executor_v2 import (
    AgentColExpertExecutorV2,
    build_computation_expert_input,
)
from agent_col_responder_context_v2 import (
    build_agent_col_responder_v2_model_context,
)
from agent_col_routing_v2 import AgentColRoutingDirective, AgentColRoutingInput
from computational_expert import ComputationExpertInput
from computational_expert_service import ComputationalExpertService
from expert_contracts import ExpertStatus
from vertex_config import (
    VertexAIConfigurationError,
    VertexAISettings,
    load_vertex_ai_settings,
)


DEFAULT_DOTENV_PATH = Path(__file__).with_name(".env")
DEFAULT_ROUTING_FIXTURE = (
    Path(__file__).with_name("tests")
    / "fixtures"
    / "agent_col_routing_v2_contract_cases.json"
)


def _load_default_routing_input() -> AgentColRoutingInput:
    fixture = json.loads(DEFAULT_ROUTING_FIXTURE.read_text(encoding="utf-8"))
    scenario = next(
        item
        for item in fixture["scenarios"]
        if item["scenario_id"] == "computation-series"
    )
    routing_payload = dict(scenario["routing_input"])
    routing_payload["available_capabilities"] = ["computation"]
    return AgentColRoutingInput.model_validate(routing_payload)


DEFAULT_ROUTING_INPUT = _load_default_routing_input()
DEFAULT_ROUTING_DIRECTIVE = AgentColRoutingDirective(
    route="computation",
    computation_intent={
        "objective": (
            "Calculate the mean and population standard deviation for the "
            "values."
        ),
        "series_inputs": [
            {
                "name": "values",
                "numeric_ids": [
                    "number-1",
                    "number-2",
                    "number-3",
                    "number-4",
                    "number-5",
                    "number-6",
                ],
            }
        ],
        "constraints": ["Use population standard deviation."],
    },
)
DEFAULT_COMPUTATION_REQUEST = build_computation_expert_input(
    DEFAULT_ROUTING_DIRECTIVE,
    DEFAULT_ROUTING_INPUT,
)


class ComputationService(Protocol):
    async def compute(self, request: ComputationExpertInput): ...


async def run_live(
    *,
    environment: Mapping[str, str] | None = None,
    dotenv_loader: Callable[[Path], object] = load_dotenv,
    service_factory: Callable[
        [VertexAISettings], ComputationService
    ] = ComputationalExpertService.from_vertex_settings,
    output: Callable[[str], None] = print,
) -> int:
    """Execute the fixed pipeline and return its documented exit code."""
    dotenv_loader(DEFAULT_DOTENV_PATH)
    try:
        settings = load_vertex_ai_settings(
            os.environ if environment is None else environment
        )
    except VertexAIConfigurationError:
        output("agent-col-computation-pipeline configuration_error")
        return 2

    service = service_factory(settings)
    executor = AgentColExpertExecutorV2(computation_service=service)
    context = await executor.execute(
        DEFAULT_ROUTING_DIRECTIVE,
        DEFAULT_ROUTING_INPUT,
    )
    result = context.expert_result
    if result is None or result.status is not ExpertStatus.COMPLETED:
        status = "invalid_output" if result is None else result.status.value
        output(f"agent-col-computation-pipeline {status}")
        return 2

    rendered = build_agent_col_responder_v2_model_context(context)
    serialized = rendered.parts[0].text
    evidence = result.evidence
    expected_action = (
        len(context.actions) == 1
        and context.actions[0].action_name == "run_computation"
        and context.actions[0].status == "completed"
    )
    bounded_projection = all(
        marker not in serialized
        for marker in ('"execution_runs"', '"code"', '"output"')
    )
    if (
        not expected_action
        or context.citations
        or evidence is None
        or not evidence.execution_verified
        or not bounded_projection
    ):
        output("agent-col-computation-pipeline invariant_mismatch")
        return 1

    output(
        "agent-col-computation-pipeline pass status=completed "
        "action=run_computation citations=0 execution_verified=true"
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run_live()))


if __name__ == "__main__":
    main()
