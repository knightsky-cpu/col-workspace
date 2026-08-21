import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from memory_routing_evaluation import (
    ExpectedProposal,
    MemoryRoutingScenario,
)
from schemas import ChatResponse


def make_scenario(
    scenario_id: str,
    *,
    expected_routing: str = "no_proposal",
    execution_mode: str = "stateless",
    state_precondition: str = "none",
) -> MemoryRoutingScenario:
    return MemoryRoutingScenario(
        scenario_id=scenario_id,
        fixture_version="1.0",
        message=f"private message for {scenario_id}",
        expected_routing=expected_routing,
        expected_proposal=(
            ExpectedProposal(
                category="response_length",
                proposed_value="concise",
            )
            if expected_routing == "propose"
            else None
        ),
        manual_semantic_review=(
            "clarification_quality"
            if expected_routing == "clarify_without_proposal"
            else "none"
        ),
        execution_mode=execution_mode,
        state_precondition=state_precondition,
    )


def make_response(*, with_proposal: bool = False) -> ChatResponse:
    return ChatResponse.model_validate(
        {
            "response": "private model response",
            "actions": (
                [
                    {
                        "action_name": "propose_memory_signal",
                        "status": "completed",
                    }
                ]
                if with_proposal
                else []
            ),
            "artifacts": [],
            "citations": [],
            "memory_proposals": (
                [
                    {
                        "proposal_id": "private-proposal-id",
                        "category": "response_length",
                        "proposed_value": "concise",
                        "expires_at": "2026-08-22T12:00:00Z",
                    }
                ]
                if with_proposal
                else []
            ),
            "adaptations": [],
        }
    )


@pytest.mark.asyncio
async def test_runner_selects_scenario_and_reports_manual_review() -> None:
    from memory_routing_check import run_routing_check

    calls: list[tuple[str, int, str]] = []

    async def request_chat(
        scenario: MemoryRoutingScenario,
        repetition: int,
        run_id: str,
    ) -> ChatResponse:
        calls.append((scenario.scenario_id, repetition, run_id))
        return make_response()

    output: list[str] = []
    exit_code = await run_routing_check(
        scenarios=(
            make_scenario("ordinary"),
            make_scenario(
                "ambiguous",
                expected_routing="clarify_without_proposal",
            ),
        ),
        selected_scenario_id="ambiguous",
        repetitions=1,
        run_id="safe-run",
        request_chat=request_chat,
        output=output.append,
    )

    assert exit_code == 0
    assert calls == [("ambiguous", 1, "safe-run")]
    assert output == ["ambiguous run=1 pass manual_review_required"]


