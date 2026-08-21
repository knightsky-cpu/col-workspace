import importlib
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import httpx
import pytest


@pytest.mark.asyncio
async def test_run_chat_idempotency_smoke_exercises_new_replay_and_conflict(
) -> None:
    try:
        module = importlib.import_module("smoke_test_chat_idempotency")
    except ModuleNotFoundError:
        pytest.fail(
            "smoke_test_chat_idempotency module is missing",
            pytrace=False,
        )

    requests: list[httpx.Request] = []
    response_payload = {
        "response": "private generated answer",
        "actions": [],
        "artifacts": [],
        "citations": [],
        "adaptations": [],
    }

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) <= 2:
            return httpx.Response(200, json=response_payload)
        return httpx.Response(
            409,
            json={
                "detail": (
                    "Idempotency key conflicts with a different chat "
                    "request."
                )
            },
        )

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        result = await module.run_chat_idempotency_smoke(
            client=client,
            id_factory=lambda: UUID(
                "12345678-1234-5678-1234-567812345678"
            ),
        )

    assert len(requests) == 3
    assert all(request.method == "POST" for request in requests)
    assert all(request.url.path == "/api/chat" for request in requests)
    assert requests[0].headers["Idempotency-Key"] == (
        "m6-2-3-12345678123456781234567812345678"
    )
    assert requests[1].headers["Idempotency-Key"] == (
        requests[0].headers["Idempotency-Key"]
    )
    assert requests[2].headers["Idempotency-Key"] == (
        requests[0].headers["Idempotency-Key"]
    )
    assert requests[0].content == requests[1].content
    assert requests[2].content != requests[0].content
    assert result.user_id == (
        "memory-m6-2-3-user-12345678123456781234567812345678"
    )
    assert result.session_id == (
        "memory-m6-2-3-session-12345678123456781234567812345678"
    )
    assert result.turn_id == (
        "dd7a63ebfeae5a7bdcf281713a0b696686eaacbedcec26402bfd34514d12d373"
    )
    assert result.user_message_id == (
        "turn--dd7a63ebfeae5a7bdcf281713a0b696686eaacbedcec26402bfd34514d12d373"
        "--user"
    )
    assert result.model_message_id == (
        "turn--dd7a63ebfeae5a7bdcf281713a0b696686eaacbedcec26402bfd34514d12d373"
        "--model"
    )
    assert result.first_status == 200
    assert result.replay_status == 200
    assert result.conflict_status == 409
    assert result.replay_equal


@pytest.mark.asyncio
async def test_run_chat_idempotency_smoke_translates_invalid_response_safely(
) -> None:
    module = importlib.import_module("smoke_test_chat_idempotency")
    private_response = "private-provider-payload"

    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=private_response)

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        with pytest.raises(
            module.ChatIdempotencySmokeError,
            match="Initial response validation failed",
        ) as exc_info:
            await module.run_chat_idempotency_smoke(client=client)

    assert private_response not in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_chat_idempotency_smoke_translates_transport_failure_safely(
) -> None:
    module = importlib.import_module("smoke_test_chat_idempotency")
    private_transport_detail = "private-network-detail"

    def handle_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(private_transport_detail, request=request)

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        with pytest.raises(
            module.ChatIdempotencySmokeError,
            match="Initial request transport failed",
        ) as exc_info:
            await module.run_chat_idempotency_smoke(client=client)

    assert private_transport_detail not in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_chat_idempotency_smoke_rejects_invalid_conflict_safely(
) -> None:
    module = importlib.import_module("smoke_test_chat_idempotency")
    private_conflict_payload = "private-conflict-payload"
    response_payload = {
        "response": "private generated answer",
        "actions": [],
        "artifacts": [],
        "citations": [],
        "adaptations": [],
    }
    call_count = 0

    def handle_request(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return httpx.Response(200, json=response_payload)
        return httpx.Response(409, text=private_conflict_payload)

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        with pytest.raises(
            module.ChatIdempotencySmokeError,
            match="Conflict response validation failed",
        ) as exc_info:
            await module.run_chat_idempotency_smoke(client=client)

    assert private_conflict_payload not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("responses", "expected_error"),
    [
        (
            [
                (503, {"response": "private-initial", "actions": []}),
            ],
            "Initial request returned unexpected status 503",
        ),
        (
            [
                (200, {"response": "private-answer", "actions": []}),
                (503, {"response": "private-replay", "actions": []}),
            ],
            "Replay request returned unexpected status 503",
        ),
        (
            [
                (200, {"response": "private-answer", "actions": []}),
                (200, {"response": "private-answer", "actions": []}),
                (200, {"detail": "private-conflict-body"}),
            ],
            "Conflict request returned unexpected status 200",
        ),
        (
            [
                (200, {"response": "private-answer", "actions": []}),
                (200, {"response": "private-answer", "actions": []}),
                (409, {"detail": "private-conflict-body"}),
            ],
            "Conflict response did not match the public contract",
        ),
    ],
)
async def test_run_chat_idempotency_smoke_rejects_status_contract_failures(
    responses: list[tuple[int, dict[str, object]]],
    expected_error: str,
) -> None:
    module = importlib.import_module("smoke_test_chat_idempotency")
    queued = list(responses)

    def handle_request(_request: httpx.Request) -> httpx.Response:
        if not queued:
            return httpx.Response(
                409,
                json={
                    "detail": (
                        "Idempotency key conflicts with a different chat "
                        "request."
                    )
                },
            )
        status_code, payload = queued.pop(0)
        return httpx.Response(status_code, json=payload)

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        with pytest.raises(
            module.ChatIdempotencySmokeError,
            match=expected_error,
        ) as exc_info:
            await module.run_chat_idempotency_smoke(client=client)

    assert "private" not in str(exc_info.value)


