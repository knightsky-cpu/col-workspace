import importlib
import asyncio
from types import SimpleNamespace

import pytest
from google.genai import types

from agent_col_numeric_projection import project_routing_numeric_candidates
from agent_col_routing import project_routing_url_candidates
from agent_col_routing_v3 import AgentColRoutingDirective
from agent_col_text_projection import project_routing_text_blocks


VALID_REQUIREMENTS_RESPONSE = (
    '{"schema_version":"3.0","route":"requirements_verification",'
    '"requirements_verification_intent":{'
    '"objective":"Compare every requirement with the supplied draft.",'
    '"requirement_block_ids":["block-3","block-4"],'
    '"subject_block_ids":["block-6"],"constraints":[]}}'
)


class FakeRoutingModels:
    def __init__(
        self,
        *,
        response_text: object = VALID_REQUIREMENTS_RESPONSE,
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


def requirements_routing_input() -> object:
    from agent_col_routing_v3 import AgentColRoutingInput

    message = (
        "Compare the subject against every requirement.\n\n"
        "Requirements:\n"
        "- Include one practical example.\n"
        "- State a material limitation.\n\n"
        "Subject:\n"
        "The response includes one practical example."
    )
    text_projection = project_routing_text_blocks(message)
    numeric_projection = project_routing_numeric_candidates(message)
    return AgentColRoutingInput(
        current_message=message,
        candidate_urls=project_routing_url_candidates(message, ()),
        numeric_candidates=numeric_projection.candidates,
        numeric_projection_incomplete=(
            numeric_projection.numeric_projection_incomplete
        ),
        text_block_candidates=text_projection.candidates,
        text_projection_incomplete=text_projection.text_projection_incomplete,
        available_capabilities=(
            "source",
            "research",
            "computation",
            "requirements_verification",
        ),
    )


def load_routing_provider_v3():
    try:
        return importlib.import_module("agent_col_routing_provider_v3")
    except ModuleNotFoundError:
        pytest.fail("agent_col_routing_provider_v3 has not been implemented")


def collect_schema_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for child in value.values()
            for key in collect_schema_keys(child)
        }
    if isinstance(value, list):
        return {
            key for child in value for key in collect_schema_keys(child)
        }
    return set()


def test_v3_provider_schema_exposes_six_routes_and_requirements_intent() -> None:
    provider = load_routing_provider_v3()

    schema = provider.build_agent_col_routing_v3_response_schema()

    assert schema["$defs"]["AgentColRoute"]["enum"] == [
        "direct",
        "clarify",
        "source",
        "research",
        "computation",
        "requirements_verification",
    ]
    assert schema["properties"]["schema_version"]["enum"] == ["3.0"]
    assert schema["$defs"]["RequirementsVerificationRoutingIntent"][
        "additionalProperties"
    ] is False
    assert "requirements_verification_intent" in schema["properties"]


def test_v3_provider_schema_relaxes_only_provider_unsupported_constraints() -> None:
    provider = load_routing_provider_v3()
    canonical = AgentColRoutingDirective.model_json_schema()

    provider_schema = provider.build_agent_col_routing_v3_response_schema()

    canonical_keys = collect_schema_keys(canonical)
    provider_keys = collect_schema_keys(provider_schema)
    assert {"minLength", "maxLength", "pattern", "maxItems"} <= canonical_keys
    assert not {"minLength", "maxLength", "pattern", "maxItems"} & provider_keys


def test_v3_provider_schema_marks_computation_task_text_numeric_free() -> None:
    provider = load_routing_provider_v3()

    schema = provider.build_agent_col_routing_v3_response_schema()
    computation = schema["$defs"]["ComputationRoutingIntent"]["properties"]
    objective_description = computation["objective"]["description"].lower()
    constraint_description = computation["constraints"]["items"][
        "description"
    ].lower()

    for description in (objective_description, constraint_description):
        assert "no digits" in description
        assert "numeric candidate id" in description


