import hashlib
import chat_turns
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from chat_turns import derive_chat_turn_ids
from schemas import (
    AgentActionReceipt,
    ArtifactReference,
    ChatResponse,
    MemoryProposalReceipt,
)


def test_derive_chat_turn_ids_hashes_key_and_bounds_message_ids() -> None:
    key = "550e8400-e29b-41d4-a716-446655440000"
    digest = hashlib.sha256(key.encode("ascii")).hexdigest()

    result = derive_chat_turn_ids(key)

    assert result.turn_id == digest
    assert result.user_message_id == f"turn--{digest}--user"
    assert result.model_message_id == f"turn--{digest}--model"
    assert len(result.user_message_id) <= 128
    assert len(result.model_message_id) <= 128


@pytest.mark.parametrize(
    "value",
    [
        None,
        7,
        "",
        " key",
        "key ",
        "key/value",
        "key.value",
        "clé",
        "a" * 129,
    ],
)
def test_derive_chat_turn_ids_rejects_invalid_keys(value: object) -> None:
    with pytest.raises(ValueError, match="idempotency_key"):
        derive_chat_turn_ids(value)  # type: ignore[arg-type]


def test_chat_turn_contract_values_drive_valid_claim() -> None:
    assert hasattr(chat_turns, "ChatTurnRequest")
    assert hasattr(chat_turns, "ChatTurnClaim")
    request = chat_turns.ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="hello",
    )
    ids = derive_chat_turn_ids("request-1")
    expires_at = datetime(2026, 8, 20, 12, 2, tzinfo=UTC)
    claim = chat_turns.ChatTurnClaim(
        request=request,
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=expires_at,
        resumed=False,
    )

    assert chat_turns.CHAT_TURN_SCHEMA_VERSION == "1.0"
    assert chat_turns.CHAT_TURN_LEASE_DURATION.total_seconds() == 120
    assert claim.request is request
    assert claim.ids is ids
    assert claim.lease_expires_at is expires_at
    with pytest.raises(FrozenInstanceError):
        claim.resumed = True  # type: ignore[misc]


def test_resumed_chat_turn_claim_carries_typed_precompleted_effects() -> None:
    request = chat_turns.ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember my preference.",
    )
    action = AgentActionReceipt(
        action_name="propose_memory_signal",
        status="completed",
    )
    proposal = MemoryProposalReceipt(
        proposal_id="response_length--proposal-1",
        category="response_length",
        proposed_value="concise",
        expires_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )
    artifact = ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id="agent-col",
        artifact_id="blueprint--artifact-1",
        schema_version="2.0",
        display_label="Agent Col blueprint",
    )

    claim = chat_turns.ChatTurnClaim(
        request=request,
        ids=derive_chat_turn_ids("request-1"),
        owner_token="owner-token",
        lease_expires_at=datetime(2026, 8, 21, 11, 0, tzinfo=UTC),
        resumed=True,
        precompleted_actions=(action,),
        precompleted_memory_proposals=(proposal,),
        precompleted_artifacts=(artifact,),
    )

    assert claim.precompleted_actions == (action,)
    assert claim.precompleted_memory_proposals == (proposal,)
    assert claim.precompleted_artifacts == (artifact,)


def test_chat_turn_replay_carries_validated_response() -> None:
    assert hasattr(chat_turns, "ChatTurnReplay")
    response = ChatResponse(response="durable answer")

    replay = chat_turns.ChatTurnReplay(response=response)

    assert replay.response is response


def test_chat_turn_errors_have_distinct_runtime_types() -> None:
    error_names = (
        "ChatTurnConflictError",
        "ChatTurnInProgressError",
        "ChatTurnOwnershipError",
        "ChatTurnStateError",
    )
    assert all(hasattr(chat_turns, name) for name in error_names)
    assert issubclass(chat_turns.ChatTurnConflictError, RuntimeError)
    assert issubclass(chat_turns.ChatTurnOwnershipError, RuntimeError)
    assert issubclass(chat_turns.ChatTurnStateError, RuntimeError)
    error = chat_turns.ChatTurnInProgressError(9)
    assert isinstance(error, RuntimeError)
    assert error.retry_after_seconds == 9


@pytest.mark.parametrize("value", [True, "9", 0, -1])
def test_in_progress_error_rejects_invalid_retry_delays(value: object) -> None:
    assert hasattr(chat_turns, "ChatTurnInProgressError")
    with pytest.raises(ValueError, match="retry_after_seconds"):
        chat_turns.ChatTurnInProgressError(value)  # type: ignore[arg-type]
