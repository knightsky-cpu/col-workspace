import asyncio
import json
from types import SimpleNamespace

import pytest
from google.genai import types

from agent_col_numeric_projection import project_routing_numeric_candidates


class FakeRoutingModels:
    def __init__(
        self,
        *,
        response_text: str = (
            '{"schema_version":"2.0","route":"computation",'
            '"computation_intent":{'
            '"objective":"Calculate descriptive statistics.",'
            '"scalar_inputs":[],"series_inputs":[{'
            '"name":"values","numeric_ids":["number-1","number-2"]}],'
            '"precision":null,"constraints":[]}}'
        ),
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.response_text = response_text
        self.error = error
        self.delay = delay
        self.calls: list[dict[str, object]] = []

    async def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.response_text)


def fake_client(models: FakeRoutingModels) -> SimpleNamespace:
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def computation_routing_input() -> object:
    from agent_col_routing_v2 import AgentColRoutingInput

    message = "Calculate the mean of 12 and 15."
    projection = project_routing_numeric_candidates(message)
    return AgentColRoutingInput(
        current_message=message,
        numeric_candidates=projection.candidates,
        available_capabilities=("source", "research", "computation"),
    )


def test_v2_provider_schema_preserves_routes_and_removes_local_constraints(
) -> None:
    from agent_col_routing_provider_v2 import (
        build_agent_col_routing_v2_response_schema,
    )
    from agent_col_routing_v2 import AgentColRoutingDirective

    schema = build_agent_col_routing_v2_response_schema()
    serialized = json.dumps(schema)
    canonical = json.dumps(AgentColRoutingDirective.model_json_schema())

    assert schema["additionalProperties"] is False
    assert schema["$defs"]["AgentColRoute"]["enum"] == [
        "direct",
        "clarify",
        "source",
        "research",
        "computation",
    ]
    assert schema["$defs"]["ComputationRoutingIntent"][
        "additionalProperties"
    ] is False
    assert "computation_intent" in schema["properties"]
    version_schema = schema["properties"]["schema_version"]
    assert version_schema["enum"] == ["2.0"]
    assert "const" not in version_schema
    assert "pattern" in canonical
    assert "maxItems" in canonical
    for local_keyword in ("minLength", "maxLength", "pattern", "maxItems"):
        assert local_keyword not in serialized


@pytest.mark.asyncio
async def test_v2_request_uses_tool_free_structured_vertex_contract() -> None:
    from agent_col_routing_provider_v2 import (
        AGENT_COL_ROUTING_V2_MODEL_NAME,
        AGENT_COL_ROUTING_V2_SYSTEM_INSTRUCTION,
        build_agent_col_routing_v2_response_schema,
        request_agent_col_routing_v2_directive,
    )

    models = FakeRoutingModels()
    routing_input = computation_routing_input()

    directive = await request_agent_col_routing_v2_directive(
        fake_client(models),
        routing_input,
    )

    assert directive.route == "computation"
    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == AGENT_COL_ROUTING_V2_MODEL_NAME == (
        "gemini-3.6-flash"
    )
    content = call["contents"][0]
    assert isinstance(content, types.Content)
    prompt = content.parts[0].text
    assert prompt is not None
    assert "[UNTRUSTED_ROUTING_INPUT]" in prompt
    assert routing_input.model_dump_json() in prompt
    assert "[/UNTRUSTED_ROUTING_INPUT]" in prompt
    config = call["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.system_instruction == AGENT_COL_ROUTING_V2_SYSTEM_INSTRUCTION
    assert config.response_mime_type == "application/json"
    assert (
        config.response_json_schema
        == build_agent_col_routing_v2_response_schema()
    )
    assert config.response_schema is None
    assert config.temperature == 0
    assert config.max_output_tokens == 1_024
    assert config.thinking_config == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.MINIMAL,
    )
    assert not config.tools


@pytest.mark.asyncio
async def test_v2_request_classifies_provider_failure_without_content_leak(
) -> None:
    from agent_col_routing_provider_v2 import (
        AgentColRoutingV2ProviderError,
        request_agent_col_routing_v2_directive,
    )

    with pytest.raises(AgentColRoutingV2ProviderError) as error:
        await request_agent_col_routing_v2_directive(
            fake_client(
                FakeRoutingModels(
                    error=RuntimeError("private-provider-payload")
                )
            ),
            computation_routing_input(),
        )

    assert str(error.value) == "Routing v2 provider request failed."
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_v2_request_classifies_timeout_separately() -> None:
    from agent_col_routing_provider_v2 import (
        AgentColRoutingV2ProviderTimeoutError,
        request_agent_col_routing_v2_directive,
    )

    with pytest.raises(AgentColRoutingV2ProviderTimeoutError):
        await request_agent_col_routing_v2_directive(
            fake_client(FakeRoutingModels(delay=0.02)),
            computation_routing_input(),
            timeout_seconds=0.001,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_text",
    (
        "",
        "not-json",
        '{"schema_version":"1.0","route":"direct"}',
        '{"schema_version":"2.0","route":"direct","private_reasoning":"secret"}',
        (
            '{"schema_version":"2.0","route":"computation",'
            '"computation_intent":{'
            '"objective":"Calculate descriptive statistics.",'
            '"values":[12,15],"scalar_inputs":[],"series_inputs":[{'
            '"name":"values","numeric_ids":["number-1","number-2"]}],'
            '"precision":null,"constraints":[]}}'
        ),
    ),
)
async def test_v2_request_classifies_malformed_output_without_content_leak(
    response_text: str,
) -> None:
    from agent_col_routing_provider_v2 import (
        AgentColRoutingV2ProviderOutputError,
        request_agent_col_routing_v2_directive,
    )

    with pytest.raises(AgentColRoutingV2ProviderOutputError) as error:
        await request_agent_col_routing_v2_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            computation_routing_input(),
        )

    assert str(error.value) == (
        "Routing v2 provider returned invalid structured output."
    )
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_v2_request_preserves_exact_input_mismatch_classification(
) -> None:
    from agent_col_routing_provider_v2 import (
        request_agent_col_routing_v2_directive,
    )
    from agent_col_routing_v2 import RoutingDirectiveInputError

    response_text = (
        '{"schema_version":"2.0","route":"computation",'
        '"computation_intent":{'
        '"objective":"Calculate descriptive statistics.",'
        '"scalar_inputs":[],"series_inputs":[{'
        '"name":"values","numeric_ids":["number-1","number-3"]}],'
        '"precision":null,"constraints":[]}}'
    )

    with pytest.raises(RoutingDirectiveInputError) as error:
        await request_agent_col_routing_v2_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            computation_routing_input(),
        )

    assert str(error.value) == (
        "Routing directive is incompatible with its input."
    )


@pytest.mark.asyncio
async def test_v2_request_rejects_nonpositive_timeout_before_provider_access(
) -> None:
    from agent_col_routing_provider_v2 import (
        request_agent_col_routing_v2_directive,
    )

    models = FakeRoutingModels()

    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        await request_agent_col_routing_v2_directive(
            fake_client(models),
            computation_routing_input(),
            timeout_seconds=0,
        )

    assert models.calls == []
