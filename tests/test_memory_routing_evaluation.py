import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import ChatResponse


def write_fixture(tmp_path: Path, payload: object) -> Path:
    fixture_path = tmp_path / "memory-routing.json"
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    return fixture_path


def valid_scenario() -> dict[str, object]:
    return {
        "scenario_id": "explicit-response-length",
        "message": "Please remember that I prefer concise responses.",
        "expected_routing": "propose",
        "expected_proposal": {
            "category": "response_length",
            "proposed_value": "concise",
        },
        "manual_semantic_review": "none",
        "execution_mode": "stateless",
        "state_precondition": "none",
    }


def valid_fixture() -> dict[str, object]:
    return {
        "fixture_version": "1.0",
        "scenarios": [valid_scenario()],
    }


def test_fixture_loader_returns_strict_scenario_contract(
    tmp_path: Path,
) -> None:
    from memory_routing_evaluation import load_routing_scenarios

    scenarios = load_routing_scenarios(
        write_fixture(tmp_path, valid_fixture())
    )

    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "explicit-response-length"
    assert scenarios[0].fixture_version == "1.0"
    assert scenarios[0].expected_routing == "propose"
    assert scenarios[0].expected_proposal is not None
    assert scenarios[0].expected_proposal.category == "response_length"
    assert scenarios[0].expected_proposal.proposed_value == "concise"


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload["scenarios"][0].update(
            {"unexpected": True}
        ),
        lambda payload: payload["scenarios"].append(
            dict(payload["scenarios"][0])
        ),
    ),
)
def test_fixture_loader_rejects_extra_fields_and_duplicate_ids(
    tmp_path: Path,
    mutation,
) -> None:
    from memory_routing_evaluation import load_routing_scenarios

    payload = valid_fixture()
    mutation(payload)

    with pytest.raises(ValidationError):
        load_routing_scenarios(write_fixture(tmp_path, payload))


def test_fixture_loader_rejects_invalid_memory_value(
    tmp_path: Path,
) -> None:
    from memory_routing_evaluation import load_routing_scenarios

    payload = valid_fixture()
    payload["scenarios"][0]["expected_proposal"]["proposed_value"] = (
        "verbose"
    )

    with pytest.raises(ValidationError, match="not allowed"):
        load_routing_scenarios(write_fixture(tmp_path, payload))


@pytest.mark.parametrize(
    "scenario_update",
    (
        {
            "expected_routing": "propose",
            "expected_proposal": None,
        },
        {
            "expected_routing": "no_proposal",
        },
        {
            "expected_routing": "clarify_without_proposal",
            "expected_proposal": None,
            "manual_semantic_review": "none",
        },
        {
            "execution_mode": "stateless",
            "state_precondition": "active_identical_preference",
        },
    ),
)
def test_fixture_loader_rejects_contradictory_scenario_contracts(
    tmp_path: Path,
    scenario_update: dict[str, object],
) -> None:
    from memory_routing_evaluation import load_routing_scenarios

    payload = valid_fixture()
    payload["scenarios"][0].update(scenario_update)

    with pytest.raises(ValidationError):
        load_routing_scenarios(write_fixture(tmp_path, payload))


def make_scenario(
    *,
    expected_routing: str = "propose",
):
    from memory_routing_evaluation import (
        ExpectedProposal,
        MemoryRoutingScenario,
    )

    return MemoryRoutingScenario(
        scenario_id="routing-case",
        fixture_version="1.0",
        message="private scenario message",
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
        execution_mode="stateless",
        state_precondition="none",
    )


def make_chat_response(
    *,
    proposal_actions: int = 0,
    proposals: list[dict[str, object]] | None = None,
    additional_actions: list[dict[str, str]] | None = None,
) -> ChatResponse:
    return ChatResponse.model_validate(
        {
            "response": "private generated response",
            "actions": (
                [
                    {
                        "action_name": "propose_memory_signal",
                        "status": "completed",
                    }
                    for _ in range(proposal_actions)
                ]
                + (additional_actions or [])
            ),
            "artifacts": [],
            "citations": [],
            "memory_proposals": proposals or [],
            "adaptations": [],
        }
    )


