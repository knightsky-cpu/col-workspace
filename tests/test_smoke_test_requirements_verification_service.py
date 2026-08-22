import pytest

from expert_contracts import ExpertStatus
from requirements_verification import (
    RequirementAssessment,
    RequirementStatusCounts,
    RequirementsVerificationEvidence,
    RequirementsVerificationPayload,
    RequirementsVerificationResult,
    SubjectEvidence,
)
from requirements_verification_service import (
    RequirementsVerificationInvalidOutputReason,
    RequirementsVerificationServiceError,
)


VALID_ENVIRONMENT = {
    "GOOGLE_CLOUD_PROJECT": "project-1",
    "GOOGLE_CLOUD_LOCATION": "global",
    "GOOGLE_GENAI_USE_ENTERPRISE": "True",
}


class FakeService:
    def __init__(
        self,
        result: RequirementsVerificationResult | Exception,
    ) -> None:
        self.result = result
        self.requests: list[object] = []

    async def verify(self, request: object) -> RequirementsVerificationResult:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def completed_result() -> RequirementsVerificationResult:
    evidence = SubjectEvidence(
        subject_block_id="SUBJECT-001",
        excerpt="The draft includes a practical example.",
        explanation="The supplied draft directly addresses the requirement.",
    )
    return RequirementsVerificationResult(
        status=ExpertStatus.COMPLETED,
        summary="Requirements verification completed for 1 requirements.",
        payload=RequirementsVerificationPayload(
            assessments=(
                RequirementAssessment(
                    requirement_id="REQ-001",
                    requirement_text="Include one practical example.",
                    status="covered",
                    evidence=(evidence,),
                ),
            ),
            counts=RequirementStatusCounts(
                covered=1,
                partial=0,
                missing=0,
                contradictory=0,
                unsupported=0,
            ),
        ),
        evidence=RequirementsVerificationEvidence(
            requirement_count=1,
            assessed_requirement_count=1,
            validated_evidence_count=1,
            referenced_subject_block_ids=("SUBJECT-001",),
        ),
    )


@pytest.mark.asyncio
async def test_live_smoke_completed_prints_bounded_evidence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from smoke_test_requirements_verification_service import run_live

    service = FakeService(completed_result())
    exit_code = await run_live(
        environment=VALID_ENVIRONMENT,
        dotenv_loader=lambda _: True,
        service_factory=lambda _: service,
    )

    assert exit_code == 0
    assert len(service.requests) == 1
    assert capsys.readouterr().out.strip() == (
        "requirements-verification-service-pass "
        "status=completed requirements=1 assessed=1 evidence=1"
    )


@pytest.mark.asyncio
async def test_live_smoke_configuration_failure_exits_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from smoke_test_requirements_verification_service import run_live

    exit_code = await run_live(
        environment={},
        dotenv_loader=lambda _: True,
        service_factory=lambda _: pytest.fail(
            "service must not be built for invalid configuration"
        ),
    )

    assert exit_code == 2
    assert capsys.readouterr().out.strip() == (
        "requirements-verification-service configuration_error"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_exit", "expected_output"),
    [
        (
            RequirementsVerificationServiceError(
                ExpertStatus.INVALID_OUTPUT,
                invalid_output_reason=(
                    RequirementsVerificationInvalidOutputReason.
                    LOCAL_VALIDATION_FAILED
                ),
            ),
            1,
            "requirements-verification-service "
            "invalid_output:local_validation_failed",
        ),
        (
            RequirementsVerificationServiceError(
                ExpertStatus.UNAVAILABLE
            ),
            2,
            "requirements-verification-service unavailable",
        ),
    ],
)
async def test_live_smoke_maps_service_failure_to_safe_exit(
    error: RequirementsVerificationServiceError,
    expected_exit: int,
    expected_output: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from smoke_test_requirements_verification_service import run_live

    exit_code = await run_live(
        environment=VALID_ENVIRONMENT,
        dotenv_loader=lambda _: True,
        service_factory=lambda _: FakeService(error),
    )

    assert exit_code == expected_exit
    assert capsys.readouterr().out.strip() == expected_output


@pytest.mark.asyncio
async def test_live_smoke_noncompleted_result_exits_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from smoke_test_requirements_verification_service import run_live

    exit_code = await run_live(
        environment=VALID_ENVIRONMENT,
        dotenv_loader=lambda _: True,
        service_factory=lambda _: FakeService(
            RequirementsVerificationResult(
                status=ExpertStatus.INVALID_OUTPUT
            )
        ),
    )

    assert exit_code == 1
    assert capsys.readouterr().out.strip() == (
        "requirements-verification-service invalid_output"
    )
