import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_check_module():
    try:
        return importlib.import_module("tool_belt_live_e2e_check")
    except ModuleNotFoundError:
        pytest.fail("tool_belt_live_e2e_check has not been implemented")


def chat_body(
    response: str,
    *,
    action: str | None = None,
    citations: tuple[tuple[str, str], ...] = (),
) -> dict[str, object]:
    actions = []
    if action is not None:
        actions.append({"action_name": action, "status": "completed"})
    return {
        "response": response,
        "actions": actions,
        "artifacts": [],
        "citations": [
            {"uri": uri, "label": label} for uri, label in citations
        ],
        "memory_proposals": [],
        "adaptations": [],
    }


def passing_bodies() -> dict[str, tuple[int, dict[str, object]]]:
    source_uri = "https://example.com/"
    research_uri = "https://www.python.org/downloads/"
    return {
        "direct-restraint": (
            200,
            chat_body("Tools are unnecessary for this stable explanation."),
        ),
        "clarification": (
            200,
            chat_body("Which two values should I compare?"),
        ),
        "source": (
            200,
            chat_body(
                f"The page at {source_uri} is an example domain.",
                action="url_context",
                citations=((source_uri, "Example Domain"),),
            ),
        ),
        "research": (
            200,
            chat_body(
                f"The current release is supported by {research_uri}.",
                action="google_search",
                citations=((research_uri, "python.org"),),
            ),
        ),
        "computation": (
            200,
            chat_body(
                "The mean is 19.5000 and population standard deviation is "
                "5.1235.",
                action="run_computation",
            ),
        ),
        "requirements-verification": (
            200,
            chat_body(
                "The example requirement is covered and the limitation "
                "requirement is missing.",
                action="verify_requirements",
            ),
        ),
        "failed-source": (
            200,
            chat_body(
                "I could not retrieve the supplied page, so I cannot make "
                "a source-grounded claim."
            ),
        ),
    }


def valid_live_cases(module):
    cases = list(module.LIVE_E2E_CASES)
    cases[-1] = module.LiveE2ECase(
        probe_id="failed-source",
        message=(
            "Analyze https://example.com/unavailable-evaluation-page using "
            "only that page, and explain clearly if retrieval fails."
        ),
        expected_action=None,
        required_projection="url",
    )
    return tuple(cases)


class PassingRequester:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []
        self.bodies = passing_bodies()

    async def __call__(
        self,
        probe_id: str,
        payload: dict[str, object],
        idempotency_key: str,
    ):
        module = load_check_module()
        self.calls.append((probe_id, payload, idempotency_key))
        if probe_id == "source-replay":
            status_code, body = self.bodies["source"]
        elif probe_id == "source-conflict":
            status_code, body = 409, {
                "detail": (
                    "Idempotency key conflicts with a different chat request."
                )
            }
        else:
            status_code, body = self.bodies[probe_id]
        return module.LiveHttpObservation(
            status_code=status_code,
            body=body,
        )


def test_catalog_is_fixed_bounded_and_synthetic() -> None:
    module = load_check_module()

    assert tuple(case.probe_id for case in module.LIVE_E2E_CASES) == (
        "direct-restraint",
        "clarification",
        "source",
        "research",
        "computation",
        "requirements-verification",
        "failed-source",
    )
    assert len(module.LIVE_E2E_CASES) == 7
    assert all(case.manual_review_required for case in module.LIVE_E2E_CASES)
    assert tuple(case.required_projection for case in module.LIVE_E2E_CASES) == (
        "none",
        "none",
        "url",
        "none",
        "numeric",
        "text",
        "url",
    )
    assert "example.invalid" in module.LIVE_E2E_CASES[-1].message
    assert all("wifiknight" not in case.message for case in module.LIVE_E2E_CASES)


def test_default_catalog_preflight_rejects_unprojectable_failed_source() -> None:
    module = load_check_module()

    with pytest.raises(module.LiveE2EConfigurationError) as captured:
        module.preflight_live_cases(module.LIVE_E2E_CASES)

    assert captured.value.probe_id == "failed-source"
    assert captured.value.reason == "missing_url_candidate"
    assert "example.invalid" not in str(captured.value)


def test_valid_catalog_preflight_uses_all_required_projections() -> None:
    module = load_check_module()

    assert module.preflight_live_cases(valid_live_cases(module)) is None


