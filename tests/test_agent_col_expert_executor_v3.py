import importlib

import pytest

from agent_col_routing_v3 import (
    AgentColRoutingDirective,
    AgentColRoutingInput,
)
from agent_col_text_projection import project_routing_text_blocks
from expert_contracts import ExpertCapability, ExpertStatus


def load_executor_v3():
    try:
        return importlib.import_module("agent_col_expert_executor_v3")
    except ModuleNotFoundError:
        pytest.fail("agent_col_expert_executor_v3 has not been implemented")


def requirements_routing_case():
    message = (
        "Compare the draft against every requirement.\n\n"
        "Requirements:\n"
        "- Include one practical example.\n"
        "- State one material limitation.\n\n"
        "Subject:\n"
        "The draft includes one practical example but states no limitation."
    )
    projection = project_routing_text_blocks(message)
    routing_input = AgentColRoutingInput(
        current_message=message,
        text_block_candidates=projection.candidates,
        text_projection_incomplete=projection.text_projection_incomplete,
        available_capabilities=("requirements_verification",),
    )
    directive = AgentColRoutingDirective(
        route="requirements_verification",
        requirements_verification_intent={
            "objective": "Assess every requirement against the draft.",
            "requirement_block_ids": ["block-3", "block-4"],
            "subject_block_ids": ["block-6"],
            "constraints": ["Use only the supplied subject."],
        },
    )
    return directive, routing_input


def test_builder_assigns_local_ids_and_preserves_exact_selected_blocks(
) -> None:
    executor_v3 = load_executor_v3()
    directive, routing_input = requirements_routing_case()

    request = executor_v3.build_requirements_verification_input(
        directive,
        routing_input,
    )

    assert request.objective == (
        "Assess every requirement against the draft."
    )
    assert tuple(
        (
            requirement.requirement_id,
            requirement.text,
            requirement.source_block_id,
        )
        for requirement in request.requirements
    ) == (
        ("REQ-001", "- Include one practical example.", "block-3"),
        ("REQ-002", "- State one material limitation.", "block-4"),
    )
    assert tuple(
        (subject.subject_block_id, subject.text, subject.source_block_id)
        for subject in request.subject_blocks
    ) == (
        (
            "SUBJECT-001",
            "The draft includes one practical example but states no limitation.",
            "block-6",
        ),
    )
    assert request.constraints == ("Use only the supplied subject.",)


class RecordingService:
    def __init__(self, result=None) -> None:
        self.result = result
        self.requests: list[object] = []

    async def analyze(self, request):
        self.requests.append(request)
        return self.result

    async def research(self, request):
        self.requests.append(request)
        return self.result

    async def compute(self, request):
        self.requests.append(request)
        return self.result


class RecordingVerificationService:
    def __init__(self) -> None:
        self.requests: list[object] = []

    async def verify(self, request):
        from requirements_verification import (
            RequirementsVerificationCandidate,
            normalize_requirements_verification_candidate,
        )

        self.requests.append(request)
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
                                    "The supplied subject directly addresses "
                                    "the requirement."
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
                                    "The supplied subject contradicts the "
                                    "requirement."
                                ),
                            }
                        ],
                        "gap": "The required limitation is absent.",
                        "recommended_action": "State one material limitation.",
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


class FailingVerificationService(RecordingVerificationService):
    def __init__(self, status: ExpertStatus, reason=None) -> None:
        super().__init__()
        self.status = status
        self.reason = reason

    async def verify(self, request):
        from requirements_verification_service import (
            RequirementsVerificationServiceError,
        )

        self.requests.append(request)
        raise RequirementsVerificationServiceError(
            self.status,
            invalid_output_reason=self.reason,
        )


class FailingResearchService(RecordingService):
    def __init__(self, reason) -> None:
        super().__init__()
        self.reason = reason

    async def research(self, request):
        from research_expert_service import ResearchExpertServiceError

        self.requests.append(request)
        raise ResearchExpertServiceError(
            ExpertStatus.INVALID_OUTPUT,
            invalid_output_reason=self.reason,
        )