def test_safe_summary_contains_only_structural_evidence() -> None:
    module = importlib.import_module("smoke_test_chat_idempotency")
    result = module.ChatIdempotencySmokeResult(
        user_id="memory-m6-2-3-user-safe-id",
        session_id="memory-m6-2-3-session-safe-id",
        turn_id="safe-turn-id",
        user_message_id="safe-user-message-id",
        model_message_id="safe-model-message-id",
        first_status=200,
        replay_status=200,
        conflict_status=409,
        replay_equal=True,
    )

    summary = result.safe_summary()

    assert summary == (
        "trusted-memory-m6-2-3 pass first=200 replay=200 conflict=409 "
        "replay_equal=true user_id=memory-m6-2-3-user-safe-id "
        "session_id=memory-m6-2-3-session-safe-id turn_id=safe-turn-id "
        "user_message_id=safe-user-message-id "
        "model_message_id=safe-model-message-id"
    )
    assert "raw-idempotency-key" not in summary
    assert module.SOURCE_MESSAGE not in summary
    assert module.CONFLICT_MESSAGE not in summary
    assert "private generated answer" not in summary


@pytest.mark.parametrize(
    ("argv", "expected_base_url"),
    [
        ([], "http://127.0.0.1:8000"),
        (["--base-url", "https://agent-col.example"],
         "https://agent-col.example"),
    ],
)
def test_main_uses_selected_base_url_and_prints_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    expected_base_url: str,
) -> None:
    module = importlib.import_module("smoke_test_chat_idempotency")
    observed_urls: list[str] = []
    result = module.ChatIdempotencySmokeResult(
        user_id="safe-user",
        session_id="safe-session",
        turn_id="safe-turn",
        user_message_id="safe-user-message",
        model_message_id="safe-model-message",
        first_status=200,
        replay_status=200,
        conflict_status=409,
        replay_equal=True,
    )

    async def fake_run_from_cli(base_url: str) -> object:
        observed_urls.append(base_url)
        return result

    monkeypatch.setattr(
        module,
        "_run_from_cli",
        fake_run_from_cli,
        raising=False,
    )

    exit_code = module.main(argv)

    assert exit_code == 0
    assert observed_urls == [expected_base_url]
    assert capsys.readouterr().out == f"{result.safe_summary()}\n"


@pytest.mark.asyncio
async def test_run_from_cli_closes_the_configured_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("smoke_test_chat_idempotency")
    observed: dict[str, object] = {}
    sentinel_result = object()

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            observed["client_kwargs"] = kwargs

        async def __aenter__(self) -> "FakeAsyncClient":
            observed["entered"] = True
            return self

        async def __aexit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            observed["closed"] = True

    async def fake_run_chat_idempotency_smoke(*, client: object) -> object:
        observed["smoke_client"] = client
        return sentinel_result

    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        module,
        "run_chat_idempotency_smoke",
        fake_run_chat_idempotency_smoke,
    )

    result = await module._run_from_cli("https://agent-col.example")

    assert result is sentinel_result
    assert observed["client_kwargs"] == {
        "base_url": "https://agent-col.example",
        "timeout": 100.0,
    }
    assert observed["entered"] is True
    assert observed["smoke_client"].__class__ is FakeAsyncClient
    assert observed["closed"] is True


def test_script_entrypoint_exposes_help_without_network() -> None:
    repository_root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(
        [
            sys.executable,
            str(repository_root / "smoke_test_chat_idempotency.py"),
            "--help",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Verify the live /api/chat idempotency contract." in (
        completed.stdout
    )
    assert completed.stderr == ""


def test_main_reports_smoke_failure_without_traceback_or_private_content(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("smoke_test_chat_idempotency")

    async def fake_run_from_cli(_base_url: str) -> object:
        raise module.ChatIdempotencySmokeError(
            "Initial request returned unexpected status 502."
        )

    monkeypatch.setattr(module, "_run_from_cli", fake_run_from_cli)

    exit_code = module.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "trusted-memory-m6-2-3 fail "
        "Initial request returned unexpected status 502.\n"
    )
    assert "Traceback" not in captured.err
