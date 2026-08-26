import hashlib
import chat_turns
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from chat_turns import derive_chat_turn_ids
from schemas import (
    AgentActionReceipt,
    ArtifactFeedbackDecisionRequest,
    ArtifactFeedbackReference,
    ArtifactReference,
    ChatResponse,
    CollaborativeNoteDecisionRequest,
    CollaborativeNoteEvent,
    CollaborativeNoteProposal,
    MemoryProposalReceipt,
    MemoryProposalReceiptV2,
)
from memory_clarifications import (
    MemoryClarificationChoice,
    MemoryClarificationReceipt,
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
    feedback_request = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="accepted",
        feedback_text="This boundary is correct.",
        expected_schema_version="2.0",
    )
    feedback = ArtifactFeedbackReference(
        feedback_id="feedback--0123456789abcdef01234567",
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        target_kind="whole_blueprint",
        decision="accepted",
        schema_version="2.0",
        created_at=datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
    )
    request = chat_turns.ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Record this artifact feedback.",
        artifact_feedback_decision=feedback_request,
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
        precompleted_artifact_feedback=(feedback,),
    )

    assert claim.precompleted_actions == (action,)
    assert claim.precompleted_memory_proposals == (proposal,)
    assert claim.precompleted_artifacts == (artifact,)
    assert claim.precompleted_artifact_feedback == (feedback,)


def test_chat_turn_replay_carries_validated_response() -> None:
    assert hasattr(chat_turns, "ChatTurnReplay")
    response = ChatResponse(response="durable answer")

    replay = chat_turns.ChatTurnReplay(response=response)

    assert replay.response is response


def test_chat_turn_contract_preserves_version_two_memory_receipts() -> None:
    proposal = MemoryProposalReceiptV2(
        proposal_id="development_environments--proposal-2",
        category="development_environments",
        proposed_value=["macos", "linux"],
        policy_version="2.0",
        expires_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    )
    request = chat_turns.ChatTurnRequest(
        project_id="agent-col",
        session_id="session-2",
        user_id="user-1",
        message="Remember that I prefer macOS and Linux environments.",
    )
    claim = chat_turns.ChatTurnClaim(
        request=request,
        ids=derive_chat_turn_ids("request-2"),
        owner_token="owner-token",
        lease_expires_at=datetime(2026, 8, 25, 12, 2, tzinfo=UTC),
        resumed=True,
        precompleted_memory_proposals=(proposal,),
    )
    response = ChatResponse(
        response="The proposal is pending your approval.",
        actions=[
            AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            )
        ],
        memory_proposals=[proposal],
    )

    assert claim.precompleted_memory_proposals == (proposal,)
    assert response.memory_proposals == [proposal]
    assert response.model_dump(mode="json")["memory_proposals"] == [
        {
            "proposal_id": "development_environments--proposal-2",
            "category": "development_environments",
            "proposed_value": ["macos", "linux"],
            "policy_version": "2.0",
            "expires_at": "2026-08-26T12:00:00Z",
        }
    ]


def test_chat_turn_contract_preserves_memory_clarification_receipt() -> None:
    clarification = MemoryClarificationReceipt(
        clarification_id="memory-clarification--clarification-1",
        choices=[
            MemoryClarificationChoice(
                candidate_index=0,
                category_label="Response length",
                value_label="detailed",
            ),
            MemoryClarificationChoice(
                candidate_index=1,
                category_label="Explanation structure",
                value_label="step by step",
            ),
        ],
        expires_at=datetime(2026, 8, 25, 12, 15, tzinfo=UTC),
    )
    request = chat_turns.ChatTurnRequest(
        project_id="agent-col",
        session_id="session-3",
        user_id="user-1",
        message="Remember that I prefer detailed explanations.",
    )
    claim = chat_turns.ChatTurnClaim(
        request=request,
        ids=derive_chat_turn_ids("request-3"),
        owner_token="owner-token",
        lease_expires_at=datetime(2026, 8, 25, 12, 2, tzinfo=UTC),
        resumed=True,
        precompleted_memory_clarifications=(clarification,),
    )
    response = ChatResponse(
        response="Which preference did you mean?",
        memory_clarifications=[clarification],
    )

    assert claim.precompleted_memory_clarifications == (clarification,)
    assert response.memory_clarifications == [clarification]
    assert response.model_dump(mode="json")["memory_clarifications"] == [
        {
            "clarification_id": "memory-clarification--clarification-1",
            "choices": [
                {
                    "candidate_index": 0,
                    "category_label": "Response length",
                    "value_label": "detailed",
                },
                {
                    "candidate_index": 1,
                    "category_label": "Explanation structure",
                    "value_label": "step by step",
                },
            ],
            "expires_at": "2026-08-25T12:15:00Z",
        }
    ]


def test_chat_turn_contract_preserves_collaborative_note_decision_effects() -> None:
    decision = CollaborativeNoteDecisionRequest(
        proposal_id="note-proposal-1",
        decision="approve",
    )
    request = chat_turns.ChatTurnRequest(
        project_id="agent-col",
        session_id="session-4",
        user_id="user-1",
        message="Approve that note.",
        collaborative_note_decision=decision,
    )
    event = CollaborativeNoteEvent(
        event_id="note-1--approved--note-proposal-1",
        note_id="note-1",
        proposal_id="note-proposal-1",
        owner_user_id="user-1",
        workspace_id="agent-col",
        event_type="approved",
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        source_session_id="session-4",
        source_message_ids=["turn-message-1"],
        revision=1,
        previous_revision=None,
        created_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    )
    claim = chat_turns.ChatTurnClaim(
        request=request,
        ids=derive_chat_turn_ids("request-4"),
        owner_token="owner-token",
        lease_expires_at=datetime(2026, 8, 26, 12, 2, tzinfo=UTC),
        resumed=True,
        precompleted_collaborative_note_events=(event,),
    )
    response = ChatResponse(
        response="The note approval was recorded.",
        actions=[
            AgentActionReceipt(
                action_name="approve_collaborative_note",
                status="completed",
            )
        ],
        collaborative_note_events=[event],
    )

    assert claim.request.collaborative_note_decision == decision
    assert claim.precompleted_collaborative_note_events == (event,)
    assert response.model_dump(mode="json")["collaborative_note_events"][0][
        "event_type"
    ] == "approved"


def test_chat_request_rejects_note_and_memory_decisions_together() -> None:
    from pydantic import ValidationError
    from schemas import ChatRequest, MemoryDecisionRequest

    with pytest.raises(ValidationError):
        ChatRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="approve both",
            memory_decision=MemoryDecisionRequest(
                proposal_id="response_length--proposal-1",
                decision="approve",
            ),
            collaborative_note_decision=CollaborativeNoteDecisionRequest(
                proposal_id="note-proposal-1",
                decision="approve",
            ),
        )


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
