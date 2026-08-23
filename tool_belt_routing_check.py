"""Decision-only live evaluation for Agent_Col's complete core tool belt."""

import argparse
import asyncio
import os
import re
import subprocess
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal, Protocol

from dotenv import load_dotenv
from google import genai
from pydantic import ValidationError

from agent_col_routing_provider_v3 import (
    AGENT_COL_ROUTING_V3_MODEL_NAME,
    AgentColRoutingV3ProviderError,
    AgentColRoutingV3ProviderOutputError,
    AgentColRoutingV3ProviderTimeoutError,
    request_agent_col_routing_v3_directive,
)
from agent_col_routing_v3 import (
    AgentColRoutingDirective,
    AgentColRoutingInput,
    RoutingDirectiveInputError,
)
from tool_belt_routing_evaluation_v3 import (
    DEFAULT_TOOL_BELT_ROUTING_V3_FIXTURE_PATH,
    ToolBeltRoutingV3Scenario,
    evaluate_tool_belt_routing_v3,
    load_tool_belt_routing_v3_scenarios,
)
from vertex_config import VertexAIConfigurationError, load_vertex_ai_settings


OutputWriter = Callable[[str], None]
DirectiveRequester = Callable[
    [ToolBeltRoutingV3Scenario, int],
    Awaitable[AgentColRoutingDirective],
]
ProviderRequester = Callable[
    [genai.Client, AgentColRoutingInput],
    Awaitable[AgentColRoutingDirective],
]


class LiveRunner(Protocol):
    async def __call__(self, **kwargs: object) -> int: ...


EvaluationMode = Literal["baseline", "declared"]
_REPOSITORY_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


def resolve_repository_commit() -> str:
    """Resolve one content-safe Git commit identifier for the report."""
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = completed.stdout.strip()
    if not _REPOSITORY_COMMIT.fullmatch(commit):
        raise ValueError("Repository commit identifier is invalid.")
    return commit


def is_repository_dirty() -> bool:
    """Return whether tracked or untracked repository changes are present."""
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(completed.stdout.strip())


def _select_scenarios(
    scenarios: tuple[ToolBeltRoutingV3Scenario, ...],
    selected_scenario_id: str | None,
) -> tuple[ToolBeltRoutingV3Scenario, ...]:
    return tuple(
        scenario
        for scenario in scenarios
        if selected_scenario_id is None
        or scenario.scenario_id == selected_scenario_id
    )


def _attempt_count(
    scenario: ToolBeltRoutingV3Scenario,
    mode: EvaluationMode,
) -> int:
    return 1 if mode == "baseline" else scenario.live_repetitions


async def run_tool_belt_routing_evaluation(
    *,
    scenarios: tuple[ToolBeltRoutingV3Scenario, ...],
    selected_scenario_id: str | None,
    mode: EvaluationMode,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Evaluate bounded model decisions and emit metadata-only results."""
    if mode not in {"baseline", "declared"}:
        output("tool-belt-routing-check configuration_error")
        return 2
    selected = _select_scenarios(scenarios, selected_scenario_id)
    if not selected:
        output("tool-belt-routing-check configuration_error")
        return 2

    has_quality_failure = False
    has_execution_failure = False
    for scenario in selected:
        repetitions = _attempt_count(scenario, mode)
        for repetition in range(1, repetitions + 1):
            prefix = f"{scenario.scenario_id} run={repetition}"
            try:
                directive = await request_directive(scenario, repetition)
            except AgentColRoutingV3ProviderTimeoutError:
                has_execution_failure = True
                output(f"{prefix} timeout_error")
                continue
            except AgentColRoutingV3ProviderOutputError as exc:
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
            except AgentColRoutingV3ProviderError:
                has_execution_failure = True
                output(f"{prefix} provider_error")
                continue
            except RoutingDirectiveInputError:
                has_execution_failure = True
                output(f"{prefix} directive_input_error")
                continue

            findings = evaluate_tool_belt_routing_v3(scenario, directive)
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
    mode: EvaluationMode,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Load and run a strict fixture without provider configuration."""
    try:
        scenarios = load_tool_belt_routing_v3_scenarios(fixture_path)
    except (OSError, ValidationError):
        output("tool-belt-routing-check configuration_error")
        return 2
    return await run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        mode=mode,
        request_directive=request_directive,
        output=output,
    )


