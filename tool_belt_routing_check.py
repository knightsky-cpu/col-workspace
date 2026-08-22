"""Decision-only live evaluation for Agent_Col's complete core tool belt."""

import argparse
import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from google import genai
from pydantic import ValidationError

from agent_col_routing_provider_v2 import (
    AgentColRoutingV2ProviderError,
    AgentColRoutingV2ProviderOutputError,
    AgentColRoutingV2ProviderTimeoutError,
    request_agent_col_routing_v2_directive,
)
from agent_col_routing_v2 import (
    AgentColRoutingDirective,
    AgentColRoutingInput,
    RoutingDirectiveInputError,
)
from tool_belt_routing_evaluation import (
    DEFAULT_TOOL_BELT_ROUTING_FIXTURE_PATH,
    ToolBeltRoutingScenario,
    evaluate_tool_belt_routing,
    load_tool_belt_routing_scenarios,
)
from vertex_config import VertexAIConfigurationError, load_vertex_ai_settings


OutputWriter = Callable[[str], None]
DirectiveRequester = Callable[
    [ToolBeltRoutingScenario, int],
    Awaitable[AgentColRoutingDirective],
]
ProviderRequester = Callable[
    [genai.Client, AgentColRoutingInput],
    Awaitable[AgentColRoutingDirective],
]


class LiveRunner(Protocol):
    async def __call__(self, **kwargs: object) -> int: ...


async def run_tool_belt_routing_evaluation(
    *,
    scenarios: tuple[ToolBeltRoutingScenario, ...],
    selected_scenario_id: str | None,
    repetitions: int,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Evaluate bounded model decisions and emit metadata-only results."""
    if repetitions < 1 or repetitions > 5:
        output("tool-belt-routing-check configuration_error")
        return 2
    selected = tuple(
        scenario
        for scenario in scenarios
        if selected_scenario_id is None
        or scenario.scenario_id == selected_scenario_id
    )
    if not selected:
        output("tool-belt-routing-check configuration_error")
        return 2

    has_quality_failure = False
    has_execution_failure = False
    for scenario in selected:
        for repetition in range(1, repetitions + 1):
            prefix = f"{scenario.scenario_id} run={repetition}"
            try:
                directive = await request_directive(scenario, repetition)
            except AgentColRoutingV2ProviderTimeoutError:
                has_execution_failure = True
                output(f"{prefix} timeout_error")
                continue
            except AgentColRoutingV2ProviderOutputError as exc:
                has_execution_failure = True
                classification = f"model_output_error:{exc.reason}"
                if exc.schema_failure_reason is not None:
                    classification += f":{exc.schema_failure_reason}"
                if (
                    exc.schema_failure_field is not None
                    and exc.schema_failure_constraint is not None
                ):
                    classification += (
                        f":{exc.schema_failure_field}"
                        f":{exc.schema_failure_constraint}"
                    )
                output(f"{prefix} {classification}")
                continue
            except AgentColRoutingV2ProviderError:
                has_execution_failure = True
                output(f"{prefix} provider_error")
                continue
            except RoutingDirectiveInputError:
                has_execution_failure = True
                output(f"{prefix} directive_input_error")
                continue

            findings = evaluate_tool_belt_routing(scenario, directive)
            if findings:
                has_quality_failure = True
                output(
                    " ".join(
                        (
                            prefix,
                            f"expected={scenario.expected_route}",
                            f"actual={directive.route}",
                            *(finding.code for finding in findings),
                        )
                    )
                )
                continue

            suffix = "pass"
            if scenario.manual_semantic_review != "none":
                suffix += " manual_review_required"
            output(
                f"{prefix} expected={scenario.expected_route} "
                f"actual={directive.route} {suffix}"
            )

    if has_execution_failure:
        return 2
    return 1 if has_quality_failure else 0


async def run_tool_belt_routing_fixture(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Load and run a strict fixture without provider configuration."""
    try:
        scenarios = load_tool_belt_routing_scenarios(fixture_path)
    except (OSError, ValidationError):
        output("tool-belt-routing-check configuration_error")
        return 2
    return await run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        repetitions=repetitions,
        request_directive=request_directive,
        output=output,
    )


async def run_live_tool_belt_routing_evaluation(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    output: OutputWriter,
    environment: Mapping[str, str] | None = None,
    client_factory: Callable[..., genai.Client] = genai.Client,
    provider_request: ProviderRequester = (
        request_agent_col_routing_v2_directive
    ),
) -> int:
    """Evaluate routing decisions directly through Vertex AI and ADC."""
    load_dotenv()
    try:
        settings = load_vertex_ai_settings(
            environment if environment is not None else os.environ
        )
    except VertexAIConfigurationError:
        output("tool-belt-routing-check configuration_error")
        return 2

    client = client_factory(**settings.client_kwargs())
    try:

        async def request_directive(
            scenario: ToolBeltRoutingScenario,
            _repetition: int,
        ) -> AgentColRoutingDirective:
            return await provider_request(client, scenario.routing_input)

        return await run_tool_belt_routing_fixture(
            fixture_path=fixture_path,
            selected_scenario_id=selected_scenario_id,
            repetitions=repetitions,
            request_directive=request_directive,
            output=output,
        )
    finally:
        try:
            await client.aio.aclose()
        finally:
            client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Agent_Col's bounded tool-belt routing decisions."
        )
    )
    parser.add_argument(
        "--scenario",
        help="Run one unified routing scenario by ID.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="Run each selected scenario 1 to 5 times.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    live_runner: LiveRunner = run_live_tool_belt_routing_evaluation,
) -> int:
    arguments = build_parser().parse_args(argv)
    return asyncio.run(
        live_runner(
            fixture_path=DEFAULT_TOOL_BELT_ROUTING_FIXTURE_PATH,
            selected_scenario_id=arguments.scenario,
            repetitions=arguments.repetitions,
            output=print,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
