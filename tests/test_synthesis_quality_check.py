import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from schemas import SynthesisBlueprint
from synthesis import SynthesisEngineError
from synthesis_quality import QualityScenario, RequiredConcept


def make_blueprint() -> SynthesisBlueprint:
    return SynthesisBlueprint.model_validate(
        {
            "synthesized_conceptual_model": {
                "project_name": "Agent Col",
                "core_value_proposition": "A collaborative partner.",
                "in_scope": ["Project planning"],
            },
            "personalization_trace": {},
            "architectural_decisions": [
                {
                    "component_name": "API",
                    "proposed_solution": "FastAPI",
                    "rationale": "Supports asynchronous Python.",
                    "alternatives": [
                        {
                            "option_name": "Flask",
                            "tradeoff": "Synchronous by default.",
                            "reason_not_selected": "Does not match the stack.",
                        }
                    ],
                }
            ],
            "socratic_clarifying_questions": [
                {
                    "question_text": "Which client comes first?",
                    "why_this_matters": "It sets the API contract.",
                    "suggested_options": [
                        {"label": "Web", "impact": "Browser access."},
                        {"label": "CLI", "impact": "Terminal access."},
                    ],
                }
            ],
            "step_by_step_execution_roadmap": [
                {
                    "phase_name": "Phase 1",
                    "objective": "Define the API.",
                    "expected_deliverable": "A tested endpoint.",
                    "micro_tasks": [
                        {
                            "task_description": "Write the endpoint.",
                            "complexity_level": "Low",
                            "verification_steps": ["Run the API test."],
                        }
                    ],
                }
            ],
        }
    )


def make_scenario(scenario_id: str) -> QualityScenario:
    return QualityScenario(
        scenario_id=scenario_id,
        fixture_version="1.1",
        source_text=f"private-source-{scenario_id}",
        profile={},
    )


@dataclass
class FakeAsyncClient:
    closed: bool = False

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class FakeClient:
    aio: FakeAsyncClient = field(default_factory=FakeAsyncClient)
    closed: bool = False

    def close(self) -> None:
        self.closed = True


@dataclass
class RecordingGenerator:
    blueprint: SynthesisBlueprint
    source_texts: list[str] = field(default_factory=list)

    async def __call__(
        self,
        client: object,
        profile: dict[str, object],
        history: list[dict[str, object]],
        source_text: str,
    ) -> SynthesisBlueprint:
        self.source_texts.append(source_text)
        return self.blueprint


@dataclass
class FailingGenerator:
    error: SynthesisEngineError

    async def __call__(
        self,
        client: object,
        profile: dict[str, object],
        history: list[dict[str, object]],
        source_text: str,
    ) -> SynthesisBlueprint:
        raise self.error


@pytest.mark.asyncio
async def test_runner_executes_only_selected_passing_scenario() -> None:
    from synthesis_quality_check import run_quality_check

    client = FakeClient()
    generator = RecordingGenerator(make_blueprint())
    output: list[str] = []

    exit_code = await run_quality_check(
        scenarios=(make_scenario("small-api"), make_scenario("agent-col")),
        selected_scenario_id="agent-col",
        client_factory=lambda: client,
        blueprint_generator=generator,
        output=output.append,
    )

    assert exit_code == 0
    assert output == ["agent-col pass"]
    assert generator.source_texts == ["private-source-agent-col"]
    assert client.aio.closed is True
    assert client.closed is True


@pytest.mark.asyncio
async def test_runner_returns_one_for_quality_findings_without_content() -> None:
    from synthesis_quality_check import run_quality_check

    scenario = QualityScenario(
        scenario_id="quality-failure",
        fixture_version="1.1",
        source_text="private-source",
        profile={},
        required_concepts=(
            RequiredConcept(
                concept_id="private-safe-rule",
                phrases=("private-missing-concept",),
            ),
        ),
    )
    output: list[str] = []

    exit_code = await run_quality_check(
        scenarios=(scenario,),
        selected_scenario_id=None,
        client_factory=FakeClient,
        blueprint_generator=RecordingGenerator(make_blueprint()),
        output=output.append,
    )

    assert exit_code == 1
    assert output == [
        "quality-failure missing_required_concept:private-safe-rule"
    ]
    assert "private-source" not in " ".join(output)
    assert "private-missing-concept" not in " ".join(output)


