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

from agent_col_routing import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
    RoutingDirectiveInputError,
)
from agent_col_routing_provider import (
    AgentColRoutingProviderError,
    AgentColRoutingProviderOutputError,
    AgentColRoutingProviderTimeoutError,
    request_agent_col_routing_directive,
)
from vertex_config import VertexAIConfigurationError, load_vertex_ai_settings


RoutingScenarioId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9-]+$",
    ),
]
DEFAULT_ROUTING_COMPATIBILITY_FIXTURE = Path(
    "tests/fixtures/agent_col_routing_contract_cases.json"
)
OutputWriter = Callable[[str], None]
DirectiveRequester = Callable[
    ["RoutingCompatibilityScenario", int],
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


class RoutingCompatibilityScenario(_StrictCompatibilityModel):
    scenario_id: RoutingScenarioId
    fixture_version: Literal["1.0"]
    routing_input: AgentColRoutingInput
    expected_route: AgentColRoute


class _RoutingScenarioDefinition(_StrictCompatibilityModel):
    scenario_id: RoutingScenarioId
    routing_input: AgentColRoutingInput
    expected_route: AgentColRoute


class _RoutingCompatibilityFixture(_StrictCompatibilityModel):
    fixture_version: Literal["1.0"]
    scenarios: tuple[_RoutingScenarioDefinition, ...] = Field(
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def require_unique_scenario_ids(self) -> Self:
        scenario_ids = tuple(
            scenario.scenario_id for scenario in self.scenarios
        )
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("Routing compatibility scenario IDs must be unique.")
        return self


def load_routing_compatibility_scenarios(
    fixture_path: Path,
) -> tuple[RoutingCompatibilityScenario, ...]:
    """Load strict compatibility cases from a versioned JSON fixture."""
    fixture = _RoutingCompatibilityFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    return tuple(
        RoutingCompatibilityScenario(
            scenario_id=scenario.scenario_id,
            fixture_version=fixture.fixture_version,
            routing_input=scenario.routing_input,
            expected_route=scenario.expected_route,
        )
        for scenario in fixture.scenarios
    )


async def run_routing_compatibility(
    *,
    scenarios: tuple[RoutingCompatibilityScenario, ...],
    selected_scenario_id: str | None,
    repetitions: int,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Run bounded compatibility cases and classify safe outcomes."""
    if repetitions < 1 or repetitions > 5:
        output("agent-col-routing-compatibility configuration_error")
        return 2
    selected = tuple(
        scenario
        for scenario in scenarios
        if selected_scenario_id is None
        or scenario.scenario_id == selected_scenario_id
    )
    if not selected:
        output("agent-col-routing-compatibility configuration_error")
        return 2

    has_mismatch = False
    has_execution_failure = False
    for scenario in selected:
        for repetition in range(1, repetitions + 1):
            prefix = f"{scenario.scenario_id} run={repetition}"
            try:
                directive = await request_directive(scenario, repetition)
            except AgentColRoutingProviderTimeoutError:
                has_execution_failure = True
                output(f"{prefix} timeout_error")
                continue
            except AgentColRoutingProviderOutputError:
                has_execution_failure = True
                output(f"{prefix} model_output_error")
                continue
            except AgentColRoutingProviderError:
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


async def run_routing_compatibility_fixture(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Load and run the compatibility fixture without provider setup."""
    try:
        scenarios = load_routing_compatibility_scenarios(fixture_path)
    except (OSError, ValidationError):
        output("agent-col-routing-compatibility configuration_error")
        return 2
    return await run_routing_compatibility(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        repetitions=repetitions,
        request_directive=request_directive,
        output=output,
    )


async def run_live_routing_compatibility(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    output: OutputWriter,
    environment: Mapping[str, str] | None = None,
    client_factory: Callable[..., genai.Client] = genai.Client,
    provider_request: ProviderRequester = (
        request_agent_col_routing_directive
    ),
) -> int:
    """Run the isolated directive contract against Vertex AI."""
    load_dotenv()
    try:
        settings = load_vertex_ai_settings(
            environment if environment is not None else os.environ
        )
    except VertexAIConfigurationError:
        output("agent-col-routing-compatibility configuration_error")
        return 2

    client = client_factory(**settings.client_kwargs())
    try:

        async def request_directive(
            scenario: RoutingCompatibilityScenario,
            _repetition: int,
        ) -> AgentColRoutingDirective:
            return await provider_request(client, scenario.routing_input)

        return await run_routing_compatibility_fixture(
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
            "Verify the Agent_Col routing directive contract against Vertex."
        )
    )
    parser.add_argument(
        "--scenario",
        help="Run one compatibility scenario by ID.",
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
    live_runner: LiveRunner = run_live_routing_compatibility,
) -> int:
    arguments = build_parser().parse_args(argv)
    return asyncio.run(
        live_runner(
            fixture_path=DEFAULT_ROUTING_COMPATIBILITY_FIXTURE,
            selected_scenario_id=arguments.scenario,
            repetitions=arguments.repetitions,
            output=print,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
