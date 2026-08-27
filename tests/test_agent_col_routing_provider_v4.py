import asyncio
import importlib
from types import SimpleNamespace

import pytest
from google.genai import types


VALID_ARTIFACT_RESPONSE = (
    '{"schema_version":"4.0","route":"artifact",'
    '"artifact_intent":{"operation":"create_blueprint",'
    '"objective":"Create the requested structured blueprint."}}'
)
VALID_SINGLE_FILE_ARTIFACT_RESPONSE = (
    '{"schema_version":"4.0","route":"artifact",'
    '"artifact_intent":{"operation":"create_single_file_artifact",'
    '"objective":"Create the requested project setup script.",'
    '"artifact_family":"code","format":"bash",'
    '"filename":"setup_project.sh"}}'
)


class FakeRoutingModels:
    def __init__(
        self,
        *,
        response_text: object = VALID_ARTIFACT_RESPONSE,
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


def artifact_routing_input(**overrides: object) -> object:
    from agent_col_routing_v4 import AgentColRoutingInput

    payload: dict[str, object] = {
        "current_message": (
            "Create a structured blueprint from this complete project "
            "description about a study partner with approved memory and "
            "verifiable milestones."
        ),
        "available_capabilities": (
            "source",
            "research",
            "computation",
            "requirements_verification",
        ),
        "artifact_creation_available": True,
        "structured_decision_present": False,
    }
    payload.update(overrides)
    return AgentColRoutingInput.model_validate(payload)


def load_routing_provider_v4():
    try:
        return importlib.import_module("agent_col_routing_provider_v4")
    except ModuleNotFoundError:
        pytest.fail("agent_col_routing_provider_v4 has not been implemented")


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


def referenced_schema(
    schema: dict[str, object],
    reference: str,
) -> dict[str, object]:
    return schema["$defs"][reference.removeprefix("#/$defs/")]


def provider_variants_by_route(
    schema: dict[str, object],
) -> dict[str, dict[str, object]]:
    definitions = schema["$defs"]
    variants: dict[str, dict[str, object]] = {}
    for option in schema["anyOf"]:
        reference = option["$ref"]
        variant = definitions[reference.removeprefix("#/$defs/")]
        route = variant["properties"]["route"]["enum"][0]
        variants[route] = variant
    return variants


def artifact_intent_variants(
    schema: dict[str, object],
) -> list[dict[str, object]]:
    artifact_directive = provider_variants_by_route(schema)["artifact"]
    artifact_intent = artifact_directive["properties"]["artifact_intent"]
    return [
        referenced_schema(schema, option["$ref"])
        for option in artifact_intent["anyOf"]
    ]


def test_v4_provider_schema_requires_the_matching_payload_for_each_route(
) -> None:
    provider = load_routing_provider_v4()

    schema = provider.build_agent_col_routing_v4_response_schema()

    variants = provider_variants_by_route(schema)
    assert set(variants) == {
        "direct",
        "clarify",
        "source",
        "research",
        "computation",
        "requirements_verification",
        "artifact",
    }
    assert next(iter(variants)) == "artifact"
    expected_payloads = {
        "direct": set(),
        "clarify": {"clarifying_question"},
        "source": {"source_intent"},
        "research": {"research_intent"},
        "computation": {"computation_intent"},
        "requirements_verification": {
            "requirements_verification_intent"
        },
        "artifact": {"artifact_intent"},
    }
    all_payloads = set().union(*expected_payloads.values())
    for route, variant in variants.items():
        payloads = expected_payloads[route]
        assert set(variant["required"]) == {
            "schema_version",
            "route",
            *payloads,
        }
        assert set(variant["properties"]) == {
            "schema_version",
            "route",
            *payloads,
        }
        assert variant["properties"]["schema_version"]["enum"] == ["4.0"]
        assert variant["additionalProperties"] is False
        assert not (all_payloads - payloads) & set(variant["properties"])

    operations = {
        option["properties"]["operation"]["enum"][0]: option
        for option in artifact_intent_variants(schema)
    }
    assert set(operations) == {
        "create_blueprint",
        "create_single_file_artifact",
    }
    blueprint = operations["create_blueprint"]
    assert blueprint["additionalProperties"] is False
    assert set(blueprint["required"]) == {"operation", "objective"}
    assert set(blueprint["properties"]) == {"operation", "objective"}

    single_file = operations["create_single_file_artifact"]
    assert single_file["additionalProperties"] is False
    assert set(single_file["required"]) == {
        "operation",
        "objective",
        "artifact_family",
        "format",
        "filename",
    }
    assert set(single_file["properties"]) == {
        "operation",
        "objective",
        "artifact_family",
        "format",
        "filename",
    }
    artifact_schema_scope = {
        "artifact_intent": [
            blueprint,
            single_file,
        ]
    }
    assert not {
        "source_text",
        "project_id",
        "artifact_id",
        "profile_value",
        "policy_version",
    } & collect_schema_keys(artifact_schema_scope)


@pytest.mark.asyncio
async def test_v4_request_rejects_artifact_route_without_required_intent(
) -> None:
    provider = load_routing_provider_v4()

    with pytest.raises(provider.AgentColRoutingV4ProviderOutputError) as error:
        await provider.request_agent_col_routing_v4_directive(
            fake_client(
                FakeRoutingModels(
                    response_text=(
                        '{"schema_version":"4.0","route":"artifact"}'
                    )
                )
            ),
            artifact_routing_input(),
        )

    assert error.value.reason == "schema_validation_failed"
    assert error.value.schema_failure_reason == "route_payload_mismatch"


@pytest.mark.asyncio
async def test_v4_request_accepts_single_file_artifact_intent() -> None:
    provider = load_routing_provider_v4()

    directive = await provider.request_agent_col_routing_v4_directive(
        fake_client(
            FakeRoutingModels(response_text=VALID_SINGLE_FILE_ARTIFACT_RESPONSE)
        ),
        artifact_routing_input(
            current_message=(
                "Create a Bash script that creates a project folder with "
                "source, tests, documentation, and readme files."
            )
        ),
    )

    assert directive.route == "artifact"
    assert directive.artifact_intent is not None
    assert directive.artifact_intent.operation == "create_single_file_artifact"
    assert directive.artifact_intent.artifact_family == "code"
    assert directive.artifact_intent.format == "bash"
    assert directive.artifact_intent.filename == "setup_project.sh"


@pytest.mark.asyncio
async def test_v4_request_rejects_single_file_artifact_without_filename(
) -> None:
    provider = load_routing_provider_v4()
    response_text = VALID_SINGLE_FILE_ARTIFACT_RESPONSE.replace(
        ',"filename":"setup_project.sh"',
        "",
    )

    with pytest.raises(provider.AgentColRoutingV4ProviderOutputError) as error:
        await provider.request_agent_col_routing_v4_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            artifact_routing_input(
                current_message=(
                    "Create a Bash script that creates a project folder with "
                    "source, tests, documentation, and readme files."
                )
            ),
        )

    assert error.value.reason == "schema_validation_failed"
    assert error.value.schema_failure_reason == "intent_invariant_failed"


