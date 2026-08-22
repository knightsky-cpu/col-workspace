import importlib
from pathlib import Path

import pytest

from computational_expert import ComputationExpertResult
from computational_expert_service import ComputationalExpertServiceError
from expert_contracts import ExpertStatus


VALID_ENVIRONMENT = {
    "GOOGLE_CLOUD_PROJECT": "project-1",
    "GOOGLE_CLOUD_LOCATION": "global",
    "GOOGLE_GENAI_USE_ENTERPRISE": "True",
}


def load_runner():
    try:
        return importlib.import_module(
            "smoke_test_agent_col_computation_pipeline"
        )
    except ModuleNotFoundError:
        pytest.fail(
            "smoke_test_agent_col_computation_pipeline is not implemented"
        )


class FakeComputationService:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.requests: list[object] = []

    async def compute(self, request):
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def completed_result(inputs) -> ComputationExpertResult:
    code = "print('PRIVATE_PIPELINE_CODE')"
    output = "PRIVATE_PIPELINE_OUTPUT\n"
    return ComputationExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "Computation completed with 1 verified run.",
            "payload": {
                "method": "Provider-executed Python computation.",
                "inputs_used": inputs.model_dump(mode="json"),
                "result": (
                    "The mean is 19.5000 and population standard deviation "
                    "is 5.1235."
                ),
                "execution_runs": [
                    {
                        "language": "python",
                        "code": code,
                        "outcome": "success",
                        "output": output,
                    }
                ],
            },
            "evidence": {
                "execution_count": 1,
                "successful_execution_count": 1,
                "code_character_count": len(code),
                "output_character_count": len(output),
            },
        }
    )


@pytest.mark.asyncio
async def test_pipeline_smoke_uses_vertex_service_and_prints_metadata_only(
) -> None:
    runner = load_runner()
    settings_seen: list[object] = []
    output: list[str] = []
    service = None

    def service_factory(settings):
        nonlocal service
        settings_seen.append(settings)
        request = runner.DEFAULT_COMPUTATION_REQUEST
        service = FakeComputationService(completed_result(request.inputs))
        return service

    exit_code = await runner.run_live(
        environment=VALID_ENVIRONMENT,
        dotenv_loader=lambda _: True,
        service_factory=service_factory,
        output=output.append,
    )

    assert exit_code == 0
    assert len(settings_seen) == 1
    assert settings_seen[0].client_kwargs() == {
        "enterprise": True,
        "project": "project-1",
        "location": "global",
    }
    assert service is not None
    assert service.requests == [runner.DEFAULT_COMPUTATION_REQUEST]
    assert output == [
        "agent-col-computation-pipeline pass status=completed "
        "action=run_computation citations=0 execution_verified=true"
    ]
    assert "PRIVATE_PIPELINE_CODE" not in output[0]
    assert "PRIVATE_PIPELINE_OUTPUT" not in output[0]


@pytest.mark.asyncio
async def test_pipeline_smoke_classifies_configuration_and_service_failure(
) -> None:
    runner = load_runner()
    output: list[str] = []

    configuration_exit = await runner.run_live(
        environment={},
        dotenv_loader=lambda _: True,
        service_factory=lambda _: pytest.fail("service must not be created"),
        output=output.append,
    )
    unavailable_exit = await runner.run_live(
        environment=VALID_ENVIRONMENT,
        dotenv_loader=lambda _: True,
        service_factory=lambda _: FakeComputationService(
            ComputationalExpertServiceError(ExpertStatus.UNAVAILABLE)
        ),
        output=output.append,
    )

    assert configuration_exit == 2
    assert unavailable_exit == 2
    assert output == [
        "agent-col-computation-pipeline configuration_error",
        "agent-col-computation-pipeline unavailable",
    ]


def test_pipeline_smoke_has_no_fastapi_firestore_or_http_client_boundary(
) -> None:
    runner = load_runner()

    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert "from main import" not in source
    assert "import main" not in source
    assert "httpx" not in source
    assert "firestore" not in source.lower()
