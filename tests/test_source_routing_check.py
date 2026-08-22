import json
from uuid import UUID

import httpx
import pytest

from schemas import ChatResponse
from source_routing_evaluation import SourceRoutingScenario


def make_scenario(
    scenario_id: str,
    *,
    expected_routing: str = "direct",
    manual_semantic_review: str = "none",
    execution_mode: str = "single",
) -> SourceRoutingScenario:
    return SourceRoutingScenario(
        scenario_id=scenario_id,
        fixture_version="1.0",
        message=f"private message for {scenario_id}",
        expected_routing=expected_routing,
        allowed_citation_urls=(
            ("https://example.com/",)
            if expected_routing == "source"
            else ()
        ),
        manual_semantic_review=manual_semantic_review,
        execution_mode=execution_mode,
    )


def make_response(
    *,
    routing: str = "direct",
) -> ChatResponse:
    action_name = {
        "source": "url_context",
        "research": "google_search",
    }.get(routing)
    citation_url = {
        "source": "https://example.com/",
        "research": "https://www.python.org/downloads/",
    }.get(routing)
    return ChatResponse.model_validate(
        {
            "response": "private model response",
            "actions": (
                [{"action_name": action_name, "status": "completed"}]
                if action_name
                else []
            ),
            "artifacts": [],
            "citations": (
                [{"uri": citation_url, "label": "Validated source"}]
                if citation_url
                else []
            ),
            "memory_proposals": [],
            "adaptations": [],
        }
    )


@pytest.mark.asyncio
async def test_runner_evaluates_receipts_and_marks_manual_review() -> None:
    from source_routing_check import run_source_routing_check

    calls: list[tuple[str, int, str]] = []

    async def request_chat(
        scenario: SourceRoutingScenario,
        repetition: int,
        run_id: str,
    ) -> tuple[ChatResponse, ...]:
        calls.append((scenario.scenario_id, repetition, run_id))
        return (make_response(routing="source"),)

    output: list[str] = []
    exit_code = await run_source_routing_check(
        scenarios=(
            make_scenario(
                "explicit-source",
                expected_routing="source",
                manual_semantic_review="source_response_quality",
            ),
        ),
        selected_scenario_id=None,
        repetitions=1,
        run_id="safe-run",
        request_chat=request_chat,
        output=output.append,
    )

    assert exit_code == 0
    assert calls == [("explicit-source", 1, "safe-run")]
    assert output == [
        "explicit-source run=1 pass manual_review_required"
    ]


@pytest.mark.asyncio
async def test_runner_distinguishes_routing_and_execution_failures() -> None:
    import source_routing_check as module

    responses = iter(
        (
            (make_response(),),
            module.SourceRoutingProviderError("private provider detail"),
        )
    )

    async def request_chat(
        _scenario: SourceRoutingScenario,
        _repetition: int,
        _run_id: str,
    ) -> tuple[ChatResponse, ...]:
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    output: list[str] = []
    exit_code = await module.run_source_routing_check(
        scenarios=(
            make_scenario("must-source", expected_routing="source"),
            make_scenario("provider-failure"),
        ),
        selected_scenario_id=None,
        repetitions=1,
        run_id="private-run-id",
        request_chat=request_chat,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        "must-source run=1 missing_source_action",
        "provider-failure run=1 provider_error",
    ]
    assert "private" not in " ".join(output)


@pytest.mark.asyncio
async def test_live_request_reuses_exact_payload_and_idempotency_key() -> None:
    from source_routing_check import request_live_chat

    requests: list[httpx.Request] = []
    expected_response = make_response(routing="source")

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=expected_response.model_dump(mode="json"),
        )

    scenario = make_scenario(
        "replay",
        expected_routing="source",
        manual_semantic_review="source_response_quality",
        execution_mode="idempotency_replay",
    )
    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        responses = await request_live_chat(
            client=client,
            scenario=scenario,
            repetition=1,
            run_id="safe-run",
        )

    assert responses == (expected_response, expected_response)
    assert len(requests) == 2
    assert requests[0].content == requests[1].content
    assert (
        requests[0].headers["Idempotency-Key"]
        == requests[1].headers["Idempotency-Key"]
    )
    payload = json.loads(requests[0].content)
    assert payload == {
        "project_id": "agent-col",
        "session_id": "m7-exp4d-safe-run-replay-1",
        "user_id": "m7-exp4d-safe-run-replay-1",
        "message": "private message for replay",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "error_name"),
    (
        (
            httpx.Response(502, text="private-provider-payload"),
            "SourceRoutingProviderError",
        ),
        (
            httpx.Response(504, text="private-timeout-payload"),
            "SourceRoutingProviderError",
        ),
        (
            httpx.Response(200, text="private-invalid-response"),
            "SourceRoutingProtocolError",
        ),
    ),
)
async def test_live_request_translates_failures_without_leaking_payloads(
    response: httpx.Response,
    error_name: str,
) -> None:
    import source_routing_check as module

    transport = httpx.MockTransport(lambda _request: response)
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
@pytest.mark.parametrize(
    ("repetitions", "run_id", "selected_scenario_id"),
    (
        (0, "safe-run", None),
        (4, "safe-run", None),
        (1, "contains spaces", None),
        (1, "safe-run", "missing-scenario"),
    ),
)
async def test_runner_rejects_invalid_configuration_before_requests(
    repetitions: int,
    run_id: str,
    selected_scenario_id: str | None,
) -> None:
    from source_routing_check import run_source_routing_check

    async def request_chat(
        _scenario: SourceRoutingScenario,
        _repetition: int,
        _run_id: str,
    ) -> tuple[ChatResponse, ...]:
        raise AssertionError("invalid configuration must make no request")

    output: list[str] = []
    exit_code = await run_source_routing_check(
        scenarios=(make_scenario("ordinary"),),
        selected_scenario_id=selected_scenario_id,
        repetitions=repetitions,
        run_id=run_id,
        request_chat=request_chat,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["source-routing-check configuration_error"]


def test_main_forwards_cli_options_and_generates_default_run_id() -> None:
    from source_routing_check import main

    received: list[dict[str, object]] = []

    async def fixture_runner(**kwargs: object) -> int:
        received.append(kwargs)
        return 1

    exit_code = main(
        [
            "--base-url",
            "https://agent-col.example",
            "--scenario",
            "explicit-single-url",
            "--repetitions",
            "2",
        ],
        fixture_runner=fixture_runner,
        id_factory=lambda: UUID(
            "12345678-1234-5678-1234-567812345678"
        ),
    )

    assert exit_code == 1
    assert len(received) == 1
    assert received[0]["base_url"] == "https://agent-col.example"
    assert received[0]["selected_scenario_id"] == "explicit-single-url"
    assert received[0]["repetitions"] == 2
    assert received[0]["run_id"] == "12345678123456781234567812345678"
