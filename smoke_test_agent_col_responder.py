from agent_col_responder import create_responder_app
from agent_col_responder_context import (
    AgentColResponderContext,
    build_agent_col_responder_model_context,
)
from agent_col_routing import AgentColRoutingDirective
from vertex_config import VertexAISettings


_SUCCESS = (
    "r3.3a responder-boundary pass tools=memory-only "
    "subagents=0 routes=direct,clarify"
)


def run_smoke() -> str:
    """Verify the responder-only structural boundary without external I/O."""
    settings = VertexAISettings(
        project="responder-boundary-smoke",
        location="global",
    )
    direct_app = create_responder_app(vertex_settings=settings)
    memory_app = create_responder_app(
        vertex_settings=settings,
        memory_service=object(),
    )

    if direct_app.root_agent.tools or direct_app.root_agent.sub_agents:
        raise RuntimeError("Responder cognitive catalog is not empty.")
    if tuple(tool.name for tool in memory_app.root_agent.tools) != (
        "propose_memory_signal",
    ):
        raise RuntimeError("Responder memory catalog is invalid.")
    if memory_app.root_agent.sub_agents:
        raise RuntimeError("Responder sub-agent catalog is not empty.")

    contexts = (
        AgentColResponderContext(
            routing_directive=AgentColRoutingDirective(route="direct")
        ),
        AgentColResponderContext(
            routing_directive=AgentColRoutingDirective(
                route="clarify",
                clarifying_question="Which source should I analyze?",
            )
        ),
    )
    rendered = tuple(
        build_agent_col_responder_model_context(context)
        for context in contexts
    )
    if any(
        content.role != "user"
        or content.parts is None
        or len(content.parts) != 1
        for content in rendered
    ):
        raise RuntimeError("Responder model context is invalid.")
    return _SUCCESS


def main() -> None:
    print(run_smoke())


if __name__ == "__main__":
    main()
