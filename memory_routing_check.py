import argparse
import asyncio
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol, Sequence
from uuid import UUID, uuid4

import httpx
from google.auth.exceptions import GoogleAuthError
from pydantic import ValidationError

from memory_routing_evaluation import (
    DEFAULT_MEMORY_ROUTING_FIXTURE_PATH,
    MemoryRoutingScenario,
    evaluate_routing,
    load_routing_scenarios,
)
from memory_routing_state import (
    MemoryRoutingStateError,
    MemoryRoutingStateManager,
)
from schemas import ChatResponse, MemoryDecisionRequest


PROJECT_ID = "agent-col"
OutputWriter = Callable[[str], None]
ChatRequester = Callable[
    [MemoryRoutingScenario, int, str, MemoryDecisionRequest | None],
    Awaitable[ChatResponse],
]
StatePreparer = Callable[
    [MemoryRoutingScenario, str, str],
    Awaitable[MemoryDecisionRequest | None],
]


class FixtureRunner(Protocol):
    async def __call__(self, **kwargs: object) -> int: ...


class MemoryRoutingProviderError(RuntimeError):
    """Raised when the provider cannot complete an evaluation turn."""


class MemoryRoutingTransportError(RuntimeError):
    """Raised when the evaluation cannot reach Agent_Col."""


class MemoryRoutingProtocolError(RuntimeError):
    """Raised when the public chat contract is not usable."""


def build_attempt_identifiers(
    *,
    scenario_id: str,
    repetition: int,
    run_id: str,
) -> tuple[str, str, str]:
    """Build bounded public identifiers without using scenario content."""
    bounded_scenario_id = scenario_id[:48]
    identifier = f"m7-5a-{run_id[:40]}-{bounded_scenario_id}-{repetition}"
    return identifier, identifier, identifier


async def request_live_chat(
    *,
    client: httpx.AsyncClient,
    scenario: MemoryRoutingScenario,
    repetition: int,
    run_id: str,
    memory_decision: MemoryDecisionRequest | None = None,
) -> ChatResponse:
    """Execute one isolated routing scenario through the public API."""
    user_id, session_id, idempotency_key = build_attempt_identifiers(
        scenario_id=scenario.scenario_id,
        repetition=repetition,
        run_id=run_id,
    )
    payload: dict[str, object] = {
        "project_id": PROJECT_ID,
        "session_id": session_id,
        "user_id": user_id,
        "message": scenario.message,
    }
    if memory_decision is not None:
        payload["memory_decision"] = memory_decision.model_dump(mode="json")
    try:
        response = await client.post(
            "/api/chat",
            headers={"Idempotency-Key": idempotency_key},
            json=payload,
        )
    except httpx.RequestError:
        raise MemoryRoutingTransportError(
            "Agent_Col transport failed."
        ) from None
    if response.status_code in (502, 504):
        raise MemoryRoutingProviderError(
            "Agent_Col provider execution failed."
        )
    if response.status_code != 200:
        raise MemoryRoutingProtocolError(
            "Agent_Col returned an unexpected status."
        )
    try:
        return ChatResponse.model_validate(response.json())
    except (TypeError, ValueError):
        raise MemoryRoutingProtocolError(
            "Agent_Col response validation failed."
        ) from None


async def run_routing_check(
    *,
    scenarios: tuple[MemoryRoutingScenario, ...],
    selected_scenario_id: str | None,
    repetitions: int,
    run_id: str,
    request_chat: ChatRequester,
    state_preparer: StatePreparer | None = None,
    output: OutputWriter,
) -> int:
    """Run selected scenarios and classify typed routing evidence."""
    if repetitions < 1 or repetitions > 5:
        output("memory-routing-check configuration_error")
        return 2
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", run_id):
        output("memory-routing-check configuration_error")
        return 2

    if selected_scenario_id is None:
        selected = tuple(
            scenario
            for scenario in scenarios
            if scenario.execution_mode == "stateless"
        )
    else:
        selected = tuple(
            scenario
            for scenario in scenarios
            if scenario.scenario_id == selected_scenario_id
        )
    if not selected or any(
        scenario.execution_mode == "stateful" and state_preparer is None
        for scenario in selected
    ):
        output("memory-routing-check configuration_error")
        return 2

    has_routing_failure = False
    has_execution_failure = False
    for scenario in selected:
        for repetition in range(1, repetitions + 1):
            prefix = f"{scenario.scenario_id} run={repetition}"
            memory_decision = None
            if scenario.execution_mode == "stateful":
                user_id, session_id, _ = build_attempt_identifiers(
                    scenario_id=scenario.scenario_id,
                    repetition=repetition,
                    run_id=run_id,
                )
                try:
                    memory_decision = await state_preparer(
                        scenario,
                        user_id,
                        session_id,
                    )
                except MemoryRoutingStateError:
                    has_execution_failure = True
                    output(f"{prefix} state_setup_error")
                    continue
            try:
                response = await request_chat(
                    scenario,
                    repetition,
                    run_id,
                    memory_decision,
                )
            except MemoryRoutingProviderError:
                has_execution_failure = True
                output(f"{prefix} provider_error")
                continue
            except MemoryRoutingTransportError:
                has_execution_failure = True
                output(f"{prefix} transport_error")
                continue
            except MemoryRoutingProtocolError:
                has_execution_failure = True
                output(f"{prefix} response_contract_error")
                continue

            findings = evaluate_routing(scenario, response)
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


