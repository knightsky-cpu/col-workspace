import importlib
from pathlib import Path

import pytest

from expert_contracts import ExpertStatus
from requirements_verification import (
    RequirementsVerificationCandidate,
    normalize_requirements_verification_candidate,
)
from requirements_verification_service import (
    RequirementsVerificationServiceError,
)


VALID_ENVIRONMENT = {
    "GOOGLE_CLOUD_PROJECT": "project-1",
    "GOOGLE_CLOUD_LOCATION": "global",
    "GOOGLE_GENAI_USE_ENTERPRISE": "True",
}


def load_runner():
    try:
        return importlib.import_module(
            "smoke_test_agent_col_requirements_verification_pipeline"
        )
    except ModuleNotFoundError:
        pytest.fail(
            "smoke_test_agent_col_requirements_verification_pipeline "
            "is not implemented"
        )


class FakeVerificationService:
    def __init__(self, outcome=None) -> None:
        self.outcome = outcome
        self.requests: list[object] = []

    async def verify(self, request):
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        if self.outcome is not None:
            return self.outcome
        candidate = RequirementsVerificationCandidate.model_validate(
            {
                "assessments": [
                    {
                        "requirement_id": "REQ-001",
                        "status": "covered",
                        "evidence": [
                            {
                                "subject_block_id": "SUBJECT-001",
                                "excerpt": "includes one practical example",
                                "explanation": (
                                    "The supplied draft addresses the "
                                    "requirement."
                                ),
                            }
                        ],
                    },
                    {
                        "requirement_id": "REQ-002",
                        "status": "contradictory",
                        "evidence": [
                            {
                                "subject_block_id": "SUBJECT-001",
                                "excerpt": "states no limitation",
                                "explanation": (
                                    "The supplied draft contradicts the "
                                    "requirement."
                                ),
                            }
                        ],
                        "gap": "The required limitation is absent.",
                        "recommended_action": (
                            "State one material limitation."
                        ),
                    },
                ],
                "overall_limitations": [
                    "Only supplied material was assessed."
                ],
            }
        )
        return normalize_requirements_verification_candidate(
            request,
            candidate,
        )


@pytest.mark.asyncio
async def test_pipeline_smoke_uses_vertex_service_and_prints_metadata_only(
) -> None:
    runner = load_runner()
    settings_seen: list[object] = []
    output: list[str] = []
    service = FakeVerificationService()

    def service_factory(settings):
        settings_seen.append(settings)
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
    assert service.requests == [runner.DEFAULT_VERIFICATION_REQUEST]
    assert output == [
        "agent-col-requirements-verification-pipeline pass "
        "status=completed action=verify_requirements citations=0 "
        "requirements=2 assessed=2"
    ]
    assert "includes one practical example" not in output[0]
    assert "states no limitation" not in output[0]


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
        service_factory=lambda _: FakeVerificationService(
            RequirementsVerificationServiceError(ExpertStatus.UNAVAILABLE)
        ),
        output=output.append,
    )

    assert configuration_exit == 2
    assert unavailable_exit == 2
    assert output == [
        "agent-col-requirements-verification-pipeline configuration_error",
        "agent-col-requirements-verification-pipeline unavailable",
    ]


def test_pipeline_smoke_has_no_fastapi_firestore_or_http_client_boundary(
) -> None:
    runner = load_runner()

    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert "from main import" not in source
    assert "import main" not in source
    assert "httpx" not in source
    assert "firestore" not in source.lower()
