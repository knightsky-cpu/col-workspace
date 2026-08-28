import _repo_path
"""Run one fixed live Computational Expert verification request."""

import asyncio
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from computational_expert import (
    ComputationExpertInput,
    ComputationExpertResult,
)
from computational_expert_service import (
    ComputationalExpertService,
    ComputationalExpertServiceError,
)
from expert_contracts import ExpertStatus
from vertex_config import (
    VertexAIConfigurationError,
    VertexAISettings,
    load_vertex_ai_settings,
)


DEFAULT_DOTENV_PATH = Path(__file__).with_name(".env")
DEFAULT_COMPUTATION_REQUEST = ComputationExpertInput(
    objective=(
        "Calculate the mean, median, population standard deviation, minimum, "
        "and maximum of the supplied values."
    ),
    inputs={
        "series": [
            {
                "name": "values",
                "values": [12, 15, 18, 21, 24, 27],
            }
        ],
        "expression": "mean(values)",
    },
    required_precision={"mode": "decimal_places", "digits": 4},
)


class ComputationService(Protocol):
    async def compute(
        self,
        request: ComputationExpertInput,
    ) -> ComputationExpertResult: ...


async def run_live(
    *,
    environment: Mapping[str, str] | None = None,
    dotenv_loader: Callable[[Path], object] = load_dotenv,
    service_factory: Callable[
        [VertexAISettings], ComputationService
    ] = ComputationalExpertService.from_vertex_settings,
) -> int:
    """Run the live smoke request and return its documented exit code."""
    dotenv_loader(DEFAULT_DOTENV_PATH)
    try:
        settings = load_vertex_ai_settings(
            os.environ if environment is None else environment
        )
    except VertexAIConfigurationError:
        print("computational-expert configuration_error")
        return 2

    service = service_factory(settings)
    try:
        result = await service.compute(DEFAULT_COMPUTATION_REQUEST)
    except ComputationalExpertServiceError as exc:
        print(f"computational-expert {exc.status.value}")
        if exc.status in {
            ExpertStatus.INVALID_OUTPUT,
            ExpertStatus.REJECTED_INPUT,
        }:
            return 1
        return 2

    if result.status is not ExpertStatus.COMPLETED:
        print(f"computational-expert {result.status.value}")
        return 1
    print(f"computational-expert-pass {result.model_dump_json()}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run_live()))


if __name__ == "__main__":
    main()