async def run_live_tool_belt_routing_evaluation(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    mode: EvaluationMode,
    output: OutputWriter,
    environment: Mapping[str, str] | None = None,
    client_factory: Callable[..., genai.Client] = genai.Client,
    provider_request: ProviderRequester = (
        request_agent_col_routing_v3_directive
    ),
    repository_commit: str | None = None,
    repository_dirty: bool | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    """Evaluate routing decisions directly through Vertex AI and ADC."""
    load_dotenv()
    try:
        settings = load_vertex_ai_settings(
            environment if environment is not None else os.environ
        )
        scenarios = load_tool_belt_routing_v3_scenarios(fixture_path)
        selected = _select_scenarios(scenarios, selected_scenario_id)
        if mode not in {"baseline", "declared"} or not selected:
            raise ValueError("Live evaluation selection is invalid.")
        commit = repository_commit or resolve_repository_commit()
        dirty = (
            is_repository_dirty()
            if repository_dirty is None
            else repository_dirty
        )
        if not _REPOSITORY_COMMIT.fullmatch(commit):
            raise ValueError("Repository commit identifier is invalid.")
    except (
        OSError,
        subprocess.SubprocessError,
        ValidationError,
        ValueError,
        VertexAIConfigurationError,
    ):
        output("tool-belt-routing-check configuration_error")
        return 2

    planned_attempts = sum(
        _attempt_count(scenario, mode) for scenario in selected
    )
    manual_review_attempts = 0
    output(
        " ".join(
            (
                "tool-belt-routing-check",
                f"fixture={selected[0].fixture_version}",
                "schema=3.0",
                f"commit={commit}",
                f"worktree={'dirty' if dirty else 'clean'}",
                f"model={AGENT_COL_ROUTING_V3_MODEL_NAME}",
                "provider=vertex_ai",
                f"mode={mode}",
                f"scenarios={len(selected)}",
                f"planned_attempts={planned_attempts}",
            )
        )
    )
    started_at = monotonic()
    client = client_factory(**settings.client_kwargs())
    provider_calls = 0
    try:

        def report_attempt(line: str) -> None:
            nonlocal manual_review_attempts
            if line.endswith("manual_review_required"):
                manual_review_attempts += 1
            output(line)

        async def request_directive(
            scenario: ToolBeltRoutingV3Scenario,
            _repetition: int,
        ) -> AgentColRoutingDirective:
            nonlocal provider_calls
            provider_calls += 1
            return await provider_request(client, scenario.routing_input)

        exit_code = await run_tool_belt_routing_evaluation(
            scenarios=selected,
            selected_scenario_id=None,
            mode=mode,
            request_directive=request_directive,
            output=report_attempt,
        )
    finally:
        try:
            await client.aio.aclose()
        finally:
            client.close()
    elapsed_ms = round((monotonic() - started_at) * 1_000)
    output(
        " ".join(
            (
                "tool-belt-routing-check summary",
                f"planned_attempts={planned_attempts}",
                f"provider_calls={provider_calls}",
                f"manual_review_attempts={manual_review_attempts}",
                f"elapsed_ms={elapsed_ms}",
                f"exit={exit_code}",
            )
        )
    )
    return exit_code


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
        "--mode",
        choices=("baseline", "declared"),
        default="baseline",
        help="Run one baseline attempt or fixture-declared repetitions.",
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
            fixture_path=DEFAULT_TOOL_BELT_ROUTING_V3_FIXTURE_PATH,
            selected_scenario_id=arguments.scenario,
            mode=arguments.mode,
            output=print,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
