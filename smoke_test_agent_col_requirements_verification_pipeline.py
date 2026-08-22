"""Run one fixed live routing-v3 requirements verification pipeline."""

import asyncio
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from google import genai

from agent_col_expert_executor_v3 import (
    AgentColExpertExecutorV3,
    build_requirements_verification_input,
)
from agent_col_responder_context_v3 import (
    build_agent_col_responder_v3_model_context,
)
from agent_col_routing_v3 import AgentColRoutingDirective, AgentColRoutingInput
from agent_col_text_projection import project_routing_text_blocks
from expert_contracts import ExpertStatus
from requirements_verification import (
    RequirementsVerificationInput,
    RequirementsVerificationResult,
)
from requirements_verification_service import RequirementsVerificationService
from vertex_config import (
    VertexAIConfigurationError,
    VertexAISettings,
    load_vertex_ai_settings,
)


DEFAULT_DOTENV_PATH = Path(__file__).with_name(".env")
DEFAULT_MESSAGE = (
    "Compare the draft against every requirement.\n\n"
    "Requirements:\n"
    "- Include one practical example.\n"
    "- State one material limitation.\n\n"
    "Subject:\n"
    "The draft includes one practical example but states no limitation."
)
_DEFAULT_TEXT_PROJECTION = project_routing_text_blocks(DEFAULT_MESSAGE)
DEFAULT_ROUTING_INPUT = AgentColRoutingInput(
    current_message=DEFAULT_MESSAGE,
    text_block_candidates=_DEFAULT_TEXT_PROJECTION.candidates,
    text_projection_incomplete=(
        _DEFAULT_TEXT_PROJECTION.text_projection_incomplete
    ),
    available_capabilities=("requirements_verification",),
)
DEFAULT_ROUTING_DIRECTIVE = AgentColRoutingDirective(
    route="requirements_verification",
    requirements_verification_intent={
        "objective": "Assess every requirement against the draft.",
        "requirement_block_ids": ["block-3", "block-4"],
        "subject_block_ids": ["block-6"],
        "constraints": ["Use only the supplied subject."],
    },
)
DEFAULT_VERIFICATION_REQUEST = build_requirements_verification_input(
    DEFAULT_ROUTING_DIRECTIVE,
    DEFAULT_ROUTING_INPUT,
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
    output: Callable[[str], None] = print,
) -> int:
    """Execute the fixed pipeline and return its documented exit code."""
    dotenv_loader(DEFAULT_DOTENV_PATH)
    try:
        settings = load_vertex_ai_settings(
            os.environ if environment is None else environment
        )
    except VertexAIConfigurationError:
        output(
            "agent-col-requirements-verification-pipeline "
            "configuration_error"
        )
        return 2

    service = service_factory(settings)
    executor = AgentColExpertExecutorV3(
        requirements_verification_service=service
    )
    context = await executor.execute(
        DEFAULT_ROUTING_DIRECTIVE,
        DEFAULT_ROUTING_INPUT,
    )
    result = context.expert_result
    if result is None or result.status is not ExpertStatus.COMPLETED:
        status = "invalid_output" if result is None else result.status.value
        output(f"agent-col-requirements-verification-pipeline {status}")
        return 2

    rendered = build_agent_col_responder_v3_model_context(context)
    serialized = rendered.parts[0].text
    evidence = result.evidence
    expected_action = (
        len(context.actions) == 1
        and context.actions[0].action_name == "verify_requirements"
        and context.actions[0].status == "completed"
    )
    bounded_projection = all(
        marker not in serialized
        for marker in (
            "CURRENT_MESSAGE_MARKER",
            "PROFILE_MARKER",
            "HISTORY_MARKER",
            "PROJECT_ID_MARKER",
            "SESSION_ID_MARKER",
            "USER_ID_MARKER",
            "IDEMPOTENCY_KEY_MARKER",
            "CREDENTIAL_MARKER",
            "PROVIDER_PAYLOAD_MARKER",
        )
    )
    if (
        not expected_action
        or context.citations
        or result.payload is None
        or evidence is None
        or evidence.requirement_count != 2
        or evidence.assessed_requirement_count != 2
        or not bounded_projection
    ):
        output(
            "agent-col-requirements-verification-pipeline "
            "invariant_mismatch"
        )
        return 1

    output(
        "agent-col-requirements-verification-pipeline pass "
        "status=completed action=verify_requirements citations=0 "
        "requirements=2 assessed=2"
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run_live()))


if __name__ == "__main__":
    main()
