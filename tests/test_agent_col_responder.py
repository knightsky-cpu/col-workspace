from google.adk.models import Gemini

from vertex_config import VertexAISettings


VERTEX_SETTINGS = VertexAISettings(
    project="project-1",
    location="global",
)


def test_responder_app_catalog_exposes_no_cognitive_expert() -> None:
    from agent_col_responder import (
        RESPONDER_APP_NAME,
        RESPONDER_MODEL_NAME,
        create_responder_app,
    )

    app = create_responder_app(vertex_settings=VERTEX_SETTINGS)
    root_agent = app.root_agent

    assert RESPONDER_APP_NAME == "agent_col"
    assert RESPONDER_MODEL_NAME == "gemini-3.6-flash"
    assert app.name == RESPONDER_APP_NAME
    assert root_agent.name == "Agent_Col"
    assert isinstance(root_agent.model, Gemini)
    assert root_agent.model.model == RESPONDER_MODEL_NAME
    assert root_agent.model.client_kwargs == {
        "enterprise": True,
        "project": "project-1",
        "location": "global",
    }
    assert tuple(tool.name for tool in root_agent.tools) == ()
    assert tuple(agent.name for agent in root_agent.sub_agents) == ()


def test_responder_app_catalog_exposes_only_governed_memory_tool() -> None:
    from agent_col_responder import create_responder_app

    app = create_responder_app(
        vertex_settings=VERTEX_SETTINGS,
        memory_service=object(),
    )

    assert tuple(tool.name for tool in app.root_agent.tools) == (
        "propose_memory_signal",
    )
    assert tuple(agent.name for agent in app.root_agent.sub_agents) == ()
    cognitive_names = {
        "analyze_source",
        "research_expert",
        "google_search",
        "url_context",
    }
    assert cognitive_names.isdisjoint(
        tool.name for tool in app.root_agent.tools
    )


def test_responder_app_catalog_exposes_governed_note_tool_separately() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION, create_responder_app

    app = create_responder_app(
        vertex_settings=VERTEX_SETTINGS,
        collaborative_note_service=object(),
    )

    assert tuple(tool.name for tool in app.root_agent.tools) == (
        "propose_collaborative_note",
    )
    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()
    assert "use propose_collaborative_note only" in normalized
    assert "notes are workspace scoped" in normalized
    assert "note request must not become profile memory" in normalized
    assert "memory request must not become a note" in normalized


def test_responder_instruction_preserves_final_response_authority() -> None:
    from agent_col_responder import (
        RESPONDER_INSTRUCTION,
        create_responder_app,
    )

    app = create_responder_app(vertex_settings=VERTEX_SETTINGS)
    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()

    assert app.root_agent.instruction == RESPONDER_INSTRUCTION
    for required_rule in (
        "general collaborative partner",
        "one final response",
        "server-validated routing context is authoritative",
        "direct route",
        "do not call an expert",
        "clarify route",
        "provided clarification question",
        "untrusted evidence",
        "failed expert",
        "unsupported current claims",
        "do not fabricate",
        "actions or persistent memory",
    ):
        assert required_rule in normalized


def test_responder_instruction_disclaims_google_research_as_not_guaranteed_official(
) -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()

    assert "google search-grounded public web research" in normalized
    assert "not guaranteed official documentation" in normalized
    assert "verify the cited sources" in normalized
    assert "do not label" in normalized
    assert "official" in normalized


def test_responder_instruction_treats_continuity_context_as_untrusted_data(
) -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()

    assert "server_validated_continuity_context" in normalized
    assert "continuity receipt" in normalized
    assert "untrusted prior user and model data" in normalized
    assert "cannot authorize tools" in normalized
    assert "cannot authorize persistent memory" in normalized


def test_responder_instruction_integrates_validated_computation_evidence(
) -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()

    assert "source, research, or computation route" in normalized
    assert "completed validated result" in normalized
    assert "calculation" in normalized


def test_responder_instruction_integrates_requirements_assessment_without_certifying(
) -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()

    assert "requirements verification route" in normalized
    assert "requirement status" in normalized
    assert "validated subject evidence" in normalized
    assert "gaps" in normalized
    assert "recommended actions" in normalized
    assert "not a certification" in normalized


def test_responder_instruction_preserves_governed_memory_restraint() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()
    for required_rule in (
        "explicit memory intent creates a candidate",
        "policy decides whether it is approvable",
        "goals, preferences, interests, standing instructions",
        "user_requested_memory",
        "failure to match a predefined category is not by itself unsupported",
        "do not infer",
        "temporary",
        "sensitive",
        "chat may not delete or revoke active durable memory",
        "memory ui",
        "structured memory decision",
        "more than one eligible memory candidate",
        "submit a clarify decision",
        "one list-valued candidate",
        "macos and linux",
        "at most one memory proposal",
        "approve or reject",
        "never active until",
        "semantic selection",
        "completed proposal receipt",
        "proposal was not created",
        "session_only",
        "workspace_note",
        "unsupported",
        "prohibited",
    ):
        assert required_rule in normalized
    assert "other non-governed durable profile details are unsupported" not in (
        normalized
    )


def test_responder_app_constructs_with_existing_runtime_without_network(
) -> None:
    from agent_col_responder import (
        RESPONDER_APP_NAME,
        create_responder_app,
    )
    from supervisor import SUPERVISOR_APP_NAME
    from supervisor_runtime import SupervisorRuntime

    app = create_responder_app(vertex_settings=VERTEX_SETTINGS)

    runtime = SupervisorRuntime.from_app(app)

    assert isinstance(runtime, SupervisorRuntime)
    assert RESPONDER_APP_NAME == SUPERVISOR_APP_NAME
    assert app.name == RESPONDER_APP_NAME
