from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from schemas import ChatResponse


ExpectedSourceRouting = Literal["source", "direct", "clarify", "research"]
SourceExecutionMode = Literal["single", "idempotency_replay"]
SourceSemanticReview = Literal[
    "none",
    "clarification_quality",
    "source_response_quality",
]
SourceRoutingFindingCode = Literal[
    "missing_source_action",
    "missing_citations",
    "multiple_source_actions",
    "unapproved_citation",
    "unnecessary_source",
    "unexpected_citations",
    "missing_research_action",
    "wrong_expert",
    "unexpected_action",
    "replay_mismatch",
]
ScenarioId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9-]+$",
    ),
]
ScenarioMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_500),
]

DEFAULT_SOURCE_ROUTING_FIXTURE_PATH = Path(
    "tests/fixtures/source_routing_cases.json"
)


class _StrictFixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ScenarioDefinition(_StrictFixtureModel):
    scenario_id: ScenarioId
    message: ScenarioMessage
    expected_routing: ExpectedSourceRouting
    allowed_citation_urls: tuple[HttpUrl, ...] = Field(max_length=3)
    manual_semantic_review: SourceSemanticReview
    execution_mode: SourceExecutionMode

    @model_validator(mode="after")
    def validate_scenario_contract(self) -> Self:
        expects_source = self.expected_routing == "source"
        if expects_source != bool(self.allowed_citation_urls):
            raise ValueError(
                "Only Source routes may define citation allowlists."
            )
        if len(set(map(str, self.allowed_citation_urls))) != len(
            self.allowed_citation_urls
        ):
            raise ValueError("Citation allowlist URLs must be unique.")
        if expects_source != (
            self.manual_semantic_review == "source_response_quality"
        ):
            raise ValueError(
                "Source routes require source-response review."
            )
        expects_clarification = self.expected_routing == "clarify"
        if expects_clarification != (
            self.manual_semantic_review == "clarification_quality"
        ):
            raise ValueError(
                "Clarification routes require clarification review."
            )
        if (
            self.execution_mode == "idempotency_replay"
            and not expects_source
        ):
            raise ValueError("Idempotency replay must evaluate Source.")
        return self


class _FixtureDocument(_StrictFixtureModel):
    fixture_version: Literal["1.0"]
    scenarios: tuple[_ScenarioDefinition, ...] = Field(
        min_length=1,
        max_length=12,
    )

    @model_validator(mode="after")
    def validate_unique_scenario_ids(self) -> Self:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Source routing scenario IDs must be unique.")
        return self


@dataclass(frozen=True, slots=True)
class SourceRoutingScenario:
    scenario_id: str
    fixture_version: str
    message: str
    expected_routing: ExpectedSourceRouting
    allowed_citation_urls: tuple[str, ...]
    manual_semantic_review: SourceSemanticReview
    execution_mode: SourceExecutionMode


@dataclass(frozen=True, slots=True)
class SourceRoutingFinding:
    code: SourceRoutingFindingCode


def load_source_routing_scenarios(
    fixture_path: Path,
) -> tuple[SourceRoutingScenario, ...]:
    """Load and validate the versioned Source routing fixture."""
    document = _FixtureDocument.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    return tuple(
        SourceRoutingScenario(
            scenario_id=scenario.scenario_id,
            fixture_version=document.fixture_version,
            message=scenario.message,
            expected_routing=scenario.expected_routing,
            allowed_citation_urls=tuple(
                str(url) for url in scenario.allowed_citation_urls
            ),
            manual_semantic_review=scenario.manual_semantic_review,
            execution_mode=scenario.execution_mode,
        )
        for scenario in document.scenarios
    )


def evaluate_source_routing(
    scenario: SourceRoutingScenario,
    responses: tuple[ChatResponse, ...],
) -> tuple[SourceRoutingFinding, ...]:
    """Evaluate Source routing through typed public response receipts."""
    response = responses[0]
    source_action_count = sum(
        action.action_name == "url_context"
        for action in response.actions
    )
    if source_action_count > 1:
        return (SourceRoutingFinding(code="multiple_source_actions"),)
    research_action_count = sum(
        action.action_name == "google_search"
        for action in response.actions
    )
    action_names = tuple(action.action_name for action in response.actions)
    if scenario.expected_routing == "source":
        if research_action_count:
            return (SourceRoutingFinding(code="wrong_expert"),)
        if any(name != "url_context" for name in action_names):
            return (SourceRoutingFinding(code="unexpected_action"),)
        if source_action_count == 0:
            return (SourceRoutingFinding(code="missing_source_action"),)
        if not response.citations:
            return (SourceRoutingFinding(code="missing_citations"),)
        if any(
            str(citation.uri) not in scenario.allowed_citation_urls
            for citation in response.citations
        ):
            return (SourceRoutingFinding(code="unapproved_citation"),)
    elif scenario.expected_routing == "research":
        if source_action_count:
            return (SourceRoutingFinding(code="wrong_expert"),)
        if any(name != "google_search" for name in action_names):
            return (SourceRoutingFinding(code="unexpected_action"),)
        if research_action_count != 1:
            return (SourceRoutingFinding(code="missing_research_action"),)
        if not response.citations:
            return (SourceRoutingFinding(code="missing_citations"),)
    else:
        if source_action_count:
            return (SourceRoutingFinding(code="unnecessary_source"),)
        if action_names:
            return (SourceRoutingFinding(code="unexpected_action"),)
        if response.citations:
            return (SourceRoutingFinding(code="unexpected_citations"),)
    if scenario.execution_mode == "idempotency_replay" and (
        len(responses) != 2 or responses[0] != responses[1]
    ):
        return (SourceRoutingFinding(code="replay_mismatch"),)
    return ()
