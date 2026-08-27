import pytest
from pydantic import BaseModel, ConfigDict, ValidationError


class ExamplePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    finding: str


class ExampleEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str


def test_completed_expert_result_preserves_typed_payload_and_evidence() -> None:
    from expert_contracts import (
        ExpertCapability,
        ExpertResult,
        ExpertStatus,
    )

    result = ExpertResult[ExamplePayload, ExampleEvidence](
        capability="research",
        status="completed",
        summary="Current evidence supports the finding.",
        limitations=("One source remains unavailable.",),
        payload=ExamplePayload(finding="Verified finding"),
        evidence=ExampleEvidence(source_id="source-1"),
    )

    assert result.capability is ExpertCapability.RESEARCH
    assert result.status is ExpertStatus.COMPLETED
    assert result.summary == "Current evidence supports the finding."
    assert result.limitations == ("One source remains unavailable.",)
    assert result.payload == ExamplePayload(finding="Verified finding")
    assert result.evidence == ExampleEvidence(source_id="source-1")


@pytest.mark.parametrize("missing_field", ("summary", "payload", "evidence"))
def test_completed_expert_result_requires_completed_fields(
    missing_field: str,
) -> None:
    from expert_contracts import ExpertResult

    values = {
        "capability": "research",
        "status": "completed",
        "summary": "Verified summary",
        "payload": ExamplePayload(finding="Verified finding"),
        "evidence": ExampleEvidence(source_id="source-1"),
    }
    values.pop(missing_field)

    with pytest.raises(ValidationError):
        ExpertResult[ExamplePayload, ExampleEvidence](**values)


@pytest.mark.parametrize(
    "status",
    ("rejected_input", "unavailable", "timed_out", "invalid_output"),
)
@pytest.mark.parametrize(
    "contaminated_field",
    ("summary", "limitations", "payload", "evidence"),
)
def test_noncompleted_expert_result_rejects_untrusted_content(
    status: str,
    contaminated_field: str,
) -> None:
    from expert_contracts import ExpertResult

    private_marker = "private-provider-payload"
    values: dict[str, object] = {
        "capability": "research",
        "status": status,
    }
    values[contaminated_field] = (
        (private_marker,)
        if contaminated_field == "limitations"
        else private_marker
    )

    with pytest.raises(ValidationError) as exc_info:
        ExpertResult[object, object](**values)

    assert private_marker not in str(exc_info.value)


@pytest.mark.parametrize(
    "invalid_fields",
    (
        {"summary": "   "},
        {"summary": "s" * 1_501},
        {"limitations": ("   ",)},
        {"limitations": ("l" * 501,)},
        {"limitations": ("bounded",) * 6},
    ),
)
def test_completed_expert_result_rejects_unbounded_text(
    invalid_fields: dict[str, object],
) -> None:
    from expert_contracts import ExpertResult

    values: dict[str, object] = {
        "capability": "research",
        "status": "completed",
        "summary": "Verified summary",
        "limitations": (),
        "payload": ExamplePayload(finding="Verified finding"),
        "evidence": ExampleEvidence(source_id="source-1"),
    }
    values.update(invalid_fields)

    with pytest.raises(ValidationError):
        ExpertResult[ExamplePayload, ExampleEvidence](**values)


def test_invalid_output_result_can_carry_content_safe_reason() -> None:
    from expert_contracts import ExpertResult, ExpertStatus

    result = ExpertResult[object, object](
        capability="research",
        status=ExpertStatus.INVALID_OUTPUT,
        invalid_output_reason="missing_grounding_metadata",
    )

    assert result.invalid_output_reason == "missing_grounding_metadata"
    assert result.summary is None
    assert result.payload is None
    assert result.evidence is None


@pytest.mark.parametrize(
    "status",
    ("completed", "rejected_input", "unavailable", "timed_out"),
)
def test_non_invalid_output_result_rejects_invalid_output_reason(
    status: str,
) -> None:
    from expert_contracts import ExpertResult

    values: dict[str, object] = {
        "capability": "research",
        "status": status,
        "invalid_output_reason": "missing_grounding_metadata",
    }
    if status == "completed":
        values.update(
            {
                "summary": "Verified summary",
                "payload": ExamplePayload(finding="Verified finding"),
                "evidence": ExampleEvidence(source_id="source-1"),
            }
        )

    with pytest.raises(ValidationError):
        ExpertResult[ExamplePayload, ExampleEvidence](**values)
