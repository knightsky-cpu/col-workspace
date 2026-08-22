import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import ChatResponse


def make_response(
    *,
    action_names: tuple[str, ...] = (),
    citation_urls: tuple[str, ...] = (),
    response_text: str = "Bounded Agent_Col response.",
) -> ChatResponse:
    return ChatResponse.model_validate(
        {
            "response": response_text,
            "actions": [
                {"action_name": name, "status": "completed"}
                for name in action_names
            ],
            "artifacts": [],
            "citations": [
                {"uri": url, "label": f"Source {index}"}
                for index, url in enumerate(citation_urls, start=1)
            ],
            "memory_proposals": [],
            "adaptations": [],
        }
    )


def source_scenario(**overrides: object):
    from source_routing_evaluation import SourceRoutingScenario

    values: dict[str, object] = {
        "scenario_id": "explicit-source",
        "fixture_version": "1.0",
        "message": "Analyze https://example.com/.",
        "expected_routing": "source",
        "allowed_citation_urls": ("https://example.com/",),
        "manual_semantic_review": "source_response_quality",
        "execution_mode": "single",
    }
    values.update(overrides)
    return SourceRoutingScenario(**values)


def test_required_source_accepts_one_action_and_allowlisted_citation() -> None:
    from source_routing_evaluation import evaluate_source_routing

    findings = evaluate_source_routing(
        source_scenario(),
        (
            make_response(
                action_names=("url_context",),
                citation_urls=("https://example.com/",),
            ),
        ),
    )

    assert findings == ()


@pytest.mark.parametrize(
    ("action_names", "citation_urls", "expected_code"),
    (
        ((), (), "missing_source_action"),
        (("url_context",), (), "missing_citations"),
        (
            ("url_context", "url_context"),
            ("https://example.com/",),
            "multiple_source_actions",
        ),
        (
            ("url_context",),
            ("https://attacker.example/",),
            "unapproved_citation",
        ),
        (
            ("google_search",),
            ("https://example.com/",),
            "wrong_expert",
        ),
    ),
)
def test_required_source_rejects_incomplete_or_wrong_receipts(
    action_names: tuple[str, ...],
    citation_urls: tuple[str, ...],
    expected_code: str,
) -> None:
    from source_routing_evaluation import evaluate_source_routing

    findings = evaluate_source_routing(
        source_scenario(),
        (
            make_response(
                action_names=action_names,
                citation_urls=citation_urls,
            ),
        ),
    )

    assert tuple(finding.code for finding in findings) == (expected_code,)


@pytest.mark.parametrize("expected_routing", ("direct", "clarify"))
def test_source_restraint_rejects_tool_or_citation_receipts(
    expected_routing: str,
) -> None:
    from source_routing_evaluation import evaluate_source_routing

    scenario = source_scenario(
        expected_routing=expected_routing,
        allowed_citation_urls=(),
        manual_semantic_review=(
            "clarification_quality"
            if expected_routing == "clarify"
            else "none"
        ),
    )

    source_findings = evaluate_source_routing(
        scenario,
        (
            make_response(
                action_names=("url_context",),
                citation_urls=("https://example.com/",),
            ),
        ),
    )
    citation_findings = evaluate_source_routing(
        scenario,
        (make_response(citation_urls=("https://example.com/",)),),
    )

    assert tuple(finding.code for finding in source_findings) == (
        "unnecessary_source",
    )
    assert tuple(finding.code for finding in citation_findings) == (
        "unexpected_citations",
    )


def test_research_boundary_requires_search_without_source() -> None:
    from source_routing_evaluation import evaluate_source_routing

    scenario = source_scenario(
        expected_routing="research",
        allowed_citation_urls=(),
        manual_semantic_review="none",
    )

    assert evaluate_source_routing(
        scenario,
        (
            make_response(
                action_names=("google_search",),
                citation_urls=("https://www.python.org/downloads/",),
            ),
        ),
    ) == ()
    findings = evaluate_source_routing(
        scenario,
        (
            make_response(
                action_names=("url_context",),
                citation_urls=("https://example.com/",),
            ),
        ),
    )

    assert tuple(finding.code for finding in findings) == ("wrong_expert",)


