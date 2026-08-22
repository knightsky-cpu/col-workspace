import argparse
import asyncio
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol, Sequence
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError

from schemas import ChatResponse
from source_routing_evaluation import (
    DEFAULT_SOURCE_ROUTING_FIXTURE_PATH,
    SourceRoutingScenario,
    evaluate_source_routing,
    load_source_routing_scenarios,
)


PROJECT_ID = "agent-col"
OutputWriter = Callable[[str], None]
ChatRequester = Callable[
    [SourceRoutingScenario, int, str],
    Awaitable[tuple[ChatResponse, ...]],
]


class FixtureRunner(Protocol):
    async def __call__(self, **kwargs: object) -> int: ...


class SourceRoutingProviderError(RuntimeError):
    """Raised when the provider cannot complete an evaluation turn."""


class SourceRoutingTransportError(RuntimeError):
    """Raised when the evaluation cannot reach Agent_Col."""


class SourceRoutingProtocolError(RuntimeError):
    """Raised when the public chat contract is not usable."""


def build_attempt_identifier(
    *,
    scenario_id: str,
    repetition: int,
    run_id: str,
) -> str:
    """Build one bounded public identifier without scenario content."""
    bounded_scenario_id = scenario_id[:48]
    return f"m7-exp4d-{run_id[:40]}-{bounded_scenario_id}-{repetition}"


async def request_live_chat(
    *,
    client: httpx.AsyncClient,
    scenario: SourceRoutingScenario,
    repetition: int,
    run_id: str,
) -> tuple[ChatResponse, ...]:
    """Execute one isolated scenario through the public chat API."""
    identifier = build_attempt_identifier(
        scenario_id=scenario.scenario_id,
        repetition=repetition,
        run_id=run_id,
    )
    payload = {
        "project_id": PROJECT_ID,
        "session_id": identifier,
        "user_id": identifier,
        "message": scenario.message,
    }
    request_count = (
        2 if scenario.execution_mode == "idempotency_replay" else 1
    )
    responses: list[ChatResponse] = []
    for _ in range(request_count):
        try:
            response = await client.post(
                "/api/chat",
                headers={"Idempotency-Key": identifier},
                json=payload,
            )
        except httpx.RequestError:
            raise SourceRoutingTransportError(
                "Agent_Col transport failed."
            ) from None
        if response.status_code in (502, 504):
            raise SourceRoutingProviderError(
                "Agent_Col provider execution failed."
            )
        if response.status_code != 200:
            raise SourceRoutingProtocolError(
                "Agent_Col returned an unexpected status."
            )
        try:
            responses.append(ChatResponse.model_validate(response.json()))
        except (TypeError, ValueError):
            raise SourceRoutingProtocolError(
                "Agent_Col response validation failed."
            ) from None
    return tuple(responses)


async def run_source_routing_check(
    *,
    scenarios: tuple[SourceRoutingScenario, ...],
    selected_scenario_id: str | None,
    repetitions: int,
    run_id: str,
    request_chat: ChatRequester,
    output: OutputWriter,
) -> int:
    """Run selected Source scenarios and classify typed evidence."""
    if repetitions < 1 or repetitions > 3:
        output("source-routing-check configuration_error")
        return 2
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", run_id):
        output("source-routing-check configuration_error")
        return 2
    selected = tuple(
        scenario
        for scenario in scenarios
        if selected_scenario_id is None
        or scenario.scenario_id == selected_scenario_id
    )
    if not selected:
        output("source-routing-check configuration_error")
        return 2

    has_routing_failure = False
    has_execution_failure = False
    for scenario in selected:
        for repetition in range(1, repetitions + 1):
            prefix = f"{scenario.scenario_id} run={repetition}"
            try:
                responses = await request_chat(
                    scenario,
                    repetition,
                    run_id,
                )
            except SourceRoutingProviderError:
                has_execution_failure = True
                output(f"{prefix} provider_error")
                continue
            except SourceRoutingTransportError:
                has_execution_failure = True
                output(f"{prefix} transport_error")
                continue
            except SourceRoutingProtocolError:
                has_execution_failure = True
                output(f"{prefix} response_contract_error")
                continue

            findings = evaluate_source_routing(scenario, responses)
            if findings:
                has_routing_failure = True
                output(
                    " ".join(
                        (prefix, *(finding.code for finding in findings))
                    )
                )
                continue
            if scenario.manual_semantic_review != "none":
                output(f"{prefix} pass manual_review_required")
            else:
                output(f"{prefix} pass")

    if has_execution_failure:
        return 2
    return 1 if has_routing_failure else 0


async def run_source_routing_fixture(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    run_id: str,
    request_chat: ChatRequester,
    output: OutputWriter,
) -> int:
    """Load the fixture safely before executing any live request."""
    try:
        scenarios = load_source_routing_scenarios(fixture_path)
    except (OSError, ValidationError):
        output("source-routing-check configuration_error")
        return 2
    return await run_source_routing_check(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        repetitions=repetitions,
        run_id=run_id,
        request_chat=request_chat,
        output=output,
    )


async def run_live_source_routing_fixture(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    run_id: str,
    base_url: str,
    output: OutputWriter,
) -> int:
    """Run the fixture against a live Agent_Col API."""
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=120.0,
        ) as client:

            async def request_chat(
                scenario: SourceRoutingScenario,
                repetition: int,
                current_run_id: str,
            ) -> tuple[ChatResponse, ...]:
                return await request_live_chat(
                    client=client,
                    scenario=scenario,
                    repetition=repetition,
                    run_id=current_run_id,
                )

            return await run_source_routing_fixture(
                fixture_path=fixture_path,
                selected_scenario_id=selected_scenario_id,
                repetitions=repetitions,
                run_id=run_id,
                request_chat=request_chat,
                output=output,
            )
    except (TypeError, ValueError):
        output("source-routing-check configuration_error")
        return 2


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded live Source routing parser."""
    parser = argparse.ArgumentParser(
        description="Evaluate Agent_Col Source routing and restraint."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the running Agent_Col API.",
    )
    parser.add_argument(
        "--scenario",
        help="Run one Source routing scenario by ID.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="Run each selected scenario 1 to 3 times.",
    )
    parser.add_argument(
        "--run-id",
        help="Content-free identifier used for isolated test records.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    fixture_runner: FixtureRunner = run_live_source_routing_fixture,
    id_factory: Callable[[], UUID] = uuid4,
) -> int:
    """Run the live M7-EXP.4D evaluation."""
    arguments = build_parser().parse_args(argv)
    run_id = arguments.run_id or id_factory().hex
    return asyncio.run(
        fixture_runner(
            fixture_path=DEFAULT_SOURCE_ROUTING_FIXTURE_PATH,
            selected_scenario_id=arguments.scenario,
            repetitions=arguments.repetitions,
            run_id=run_id,
            base_url=arguments.base_url,
            output=print,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