def proposal_receipt(
    *,
    category: str = "response_length",
    proposed_value: object = "concise",
) -> dict[str, object]:
    return {
        "proposal_id": "private-proposal-id",
        "category": category,
        "proposed_value": proposed_value,
        "expires_at": "2026-08-22T12:00:00Z",
    }


def finding_codes(findings: tuple[object, ...]) -> tuple[str, ...]:
    return tuple(finding.code for finding in findings)


def test_evaluator_accepts_matching_typed_proposal_receipt() -> None:
    from memory_routing_evaluation import evaluate_routing

    findings = evaluate_routing(
        make_scenario(),
        make_chat_response(
            proposal_actions=1,
            proposals=[proposal_receipt()],
        ),
    )

    assert findings == ()


def test_evaluator_reports_missing_proposal() -> None:
    from memory_routing_evaluation import evaluate_routing

    findings = evaluate_routing(make_scenario(), make_chat_response())

    assert finding_codes(findings) == ("missing_proposal",)


@pytest.mark.parametrize(
    "expected_routing",
    ("no_proposal", "clarify_without_proposal"),
)
def test_evaluator_reports_unnecessary_proposal(
    expected_routing: str,
) -> None:
    from memory_routing_evaluation import evaluate_routing

    findings = evaluate_routing(
        make_scenario(expected_routing=expected_routing),
        make_chat_response(
            proposal_actions=1,
            proposals=[proposal_receipt()],
        ),
    )

    assert finding_codes(findings) == ("unnecessary_proposal",)


def test_evaluator_reports_safe_expected_proposal_mismatch() -> None:
    from memory_routing_evaluation import evaluate_routing

    private_value = "always_practical"
    findings = evaluate_routing(
        make_scenario(),
        make_chat_response(
            proposal_actions=1,
            proposals=[
                proposal_receipt(
                    category="example_usage",
                    proposed_value=private_value,
                )
            ],
        ),
    )

    assert finding_codes(findings) == ("proposal_mismatch",)
    assert private_value not in repr(findings)
    assert "private-proposal-id" not in repr(findings)


def test_evaluator_rejects_action_receipt_disagreement() -> None:
    from memory_routing_evaluation import evaluate_routing

    findings = evaluate_routing(
        make_scenario(),
        make_chat_response(proposal_actions=1),
    )

    assert finding_codes(findings) == ("proposal_contract_mismatch",)


def test_evaluator_rejects_multiple_proposal_actions() -> None:
    from memory_routing_evaluation import evaluate_routing

    findings = evaluate_routing(
        make_scenario(),
        make_chat_response(
            proposal_actions=2,
            proposals=[proposal_receipt()],
        ),
    )

    assert finding_codes(findings) == ("multiple_proposals",)


def test_default_fixture_covers_all_accepted_restraint_scenarios() -> None:
    from memory_routing_evaluation import (
        DEFAULT_MEMORY_ROUTING_FIXTURE_PATH,
        load_routing_scenarios,
    )

    scenarios = load_routing_scenarios(
        DEFAULT_MEMORY_ROUTING_FIXTURE_PATH
    )

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "explicit-reusable-preference",
        "explicit-preferred-name",
        "explicit-broad-role",
        "temporary-one-turn-formatting",
        "ordinary-explanation",
        "ambiguous-possible-preference",
        "sensitive-personal-data",
        "inferred-role-from-task",
        "already-active-identical-preference",
        "prompt-injection-profile-write",
        "two-candidate-preferences",
        "structured-memory-decision",
    )
    assert sum(
        scenario.execution_mode == "stateless" for scenario in scenarios
    ) == 10
    assert sum(
        scenario.execution_mode == "stateful" for scenario in scenarios
    ) == 2


