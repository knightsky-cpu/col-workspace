import json
from pathlib import Path

import pytest

from computational_expert import (
    ComputationExpertEvidence,
    ComputationExpertPayload,
    ComputationExpertResult,
    ComputationInputs,
    ExecutionRunEvidence,
)
from computational_expert_service import ComputationalExpertServiceError
from expert_contracts import ExpertStatus


VALID_ENVIRONMENT = {
    "GOOGLE_CLOUD_PROJECT": "project-1",
    "GOOGLE_CLOUD_LOCATION": "global",
    "GOOGLE_GENAI_USE_ENTERPRISE": "True",
}


class FakeService:
    def __init__(
        self,
        result: ComputationExpertResult | Exception,
    ) -> None:
        self.result = result
        self.requests: list[object] = []

    async def compute(self, request: object) -> ComputationExpertResult:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def completed_result() -> ComputationExpertResult:
    run = ExecutionRunEvidence(
        code="print(sum([12, 15, 18, 21, 24, 27]) / 6)",
        outcome="success",
        output="19.5\n",
    )
    return ComputationExpertResult(
        status=ExpertStatus.COMPLETED,
        summary="Computed the requested descriptive statistics.",
        payload=ComputationExpertPayload(
            method="Provider-executed Python computation.",
            inputs_used=ComputationInputs(
                series=(
                    {
                        "name": "values",
                        "values": (12, 15, 18, 21, 24, 27),
                    },
                ),
                expression="mean(values)",
            ),
            result="The arithmetic mean is 19.5.",
            execution_runs=(run,),
        ),
        evidence=ComputationExpertEvidence(
            execution_count=1,
            successful_execution_count=1,
            code_character_count=len(run.code),
            output_character_count=len(run.output),
        ),
    )


@pytest.mark.asyncio
async def test_live_smoke_completed_prints_validated_result_and_evidence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from smoke_test_computational_expert import run_live

    service = FakeService(completed_result())

    exit_code = await run_live(
        environment=VALID_ENVIRONMENT,
        dotenv_loader=lambda _: True,
        service_factory=lambda _: service,
    )

    assert exit_code == 0
    assert len(service.requests) == 1
    output = capsys.readouterr().out.strip()
    prefix, serialized = output.split(" ", maxsplit=1)
    assert prefix == "computational-expert-pass"
    assert json.loads(serialized) == completed_result().model_dump(
        mode="json"
    )


@pytest.mark.asyncio
async def test_live_smoke_noncompleted_result_exits_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from smoke_test_computational_expert import run_live

    exit_code = await run_live(
        environment=VALID_ENVIRONMENT,
        dotenv_loader=lambda _: True,
        service_factory=lambda _: FakeService(
            ComputationExpertResult(status=ExpertStatus.INVALID_OUTPUT)
        ),
    )

    assert exit_code == 1
    assert capsys.readouterr().out.strip() == (
        "computational-expert invalid_output"
    )


@pytest.mark.asyncio
async def test_live_smoke_service_failure_exits_two_without_detail(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from smoke_test_computational_expert import run_live

    sensitive_detail = "do-not-print-provider-exception-content"
    error = ComputationalExpertServiceError(ExpertStatus.UNAVAILABLE)
    error.__cause__ = RuntimeError(sensitive_detail)

    exit_code = await run_live(
        environment=VALID_ENVIRONMENT,
        dotenv_loader=lambda _: True,
        service_factory=lambda _: FakeService(error),
    )

    assert exit_code == 2
    output = capsys.readouterr().out.strip()
    assert output == "computational-expert unavailable"
    assert sensitive_detail not in output


@pytest.mark.asyncio
async def test_live_smoke_loads_repository_dotenv_before_configuration(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from smoke_test_computational_expert import DEFAULT_DOTENV_PATH, run_live

    loaded_paths: list[Path] = []

    exit_code = await run_live(
        environment={},
        dotenv_loader=lambda path: loaded_paths.append(path) or True,
        service_factory=lambda _: pytest.fail(
            "service must not be created for invalid configuration"
        ),
    )

    assert exit_code == 2
    assert loaded_paths == [DEFAULT_DOTENV_PATH]
    assert capsys.readouterr().out.strip() == (
        "computational-expert configuration_error"
    )