async def run_routing_fixture(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    run_id: str,
    request_chat: ChatRequester,
    state_preparer: StatePreparer | None = None,
    output: OutputWriter,
) -> int:
    """Load a fixture safely before executing any live request."""
    try:
        scenarios = load_routing_scenarios(fixture_path)
    except (OSError, ValidationError):
        output("memory-routing-check configuration_error")
        return 2
    return await run_routing_check(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        repetitions=repetitions,
        run_id=run_id,
        request_chat=request_chat,
        state_preparer=state_preparer,
        output=output,
    )


async def run_live_routing_fixture(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
    run_id: str,
    base_url: str,
    output: OutputWriter,
) -> int:
    """Run the routing fixture against a live Agent_Col API."""
    state_manager: MemoryRoutingStateManager | None = None
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=100.0,
        ) as client:

            async def request_chat(
                scenario: MemoryRoutingScenario,
                repetition: int,
                current_run_id: str,
                memory_decision: MemoryDecisionRequest | None,
            ) -> ChatResponse:
                return await request_live_chat(
                    client=client,
                    scenario=scenario,
                    repetition=repetition,
                    run_id=current_run_id,
                    memory_decision=memory_decision,
                )

            async def prepare_state(
                scenario: MemoryRoutingScenario,
                user_id: str,
                session_id: str,
            ) -> MemoryDecisionRequest | None:
                nonlocal state_manager
                if state_manager is None:
                    from database import MemoryEngine
                    from trusted_memory_service import TrustedMemoryService

                    try:
                        database = MemoryEngine()
                    except (GoogleAuthError, OSError, ValueError):
                        raise MemoryRoutingStateError(
                            "Stateful routing initialization failed."
                        ) from None
                    state_manager = MemoryRoutingStateManager(
                        database=database,
                        memory_service=TrustedMemoryService(database=database),
                    )
                return await state_manager.prepare(
                    scenario,
                    user_id=user_id,
                    session_id=session_id,
                )

            return await run_routing_fixture(
                fixture_path=fixture_path,
                selected_scenario_id=selected_scenario_id,
                repetitions=repetitions,
                run_id=run_id,
                request_chat=request_chat,
                state_preparer=prepare_state,
                output=output,
            )
    except (TypeError, ValueError):
        output("memory-routing-check configuration_error")
        return 2
    finally:
        if state_manager is not None:
            state_manager.close()


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded live routing-evaluation parser."""
    parser = argparse.ArgumentParser(
        description="Evaluate Agent_Col governed-memory routing restraint."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the running Agent_Col API.",
    )
    parser.add_argument(
        "--scenario",
        help=(
            "Run one scenario by ID; stateful scenarios require explicit "
            "selection."
        ),
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="Run each selected scenario 1 to 5 times.",
    )
    parser.add_argument(
        "--run-id",
        help=(
            "Content-free identifier used to create isolated test records."
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    fixture_runner: FixtureRunner = run_live_routing_fixture,
    id_factory: Callable[[], UUID] = uuid4,
) -> int:
    """Run the live M7.5 routing evaluation with content-free reporting."""
    arguments = build_parser().parse_args(argv)
    run_id = arguments.run_id or id_factory().hex
    return asyncio.run(
        fixture_runner(
            fixture_path=DEFAULT_MEMORY_ROUTING_FIXTURE_PATH,
            selected_scenario_id=arguments.scenario,
            repetitions=arguments.repetitions,
            run_id=run_id,
            base_url=arguments.base_url,
            output=print,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
