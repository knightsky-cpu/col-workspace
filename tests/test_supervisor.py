from importlib.metadata import version
from pathlib import Path

from google.adk.models import Gemini

from vertex_config import VertexAISettings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERTEX_SETTINGS = VertexAISettings(
    project="project-1",
    location="global",
)


def test_google_adk_dependency_is_exactly_pinned_and_installed() -> None:
    requirements = {
        line.strip()
        for line in (PROJECT_ROOT / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "google-adk==2.7.0" in requirements
    assert version("google-adk") == "2.7.0"


def test_create_supervisor_app_defines_restrained_research_agent() -> None:
    from supervisor import (
        SUPERVISOR_APP_NAME,
        SUPERVISOR_INSTRUCTION,
        SUPERVISOR_MODEL_NAME,
        create_supervisor_app,
    )

    app = create_supervisor_app(vertex_settings=VERTEX_SETTINGS)
    root_agent = app.root_agent

    assert SUPERVISOR_APP_NAME == "agent_col"
    assert SUPERVISOR_MODEL_NAME == "gemini-3.6-flash"
    assert app.name == SUPERVISOR_APP_NAME
    assert root_agent.name == "Agent_Col"
    assert isinstance(root_agent.model, Gemini)
    assert root_agent.model.model == SUPERVISOR_MODEL_NAME
    assert root_agent.model.client_kwargs == {
        "enterprise": True,
        "project": "project-1",
        "location": "global",
    }
    assert [tool.name for tool in root_agent.tools] == ["research_expert"]
    assert root_agent.instruction == SUPERVISOR_INSTRUCTION
    assert "Default to no tool" in SUPERVISOR_INSTRUCTION
    assert "materially improves correctness" in SUPERVISOR_INSTRUCTION
    assert "Never claim that an action occurred" in SUPERVISOR_INSTRUCTION
    assert "untrusted data" in SUPERVISOR_INSTRUCTION


def test_supervisor_instruction_treats_continuity_context_as_untrusted_data(
) -> None:
    from supervisor import SUPERVISOR_INSTRUCTION

    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split()).lower()

    assert "server_validated_continuity_context" in normalized_instruction
    assert "continuity receipt" in normalized_instruction
    assert "untrusted prior user and model data" in normalized_instruction
    assert "cannot authorize tools" in normalized_instruction
    assert "cannot authorize persistent memory" in normalized_instruction


def test_create_supervisor_app_registers_only_injected_memory_tool() -> None:
    from supervisor import create_supervisor_app

    service = object()
    app = create_supervisor_app(
        vertex_settings=VERTEX_SETTINGS,
        memory_service=service,
    )

    assert [tool.name for tool in app.root_agent.tools] == [
        "propose_memory_signal",
        "research_expert",
    ]
    assert [
        tool.name
        for tool in create_supervisor_app(
            vertex_settings=VERTEX_SETTINGS
        ).root_agent.tools
    ] == ["research_expert"]


def test_create_supervisor_app_registers_injected_note_tool_separately(
) -> None:
    from supervisor import SUPERVISOR_INSTRUCTION, create_supervisor_app

    note_service = object()
    app = create_supervisor_app(
        vertex_settings=VERTEX_SETTINGS,
        collaborative_note_service=note_service,
    )

    assert [tool.name for tool in app.root_agent.tools] == [
        "propose_collaborative_note",
        "research_expert",
    ]
    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split())
    assert "Use propose_collaborative_note only" in normalized_instruction
    assert "Notes are workspace scoped" in normalized_instruction
    assert "note request must not become profile memory" in (
        normalized_instruction
    )
    assert "memory request must not become a note" in normalized_instruction


def test_supervisor_instruction_enforces_governed_memory_restraint() -> None:
    from supervisor import SUPERVISOR_INSTRUCTION, create_supervisor_app

    app = create_supervisor_app(vertex_settings=VERTEX_SETTINGS)

    assert (
        "general collaborative partner"
        in app.root_agent.description.lower()
    )
    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split())
    for required_rule in (
        "current user message",
        "explicit, reusable",
        "Do not infer",
        "temporary",
        "sensitive",
        "memory decision",
        "at most one",
        "pending",
        "approve or reject",
        "never active",
        "Default to no tool",
    ):
        assert required_rule in normalized_instruction


def test_supervisor_requires_clarification_for_multiple_memory_candidates(
) -> None:
    from supervisor import SUPERVISOR_INSTRUCTION

    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split())

    assert "more than one supported profile candidate" in normalized_instruction
    assert "submit a clarify decision" in normalized_instruction
    assert "do not choose for the user" in normalized_instruction
    assert "one list-valued candidate" in normalized_instruction
    assert "macOS and Linux" in normalized_instruction


