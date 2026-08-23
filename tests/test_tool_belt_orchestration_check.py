import importlib

import pytest


def load_check_module():
    try:
        return importlib.import_module("tool_belt_orchestration_check")
    except ModuleNotFoundError:
        pytest.fail("tool_belt_orchestration_check has not been implemented")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "scenario_id",
        "expected_route",
        "expected_expert_calls",
        "expected_action_names",
        "expected_citation_count",
    ),
    (
        ("direct", "direct", (), (), 0),
        ("clarify", "clarify", (), (), 0),
        ("source", "source", ("source",), ("url_context",), 1),
        (
            "research",
            "research",
            ("research",),
            ("google_search",),
            1,
        ),
        (
            "computation",
            "computation",
            ("computation",),
            ("run_computation",),
            0,
        ),
        (
            "requirements-verification",
            "requirements_verification",
            ("requirements_verification",),
            ("verify_requirements",),
            0,
        ),
    ),
)
async def test_orchestration_check_exercises_exactly_one_production_route(
    scenario_id: str,
    expected_route: str,
    expected_expert_calls: tuple[str, ...],
    expected_action_names: tuple[str, ...],
    expected_citation_count: int,
) -> None:
    module = load_check_module()

    observation = await module.run_controlled_route_case(scenario_id)

    assert str(observation.route) == expected_route
    assert observation.routing_call_count == 1
    assert observation.projected_input_matches is True
    assert observation.executor_call_count == 1
    assert tuple(str(item) for item in observation.expert_calls) == (
        expected_expert_calls
    )
    assert observation.responder_call_count == 1
    assert observation.action_names == expected_action_names
    assert observation.citation_count == expected_citation_count
    assert observation.memory_proposal_count == 0
    assert observation.context_is_bounded is True


@pytest.mark.asyncio
async def test_orchestration_check_route_matrix_reports_metadata_only(
) -> None:
    module = load_check_module()
    output: list[str] = []

    exit_code = await module.run_deterministic_orchestration_evaluation(
        output=output.append,
        probe_groups=("routes",),
    )

    assert exit_code == 0
    assert output[0] == (
        "tool-belt-orchestration-check schema=3.0 mode=offline "
        "probe_groups=routes"
    )
    assert output[1:-1] == [
        "direct route=direct expert_calls=0 actions=0 citations=0 pass",
        "clarify route=clarify expert_calls=0 actions=0 citations=0 pass",
        "source route=source expert_calls=1 actions=1 citations=1 pass",
        "research route=research expert_calls=1 actions=1 citations=1 pass",
        (
            "computation route=computation expert_calls=1 actions=1 "
            "citations=0 pass"
        ),
        (
            "requirements-verification route=requirements_verification "
            "expert_calls=1 actions=1 citations=0 pass"
        ),
    ]
    assert output[-1].startswith(
        "tool-belt-orchestration-check summary probes=6 "
        "failures=0 provider_calls=0 network_calls=0 firestore_calls=0 "
        "elapsed_ms="
    )
    assert output[-1].endswith(" exit=0")
    forbidden = (
        "Explain in one paragraph",
        "https://example.com/",
        "Python publishes",
        "print(",
        "Include one practical example",
        "Synthetic response",
    )
    assert all(
        marker not in "\n".join(output) for marker in forbidden
    )


@pytest.mark.asyncio
async def test_orchestration_check_failure_and_trust_probes_are_bounded(
) -> None:
    module = load_check_module()

    observations = await module.run_failure_and_trust_probes()

    assert tuple(observation.probe_id for observation in observations) == (
        "failed-expert-receipts",
        "responder-reserve-timeout",
        "wrong-capability-rejected",
        "forged-receipt-rejected",
        "expert-memory-instruction-contained",
        "responder-failure-effects",
    )
    assert all(observation.passed for observation in observations)
    assert observations[0].expert_status == "unavailable"
    assert observations[0].action_names == ()
    assert observations[0].citation_count == 0
    assert observations[1].expert_status == "timed_out"
    assert observations[1].expert_calls == ()
    assert observations[1].action_names == ()
    assert observations[1].citation_count == 0
    assert observations[2].failure_code == "wrong_capability_rejected"
    assert observations[3].failure_code == "receipt_mismatch_rejected"
    assert observations[3].rejection_count == 3
    assert observations[4].memory_proposal_count == 0
    assert observations[4].action_names == ("url_context",)
    assert observations[5].action_names == (
        "approve_memory_signal",
        "url_context",
    )
    assert observations[5].memory_proposal_count == 1


