import json
from types import SimpleNamespace

import pytest

from working_state import WorkingStateSnapshot


class FakeModels:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.arguments: dict[str, object] = {}

    async def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.arguments = kwargs
        return SimpleNamespace(text=self.response_text)


def fake_genai_client(response_text: str) -> SimpleNamespace:
    return SimpleNamespace(aio=SimpleNamespace(models=FakeModels(response_text)))


def working_state_payload(**overrides) -> dict[str, object]:
    values = {
        "schema_version": "1.0",
        "status": "active",
        "authority": "non_authoritative",
        "user_id": "user-1",
        "project_id": "project-1",
        "session_id": "session-1",
        "source_message_id": "message-1",
        "request_summary": "Deployment plan with Cloud Run under consideration.",
        "current_goal": "Choose a deployment plan.",
        "intent_hypothesis": (
            "The user likely wants a secure deployment plan and is unsure "
            "whether background workers are necessary."
        ),
        "active_constraints": ["security matters more than speed"],
        "unresolved_questions": [
            {
                "question": (
                    "Does artifact generation need to survive browser "
                    "disconnects?"
                ),
                "why_it_matters": (
                    "This determines whether synchronous Cloud Run is enough."
                ),
                "blocking_status": "useful",
            }
        ],
        "clarification_status": "useful",
        "next_step_hypothesis": (
            "Prefer a synchronous MVP unless durability becomes required."
        ),
        "confidence": "medium",
        "updated_at": None,
    }
    values.update(overrides)
    return values


def working_state_draft_payload(**overrides) -> dict[str, object]:
    values = working_state_payload()
    for key in (
        "schema_version",
        "status",
        "authority",
        "user_id",
        "project_id",
        "session_id",
        "source_message_id",
        "updated_at",
    ):
        values.pop(key)
    values.update(overrides)
    return values


def update_response_payload(**overrides) -> dict[str, object]:
    values = {
        "update_required": True,
        "snapshot": working_state_draft_payload(),
    }
    values.update(overrides)
    return values


def update_request():
    from working_state_service import WorkingStateUpdateInput

    return WorkingStateUpdateInput(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_message_id="message-1",
        current_message=(
            "I want a deployment plan, probably Cloud Run, but security "
            "matters more than speed."
        ),
        model_response="We can start with a synchronous Cloud Run plan.",
        previous_state=None,
        recent_user_messages=(),
        route="direct",
    )


@pytest.mark.asyncio
async def test_generate_working_state_update_accepts_valid_snapshot() -> None:
    import working_state_service as service

    client = fake_genai_client(json.dumps(update_response_payload()))

    result = await service.generate_working_state_update(
        client,
        update_request(),
    )

    assert result.update_required is True
    assert isinstance(result.snapshot, WorkingStateSnapshot)
    assert result.snapshot.user_id == "user-1"
    assert result.snapshot.project_id == "project-1"
    assert result.snapshot.session_id == "session-1"
    assert result.snapshot.source_message_id == "message-1"
    assert result.snapshot.authority == "non_authoritative"
    assert result.snapshot.request_summary.startswith("Deployment plan")
    arguments = client.aio.models.arguments
    assert arguments["model"] == service.WORKING_STATE_MODEL_NAME
    config = arguments["config"]
    assert config.response_mime_type == "application/json"
    assert config.temperature == 0.1
    instruction = " ".join(config.system_instruction.split())
    assert "hidden current-session working-state provider" in instruction
    assert "non-authoritative" in instruction
    assert "not user-facing" in instruction
    assert "Do not store raw hidden chain-of-thought" in instruction
    prompt = arguments["contents"][0].parts[0].text
    assert "[WORKING_STATE_UPDATE_INPUT]" in prompt
    assert "security matters more than speed" in prompt


@pytest.mark.asyncio
async def test_generate_working_state_update_accepts_no_update() -> None:
    import working_state_service as service

    client = fake_genai_client(
        json.dumps({"update_required": False, "snapshot": None})
    )

    result = await service.generate_working_state_update(
        client,
        update_request(),
    )

    assert result.update_required is False
    assert result.snapshot is None


@pytest.mark.asyncio
async def test_generate_working_state_update_rejects_overlong_state() -> None:
    import working_state_service as service

    client = fake_genai_client(
        json.dumps(
            update_response_payload(
                snapshot=working_state_draft_payload(request_summary="x" * 201)
            )
        )
    )

    with pytest.raises(service.WorkingStateGenerationError):
        await service.generate_working_state_update(client, update_request())


@pytest.mark.asyncio
async def test_generate_working_state_update_does_not_let_provider_override_server_fields() -> None:
    import working_state_service as service

    draft = working_state_draft_payload(
        authority="session_state",
        user_id="provider-user",
        project_id="provider-project",
        session_id="provider-session",
        source_message_id="provider-message",
        schema_version="999",
        status="empty",
        updated_at="2099-01-01T00:00:00Z",
    )
    client = fake_genai_client(
        json.dumps(update_response_payload(snapshot=draft))
    )

    result = await service.generate_working_state_update(
        client,
        update_request(),
    )

    assert result.update_required is True
    assert result.snapshot is not None
    assert result.snapshot.authority == "non_authoritative"
    assert result.snapshot.user_id == "user-1"
    assert result.snapshot.project_id == "project-1"
    assert result.snapshot.session_id == "session-1"
    assert result.snapshot.source_message_id == "message-1"
    assert result.snapshot.schema_version == "1.0"
    assert result.snapshot.status == "active"
    assert result.snapshot.updated_at is None


@pytest.mark.asyncio
async def test_generate_working_state_update_rejects_raw_reasoning_field(
) -> None:
    import working_state_service as service

    snapshot = working_state_payload()
    snapshot["reasoning"] = "raw hidden reasoning must not be persisted"
    client = fake_genai_client(
        json.dumps(update_response_payload(snapshot=snapshot))
    )

    with pytest.raises(service.WorkingStateGenerationError):
        await service.generate_working_state_update(client, update_request())
