"""Live compatibility runner for the parallel Agent_Col routing v3 contract."""

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

from agent_col_numeric_projection import project_routing_numeric_candidates
from agent_col_routing import (
    project_routing_url_candidates,
)
from agent_col_routing_provider_v3 import (
    AgentColRoutingV3ProviderError,
    AgentColRoutingV3ProviderOutputError,
    AgentColRoutingV3ProviderTimeoutError,
    request_agent_col_routing_v3_directive,
)
from agent_col_routing_v3 import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
    RoutingV3MessageText,
    RoutingDirectiveInputError,
)
from agent_col_text_projection import (
    RoutingTextBlockId,
    project_routing_text_blocks,
)
from vertex_config import VertexAIConfigurationError, load_vertex_ai_settings


RoutingV3ScenarioId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9-]+$",
    ),
]
DEFAULT_ROUTING_V3_COMPATIBILITY_FIXTURE = Path(
    "tests/fixtures/agent_col_routing_v3_contract_cases.json"
)
OutputWriter = Callable[[str], None]
DirectiveRequester = Callable[
    ["RoutingV3CompatibilityScenario", int],
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


class RoutingV3CompatibilityScenario(_StrictCompatibilityModel):
    scenario_id: RoutingV3ScenarioId
    fixture_version: Literal["3.0"]
    routing_input: AgentColRoutingInput
    expected_route: AgentColRoute
    expected_requirement_block_ids: tuple[RoutingTextBlockId, ...] = Field(
        default_factory=tuple,
        max_length=50,
    )
    expected_subject_block_ids: tuple[RoutingTextBlockId, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )

    @model_validator(mode="after")
    def require_coherent_expected_selection(self) -> Self:
        has_requirements = bool(self.expected_requirement_block_ids)
        has_subject = bool(self.expected_subject_block_ids)
        if self.expected_route is AgentColRoute.REQUIREMENTS_VERIFICATION:
            if not (has_requirements and has_subject):
                raise ValueError(
                    "Requirements route requires expected block selections."
                )
        elif has_requirements or has_subject:
            raise ValueError(
                "Non-requirements routes cannot expect block selections."
            )
        return self


class _RoutingV3ScenarioDefinition(_StrictCompatibilityModel):
    scenario_id: RoutingV3ScenarioId
    message: RoutingV3MessageText
    expected_route: AgentColRoute
    expected_requirement_block_ids: tuple[RoutingTextBlockId, ...] = Field(
        default_factory=tuple,
        max_length=50,
    )
    expected_subject_block_ids: tuple[RoutingTextBlockId, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )

    @model_validator(mode="after")
    def require_coherent_expected_selection(self) -> Self:
        has_requirements = bool(self.expected_requirement_block_ids)
        has_subject = bool(self.expected_subject_block_ids)
        if self.expected_route is AgentColRoute.REQUIREMENTS_VERIFICATION:
            if not (has_requirements and has_subject):
                raise ValueError(
                    "Requirements route requires expected block selections."
                )
        elif has_requirements or has_subject:
            raise ValueError(
                "Non-requirements routes cannot expect block selections."
            )
        return self


class _RoutingV3CompatibilityFixture(_StrictCompatibilityModel):
    fixture_version: Literal["3.0"]
    scenarios: tuple[_RoutingV3ScenarioDefinition, ...] = Field(
        min_length=1,
        max_length=12,
    )

    @model_validator(mode="after")
    def require_unique_scenario_ids(self) -> Self:
        scenario_ids = tuple(
            scenario.scenario_id for scenario in self.scenarios
        )
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError(
                "Routing v3 compatibility scenario IDs must be unique."
            )
        return self


def _build_routing_input(message: str) -> AgentColRoutingInput:
    text_projection = project_routing_text_blocks(message)
    numeric_projection = project_routing_numeric_candidates(message)
    return AgentColRoutingInput(
        current_message=message,
        candidate_urls=project_routing_url_candidates(message, ()),
        numeric_candidates=numeric_projection.candidates,
        numeric_projection_incomplete=(
            numeric_projection.numeric_projection_incomplete
        ),
        text_block_candidates=text_projection.candidates,
        text_projection_incomplete=text_projection.text_projection_incomplete,
        available_capabilities=(
            "source",
            "research",
            "computation",
            "requirements_verification",
        ),
    )


def load_routing_v3_compatibility_scenarios(
    fixture_path: Path,
) -> tuple[RoutingV3CompatibilityScenario, ...]:
    """Load strict routing-v3 compatibility cases from JSON."""
    fixture = _RoutingV3CompatibilityFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    scenarios = tuple(
        RoutingV3CompatibilityScenario(
            scenario_id=scenario.scenario_id,
            fixture_version=fixture.fixture_version,
            routing_input=_build_routing_input(scenario.message),
            expected_route=scenario.expected_route,
            expected_requirement_block_ids=(
                scenario.expected_requirement_block_ids
            ),
            expected_subject_block_ids=scenario.expected_subject_block_ids,
        )
        for scenario in fixture.scenarios
    )
    for scenario in scenarios:
        available_ids = {
            candidate.candidate_id
            for candidate in scenario.routing_input.text_block_candidates
        }
        expected_ids = {
            *scenario.expected_requirement_block_ids,
            *scenario.expected_subject_block_ids,
        }
        if not expected_ids <= available_ids:
            raise ValidationError.from_exception_data(
                "RoutingV3CompatibilityScenario",
                [
                    {
                        "type": "value_error",
                        "loc": (),
                        "input": None,
                        "ctx": {
                            "error": ValueError(
                                "Expected block selection is unavailable."
                            )
                        },
                    }
                ],
            )
    return scenarios


async def run_routing_v3_compatibility(
    *,
    scenarios: tuple[RoutingV3CompatibilityScenario, ...],
    selected_scenario_id: str | None,
    repetitions: int,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Run bounded v3 compatibility cases and emit metadata-only results."""
    if repetitions < 1 or repetitions > 5:
        output("agent-col-routing-v3-compatibility configuration_error")
        return 2
    selected = tuple(
        scenario
        for scenario in scenarios
        if selected_scenario_id is None
        or scenario.scenario_id == selected_scenario_id
    )
    if not selected:
        output("agent-col-routing-v3-compatibility configuration_error")
        return 2

    has_mismatch = False
    has_execution_failure = False
    for scenario in selected:
        for repetition in range(1, repetitions + 1):
            prefix = f"{scenario.scenario_id} run={repetition}"
            try:
                directive = await request_directive(scenario, repetition)
            except AgentColRoutingV3ProviderTimeoutError:
                has_execution_failure = True
                output(f"{prefix} timeout_error")
                continue
            except AgentColRoutingV3ProviderOutputError:
                has_execution_failure = True
                output(f"{prefix} model_output_error")
                continue
            except AgentColRoutingV3ProviderError:
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
            elif directive.route is AgentColRoute.REQUIREMENTS_VERIFICATION:
                intent = directive.requirements_verification_intent
                if intent is None or (
                    intent.requirement_block_ids
                    != scenario.expected_requirement_block_ids
                    or intent.subject_block_ids
                    != scenario.expected_subject_block_ids
                ):
                    has_mismatch = True
                    result = "selection_mismatch"
            output(
                f"{prefix} expected={scenario.expected_route} "
                f"actual={directive.route} {result}"
            )

    if has_execution_failure:
        return 2
    return 1 if has_mismatch else 0


async def run_routing_v3_compatibility_fixture(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Load and run the v3 fixture without provider setup."""
    try:
        scenarios = load_routing_v3_compatibility_scenarios(fixture_path)
    except (OSError, ValidationError):
        output("agent-col-routing-v3-compatibility configuration_error")
        return 2
    return await run_routing_v3_compatibility(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        repetitions=repetitions,
        request_directive=request_directive,
        output=output,
    )


async def run_live_routing_v3_compatibility(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    output: OutputWriter,
    environment: Mapping[str, str] | None = None,
    client_factory: Callable[..., genai.Client] = genai.Client,
    provider_request: ProviderRequester = (
        request_agent_col_routing_v3_directive
    ),
) -> int:
    """Run the isolated routing-v3 contract against Vertex AI."""
    load_dotenv()
    try:
        settings = load_vertex_ai_settings(
            environment if environment is not None else os.environ
        )
    except VertexAIConfigurationError:
        output("agent-col-routing-v3-compatibility configuration_error")
        return 2

    client = client_factory(**settings.client_kwargs())
    try:

        async def request_directive(
            scenario: RoutingV3CompatibilityScenario,
            _repetition: int,
        ) -> AgentColRoutingDirective:
            return await provider_request(client, scenario.routing_input)

        return await run_routing_v3_compatibility_fixture(
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
            "Verify the parallel Agent_Col routing v3 contract against Vertex."
        )
    )
    parser.add_argument(
        "--scenario",
        help="Run one routing-v3 compatibility scenario by ID.",
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
    live_runner: LiveRunner = run_live_routing_v3_compatibility,
) -> int:
    arguments = build_parser().parse_args(argv)
    return asyncio.run(
        live_runner(
            fixture_path=DEFAULT_ROUTING_V3_COMPATIBILITY_FIXTURE,
            selected_scenario_id=arguments.scenario,
            repetitions=arguments.repetitions,
            output=print,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