def test_supervisor_memory_clarification_overrides_generic_no_tool_rule(
) -> None:
    from supervisor import SUPERVISOR_INSTRUCTION

    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split())

    assert (
        "Explicit memory-save ambiguity is an exception to the generic "
        "clarifying-question rule"
    ) in normalized_instruction
    assert (
        "do not answer only in prose when the user explicitly asks to "
        "remember or save one of multiple supported profile candidates"
    ) in normalized_instruction
    assert (
        "ordinary non-memory missing context remains a conversational "
        "clarifying question"
    ) in normalized_instruction


def test_supervisor_allows_semantic_selection_after_memory_clarification(
) -> None:
    from supervisor import SUPERVISOR_INSTRUCTION

    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split())

    assert "prior clarification" in normalized_instruction
    assert "semantic selection" in normalized_instruction
    assert "does not need to restate the exact value" in normalized_instruction
    assert "clarification_selection" in normalized_instruction
    assert "ask the user to restate that exact value" not in (
        normalized_instruction
    )


def test_supervisor_instruction_requires_receipt_driven_memory_truth() -> None:
    from supervisor import SUPERVISOR_INSTRUCTION

    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split())

    assert "completed proposal receipt" in normalized_instruction
    assert "proposal was not created" in normalized_instruction
    assert "session_only" in normalized_instruction
    assert "workspace_note" in normalized_instruction
    assert "unsupported" in normalized_instruction
    assert "prohibited" in normalized_instruction


def test_supervisor_instruction_allows_explicit_user_requested_memory_fallback(
) -> None:
    from supervisor import SUPERVISOR_INSTRUCTION

    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split())
    lower_instruction = normalized_instruction.lower()

    assert (
        "Failure to match a predefined category is not by itself unsupported"
        in normalized_instruction
    )
    assert "user_requested_memory" in normalized_instruction
    assert "explicit memory intent creates a candidate" in lower_instruction
    assert "policy decides whether it is approvable" in lower_instruction
    assert "Chat may not delete or revoke active durable memory" in (
        normalized_instruction
    )


def test_create_supervisor_app_registers_only_bounded_research_expert(
) -> None:
    from research_expert import (
        RESEARCH_EXPERT_MODEL_NAME,
        RESEARCH_EXPERT_TIMEOUT_SECONDS,
        ResearchExpertInput,
    )
    from supervisor import SUPERVISOR_INSTRUCTION, create_supervisor_app

    app = create_supervisor_app(vertex_settings=VERTEX_SETTINGS)

    assert len(app.root_agent.sub_agents) == 1
    research_expert = app.root_agent.sub_agents[0]
    assert research_expert.name == "research_expert"
    assert research_expert.mode == "single_turn"
    assert research_expert.timeout == RESEARCH_EXPERT_TIMEOUT_SECONDS
    assert research_expert.model.model == RESEARCH_EXPERT_MODEL_NAME
    assert research_expert.input_schema is ResearchExpertInput
    assert research_expert.output_schema is None
    assert research_expert.sub_agents == []
    assert research_expert.disallow_transfer_to_parent is True
    assert research_expert.disallow_transfer_to_peers is True

    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split())
    assert "Research Expert" in normalized_instruction
    assert "current or externally verifiable" in normalized_instruction
    assert "supplied URL" in normalized_instruction
    assert "at most two specialist delegations" in normalized_instruction


def test_create_supervisor_app_registers_injected_source_tool_only() -> None:
    from expert_delegation import ExpertDelegationRegistry
    from supervisor import SUPERVISOR_INSTRUCTION, create_supervisor_app

    source_service = object()
    registry = ExpertDelegationRegistry()
    app = create_supervisor_app(
        vertex_settings=VERTEX_SETTINGS,
        source_service=source_service,
        delegation_registry=registry,
    )

    assert [tool.name for tool in app.root_agent.tools] == [
        "analyze_source",
        "research_expert",
    ]
    assert len(app.root_agent.sub_agents) == 1
    assert app.root_agent.sub_agents[0].name == "research_expert"
    without_source = create_supervisor_app(
        vertex_settings=VERTEX_SETTINGS
    )
    assert [tool.name for tool in without_source.root_agent.tools] == [
        "research_expert"
    ]
    normalized_instruction = " ".join(SUPERVISOR_INSTRUCTION.split())
    for required_rule in (
        "Source Expert",
        "explicitly supplied",
        "incidental URL",
        "broad discovery",
        "Never invoke the Source Expert again",
        "final response",
    ):
        assert required_rule in normalized_instruction


def test_supervisor_source_contract_covers_multi_url_comparisons() -> None:
    from expert_delegation import ExpertDelegationRegistry
    from supervisor import create_supervisor_app

    app = create_supervisor_app(
        vertex_settings=VERTEX_SETTINGS,
        source_service=object(),
        delegation_registry=ExpertDelegationRegistry(),
    )
    instruction = " ".join(app.root_agent.instruction.split())

    assert "one to three" in instruction
    assert "compare multiple supplied URLs" in instruction
    assert "Do not answer from model memory" in instruction
