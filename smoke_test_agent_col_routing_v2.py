"""Live compatibility runner for the parallel Agent_Col routing v2 contract."""

import argparse
import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from dotenv import load_dotenv
from google import genai
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from agent_col_routing_provider_v2 import (
    AgentColRoutingV2ProviderError,
    AgentColRoutingV2ProviderOutputError,
    AgentColRoutingV2ProviderTimeoutError,
    request_agent_col_routing_v2_directive,
)
from agent_col_routing_v2 import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
    RoutingDirectiveInputError,
)
from vertex_config import VertexAIConfigurationError, load_vertex_ai_settings


RoutingV2ScenarioId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9-]+$",
    ),
]
DEFAULT_ROUTING_V2_COMPATIBILITY_FIXTURE = Path(
    "tests/fixtures/agent_col_routing_v2_contract_cases.json"
)
OutputWriter = Callable[[str], None]
DirectiveRequester = Callable[
    ["RoutingV2CompatibilityScenario", int],
    Awaitable[AgentColRoutingDirective],
]
ProviderRequester = Callable[
    [genai.Client, AgentColRoutingInput],
    Awaitable[AgentColRoutingDirective],
]


class LiveRunner(Protocol):
    async def __call__(self, **kwargs: object) -> int: ...


class _StrictCompatibilityModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class RoutingV2CompatibilityScenario(_StrictCompatibilityModel):
    scenario_id: RoutingV2ScenarioId
    fixture_version: Literal["2.0"]
    routing_input: AgentColRoutingInput
    expected_route: AgentColRoute


class _RoutingV2ScenarioDefinition(_StrictCompatibilityModel):
    scenario_id: RoutingV2ScenarioId
    routing_input: AgentColRoutingInput
    expected_route: AgentColRoute


class _RoutingV2CompatibilityFixture(_StrictCompatibilityModel):
    fixture_version: Literal["2.0"]
    scenarios: tuple[_RoutingV2ScenarioDefinition, ...] = Field(
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def require_unique_scenario_ids(self) -> Self:
        scenario_ids = tuple(
            scenario.scenario_id for scenario in self.scenarios
        )
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError(
                "Routing v2 compatibility scenario IDs must be unique."
            )
        return self


def load_routing_v2_compatibility_scenarios(
    fixture_path: Path,
) -> tuple[RoutingV2CompatibilityScenario, ...]:
    """Load strict routing v2 compatibility cases from JSON."""
    fixture = _RoutingV2CompatibilityFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    return tuple(
        RoutingV2CompatibilityScenario(
            scenario_id=scenario.scenario_id,
            fixture_version=fixture.fixture_version,
            routing_input=scenario.routing_input,
            expected_route=scenario.expected_route,
        )
        for scenario in fixture.scenarios
    )


async def run_routing_v2_compatibility(
    *,
    scenarios: tuple[RoutingV2CompatibilityScenario, ...],
    selected_scenario_id: str | None,
    repetitions: int,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Run bounded v2 compatibility cases and emit metadata-only results."""
    if repetitions < 1 or repetitions > 5:
        output("agent-col-routing-v2-compatibility configuration_error")
        return 2
    selected = tuple(
        scenario
        for scenario in scenarios
        if selected_scenario_id is None
        or scenario.scenario_id == selected_scenario_id
    )
    if not selected:
        output("agent-col-routing-v2-compatibility configuration_error")
        return 2

    has_mismatch = False
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
            except AgentColRoutingV2ProviderOutputError:
                has_execution_failure = True
                output(f"{prefix} model_output_error")
                continue
            except AgentColRoutingV2ProviderError:
                has_execution_failure = True
                output(f"{prefix} provider_error")
                continue
            except RoutingDirectiveInputError:
                has_execution_failure = True
                output(f"{prefix} directive_input_error")
                continue

            result = "pass"
            if directive.route is not scenario.expected_route:
                has_mismatch = True
                result = "route_mismatch"
            output(
                f"{prefix} expected={scenario.expected_route} "
                f"actual={directive.route} {result}"
            )

    if has_execution_failure:
        return 2
    return 1 if has_mismatch else 0


async def run_routing_v2_compatibility_fixture(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Load and run the v2 fixture without provider setup."""
    try:
        scenarios = load_routing_v2_compatibility_scenarios(fixture_path)
    except (OSError, ValidationError):
        output("agent-col-routing-v2-compatibility configuration_error")
        return 2
    return await run_routing_v2_compatibility(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        repetitions=repetitions,
        request_directive=request_directive,
        output=output,
    )


async def run_live_routing_v2_compatibility(
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
    """Run the isolated routing v2 contract against Vertex AI."""
    load_dotenv()
    try:
        settings = load_vertex_ai_settings(
            environment if environment is not None else os.environ
        )
    except VertexAIConfigurationError:
        output("agent-col-routing-v2-compatibility configuration_error")
        return 2

    client = client_factory(**settings.client_kwargs())
    try:

        async def request_directive(
            scenario: RoutingV2CompatibilityScenario,
            _repetition: int,
        ) -> AgentColRoutingDirective:
            return await provider_request(client, scenario.routing_input)

        return await run_routing_v2_compatibility_fixture(
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
            "Verify the parallel Agent_Col routing v2 contract against Vertex."
        )
    )
    parser.add_argument(
        "--scenario",
        help="Run one routing v2 compatibility scenario by ID.",
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
    live_runner: LiveRunner = run_live_routing_v2_compatibility,
) -> int:
    arguments = build_parser().parse_args(argv)
    return asyncio.run(
        live_runner(
            fixture_path=DEFAULT_ROUTING_V2_COMPATIBILITY_FIXTURE,
            selected_scenario_id=arguments.scenario,
            repetitions=arguments.repetitions,
            output=print,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