def test_direct_route_rejects_unrelated_completed_action() -> None:
    from source_routing_evaluation import evaluate_source_routing

    scenario = source_scenario(
        expected_routing="direct",
        allowed_citation_urls=(),
        manual_semantic_review="none",
    )

    findings = evaluate_source_routing(
        scenario,
        (make_response(action_names=("google_search",)),),
    )

    assert tuple(finding.code for finding in findings) == (
        "unexpected_action",
    )


def test_idempotency_replay_requires_exact_typed_response() -> None:
    from source_routing_evaluation import evaluate_source_routing

    scenario = source_scenario(execution_mode="idempotency_replay")
    first = make_response(
        action_names=("url_context",),
        citation_urls=("https://example.com/",),
    )
    changed = first.model_copy(update={"response": "Changed response."})

    assert evaluate_source_routing(scenario, (first, first)) == ()
    findings = evaluate_source_routing(scenario, (first, changed))

    assert tuple(finding.code for finding in findings) == (
        "replay_mismatch",
    )


def write_fixture(path: Path, scenarios: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"fixture_version": "1.0", "scenarios": scenarios}),
        encoding="utf-8",
    )
    return path


def valid_scenario_definition() -> dict[str, object]:
    return {
        "scenario_id": "explicit-source",
        "message": "Analyze https://example.com/.",
        "expected_routing": "source",
        "allowed_citation_urls": ["https://example.com/"],
        "manual_semantic_review": "source_response_quality",
        "execution_mode": "single",
    }


def test_fixture_loader_returns_strict_versioned_scenarios(
    tmp_path: Path,
) -> None:
    from source_routing_evaluation import load_source_routing_scenarios

    fixture = write_fixture(
        tmp_path / "source-routing.json",
        [valid_scenario_definition()],
    )

    scenarios = load_source_routing_scenarios(fixture)

    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "explicit-source"
    assert scenarios[0].fixture_version == "1.0"
    assert scenarios[0].allowed_citation_urls == (
        "https://example.com/",
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "extra_field",
        "duplicate_id",
        "source_without_allowlist",
        "direct_with_allowlist",
        "clarify_without_review",
        "replay_non_source",
    ),
)
def test_fixture_loader_rejects_contradictory_definitions(
    tmp_path: Path,
    mutation: str,
) -> None:
    from source_routing_evaluation import load_source_routing_scenarios

    scenario = valid_scenario_definition()
    scenarios = [scenario]
    if mutation == "extra_field":
        scenario["private_profile"] = "must-not-load"
    elif mutation == "duplicate_id":
        scenarios.append(dict(scenario))
    elif mutation == "source_without_allowlist":
        scenario["allowed_citation_urls"] = []
    elif mutation == "direct_with_allowlist":
        scenario["expected_routing"] = "direct"
        scenario["manual_semantic_review"] = "none"
    elif mutation == "clarify_without_review":
        scenario["expected_routing"] = "clarify"
        scenario["allowed_citation_urls"] = []
        scenario["manual_semantic_review"] = "none"
    elif mutation == "replay_non_source":
        scenario["expected_routing"] = "direct"
        scenario["allowed_citation_urls"] = []
        scenario["manual_semantic_review"] = "none"
        scenario["execution_mode"] = "idempotency_replay"
    fixture = write_fixture(
        tmp_path / "source-routing.json",
        scenarios,
    )

    with pytest.raises(ValidationError):
        load_source_routing_scenarios(fixture)


def test_default_fixture_covers_approved_source_boundaries() -> None:
    from source_routing_evaluation import (
        DEFAULT_SOURCE_ROUTING_FIXTURE_PATH,
        load_source_routing_scenarios,
    )

    scenarios = load_source_routing_scenarios(
        DEFAULT_SOURCE_ROUTING_FIXTURE_PATH
    )

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "explicit-single-url",
        "explicit-multiple-urls",
        "stable-no-url",
        "incidental-url",
        "explicit-no-tools-with-url",
        "ambiguous-url",
        "idempotent-source-replay",
    )
    assert tuple(scenario.expected_routing for scenario in scenarios) == (
        "source",
        "source",
        "direct",
        "direct",
        "direct",
        "clarify",
        "source",
    )
