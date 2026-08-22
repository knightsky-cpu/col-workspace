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


def test_responder_instruction_integrates_validated_computation_evidence(
) -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()

    assert "source, research, or computation route" in normalized
    assert "completed validated result" in normalized
    assert "calculation" in normalized


def test_responder_instruction_preserves_governed_memory_restraint() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()
    for required_rule in (
        "explicit, reusable collaboration preference",
        "allowed light identity detail",
        "do not infer",
        "temporary",
        "sensitive",
        "structured memory decision",
        "more than one eligible memory candidate",
        "do not call propose_memory_signal",
        "at most one memory proposal",
        "approve or reject",
        "never active until",
    ):
        assert required_rule in normalized


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