def test_v4_provider_schema_relaxes_only_provider_unsupported_constraints(
) -> None:
    provider = load_routing_provider_v4()
    from agent_col_routing_v4 import AgentColRoutingDirective

    canonical = AgentColRoutingDirective.model_json_schema()
    provider_schema = provider.build_agent_col_routing_v4_response_schema()

    canonical_keys = collect_schema_keys(canonical)
    provider_keys = collect_schema_keys(provider_schema)
    assert {"minLength", "maxLength", "pattern", "maxItems"} <= canonical_keys
    assert not {"minLength", "maxLength", "pattern", "maxItems"} & provider_keys


def test_v4_provider_schema_marks_artifact_objective_numeric_free() -> None:
    provider = load_routing_provider_v4()

    schema = provider.build_agent_col_routing_v4_response_schema()
    descriptions = [
        variant["properties"]["objective"]["description"].lower()
        for variant in artifact_intent_variants(schema)
    ]

    assert descriptions
    for description in descriptions:
        assert "no digits" in description
        assert "source material" in description


@pytest.mark.asyncio
async def test_v4_request_uses_tool_free_structured_vertex_contract() -> None:
    provider = load_routing_provider_v4()
    models = FakeRoutingModels()
    routing_input = artifact_routing_input()

    directive = await provider.request_agent_col_routing_v4_directive(
        fake_client(models),
        routing_input,
    )

    assert directive.route == "artifact"
    assert directive.artifact_intent.operation == "create_blueprint"
    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == provider.AGENT_COL_ROUTING_V4_MODEL_NAME == (
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
    assert config.system_instruction == (
        provider.AGENT_COL_ROUTING_V4_SYSTEM_INSTRUCTION
    )
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == (
        provider.build_agent_col_routing_v4_response_schema()
    )
    assert config.response_schema is None
    assert config.temperature == 0
    assert config.max_output_tokens == 2_048
    assert config.thinking_config == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.MINIMAL,
    )
    assert not config.tools


