import asyncio
import json
from types import SimpleNamespace

import pytest
from google.genai import types


class FakeRoutingModels:
    def __init__(
        self,
        *,
        response_text: str = (
            '{"schema_version":"1.0","route":"source",'
            '"source_intent":{"objective":"Compare both pages.",'
            '"selected_url_ids":["url-1"],"constraints":[]}}'
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


def source_routing_input() -> object:
    from agent_col_routing import AgentColRoutingInput

    return AgentColRoutingInput(
        current_message=(
            "Compare the supplied public pages using only page evidence."
        ),
        candidate_urls=(
            {
                "candidate_id": "url-1",
                "url": "https://example.com/one",
                "source": "current_message",
            },
        ),
        available_capabilities=("source", "research"),
    )


def test_provider_schema_preserves_directives_and_removes_local_constraints(
) -> None:
    from agent_col_routing_provider import (
        build_agent_col_routing_response_schema,
    )

    schema = build_agent_col_routing_response_schema()
    serialized = json.dumps(schema)

    assert schema["additionalProperties"] is False
    assert schema["$defs"]["AgentColRoute"]["enum"] == [
        "direct",
        "clarify",
        "source",
        "research",
    ]
    assert schema["$defs"]["SourceRoutingIntent"][
        "additionalProperties"
    ] is False
    assert schema["$defs"]["ResearchRoutingIntent"][
        "additionalProperties"
    ] is False
    assert "source_intent" in schema["properties"]
    assert "research_intent" in schema["properties"]
    version_schema = schema["properties"]["schema_version"]
    assert version_schema["enum"] == ["1.0"]
    assert "const" not in version_schema
    for local_keyword in ("minLength", "maxLength", "pattern", "maxItems"):
        assert local_keyword not in serialized


@pytest.mark.asyncio
async def test_request_uses_tool_free_structured_vertex_contract() -> None:
    from agent_col_routing_provider import (
        AGENT_COL_ROUTING_MODEL_NAME,
        build_agent_col_routing_response_schema,
        request_agent_col_routing_directive,
    )

    models = FakeRoutingModels()
    routing_input = source_routing_input()

    directive = await request_agent_col_routing_directive(
        fake_client(models),
        routing_input,
    )

    assert directive.route == "source"
    assert directive.source_intent is not None
    assert directive.source_intent.selected_url_ids == ("url-1",)
    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == AGENT_COL_ROUTING_MODEL_NAME == (
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
    assert config.response_mime_type == "application/json"
    assert (
        config.response_json_schema
        == build_agent_col_routing_response_schema()
    )
    assert config.response_schema is None
    assert config.temperature == 0
    assert config.max_output_tokens == 256
    assert config.thinking_config == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.MINIMAL,
    )
    assert not config.tools


@pytest.mark.asyncio
async def test_request_classifies_provider_failure_without_content_leak(
) -> None:
    from agent_col_routing_provider import (
        AgentColRoutingProviderError,
        request_agent_col_routing_directive,
    )

    with pytest.raises(AgentColRoutingProviderError) as error:
        await request_agent_col_routing_directive(
            fake_client(
                FakeRoutingModels(
                    error=RuntimeError("private-provider-payload")
                )
            ),
            source_routing_input(),
        )

    assert str(error.value) == "Routing provider request failed."
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_request_classifies_timeout_separately() -> None:
    from agent_col_routing_provider import (
        AgentColRoutingProviderTimeoutError,
        request_agent_col_routing_directive,
    )

    with pytest.raises(AgentColRoutingProviderTimeoutError):
        await request_agent_col_routing_directive(
            fake_client(FakeRoutingModels(delay=0.02)),
            source_routing_input(),
            timeout_seconds=0.001,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_text",
    (
        "",
        "not-json",
        '{"route":"source"}',
        '{"schema_version":"1.0.0","route":"direct"}',
        '{"route":"direct","private_reasoning":"secret"}',
    ),
)
async def test_request_classifies_malformed_output_without_content_leak(
    response_text: str,
) -> None:
    from agent_col_routing_provider import (
        AgentColRoutingProviderOutputError,
        request_agent_col_routing_directive,
    )

    with pytest.raises(AgentColRoutingProviderOutputError) as error:
        await request_agent_col_routing_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            source_routing_input(),
        )

    assert str(error.value) == (
        "Routing provider returned invalid structured output."
    )
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_request_preserves_exact_input_mismatch_classification() -> None:
    from agent_col_routing import RoutingDirectiveInputError
    from agent_col_routing_provider import request_agent_col_routing_directive

    response_text = (
        '{"schema_version":"1.0","route":"source",'
        '"source_intent":{"objective":"Analyze another page.",'
        '"selected_url_ids":["url-2"],"constraints":[]}}'
    )

    with pytest.raises(RoutingDirectiveInputError) as error:
        await request_agent_col_routing_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            source_routing_input(),
        )

    assert str(error.value) == (
        "Routing directive is incompatible with its input."
    )


@pytest.mark.asyncio
async def test_request_rejects_nonpositive_timeout_before_provider_access(
) -> None:
    from agent_col_routing_provider import request_agent_col_routing_directive

    models = FakeRoutingModels()

    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        await request_agent_col_routing_directive(
            fake_client(models),
            source_routing_input(),
            timeout_seconds=0,
        )

    assert models.calls == []