@pytest.mark.asyncio
async def test_runner_returns_one_for_routing_failure_without_content() -> None:
    from memory_routing_check import run_routing_check

    async def request_chat(
        _scenario: MemoryRoutingScenario,
        _repetition: int,
        _run_id: str,
    ) -> ChatResponse:
        return make_response()

    output: list[str] = []
    exit_code = await run_routing_check(
        scenarios=(make_scenario("must-propose", expected_routing="propose"),),
        selected_scenario_id=None,
        repetitions=1,
        run_id="private-run-id",
        request_chat=request_chat,
        output=output.append,
    )

    assert exit_code == 1
    assert output == ["must-propose run=1 missing_proposal"]
    assert "private message" not in " ".join(output)
    assert "private-run-id" not in " ".join(output)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_name", "expected_code"),
    (
        ("MemoryRoutingProviderError", "provider_error"),
        ("MemoryRoutingTransportError", "transport_error"),
        ("MemoryRoutingProtocolError", "response_contract_error"),
    ),
)
async def test_runner_returns_two_for_execution_failure_and_continues(
    error_name: str,
    expected_code: str,
) -> None:
    import memory_routing_check as module

    calls = 0

    async def request_chat(
        _scenario: MemoryRoutingScenario,
        _repetition: int,
        _run_id: str,
    ) -> ChatResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise getattr(module, error_name)("private failure detail")
        return make_response()

    output: list[str] = []
    exit_code = await module.run_routing_check(
        scenarios=(make_scenario("one"), make_scenario("two")),
        selected_scenario_id=None,
        repetitions=1,
        run_id="private-run-id",
        request_chat=request_chat,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        f"one run=1 {expected_code}",
        "two run=1 pass",
    ]
    assert calls == 2
    assert "private failure detail" not in " ".join(output)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selected_scenario_id", "scenarios"),
    (
        ("unknown", (make_scenario("known"),)),
        (
            "stateful",
            (
                make_scenario(
                    "stateful",
                    execution_mode="stateful",
                    state_precondition="active_identical_preference",
                ),
            ),
        ),
    ),
)
async def test_runner_rejects_unknown_or_stateful_selection_before_request(
    selected_scenario_id: str,
    scenarios: tuple[MemoryRoutingScenario, ...],
) -> None:
    from memory_routing_check import run_routing_check

    requests = 0

    async def request_chat(
        _scenario: MemoryRoutingScenario,
        _repetition: int,
        _run_id: str,
    ) -> ChatResponse:
        nonlocal requests
        requests += 1
        return make_response()

    output: list[str] = []
    exit_code = await run_routing_check(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        repetitions=1,
        run_id="safe-run",
        request_chat=request_chat,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["memory-routing-check configuration_error"]
    assert requests == 0


@pytest.mark.asyncio
async def test_runner_uses_each_requested_repetition_once() -> None:
    from memory_routing_check import run_routing_check

    repetitions: list[int] = []

    async def request_chat(
        _scenario: MemoryRoutingScenario,
        repetition: int,
        _run_id: str,
    ) -> ChatResponse:
        repetitions.append(repetition)
        return make_response()

    output: list[str] = []
    exit_code = await run_routing_check(
        scenarios=(make_scenario("ordinary"),),
        selected_scenario_id=None,
        repetitions=3,
        run_id="safe-run",
        request_chat=request_chat,
        output=output.append,
    )

    assert exit_code == 0
    assert repetitions == [1, 2, 3]
    assert output == [
        "ordinary run=1 pass",
        "ordinary run=2 pass",
        "ordinary run=3 pass",
    ]


def test_attempt_identifiers_are_unique_bounded_and_content_free() -> None:
    from memory_routing_check import build_attempt_identifiers

    first = build_attempt_identifiers(
        scenario_id="a-very-long-scenario-name-that-must-remain-bounded",
        repetition=1,
        run_id="safe-run",
    )
    second = build_attempt_identifiers(
        scenario_id="a-very-long-scenario-name-that-must-remain-bounded",
        repetition=2,
        run_id="safe-run",
    )

    assert first != second
    assert max(map(len, first)) <= 128
    assert max(map(len, second)) <= 128
    assert "private" not in " ".join(first + second)


@pytest.mark.asyncio
async def test_live_request_uses_unique_owned_ids_and_typed_response() -> None:
    from memory_routing_check import request_live_chat

    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=make_response().model_dump(mode="json"))

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await request_live_chat(
            client=client,
            scenario=make_scenario("ordinary"),
            repetition=2,
            run_id="safe-run",
        )

    assert response == make_response()
    assert len(requests) == 1
    request = requests[0]
    payload = json.loads(request.content)
    assert request.url.path == "/api/chat"
    assert request.headers["Idempotency-Key"].endswith("ordinary-2")
    assert payload == {
        "project_id": "agent-col",
        "session_id": "m7-5a-safe-run-ordinary-2",
        "user_id": "m7-5a-safe-run-ordinary-2",
        "message": "private message for ordinary",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "error_name"),
    (
        (
            httpx.Response(502, text="private-provider-payload"),
            "MemoryRoutingProviderError",
        ),
        (
            httpx.Response(200, text="private-invalid-response"),
            "MemoryRoutingProtocolError",
        ),
    ),
)
async def test_live_request_translates_provider_and_contract_failures_safely(
    response: httpx.Response,
    error_name: str,
) -> None:
    import memory_routing_check as module

    def handle_request(_request: httpx.Request) -> httpx.Response:
        return response

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        with pytest.raises(getattr(module, error_name)) as exc_info:
            await module.request_live_chat(
                client=client,
                scenario=make_scenario("ordinary"),
                repetition=1,
                run_id="safe-run",
            )

    assert "private" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_fixture_runner_rejects_malformed_fixture_safely(
    tmp_path: Path,
) -> None:
    from memory_routing_check import run_routing_fixture

    fixture_path = tmp_path / "private-fixture.json"
    fixture_path.write_text('{"private-content":', encoding="utf-8")
    requests = 0

    async def request_chat(
        _scenario: MemoryRoutingScenario,
        _repetition: int,
        _run_id: str,
    ) -> ChatResponse:
        nonlocal requests
        requests += 1
        return make_response()

    output: list[str] = []
    exit_code = await run_routing_fixture(
        fixture_path=fixture_path,
        selected_scenario_id=None,
        repetitions=1,
        run_id="safe-run",
        request_chat=request_chat,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["memory-routing-check configuration_error"]
    assert requests == 0
    assert "private-content" not in " ".join(output)


def test_main_forwards_explicit_live_evaluation_options() -> None:
    from memory_routing_check import main

    received: list[dict[str, object]] = []

    async def fixture_runner(**kwargs: object) -> int:
        received.append(kwargs)
        return 1

    exit_code = main(
        [
            "--base-url",
            "https://agent-col.example",
            "--scenario",
            "ordinary-explanation",
            "--repetitions",
            "3",
            "--run-id",
            "manual-baseline",
        ],
        fixture_runner=fixture_runner,
    )

    assert exit_code == 1
    assert len(received) == 1
    assert received[0]["base_url"] == "https://agent-col.example"
    assert received[0]["selected_scenario_id"] == "ordinary-explanation"
    assert received[0]["repetitions"] == 3
    assert received[0]["run_id"] == "manual-baseline"
    assert callable(received[0]["output"])


def test_main_generates_content_free_run_id_when_omitted() -> None:
    from memory_routing_check import main

    received_run_ids: list[str] = []

    async def fixture_runner(**kwargs: object) -> int:
        received_run_ids.append(str(kwargs["run_id"]))
        return 0

    exit_code = main(
        [],
        fixture_runner=fixture_runner,
        id_factory=lambda: UUID(
            "12345678-1234-5678-1234-567812345678"
        ),
    )

    assert exit_code == 0
    assert received_run_ids == ["12345678123456781234567812345678"]