@pytest.mark.asyncio
async def test_v3_request_uses_tool_free_structured_vertex_contract() -> None:
    provider = load_routing_provider_v3()
    models = FakeRoutingModels()
    routing_input = requirements_routing_input()

    directive = await provider.request_agent_col_routing_v3_directive(
        fake_client(models),
        routing_input,
    )

    assert directive.route == "requirements_verification"
    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == provider.AGENT_COL_ROUTING_V3_MODEL_NAME == (
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
    assert config.system_instruction == provider.AGENT_COL_ROUTING_V3_SYSTEM_INSTRUCTION
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == (
        provider.build_agent_col_routing_v3_response_schema()
    )
    assert config.response_schema is None
    assert config.temperature == 0
    assert config.max_output_tokens == 2_048
    assert config.thinking_config == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.MINIMAL,
    )
    assert not config.tools


@pytest.mark.asyncio
async def test_v3_request_sends_numeric_free_computation_task_text_contract(
) -> None:
    provider = load_routing_provider_v3()
    models = FakeRoutingModels()

    await provider.request_agent_col_routing_v3_directive(
        fake_client(models),
        requirements_routing_input(),
    )

    config = models.calls[0]["config"]
    instruction = " ".join(config.system_instruction.split())
    assert (
        "Computation objective and constraints must contain no digits or "
        "numeric-like syntax."
    ) in instruction
    assert (
        "Select every operand and precision value only through numeric "
        "candidate ID fields."
    ) in instruction
    assert "Computation shape example only" in instruction
    assert '"objective":"Calculate the requested statistic."' in instruction
    assert '"digits_numeric_id":"number-3"' in instruction
    assert '"constraints":[]' in instruction


def test_v3_instruction_preserves_restraint_and_selection_rules() -> None:
    provider = load_routing_provider_v3()
    instruction = " ".join(
        provider.AGENT_COL_ROUTING_V3_SYSTEM_INSTRUCTION.split()
    )

    for expected in (
        "Choose only a capability listed in available_capabilities.",
        "At most one expert capability may be selected.",
        "Multi-capability requests choose clarify",
        "explicit comparison objective",
        "Select only provided block IDs",
        "keep requirement and subject IDs disjoint",
        "Never copy, rewrite, summarize, infer, or emit requirement or subject text.",
        "incomplete text projection",
        "retrieval-plus-verification requests",
        "general requirements advice",
        "explicit no-expert requests",
        "Never call tools",
    ):
        assert expected in instruction


@pytest.mark.asyncio
async def test_v3_request_classifies_provider_failure_without_content_leak(
    caplog,
) -> None:
    provider = load_routing_provider_v3()

    with pytest.raises(provider.AgentColRoutingV3ProviderError) as error:
        await provider.request_agent_col_routing_v3_directive(
            fake_client(
                FakeRoutingModels(error=RuntimeError("private-provider-payload"))
            ),
            requirements_routing_input(),
        )

    assert str(error.value) == "Routing v3 provider request failed."
    assert "private" not in str(error.value)
    assert "private" not in repr(error.value)
    assert "private-provider-payload" not in caplog.text


@pytest.mark.asyncio
async def test_v3_request_classifies_timeout_separately() -> None:
    provider = load_routing_provider_v3()

    with pytest.raises(provider.AgentColRoutingV3ProviderTimeoutError):
        await provider.request_agent_col_routing_v3_directive(
            fake_client(FakeRoutingModels(delay=0.02)),
            requirements_routing_input(),
            timeout_seconds=0.001,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_text", "expected_reason"),
    (
        ("", "missing_response_text"),
        (None, "missing_response_text"),
        ("not-json", "invalid_json"),
        ('{"schema_version":"2.0","route":"direct"}', "schema_validation_failed"),
        (
            '{"schema_version":"3.0","route":"direct",'
            '"private_reasoning":"secret"}',
            "schema_validation_failed",
        ),
        (
            '{"schema_version":"3.0","route":"requirements_verification",'
            '"requirements_verification_intent":{'
            '"objective":"Compare the supplied material.",'
            '"requirement_block_ids":["block-3"],'
            '"subject_block_ids":["block-6"],"constraints":[]},'
            '"source_intent":{"objective":"Analyze a page.",'
            '"selected_url_ids":["url-1"],"constraints":[]}}',
            "schema_validation_failed",
        ),
        (
            '{"schema_version":"3.0","route":"requirements_verification",'
            '"requirements_verification_intent":{'
            '"objective":"Compare the supplied material.",'
            '"requirement_block_ids":["block-3","block-3"],'
            '"subject_block_ids":["block-6"],"constraints":[]}}',
            "schema_validation_failed",
        ),
    ),
)
async def test_v3_request_classifies_malformed_output_without_content_leak(
    response_text: object,
    expected_reason: str,
) -> None:
    provider = load_routing_provider_v3()

    with pytest.raises(provider.AgentColRoutingV3ProviderOutputError) as error:
        await provider.request_agent_col_routing_v3_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            requirements_routing_input(),
        )

    assert str(error.value) == (
        "Routing v3 provider returned invalid structured output."
    )
    assert error.value.reason == expected_reason
    assert "secret" not in str(error.value)
    assert "secret" not in repr(error.value)
    if expected_reason != "missing_response_text":
        assert error.value.__cause__ is None
        assert error.value.__context__ is None
        assert error.value.__suppress_context__ is True


