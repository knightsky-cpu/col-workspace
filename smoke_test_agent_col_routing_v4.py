"""Live compatibility check for the parallel artifact routing v4 boundary."""

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence

from dotenv import load_dotenv
from google import genai

from agent_col_routing_provider_v4 import (
    AgentColRoutingV4ProviderError,
    AgentColRoutingV4ProviderOutputError,
    AgentColRoutingV4ProviderTimeoutError,
    request_agent_col_routing_v4_directive,
)
from agent_col_routing_v4 import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
    RoutingDirectiveInputError,
)
from vertex_config import VertexAIConfigurationError, load_vertex_ai_settings


OutputWriter = Callable[[str], None]
DirectiveRequester = Callable[
    [AgentColRoutingInput],
    Awaitable[AgentColRoutingDirective],
]


def build_artifact_routing_input() -> AgentColRoutingInput:
    """Build one substantial, bounded blueprint-creation routing case."""
    message = (
        "Create a structured blueprint from this complete brief. "
        "Goal: build a cross-domain study partner that helps learners plan "
        "sessions and reflect on progress. Users: university students and "
        "independent learners. Required behavior: ask clarifying questions, "
        "save only explicitly approved collaboration preferences, retrieve "
        "those preferences in later sessions, explain each adaptation, and "
        "let users revoke or delete memory. Scope: conversational planning, "
        "preference approval, cross-session adaptation, progress milestones, "
        "and audit receipts. Exclude: health advice, sensitive personal data, "
        "autonomous grading, and hidden profiling. Deliverable: a locally "
        "validated FastAPI service backed by Firestore with testable "
        "milestones and a lightweight browser workspace."
    )
    return AgentColRoutingInput(
        current_message=message,
        available_capabilities=(
            "source",
            "research",
            "computation",
            "requirements_verification",
        ),
        artifact_creation_available=True,
        structured_decision_present=False,
    )


async def run_artifact_routing_compatibility(
    *,
    request_directive: DirectiveRequester,
    output: OutputWriter,
) -> int:
    """Run one metadata-only artifact-routing compatibility case."""
    try:
        directive = await request_directive(build_artifact_routing_input())
    except AgentColRoutingV4ProviderTimeoutError:
        output("agent-col-routing-v4 timeout_error")
        return 2
    except AgentColRoutingV4ProviderOutputError as exc:
        classification = exc.schema_failure_reason or exc.reason
        output(f"agent-col-routing-v4 model_output_error:{classification}")
        return 2
    except AgentColRoutingV4ProviderError:
        output("agent-col-routing-v4 provider_error")
        return 2
    except RoutingDirectiveInputError:
        output("agent-col-routing-v4 directive_input_error")
        return 2

    if directive.route is not AgentColRoute.ARTIFACT:
        output(
            "agent-col-routing-v4 expected=artifact "
            f"actual={directive.route} route_mismatch"
        )
        return 1
    intent = directive.artifact_intent
    if intent is None or intent.operation != "create_blueprint":
        output("agent-col-routing-v4 artifact_intent_mismatch")
        return 1
    output(
        "agent-col-routing-v4 route=artifact "
        "operation=create_blueprint pass"
    )
    return 0


async def run_live_artifact_routing_compatibility(
    *,
    output: OutputWriter,
    environment: Mapping[str, str] | None = None,
    client_factory: Callable[..., genai.Client] = genai.Client,
) -> int:
    """Run the bounded compatibility case against configured Vertex AI."""
    load_dotenv()
    try:
        settings = load_vertex_ai_settings(
            environment if environment is not None else os.environ
        )
    except VertexAIConfigurationError:
        output("agent-col-routing-v4 configuration_error")
        return 2

    client = client_factory(**settings.client_kwargs())
    try:
        async def request(
            routing_input: AgentColRoutingInput,
        ) -> AgentColRoutingDirective:
            return await request_agent_col_routing_v4_directive(
                client,
                routing_input,
            )

        return await run_artifact_routing_compatibility(
            request_directive=request,
            output=output,
        )
    finally:
        try:
            await client.aio.aclose()
        finally:
            client.close()


def main(_argv: Sequence[str] | None = None) -> int:
    return asyncio.run(
        run_live_artifact_routing_compatibility(output=print)
    )


if __name__ == "__main__":
    raise SystemExit(main())