@pytest.mark.asyncio
async def test_live_preflight_rejects_before_http_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_check_module()
    output: list[str] = []

    monkeypatch.setattr(
        module,
        "load_vertex_ai_settings",
        lambda _environment: SimpleNamespace(
            project="synthetic-project",
            location="global",
        ),
    )
    monkeypatch.setattr(module, "resolve_repository_commit", lambda: "a" * 40)
    monkeypatch.setattr(module, "is_repository_dirty", lambda: False)

    class ForbiddenHttpClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("HTTP client must not be constructed")

    monkeypatch.setattr(module.httpx, "AsyncClient", ForbiddenHttpClient)

    exit_code = await module.run_live(
        run_id="preflight-only",
        base_url="http://127.0.0.1:8000",
        report_path=tmp_path / "unused.json",
        output=output.append,
        environment={},
    )

    assert exit_code == 2
    assert output == [
        "tool-belt-live-e2e-check configuration_error "
        "probe=failed-source reason=missing_url_candidate"
    ]


def test_identifiers_are_bounded_unique_and_firestore_traceable() -> None:
    module = load_check_module()

    identity = module.build_live_identity(
        run_id="manual-20260823-01",
        probe_id="source",
    )

    assert identity.user_id == "m7-e2e-manual-20260823-01-source"
    assert identity.session_id == identity.user_id
    assert identity.idempotency_key == identity.user_id
    assert identity.firestore_paths == (
        "sessions/m7-e2e-manual-20260823-01-source",
        f"sessions/{identity.session_id}/turns/{identity.turn_id}",
        (
            f"sessions/{identity.session_id}/messages/"
            f"turn--{identity.turn_id}--user"
        ),
        (
            f"sessions/{identity.session_id}/messages/"
            f"turn--{identity.turn_id}--model"
        ),
    )


@pytest.mark.parametrize(
    "run_id",
    ("", "contains space", "UPPERCASE", "x" * 33, "../escape"),
)
def test_run_id_validation_rejects_unsafe_values(run_id: str) -> None:
    module = load_check_module()

    with pytest.raises(ValueError, match="run_id"):
        module.validate_run_id(run_id)