@pytest.mark.asyncio
async def test_v3_request_preserves_exact_input_mismatch_classification() -> None:
    provider = load_routing_provider_v3()
    from agent_col_routing_v3 import RoutingDirectiveInputError

    response_text = VALID_REQUIREMENTS_RESPONSE.replace(
        '"subject_block_ids":["block-6"]',
        '"subject_block_ids":["block-7"]',
    )

    with pytest.raises(RoutingDirectiveInputError) as error:
        await provider.request_agent_col_routing_v3_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            requirements_routing_input(),
        )

    assert str(error.value) == "Routing directive is incompatible with its input."


@pytest.mark.asyncio
async def test_v3_request_subclassifies_route_payload_mismatch() -> None:
    provider = load_routing_provider_v3()

    with pytest.raises(provider.AgentColRoutingV3ProviderOutputError) as error:
        await provider.request_agent_col_routing_v3_directive(
            fake_client(
                FakeRoutingModels(
                    response_text='{"schema_version":"3.0","route":"clarify"}'
                )
            ),
            requirements_routing_input(),
        )

    assert error.value.reason == "schema_validation_failed"
    assert error.value.schema_failure_reason == "route_payload_mismatch"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_text", "expected_field", "expected_constraint"),
    (
        (
            '{"schema_version":"2.0","route":"direct"}',
            "schema_version",
            "literal_error",
        ),
        (
            '{"schema_version":"3.0","route":"unsupported"}',
            "route",
            "enum",
        ),
        (
            '{"schema_version":"3.0","route":"requirements_verification",'
            '"requirements_verification_intent":{"objective":"",'
            '"requirement_block_ids":["block-3"],'
            '"subject_block_ids":["block-6"],"constraints":[]}}',
            "requirements_verification_intent",
            "string_too_short",
        ),
    ),
)
async def test_v3_request_locates_safe_field_constraint_failure(
    response_text: str,
    expected_field: str,
    expected_constraint: str,
) -> None:
    provider = load_routing_provider_v3()

    with pytest.raises(provider.AgentColRoutingV3ProviderOutputError) as error:
        await provider.request_agent_col_routing_v3_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            requirements_routing_input(),
        )

    assert error.value.schema_failure_reason == "field_constraint_failed"
    assert error.value.schema_failure_field == expected_field
    assert error.value.schema_failure_constraint == expected_constraint
    assert response_text not in repr(error.value)


@pytest.mark.asyncio
async def test_v3_request_subclassifies_requirements_intent_invariant() -> None:
    provider = load_routing_provider_v3()
    response_text = (
        '{"schema_version":"3.0","route":"requirements_verification",'
        '"requirements_verification_intent":{'
        '"objective":"Compare the supplied material.",'
        '"requirement_block_ids":["block-3","block-3"],'
        '"subject_block_ids":["block-6"],"constraints":[]}}'
    )

    with pytest.raises(provider.AgentColRoutingV3ProviderOutputError) as error:
        await provider.request_agent_col_routing_v3_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            requirements_routing_input(),
        )

    assert error.value.schema_failure_reason == "intent_invariant_failed"


@pytest.mark.asyncio
async def test_v3_request_rejects_nonpositive_timeout_before_provider_access() -> None:
    provider = load_routing_provider_v3()
    models = FakeRoutingModels()

    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        await provider.request_agent_col_routing_v3_directive(
            fake_client(models),
            requirements_routing_input(),
            timeout_seconds=0,
        )

    assert models.calls == []