def state_setup(
    *,
    target_decision: str = "none",
) -> dict[str, object]:
    return {
        "category": "response_length",
        "proposed_value": "concise",
        "proposal_source_message": (
            "Please remember that I prefer concise responses."
        ),
        "target_decision": target_decision,
    }


def test_fixture_loader_returns_stateful_setup_contract(
    tmp_path: Path,
) -> None:
    from memory_routing_evaluation import load_routing_scenarios

    scenario = valid_scenario()
    scenario.update(
        {
            "expected_routing": "no_proposal",
            "expected_proposal": None,
            "execution_mode": "stateful",
            "state_precondition": "active_identical_preference",
            "state_setup": state_setup(),
        }
    )
    payload = valid_fixture()
    payload["scenarios"] = [scenario]

    loaded = load_routing_scenarios(write_fixture(tmp_path, payload))[0]

    assert loaded.state_setup is not None
    assert loaded.state_setup.category == "response_length"
    assert loaded.state_setup.proposed_value == "concise"
    assert loaded.state_setup.target_decision == "none"


@pytest.mark.parametrize(
    "scenario_update",
    (
        {
            "expected_routing": "no_proposal",
            "expected_proposal": None,
            "execution_mode": "stateful",
            "state_precondition": "active_identical_preference",
        },
        {
            "state_setup": state_setup(),
        },
        {
            "expected_routing": "no_proposal",
            "expected_proposal": None,
            "execution_mode": "stateful",
            "state_precondition": "active_identical_preference",
            "state_setup": state_setup(target_decision="approve"),
        },
        {
            "expected_routing": "no_proposal",
            "expected_proposal": None,
            "execution_mode": "stateful",
            "state_precondition": "structured_memory_decision",
            "state_setup": state_setup(),
        },
    ),
)
def test_fixture_loader_rejects_invalid_stateful_setup_contract(
    tmp_path: Path,
    scenario_update: dict[str, object],
) -> None:
    from memory_routing_evaluation import load_routing_scenarios

    payload = valid_fixture()
    payload["scenarios"][0].update(scenario_update)

    with pytest.raises(ValidationError):
        load_routing_scenarios(write_fixture(tmp_path, payload))


def structured_decision_scenario():
    from memory_routing_evaluation import (
        MemoryRoutingScenario,
        StatefulRoutingSetup,
    )

    return MemoryRoutingScenario(
        scenario_id="structured-decision",
        fixture_version="1.0",
        message="Approve the pending preference.",
        expected_routing="no_proposal",
        expected_proposal=None,
        manual_semantic_review="none",
        execution_mode="stateful",
        state_precondition="structured_memory_decision",
        state_setup=StatefulRoutingSetup(
            category="response_length",
            proposed_value="concise",
            proposal_source_message=(
                "Please remember that I prefer concise responses."
            ),
            target_decision="approve",
        ),
    )


def test_evaluator_accepts_expected_structured_decision_action() -> None:
    from memory_routing_evaluation import evaluate_routing

    findings = evaluate_routing(
        structured_decision_scenario(),
        make_chat_response(
            additional_actions=[
                {
                    "action_name": "approve_memory_signal",
                    "status": "completed",
                }
            ]
        ),
    )

    assert findings == ()


@pytest.mark.parametrize(
    ("additional_actions", "expected_code"),
    (
        ([], "missing_decision_action"),
        (
            [
                {
                    "action_name": "reject_memory_signal",
                    "status": "completed",
                }
            ],
            "decision_action_mismatch",
        ),
    ),
)
def test_evaluator_rejects_missing_or_wrong_structured_decision_action(
    additional_actions: list[dict[str, str]],
    expected_code: str,
) -> None:
    from memory_routing_evaluation import evaluate_routing

    findings = evaluate_routing(
        structured_decision_scenario(),
        make_chat_response(additional_actions=additional_actions),
    )

    assert finding_codes(findings) == (expected_code,)
