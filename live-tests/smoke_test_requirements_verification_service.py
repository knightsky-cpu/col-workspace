import _repo_path
"""Run one fixed live Requirements Verification provider request."""

import asyncio
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from google import genai

from expert_contracts import ExpertStatus
from requirements_verification import (
    RequirementsVerificationInput,
    RequirementsVerificationResult,
)
from requirements_verification_service import (
    RequirementsVerificationService,
    RequirementsVerificationServiceError,
)
from vertex_config import (
    VertexAIConfigurationError,
    VertexAISettings,
    load_vertex_ai_settings,
)


DEFAULT_DOTENV_PATH = Path(__file__).with_name(".env")
DEFAULT_REQUEST = RequirementsVerificationInput(
    objective="Assess every requirement against the supplied draft.",
    requirements=(
        {
            "requirement_id": "REQ-001",
            "text": "Include one practical example.",
            "source_block_id": "block-1",
        },
    ),
    subject_blocks=(
        {
            "subject_block_id": "SUBJECT-001",
            "text": "The draft includes a practical example.",
            "source_block_id": "block-2",
        },
    ),
    constraints=("Assess only the supplied draft.",),
)


class VerificationService(Protocol):
    async def verify(
        self,
        request: RequirementsVerificationInput,
    ) -> RequirementsVerificationResult: ...


def _build_service(
    settings: VertexAISettings,
) -> RequirementsVerificationService:
    return RequirementsVerificationService(
        client=genai.Client(**settings.client_kwargs())
    )


async def run_live(
    *,
    environment: Mapping[str, str] | None = None,
    dotenv_loader: Callable[[Path], object] = load_dotenv,
    service_factory: Callable[
        [VertexAISettings], VerificationService
    ] = _build_service,
) -> int:
    """Run the live request and return its documented exit code."""
    dotenv_loader(DEFAULT_DOTENV_PATH)
    try:
        settings = load_vertex_ai_settings(
            os.environ if environment is None else environment
        )
    except VertexAIConfigurationError:
        print("requirements-verification-service configuration_error")
        return 2

    service = service_factory(settings)
    try:
        result = await service.verify(DEFAULT_REQUEST)
    except RequirementsVerificationServiceError as exc:
        suffix = (
            f":{exc.invalid_output_reason.value}"
            if exc.invalid_output_reason is not None
            else ""
        )
        print(
            "requirements-verification-service "
            f"{exc.status.value}{suffix}"
        )
        if exc.status in {
            ExpertStatus.INVALID_OUTPUT,
            ExpertStatus.REJECTED_INPUT,
        }:
            return 1
        return 2

    if (
        result.status is not ExpertStatus.COMPLETED
        or result.payload is None
        or result.evidence is None
    ):
        print(f"requirements-verification-service {result.status.value}")
        return 1

    print(
        "requirements-verification-service-pass "
        f"status={result.status.value} "
        f"requirements={result.evidence.requirement_count} "
        f"assessed={result.evidence.assessed_requirement_count} "
        f"evidence={result.evidence.validated_evidence_count}"
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run_live()))


if __name__ == "__main__":
    main()