def test_v4_instruction_preserves_artifact_authority_and_restraint() -> None:
    provider = load_routing_provider_v4()
    instruction = " ".join(
        provider.AGENT_COL_ROUTING_V4_SYSTEM_INSTRUCTION.split()
    )

    for expected in (
        "Agent_Col",
        "At most one expert or artifact capability may be selected.",
        "artifact_creation_available",
        "structured_decision_present is false",
        "operation and a short nonnumeric objective only",
        "Never emit source text",
        "project IDs",
        "artifact IDs",
        "profile values",
        "feedback",
        "schema or provider configuration",
        "Never call tools",
    ):
        assert expected in instruction


@pytest.mark.asyncio
async def test_v4_request_rejects_model_supplied_artifact_authority_safely(
) -> None:
    provider = load_routing_provider_v4()
    response_text = VALID_ARTIFACT_RESPONSE.replace(
        '"objective":"Create the requested structured blueprint."',
        '"objective":"Create the requested structured blueprint.",'
        '"project_id":"private-project"',
    )

    with pytest.raises(provider.AgentColRoutingV4ProviderOutputError) as error:
        await provider.request_agent_col_routing_v4_directive(
            fake_client(FakeRoutingModels(response_text=response_text)),
            artifact_routing_input(),
        )

    assert error.value.reason == "schema_validation_failed"
    assert error.value.schema_failure_reason == "unexpected_field"
    assert "private-project" not in str(error.value)
    assert "private-project" not in repr(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("input_overrides", "expected_reason"),
    (
        ({"artifact_creation_available": False}, "artifact_unavailable"),
        ({"structured_decision_present": True}, "structured_decision_present"),
    ),
)
async def test_v4_request_preserves_exact_artifact_input_mismatch(
    input_overrides: dict[str, object],
    expected_reason: str,
) -> None:
    provider = load_routing_provider_v4()
    from agent_col_routing_v4 import RoutingDirectiveInputError

    with pytest.raises(RoutingDirectiveInputError) as error:
        await provider.request_agent_col_routing_v4_directive(
            fake_client(FakeRoutingModels()),
            artifact_routing_input(**input_overrides),
        )

    assert error.value.reason == expected_reason


@pytest.mark.asyncio
async def test_v4_request_classifies_provider_failure_without_content_leak(
    caplog,
) -> None:
    provider = load_routing_provider_v4()

    with pytest.raises(provider.AgentColRoutingV4ProviderError) as error:
        await provider.request_agent_col_routing_v4_directive(
            fake_client(
                FakeRoutingModels(error=RuntimeError("private-provider-payload"))
            ),
            artifact_routing_input(),
        )

    assert str(error.value) == "Routing v4 provider request failed."
    assert "private" not in str(error.value)
    assert "private" not in repr(error.value)
    assert "private-provider-payload" not in caplog.text


@pytest.mark.asyncio
async def test_v4_request_classifies_timeout_separately() -> None:
    provider = load_routing_provider_v4()

    with pytest.raises(provider.AgentColRoutingV4ProviderTimeoutError):
        await provider.request_agent_col_routing_v4_directive(
            fake_client(FakeRoutingModels(delay=0.02)),
            artifact_routing_input(),
            timeout_seconds=0.001,
        )