@pytest.mark.asyncio
async def test_bounded_runner_executes_exactly_nine_requests_and_writes_report(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    requester = PassingRequester()
    output: list[str] = []
    report_path = tmp_path / "manual-review.json"

    exit_code = await module.run_bounded_live_e2e(
        run_id="manual-20260823-01",
        request_chat=requester,
        report_path=report_path,
        output=output.append,
        repository_commit="a" * 40,
        repository_dirty=False,
        configured_project="synthetic-project",
        configured_location="global",
        now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
        monotonic_values=iter((10.0, 10.5)),
        cases=valid_live_cases(module),
    )

    assert exit_code == 0
    assert [call[0] for call in requester.calls] == [
        "direct-restraint",
        "clarification",
        "source",
        "research",
        "computation",
        "requirements-verification",
        "failed-source",
        "source-replay",
        "source-conflict",
    ]
    source_call = requester.calls[2]
    replay_call = requester.calls[7]
    conflict_call = requester.calls[8]
    assert replay_call[1:] == source_call[1:]
    assert conflict_call[2] == source_call[2]
    assert conflict_call[1]["message"] != source_call[1]["message"]

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_version"] == "1.0"
    assert report["fixture_version"] == "3.0"
    assert report["routing_schema_version"] == "3.0"
    assert report["repository"] == {
        "commit": "a" * 40,
        "worktree": "clean",
    }
    assert report["provider"] == {
        "mode": "vertex_ai",
        "project": "synthetic-project",
        "location": "global",
        "provider_calls": "not_observable_at_http_boundary",
    }
    assert report["summary"] == {
        "http_requests": 9,
        "automatable_failures": 0,
        "inconclusive_failures": 0,
        "manual_review_cases": 7,
        "elapsed_ms": 500,
        "exit_code": 0,
    }
    assert len(report["probes"]) == 9
    assert report["probes"][0]["response"]["response"].startswith(
        "Tools are unnecessary"
    )
    assert report["probes"][0]["manual_review_required"] is True
    failed_source = next(
        probe
        for probe in report["probes"]
        if probe["probe_id"] == "failed-source"
    )
    assert failed_source["classification"] == (
        "pass_public_failure_contract"
    )
    assert report["probes"][-1]["http_status"] == 409

    terminal = "\n".join(output)
    assert "Tools are unnecessary" not in terminal
    assert "Which two values" not in terminal
    assert "19.5000" not in terminal
    assert str(report_path) in terminal
    assert "manual_review_cases=7" in terminal


@pytest.mark.asyncio
async def test_unobservable_expert_outcome_returns_two_and_continues_sample(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    requester = PassingRequester()
    requester.bodies["computation"] = (
        200,
        chat_body("The answer is unavailable."),
    )
    output: list[str] = []

    exit_code = await module.run_bounded_live_e2e(
        run_id="semantic-failure",
        request_chat=requester,
        report_path=tmp_path / "report.json",
        output=output.append,
        repository_commit="b" * 40,
        repository_dirty=True,
        configured_project="synthetic-project",
        configured_location="global",
        cases=valid_live_cases(module),
    )

    assert exit_code == 2
    assert len(requester.calls) == 9
    assert any(
        line == "computation http=200 expert_outcome_unobservable"
        for line in output
    )
    assert all("The answer is unavailable" not in line for line in output)


@pytest.mark.asyncio
async def test_provider_failure_returns_two_and_preserves_semantic_findings(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    requester = PassingRequester()
    requester.bodies["research"] = (502, {"detail": "private provider error"})
    requester.bodies["computation"] = (
        200,
        chat_body("The result is 19.5000 and 5.1235."),
    )
    output: list[str] = []

    exit_code = await module.run_bounded_live_e2e(
        run_id="mixed-failure",
        request_chat=requester,
        report_path=tmp_path / "report.json",
        output=output.append,
        repository_commit="c" * 40,
        repository_dirty=False,
        configured_project="synthetic-project",
        configured_location="global",
        cases=valid_live_cases(module),
    )

    assert exit_code == 2
    assert len(requester.calls) == 9
    assert "research http=502 provider_error" in output
    assert "computation http=200 expert_outcome_unobservable" in output
    assert all("private provider error" not in line for line in output)


@pytest.mark.asyncio
async def test_citation_must_be_attached_to_response_text(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    requester = PassingRequester()
    requester.bodies["source"] = (
        200,
        chat_body(
            "The page is an example domain.",
            action="url_context",
            citations=(("https://example.com/", "Example Domain"),),
        ),
    )

    exit_code = await module.run_bounded_live_e2e(
        run_id="citation-failure",
        request_chat=requester,
        report_path=tmp_path / "report.json",
        output=lambda _line: None,
        repository_commit="d" * 40,
        repository_dirty=False,
        configured_project="synthetic-project",
        configured_location="global",
        cases=valid_live_cases(module),
    )

    assert exit_code == 1


def test_live_http_adapter_classifies_transport_without_retry() -> None:
    module = load_check_module()

    class FailingClient:
        def __init__(self) -> None:
            self.calls = 0

        async def post(self, *args, **kwargs):
            import httpx

            self.calls += 1
            raise httpx.ConnectError("private transport details")

    client = FailingClient()

    async def exercise():
        return await module.request_live_chat(
            client=client,
            probe_id="direct-restraint",
            payload={"message": "synthetic"},
            idempotency_key="synthetic-key",
        )

    import asyncio

    with pytest.raises(module.LiveE2ETransportError):
        asyncio.run(exercise())
    assert client.calls == 1


@pytest.mark.asyncio
async def test_existing_report_is_rejected_before_any_live_request(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    requester = PassingRequester()
    report_path = tmp_path / "existing.json"
    report_path.write_text("preserve-me\n", encoding="utf-8")

    with pytest.raises(ValueError, match="report_path"):
        await module.run_bounded_live_e2e(
            run_id="existing-report",
            request_chat=requester,
            report_path=report_path,
            output=lambda _line: None,
            repository_commit="e" * 40,
            repository_dirty=False,
            configured_project="synthetic-project",
            configured_location="global",
            cases=valid_live_cases(module),
        )

    assert requester.calls == []
    assert report_path.read_text(encoding="utf-8") == "preserve-me\n"


def test_imperative_clarification_is_automatable_pass_pending_review() -> None:
    module = load_check_module()
    case = next(
        case
        for case in module.LIVE_E2E_CASES
        if case.probe_id == "clarification"
    )

    result = module.evaluate_case(
        case,
        module.LiveHttpObservation(
            status_code=200,
            body=chat_body(
                "Please provide the initial and final numeric values."
            ),
        ),
    )

    assert result.outcome == "pass"
    assert result.classification == "pass"


def test_missing_expert_receipt_without_citations_is_inconclusive() -> None:
    module = load_check_module()
    case = next(
        case for case in module.LIVE_E2E_CASES if case.probe_id == "research"
    )

    result = module.evaluate_case(
        case,
        module.LiveHttpObservation(
            status_code=200,
            body=chat_body(
                "The search did not return validated grounding evidence."
            ),
        ),
    )

    assert result.outcome == "inconclusive"
    assert result.classification == "expert_outcome_unobservable"
