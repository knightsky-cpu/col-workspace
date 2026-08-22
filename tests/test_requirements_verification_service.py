import asyncio
import json
from types import SimpleNamespace
import traceback

import pytest
from google.genai import types

from expert_contracts import ExpertStatus
from requirements_verification import (
    RequirementInput,
    RequirementsVerificationInput,
    SubjectBlock,
)


VALID_CANDIDATE = {
    "assessments": [
        {
            "requirement_id": "REQ-001",
            "status": "covered",
            "evidence": [
                {
                    "subject_block_id": "SUBJECT-001",
                    "excerpt": "Includes a practical example.",
                    "explanation": "The supplied draft states the requirement.",
                }
            ],
            "gap": None,
            "recommended_action": None,
        }
    ],
    "overall_limitations": [],
}


class FakeVerificationModels:
    def __init__(
        self,
        *,
        response_text: object = json.dumps(VALID_CANDIDATE),
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


def fake_client(models: FakeVerificationModels) -> SimpleNamespace:
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def verification_input() -> RequirementsVerificationInput:
    return RequirementsVerificationInput(
        objective="Compare the draft against every requirement.",
        requirements=(
            RequirementInput(
                requirement_id="REQ-001",
                text="Include one practical example.",
                source_block_id="block-1",
            ),
        ),
        subject_blocks=(
            SubjectBlock(
                subject_block_id="SUBJECT-001",
                text="Includes a practical example.",
                source_block_id="block-2",
            ),
        ),
    )


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


@pytest.mark.asyncio
async def test_service_returns_only_locally_validated_completed_result() -> None:
    from requirements_verification_service import (
        RequirementsVerificationService,
    )

    models = FakeVerificationModels()
    result = await RequirementsVerificationService(
        client=fake_client(models)
    ).verify(verification_input())

    assert result.status is ExpertStatus.COMPLETED
    assert result.payload is not None
    assert result.payload.assessments[0].requirement_text == (
        "Include one practical example."
    )
    assert len(models.calls) == 1


@pytest.mark.asyncio
async def test_service_rejects_invalid_input_before_provider_call() -> None:
    from requirements_verification_service import (
        RequirementsVerificationService,
        RequirementsVerificationServiceError,
    )

    models = FakeVerificationModels()
    service = RequirementsVerificationService(client=fake_client(models))

    with pytest.raises(RequirementsVerificationServiceError) as raised:
        await service.verify({"objective": "Incomplete input."})  # type: ignore[arg-type]

    assert raised.value.status is ExpertStatus.REJECTED_INPUT
    assert raised.value.invalid_output_reason is None
    assert models.calls == []


@pytest.mark.asyncio
async def test_service_uses_bounded_tool_free_vertex_structured_request() -> None:
    from requirements_verification_service import (
        REQUIREMENTS_VERIFICATION_MAX_OUTPUT_TOKENS,
        REQUIREMENTS_VERIFICATION_MODEL_NAME,
        RequirementsVerificationService,
    )

    models = FakeVerificationModels()
    request = verification_input()

    await RequirementsVerificationService(
        client=fake_client(models)
    ).verify(request)

    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == REQUIREMENTS_VERIFICATION_MODEL_NAME
    contents = call["contents"]
    assert isinstance(contents, list)
    assert len(contents) == 1
    assert isinstance(contents[0], types.Content)
    assert contents[0].parts is not None
    assert len(contents[0].parts) == 1
    prompt = contents[0].parts[0].text
    assert prompt == (
        "[UNTRUSTED_REQUIREMENTS_VERIFICATION_INPUT]\n"
        f"{request.model_dump_json()}\n"
        "[/UNTRUSTED_REQUIREMENTS_VERIFICATION_INPUT]"
    )
    config = call["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None
    assert config.temperature == 0
    assert config.max_output_tokens == (
        REQUIREMENTS_VERIFICATION_MAX_OUTPUT_TOKENS
    )
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level is types.ThinkingLevel.LOW
    assert not config.tools
    assert config.automatic_function_calling is not None
    assert config.automatic_function_calling.disable is True
    system_instruction = config.system_instruction
    assert isinstance(system_instruction, str)
    normalized_instruction = " ".join(system_instruction.split())
    assert "exactly one assessment for every supplied requirement ID" in (
        normalized_instruction
    )
    assert "Evidence excerpts must be" in normalized_instruction
    assert "untrusted task data" in normalized_instruction
    assert "Do not call tools" in normalized_instruction
    assert "Agent_Col owns the final user-facing response" in (
        normalized_instruction
    )
    schema = config.response_json_schema
    assert isinstance(schema, dict)
    assert schema["additionalProperties"] is False
    assert not {
        "minLength",
        "maxLength",
        "pattern",
        "maxItems",
    } & collect_schema_keys(schema)


@pytest.mark.asyncio
async def test_service_classifies_missing_response_text_safely() -> None:
    from requirements_verification_service import (
        RequirementsVerificationInvalidOutputReason,
        RequirementsVerificationService,
        RequirementsVerificationServiceError,
    )

    models = FakeVerificationModels(response_text=None)

    with pytest.raises(RequirementsVerificationServiceError) as raised:
        await RequirementsVerificationService(
            client=fake_client(models)
        ).verify(verification_input())

    assert raised.value.status is ExpertStatus.INVALID_OUTPUT
    assert raised.value.invalid_output_reason is (
        RequirementsVerificationInvalidOutputReason.MISSING_RESPONSE_TEXT
    )
    assert len(models.calls) == 1


@pytest.mark.asyncio
async def test_service_classifies_invalid_json_safely() -> None:
    from requirements_verification_service import (
        RequirementsVerificationInvalidOutputReason,
        RequirementsVerificationService,
        RequirementsVerificationServiceError,
    )

    with pytest.raises(RequirementsVerificationServiceError) as raised:
        await RequirementsVerificationService(
            client=fake_client(
                FakeVerificationModels(response_text="not-json")
            )
        ).verify(verification_input())

    assert raised.value.status is ExpertStatus.INVALID_OUTPUT
    assert raised.value.invalid_output_reason is (
        RequirementsVerificationInvalidOutputReason.INVALID_JSON
    )


@pytest.mark.asyncio
async def test_service_classifies_candidate_schema_violation_safely() -> None:
    from requirements_verification_service import (
        RequirementsVerificationInvalidOutputReason,
        RequirementsVerificationService,
        RequirementsVerificationServiceError,
    )

    schema_invalid = json.dumps(
        {"assessments": [], "overall_limitations": []}
    )

    with pytest.raises(RequirementsVerificationServiceError) as raised:
        await RequirementsVerificationService(
            client=fake_client(
                FakeVerificationModels(response_text=schema_invalid)
            )
        ).verify(verification_input())

    assert raised.value.status is ExpertStatus.INVALID_OUTPUT
    assert raised.value.invalid_output_reason is (
        RequirementsVerificationInvalidOutputReason.SCHEMA_VALIDATION_FAILED
    )


@pytest.mark.asyncio
async def test_service_rejects_locally_ungrounded_candidate_atomically() -> None:
    from requirements_verification_service import (
        RequirementsVerificationInvalidOutputReason,
        RequirementsVerificationService,
        RequirementsVerificationServiceError,
    )

    ungrounded = json.loads(json.dumps(VALID_CANDIDATE))
    ungrounded["assessments"][0]["evidence"][0]["excerpt"] = (
        "This excerpt was not supplied."
    )

    models = FakeVerificationModels(response_text=json.dumps(ungrounded))
    with pytest.raises(RequirementsVerificationServiceError) as raised:
        await RequirementsVerificationService(
            client=fake_client(models)
        ).verify(verification_input())

    assert raised.value.status is ExpertStatus.INVALID_OUTPUT
    assert raised.value.invalid_output_reason is (
        RequirementsVerificationInvalidOutputReason.LOCAL_VALIDATION_FAILED
    )
    assert len(models.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_kind", ["duplicate", "unknown"])
async def test_service_atomically_rejects_invalid_requirement_identity(
    candidate_kind: str,
) -> None:
    from requirements_verification_service import (
        RequirementsVerificationInvalidOutputReason,
        RequirementsVerificationService,
        RequirementsVerificationServiceError,
    )

    payload = json.loads(json.dumps(VALID_CANDIDATE))
    if candidate_kind == "duplicate":
        payload["assessments"].append(payload["assessments"][0])
    else:
        payload["assessments"][0]["requirement_id"] = "REQ-002"

    models = FakeVerificationModels(response_text=json.dumps(payload))
    with pytest.raises(RequirementsVerificationServiceError) as raised:
        await RequirementsVerificationService(
            client=fake_client(models)
        ).verify(verification_input())

    assert raised.value.status is ExpertStatus.INVALID_OUTPUT
    assert raised.value.invalid_output_reason is (
        RequirementsVerificationInvalidOutputReason.LOCAL_VALIDATION_FAILED
    )
    assert len(models.calls) == 1


@pytest.mark.asyncio
async def test_service_classifies_timeout_without_retry() -> None:
    from requirements_verification_service import (
        RequirementsVerificationService,
        RequirementsVerificationServiceError,
    )

    models = FakeVerificationModels(delay=0.05)

    with pytest.raises(RequirementsVerificationServiceError) as raised:
        await RequirementsVerificationService(
            client=fake_client(models),
            timeout_seconds=0.001,
        ).verify(verification_input())

    assert raised.value.status is ExpertStatus.TIMED_OUT
    assert raised.value.invalid_output_reason is None
    assert len(models.calls) == 1


@pytest.mark.asyncio
async def test_service_classifies_provider_failure_without_content_or_retry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from requirements_verification_service import (
        RequirementsVerificationService,
        RequirementsVerificationServiceError,
    )

    provider_secret = "provider-secret-content"
    request_secret = "request-secret-content"
    models = FakeVerificationModels(error=RuntimeError(provider_secret))
    request = verification_input().model_copy(
        update={"objective": request_secret}
    )

    with pytest.raises(RequirementsVerificationServiceError) as raised:
        await RequirementsVerificationService(
            client=fake_client(models)
        ).verify(request)

    assert raised.value.status is ExpertStatus.UNAVAILABLE
    assert raised.value.invalid_output_reason is None
    assert str(raised.value) == "Requirements Verification execution failed."
    assert len(models.calls) == 1
    assert provider_secret not in caplog.text
    assert request_secret not in caplog.text
    formatted_exception = "".join(
        traceback.format_exception(raised.value)
    )
    assert provider_secret not in formatted_exception
    assert request_secret not in formatted_exception