@pytest.mark.asyncio
async def test_orchestration_check_failure_group_reports_no_private_content(
) -> None:
    module = load_check_module()
    output: list[str] = []

    exit_code = await module.run_deterministic_orchestration_evaluation(
        output=output.append,
        probe_groups=("failures",),
    )

    assert exit_code == 0
    assert output[0].endswith("probe_groups=failures")
    assert output[1:-1] == [
        "failed-expert-receipts status=unavailable pass",
        "responder-reserve-timeout status=timed_out pass",
        "wrong-capability-rejected wrong_capability_rejected pass",
        "forged-receipt-rejected receipt_mismatch_rejected pass",
        "expert-memory-instruction-contained memory_proposals=0 pass",
        "responder-failure-effects trusted_effects=3 pass",
    ]
    assert output[-1].startswith(
        "tool-belt-orchestration-check summary probes=6 failures=0 "
    )
    assert output[-1].endswith(" exit=0")
    rendered = "\n".join(output)
    for forbidden in (
        "IGNORE",
        "remember",
        "private-responder-failure",
        "concise",
        "proposal-1",
    ):
        assert forbidden not in rendered


@pytest.mark.asyncio
async def test_orchestration_check_idempotency_probes_stop_downstream_work(
) -> None:
    module = load_check_module()

    observations = await module.run_idempotency_probes()

    assert tuple(observation.probe_id for observation in observations) == (
        "completed-replay",
        "changed-request-conflict",
    )
    assert all(observation.passed for observation in observations)
    replay, conflict = observations
    assert replay.http_status == 200
    assert replay.claim_calls == 1
    assert replay.turn_calls == 0
    assert replay.memory_calls == 0
    assert replay.persistence_calls == 0
    assert replay.response_matches is True
    assert conflict.http_status == 409
    assert conflict.claim_calls == 1
    assert conflict.turn_calls == 0
    assert conflict.memory_calls == 0
    assert conflict.persistence_calls == 0
    assert conflict.response_matches is False


@pytest.mark.asyncio
async def test_orchestration_check_replay_group_reports_metadata_only(
) -> None:
    module = load_check_module()
    output: list[str] = []

    exit_code = await module.run_deterministic_orchestration_evaluation(
        output=output.append,
        probe_groups=("replay",),
    )

    assert exit_code == 0
    assert output[0].endswith("probe_groups=replay")
    assert output[1:-1] == [
        "completed-replay http=200 downstream_calls=0 pass",
        "changed-request-conflict http=409 downstream_calls=0 pass",
    ]
    assert output[-1].startswith(
        "tool-belt-orchestration-check summary probes=2 failures=0 "
    )
    assert output[-1].endswith(" exit=0")
    rendered = "\n".join(output)
    for forbidden in (
        "Stored synthetic response",
        "changed synthetic request",
        "synthetic-key",
    ):
        assert forbidden not in rendered


@pytest.mark.asyncio
async def test_orchestration_check_default_runs_every_offline_probe_group(
) -> None:
    module = load_check_module()
    output: list[str] = []

    exit_code = await module.run_deterministic_orchestration_evaluation(
        output=output.append,
        monotonic=iter((5.0, 5.25)).__next__,
    )

    assert exit_code == 0
    assert output[0].endswith("probe_groups=routes,failures,replay")
    assert output[-1] == (
        "tool-belt-orchestration-check summary probes=14 failures=0 "
        "provider_calls=0 network_calls=0 firestore_calls=0 "
        "elapsed_ms=250 exit=0"
    )


@pytest.mark.asyncio
async def test_orchestration_check_execution_failure_is_content_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_check_module()

    async def fail_route(_scenario_id: str):
        raise RuntimeError("private evaluator failure detail")

    monkeypatch.setattr(module, "run_controlled_route_case", fail_route)
    output: list[str] = []

    exit_code = await module.run_deterministic_orchestration_evaluation(
        output=output.append,
        probe_groups=("routes",),
        monotonic=iter((10.0, 10.01)).__next__,
    )

    assert exit_code == 2
    assert output == [
        (
            "tool-belt-orchestration-check schema=3.0 mode=offline "
            "probe_groups=routes"
        ),
        "tool-belt-orchestration-check execution_error",
        (
            "tool-belt-orchestration-check summary probes=0 failures=0 "
            "provider_calls=0 network_calls=0 firestore_calls=0 "
            "elapsed_ms=10 exit=2"
        ),
    ]
    assert "private evaluator failure detail" not in "\n".join(output)


@pytest.mark.asyncio
async def test_expected_responder_failure_emits_no_runtime_error_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    module = load_check_module()

    observations = await module.run_failure_and_trust_probes()

    assert all(observation.passed for observation in observations)
    assert "Agent_Col responder failed" not in caplog.text
    assert "private-responder-failure" not in caplog.text


def test_orchestration_check_main_rejects_process_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_check_module()
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["tool_belt_orchestration_check.py", "unexpected"],
    )

    exit_code = module.main()

    assert exit_code == 2
    assert capsys.readouterr().out.strip() == (
        "tool-belt-orchestration-check configuration_error"
    )