def test_executor_v3_derives_stable_four_capability_order() -> None:
    executor_v3 = load_executor_v3()

    executor = executor_v3.AgentColExpertExecutorV3(
        source_service=RecordingService(),
        research_service=RecordingService(),
        computation_service=RecordingService(),
        requirements_verification_service=RecordingVerificationService(),
    )

    assert executor.available_capabilities == (
        ExpertCapability.SOURCE,
        ExpertCapability.RESEARCH,
        ExpertCapability.COMPUTATION,
        ExpertCapability.REQUIREMENTS_VERIFICATION,
    )


@pytest.mark.asyncio
async def test_executor_v3_executes_verification_once_and_derives_receipt(
) -> None:
    executor_v3 = load_executor_v3()
    directive, routing_input = requirements_routing_case()
    service = RecordingVerificationService()
    executor = executor_v3.AgentColExpertExecutorV3(
        requirements_verification_service=service
    )

    context = await executor.execute(directive, routing_input)

    assert len(service.requests) == 1
    assert service.requests[0] == (
        executor_v3.build_requirements_verification_input(
            directive,
            routing_input,
        )
    )
    assert context.expert_result is not None
    assert context.expert_result.status is ExpertStatus.COMPLETED
    assert context.actions[0].model_dump() == {
        "action_name": "verify_requirements",
        "status": "completed",
    }
    assert context.citations == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    (
        ExpertStatus.REJECTED_INPUT,
        ExpertStatus.UNAVAILABLE,
        ExpertStatus.TIMED_OUT,
        ExpertStatus.INVALID_OUTPUT,
    ),
)
async def test_executor_v3_contains_verification_failure_without_fallback(
    status: ExpertStatus,
) -> None:
    executor_v3 = load_executor_v3()
    directive, routing_input = requirements_routing_case()
    verification = FailingVerificationService(status)
    source = RecordingService()
    research = RecordingService()
    computation = RecordingService()
    executor = executor_v3.AgentColExpertExecutorV3(
        source_service=source,
        research_service=research,
        computation_service=computation,
        requirements_verification_service=verification,
    )
    routing_input = routing_input.model_copy(
        update={
            "available_capabilities": (
                "source",
                "research",
                "computation",
                "requirements_verification",
            )
        }
    )

    context = await executor.execute(directive, routing_input)

    assert len(verification.requests) == 1
    assert source.requests == []
    assert research.requests == []
    assert computation.requests == []
    assert context.expert_result is not None
    assert context.expert_result.status is status
    assert context.expert_result.summary is None
    assert context.expert_result.payload is None
    assert context.expert_result.evidence is None
    assert context.actions == ()
    assert context.citations == ()


@pytest.mark.asyncio
async def test_executor_v3_preserves_research_invalid_output_reason() -> None:
    from research_expert import ResearchInvalidOutputReason

    executor_v3 = load_executor_v3()
    directive = AgentColRoutingDirective(
        route="research",
        research_intent={
            "question": "What is the current stable Python release?",
            "objective": "Verify with public sources.",
        },
    )
    routing_input = AgentColRoutingInput(
        current_message="What is the current stable Python release?",
        available_capabilities=("research",),
    )
    research = FailingResearchService(
        ResearchInvalidOutputReason.MISSING_GROUNDING_METADATA
    )
    executor = executor_v3.AgentColExpertExecutorV3(
        research_service=research,
    )

    context = await executor.execute(directive, routing_input)

    assert len(research.requests) == 1
    assert context.expert_result is not None
    assert context.expert_result.status is ExpertStatus.INVALID_OUTPUT
    assert context.expert_result.invalid_output_reason == (
        "missing_grounding_metadata"
    )
    assert context.actions == ()
    assert context.citations == ()


