import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import ChatResponse


def make_response(
    *,
    search_actions: int = 0,
    citation_count: int = 0,
) -> ChatResponse:
    return ChatResponse.model_validate(
        {
            "response": "Bounded model response.",
            "actions": [
                {
                    "action_name": "google_search",
                    "status": "completed",
                }
                for _ in range(search_actions)
            ],
            "artifacts": [],
            "citations": [
                {
                    "uri": f"https://example.com/source-{index}",
                    "label": f"Source {index}",
                }
                for index in range(1, citation_count + 1)
            ],
            "memory_proposals": [],
            "adaptations": [],
        }
    )


def test_required_research_accepts_one_search_with_grounded_citations() -> None:
    from research_routing_evaluation import (
        ResearchRoutingScenario,
        evaluate_research_routing,
    )

    scenario = ResearchRoutingScenario(
        scenario_id="current-fact",
        fixture_version="1.0",
        message="What is the current stable Python release?",
        expected_routing="research",
        manual_semantic_review="none",
        execution_mode="single",
    )

    findings = evaluate_research_routing(
        scenario,
        (make_response(search_actions=1, citation_count=2),),
    )

    assert findings == ()


@pytest.mark.parametrize(
    ("search_actions", "citation_count", "expected_code"),
    (
        (0, 0, "missing_research_action"),
        (1, 0, "missing_citations"),
        (2, 1, "multiple_research_actions"),
    ),
)
def test_required_research_rejects_incomplete_or_duplicate_receipts(
    search_actions: int,
    citation_count: int,
    expected_code: str,
) -> None:
    from research_routing_evaluation import (
        ResearchRoutingScenario,
        evaluate_research_routing,
    )

    scenario = ResearchRoutingScenario(
        scenario_id="current-fact",
        fixture_version="1.0",
        message="What is the current stable Python release?",
        expected_routing="research",
        manual_semantic_review="none",
        execution_mode="single",
    )

    findings = evaluate_research_routing(
        scenario,
        (
            make_response(
                search_actions=search_actions,
                citation_count=citation_count,
            ),
        ),
    )

    assert tuple(finding.code for finding in findings) == (expected_code,)


@pytest.mark.parametrize("expected_routing", ("direct", "clarify"))
def test_restraint_routes_reject_search_or_citation_receipts(
    expected_routing: str,
) -> None:
    from research_routing_evaluation import (
        ResearchRoutingScenario,
        evaluate_research_routing,
    )

    scenario = ResearchRoutingScenario(
        scenario_id="restraint",
        fixture_version="1.0",
        message="Use no external tools.",
        expected_routing=expected_routing,
        manual_semantic_review=(
            "clarification_quality"
            if expected_routing == "clarify"
            else "none"
        ),
        execution_mode="single",
    )

    search_findings = evaluate_research_routing(
        scenario,
        (make_response(search_actions=1, citation_count=1),),
    )
    citation_findings = evaluate_research_routing(
        scenario,
        (make_response(citation_count=1),),
    )

    assert tuple(finding.code for finding in search_findings) == (
        "unnecessary_research",
    )
    assert tuple(finding.code for finding in citation_findings) == (
        "unexpected_citations",
    )


def test_idempotency_replay_requires_exact_stored_response() -> None:
    from research_routing_evaluation import (
        ResearchRoutingScenario,
        evaluate_research_routing,
    )

    scenario = ResearchRoutingScenario(
        scenario_id="replay",
        fixture_version="1.0",
        message="Verify a current fact.",
        expected_routing="research",
        manual_semantic_review="none",
        execution_mode="idempotency_replay",
    )
    first = make_response(search_actions=1, citation_count=1)
    changed = first.model_copy(update={"response": "Changed response."})

    assert evaluate_research_routing(scenario, (first, first)) == ()
    findings = evaluate_research_routing(scenario, (first, changed))
    assert tuple(finding.code for finding in findings) == (
        "replay_mismatch",
    )


def test_fixture_loader_validates_scenario_semantics(tmp_path: Path) -> None:
    from research_routing_evaluation import load_research_routing_scenarios

    fixture_path = tmp_path / "research-routing.json"
    fixture_path.write_text(
        json.dumps(
            {
                "fixture_version": "1.0",
                "scenarios": [
                    {
                        "scenario_id": "ambiguous-research",
                        "message": "Research the latest changes for me.",
                        "expected_routing": "clarify",
                        "manual_semantic_review": "clarification_quality",
                        "execution_mode": "single",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    scenarios = load_research_routing_scenarios(fixture_path)

    assert scenarios == (
        load_research_routing_scenarios(fixture_path)[0],
    )
    assert scenarios[0].scenario_id == "ambiguous-research"
    assert scenarios[0].expected_routing == "clarify"

    document = json.loads(fixture_path.read_text(encoding="utf-8"))
    document["scenarios"][0]["manual_semantic_review"] = "none"
    fixture_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_research_routing_scenarios(fixture_path)


def test_default_fixture_covers_approved_live_routing_boundaries() -> None:
    from research_routing_evaluation import (
        DEFAULT_RESEARCH_ROUTING_FIXTURE_PATH,
        load_research_routing_scenarios,
    )

    scenarios = load_research_routing_scenarios(
        DEFAULT_RESEARCH_ROUTING_FIXTURE_PATH
    )

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "current-public-fact",
        "stable-explanation",
        "supplied-url",
        "explicit-no-external-tools",
        "ambiguous-research",
        "grounded-research-evidence",
        "idempotent-research-replay",
    )
    assert tuple(scenario.expected_routing for scenario in scenarios) == (
        "research",
        "direct",
        "direct",
        "direct",
        "clarify",
        "research",
        "research",
    )
    assert scenarios[2].manual_semantic_review == "source_boundary_quality"
    assert scenarios[4].manual_semantic_review == "clarification_quality"
    assert scenarios[-1].execution_mode == "idempotency_replay"
