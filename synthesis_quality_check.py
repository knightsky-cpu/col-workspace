import argparse
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from google import genai
from pydantic import ValidationError

from schemas import SynthesisBlueprint
from synthesis import SynthesisEngineError, generate_blueprint
from synthesis_quality import (
    DEFAULT_QUALITY_FIXTURE_PATH,
    QualityScenario,
    evaluate_blueprint,
    load_quality_scenarios,
)


class AsyncClientHandle(Protocol):
    async def aclose(self) -> None: ...


class ClientHandle(Protocol):
    aio: AsyncClientHandle

    def close(self) -> None: ...


ClientFactory = Callable[[], ClientHandle]
BlueprintGenerator = Callable[
    [ClientHandle, dict[str, object], list[dict[str, object]], str],
    Awaitable[SynthesisBlueprint],
]
OutputWriter = Callable[[str], None]
FixtureRunner = Callable[..., Awaitable[int]]
EnvironmentLoader = Callable[[], object]


async def run_quality_fixture(
    *,
    fixture_path: Path,
    selected_scenario_id: str | None,
    client_factory: ClientFactory,
    blueprint_generator: BlueprintGenerator,
    output: OutputWriter,
) -> int:
    """Load scenarios before creating a client, then run evaluation."""
    try:
        scenarios = load_quality_scenarios(fixture_path)
    except (OSError, ValidationError):
        output("quality-check configuration_error")
        return 2
    return await run_quality_check(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        client_factory=client_factory,
        blueprint_generator=blueprint_generator,
        output=output,
    )


async def run_quality_check(
    *,
    scenarios: tuple[QualityScenario, ...],
    selected_scenario_id: str | None,
    client_factory: ClientFactory,
    blueprint_generator: BlueprintGenerator,
    output: OutputWriter,
) -> int:
    """Generate and evaluate the selected quality scenarios."""
    selected = scenarios
    if selected_scenario_id is not None:
        selected = tuple(
            scenario
            for scenario in scenarios
            if scenario.scenario_id == selected_scenario_id
        )
    if not selected:
        output("quality-check configuration_error")
        return 2

    try:
        client = client_factory()
    except Exception:
        output("quality-check configuration_error")
        return 2
    has_quality_findings = False
    try:
        for scenario in selected:
            blueprint = await blueprint_generator(
                client,
                dict(scenario.profile),
                [],
                scenario.source_text,
            )
            findings = evaluate_blueprint(scenario, blueprint)
            if findings:
                has_quality_findings = True
                output(
                    " ".join(
                        (
                            scenario.scenario_id,
                            *(finding.code for finding in findings),
                        )
                    )
                )
            else:
                output(f"{scenario.scenario_id} pass")
    except SynthesisEngineError:
        output(f"{scenario.scenario_id} provider_error")
        return 2
    finally:
        try:
            await client.aio.aclose()
        finally:
            client.close()
    return 1 if has_quality_findings else 0


def main(
    argv: list[str] | None = None,
    *,
    fixture_runner: FixtureRunner = run_quality_fixture,
    environment_loader: EnvironmentLoader = load_dotenv,
) -> int:
    """Run explicit live synthesis quality evaluation."""
    parser = argparse.ArgumentParser(
        description="Run Agent_Col synthesis quality scenarios."
    )
    parser.add_argument(
        "--scenario",
        help="Run only the scenario with this ID.",
    )
    arguments = parser.parse_args(argv)
    environment_loader()
    return asyncio.run(
        fixture_runner(
            fixture_path=DEFAULT_QUALITY_FIXTURE_PATH,
            selected_scenario_id=arguments.scenario,
            client_factory=genai.Client,
            blueprint_generator=generate_blueprint,
            output=print,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