@pytest.mark.asyncio
async def test_executor_v3_preserves_verification_invalid_output_reason(
) -> None:
    from requirements_verification_service import (
        RequirementsVerificationInvalidOutputReason,
    )

    executor_v3 = load_executor_v3()
    directive, routing_input = requirements_routing_case()
    verification = FailingVerificationService(
        ExpertStatus.INVALID_OUTPUT,
        RequirementsVerificationInvalidOutputReason.INVALID_JSON,
    )
    executor = executor_v3.AgentColExpertExecutorV3(
        requirements_verification_service=verification,
    )

    context = await executor.execute(directive, routing_input)

    assert len(verification.requests) == 1
    assert context.expert_result is not None
    assert context.expert_result.status is ExpertStatus.INVALID_OUTPUT
    assert context.expert_result.invalid_output_reason == "invalid_json"
    assert context.actions == ()
    assert context.citations == ()


@pytest.mark.asyncio
async def test_executor_v3_contains_verification_request_drift_as_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor_v3 = load_executor_v3()
    directive, routing_input = requirements_routing_case()
    verification = RecordingVerificationService()
    executor = executor_v3.AgentColExpertExecutorV3(
        requirements_verification_service=verification
    )

    def reject_internal_construction(*_args):
        from requirements_verification import RequirementsVerificationInput

        return RequirementsVerificationInput.model_validate(
            {
                "objective": " ",
                "requirements": [],
                "subject_blocks": [],
            }
        )

    monkeypatch.setattr(
        executor_v3,
        "build_requirements_verification_input",
        reject_internal_construction,
    )

    context = await executor.execute(directive, routing_input)

    assert verification.requests == []
    assert context.expert_result is not None
    assert context.expert_result.status is ExpertStatus.REJECTED_INPUT
    assert context.expert_result.summary is None
    assert context.expert_result.payload is None
    assert context.expert_result.evidence is None
    assert context.actions == ()
    assert context.citations == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "directive",
    (
        AgentColRoutingDirective(route="direct"),
        AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which subject should I assess?",
        ),
    ),
)
async def test_executor_v3_uses_zero_experts_for_direct_and_clarify(
    directive,
) -> None:
    executor_v3 = load_executor_v3()
    verification = RecordingVerificationService()
    executor = executor_v3.AgentColExpertExecutorV3(
        requirements_verification_service=verification
    )
    routing_input = AgentColRoutingInput(
        current_message="Explain the request.",
        available_capabilities=("requirements_verification",),
    )

    context = await executor.execute(directive, routing_input)

    assert context.routing_directive == directive
    assert context.expert_result is None
    assert context.actions == ()
    assert context.citations == ()
    assert verification.requests == []


@pytest.mark.asyncio
async def test_executor_v3_rejects_configuration_mismatch_before_access(
) -> None:
    executor_v3 = load_executor_v3()
    verification = RecordingVerificationService()
    executor = executor_v3.AgentColExpertExecutorV3(
        requirements_verification_service=verification
    )
    routing_input = AgentColRoutingInput(
        current_message="Answer directly.",
        available_capabilities=(
            "source",
            "requirements_verification",
        ),
    )

    with pytest.raises(
        executor_v3.AgentColExpertExecutorV3ConfigurationError
    ):
        await executor.execute(
            AgentColRoutingDirective(route="direct"),
            routing_input,
        )

    assert verification.requests == []


@pytest.mark.asyncio
async def test_executor_v3_does_not_hide_unexpected_verification_error(
) -> None:
    executor_v3 = load_executor_v3()
    directive, routing_input = requirements_routing_case()

    class BrokenVerificationService(RecordingVerificationService):
        async def verify(self, request):
            self.requests.append(request)
            raise RuntimeError("programming defect")

    verification = BrokenVerificationService()
    executor = executor_v3.AgentColExpertExecutorV3(
        requirements_verification_service=verification
    )

    with pytest.raises(RuntimeError, match="programming defect"):
        await executor.execute(directive, routing_input)

    assert len(verification.requests) == 1