@pytest.mark.asyncio
async def test_fixture_runner_reports_safe_named_concept_id(
    tmp_path: Path,
) -> None:
    from synthesis_quality_check import run_quality_fixture

    fixture_path = tmp_path / "quality.json"
    fixture_path.write_text(
        json.dumps(
            {
                "fixture_version": "1.1",
                "scenarios": [
                    {
                        "scenario_id": "quality-failure",
                        "source_text": "private-source",
                        "profile": {},
                        "required_concepts": [
                            {
                                "concept_id": "safe-rule-id",
                                "phrases": ["private-missing-concept"],
                            }
                        ],
                        "forbidden_claims": [],
                        "expected_adaptation_keys": [],
                        "min_architectural_decisions": 0,
                        "max_architectural_decisions": 4,
                        "min_clarifying_questions": 0,
                        "max_clarifying_questions": 3,
                        "min_roadmap_milestones": 0,
                        "max_roadmap_milestones": 4,
                        "min_diagnostic_warnings": 0,
                        "max_diagnostic_warnings": 4,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output: list[str] = []

    exit_code = await run_quality_fixture(
        fixture_path=fixture_path,
        selected_scenario_id=None,
        client_factory=FakeClient,
        blueprint_generator=RecordingGenerator(make_blueprint()),
        output=output.append,
    )

    assert exit_code == 1
    assert output == [
        "quality-failure missing_required_concept:safe-rule-id"
    ]
    assert "private-source" not in " ".join(output)
    assert "private-missing-concept" not in " ".join(output)


@pytest.mark.asyncio
async def test_runner_returns_two_and_closes_client_on_provider_failure() -> None:
    from synthesis_quality_check import run_quality_check

    client = FakeClient()
    output: list[str] = []

    exit_code = await run_quality_check(
        scenarios=(make_scenario("provider-failure"),),
        selected_scenario_id=None,
        client_factory=lambda: client,
        blueprint_generator=FailingGenerator(
            SynthesisEngineError("private-provider-detail")
        ),
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["provider-failure provider_error"]
    assert client.aio.closed is True
    assert client.closed is True
    assert "private-provider-detail" not in " ".join(output)


@pytest.mark.asyncio
async def test_runner_rejects_unknown_selection_before_client_creation() -> None:
    from synthesis_quality_check import run_quality_check

    clients_created = 0
    output: list[str] = []

    def create_client() -> FakeClient:
        nonlocal clients_created
        clients_created += 1
        return FakeClient()

    exit_code = await run_quality_check(
        scenarios=(make_scenario("known-scenario"),),
        selected_scenario_id="private-unknown-scenario",
        client_factory=create_client,
        blueprint_generator=RecordingGenerator(make_blueprint()),
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["quality-check configuration_error"]
    assert clients_created == 0
    assert "private-unknown-scenario" not in " ".join(output)


@pytest.mark.asyncio
async def test_runner_returns_two_when_client_configuration_fails() -> None:
    from synthesis_quality_check import run_quality_check

    output: list[str] = []

    def fail_client_creation() -> FakeClient:
        raise RuntimeError("private-configuration-detail")

    exit_code = await run_quality_check(
        scenarios=(make_scenario("configuration-failure"),),
        selected_scenario_id=None,
        client_factory=fail_client_creation,
        blueprint_generator=RecordingGenerator(make_blueprint()),
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["quality-check configuration_error"]
    assert "private-configuration-detail" not in " ".join(output)


@pytest.mark.asyncio
async def test_fixture_runner_rejects_malformed_fixture_before_client(
    tmp_path: Path,
) -> None:
    from synthesis_quality_check import run_quality_fixture

    fixture_path = tmp_path / "private-fixture.json"
    fixture_path.write_text('{"private-content":', encoding="utf-8")
    clients_created = 0
    output: list[str] = []

    def create_client() -> FakeClient:
        nonlocal clients_created
        clients_created += 1
        return FakeClient()

    exit_code = await run_quality_fixture(
        fixture_path=fixture_path,
        selected_scenario_id=None,
        client_factory=create_client,
        blueprint_generator=RecordingGenerator(make_blueprint()),
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["quality-check configuration_error"]
    assert clients_created == 0
    assert "private-content" not in " ".join(output)


def test_main_forwards_explicit_scenario_without_network_access() -> None:
    from synthesis_quality_check import main

    selected_ids: list[str | None] = []
    environment_loads = 0

    async def record_fixture_run(**kwargs: object) -> int:
        selected = kwargs["selected_scenario_id"]
        assert isinstance(selected, str)
        selected_ids.append(selected)
        return 0

    def load_environment() -> None:
        nonlocal environment_loads
        environment_loads += 1

    exit_code = main(
        ["--scenario", "agent-col-architecture"],
        fixture_runner=record_fixture_run,
        environment_loader=load_environment,
    )

    assert exit_code == 0
    assert selected_ids == ["agent-col-architecture"]
    assert environment_loads == 1
