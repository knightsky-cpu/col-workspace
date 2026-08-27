from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

import database
from chat_turns import (
    ChatTurnClaim,
    ChatTurnConflictError,
    ChatTurnIds,
    ChatTurnInProgressError,
    ChatTurnOwnershipError,
    ChatTurnReplay,
    ChatTurnRequest,
    ChatTurnStateError,
    derive_chat_turn_ids,
)
from database import MemoryEngine, MemoryEngineError
from database import ChatSessionOwnershipError
from memory_clarifications import (
    MemoryClarificationEnvelope,
    derive_memory_clarification_id,
)
from schemas import (
    AdaptationReceipt,
    AdaptationReceiptV2,
    AgentActionReceipt,
    ArtifactFeedbackDecisionRequest,
    ArtifactFeedbackReference,
    ArtifactReference,
    ChatResponse,
    CollaborativeNoteDecisionRequest,
    CollaborativeNoteEvent,
    ContinuityChoice,
    ContinuitySelectionRequest,
    ContinuitySourceReceipt,
    MemoryDecisionRequest,
    MemoryClarificationReceipt,
    MemoryClarificationSelectionRequest,
    MemoryProposalReceipt,
)
from working_state import WorkingStateSnapshot


NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def make_working_state_snapshot(**overrides) -> WorkingStateSnapshot:
    values = {
        "user_id": "user-1",
        "project_id": "agent-col",
        "session_id": "session-1",
        "source_message_id": "message-1",
        "request_summary": "Deployment plan with Cloud Run under consideration.",
        "current_goal": "Choose a deployment plan.",
        "intent_hypothesis": (
            "The user likely wants a secure deployment plan and is unsure "
            "whether background workers are necessary."
        ),
        "active_constraints": ("security matters more than speed",),
        "unresolved_questions": (),
        "clarification_status": "useful",
        "next_step_hypothesis": (
            "Prefer a synchronous MVP unless durability becomes required."
        ),
        "confidence": "medium",
        "updated_at": NOW,
    }
    values.update(overrides)
    return WorkingStateSnapshot(**values)


def test_adaptation_receipt_documents_accept_v2_receipts() -> None:
    receipt = AdaptationReceiptV2(
        signal_id="development_environments--signal-v2",
        category="development_environments",
        value=["linux", "macos"],
        source_event_id=(
            "development_environments--signal-v2--approved"
        ),
        status="provided_to_model",
    )

    documents = MemoryEngine._adaptation_receipt_documents((receipt,))

    assert documents == [receipt.model_dump(mode="python")]


def install_transaction_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def run_without_sdk_retry(callback):
        async def run(transaction, *args, **kwargs):
            return await callback(transaction, *args, **kwargs)

        return run

    monkeypatch.setattr(
        "database.firestore.async_transactional",
        run_without_sdk_retry,
    )


def snapshot(
    *, exists: bool, data: dict[str, object] | None = None
) -> SimpleNamespace:
    return SimpleNamespace(exists=exists, to_dict=lambda: data)


def working_state_store(
    *,
    session_exists: bool = True,
    session_data: dict[str, object] | None = None,
    state_exists: bool = True,
    state_data: dict[str, object] | None = None,
) -> SimpleNamespace:
    client = MagicMock()
    sessions = MagicMock()
    session = MagicMock()
    working_state = MagicMock()
    current = MagicMock()
    client.collection.return_value = sessions
    sessions.document.return_value = session

    def session_collection(name: str) -> MagicMock:
        if name == "working_state":
            return working_state
        raise AssertionError(f"Unexpected collection: {name}")

    session.collection.side_effect = session_collection
    working_state.document.return_value = current
    current.set = AsyncMock()
    session.get = AsyncMock(
        return_value=snapshot(
            exists=session_exists,
            data=session_data
            if session_data is not None
            else {"project_id": "agent-col", "user_id": "user-1"},
        )
    )
    current.get = AsyncMock(
        return_value=snapshot(exists=state_exists, data=state_data)
    )
    return SimpleNamespace(
        client=client,
        session=session,
        working_state=working_state,
        current=current,
    )


class ChatTurnStore:
    def __init__(self, ids: ChatTurnIds) -> None:
        self.client = MagicMock()
        self.sessions = MagicMock()
        self.session_ref = MagicMock()
        self.turns = MagicMock()
        self.messages = MagicMock()
        self.turn_ref = MagicMock()
        self.user_message_ref = MagicMock()
        self.model_message_ref = MagicMock()
        self.transaction = MagicMock()

        self.client.collection.return_value = self.sessions
        self.sessions.document.return_value = self.session_ref

        def session_collection(name: str) -> MagicMock:
            if name == "turns":
                return self.turns
            if name == "messages":
                return self.messages
            raise AssertionError(f"Unexpected collection: {name}")

        def message_document(message_id: str) -> MagicMock:
            if message_id == ids.user_message_id:
                return self.user_message_ref
            if message_id == ids.model_message_id:
                return self.model_message_ref
            raise AssertionError(f"Unexpected message ID: {message_id}")

        self.session_ref.collection.side_effect = session_collection
        self.turns.document.return_value = self.turn_ref
        self.messages.document.side_effect = message_document
        self.client.transaction.return_value = self.transaction
        self.session_ref.get = AsyncMock(
            return_value=snapshot(
                exists=True,
                data={"project_id": "agent-col", "user_id": "user-1"},
            )
        )


class ArtifactEffectStore(ChatTurnStore):
    def __init__(self, ids: ChatTurnIds) -> None:
        super().__init__(ids)
        self.projects = MagicMock()
        self.project_ref = MagicMock()
        self.blueprints = MagicMock()
        self.blueprint_ref = MagicMock()
        self.artifacts = MagicMock()
        self.artifact_ref = MagicMock()

        def root_collection(name: str) -> MagicMock:
            if name == "sessions":
                return self.sessions
            if name == "projects":
                return self.projects
            raise AssertionError(f"Unexpected root collection: {name}")

        self.client.collection.side_effect = root_collection
        self.projects.document.return_value = self.project_ref
        def project_collection(name: str) -> MagicMock:
            if name == "blueprints":
                return self.blueprints
            if name == "artifacts":
                return self.artifacts
            raise AssertionError(f"Unexpected project collection: {name}")

        self.project_ref.collection.side_effect = project_collection
        self.blueprints.document.return_value = self.blueprint_ref
        self.artifacts.document.return_value = self.artifact_ref


class FeedbackEffectStore(ChatTurnStore):
    def __init__(self, ids: ChatTurnIds) -> None:
        super().__init__(ids)
        self.projects = MagicMock()
        self.project_ref = MagicMock()
        self.blueprints = MagicMock()
        self.blueprint_ref = MagicMock()
        self.feedback_collection = MagicMock()
        self.feedback_ref = MagicMock()
        self.prior_feedback_ref = MagicMock()
        self.supersessions_collection = MagicMock()
        self.supersession_ref = MagicMock()

        def root_collection(name: str) -> MagicMock:
            if name == "sessions":
                return self.sessions
            if name == "projects":
                return self.projects
            raise AssertionError(f"Unexpected root collection: {name}")

        self.client.collection.side_effect = root_collection
        self.projects.document.return_value = self.project_ref
        self.project_ref.collection.return_value = self.blueprints
        self.blueprints.document.return_value = self.blueprint_ref

        def blueprint_collection(name: str) -> MagicMock:
            if name == "feedback":
                return self.feedback_collection
            if name == "feedback_supersessions":
                return self.supersessions_collection
            raise AssertionError(f"Unexpected blueprint collection: {name}")

        def feedback_document(feedback_id: str) -> MagicMock:
            if feedback_id == "feedback--prior-event":
                return self.prior_feedback_ref
            return self.feedback_ref

        self.blueprint_ref.collection.side_effect = blueprint_collection
        self.feedback_collection.document.side_effect = feedback_document
        self.supersessions_collection.document.return_value = (
            self.supersession_ref
        )


def turn_document(
    ids: ChatTurnIds,
    *,
    status: str = "in_progress",
    project_id: str = "agent-col",
    user_id: str = "user-1",
    owner: str = "existing-owner",
    lease_expires_at: datetime = NOW + timedelta(seconds=30),
) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": "1.0",
        "status": status,
        "project_id": project_id,
        "user_id": user_id,
        "memory_decision": None,
        "user_message_id": ids.user_message_id,
        "model_message_id": ids.model_message_id,
        "created_at": NOW - timedelta(seconds=1),
        "updated_at": NOW - timedelta(seconds=1),
    }
    if status == "in_progress":
        data["lease_owner"] = owner
        data["lease_expires_at"] = lease_expires_at
    else:
        data.update(
            {
                "actions": [],
                "artifacts": [],
                "artifact_feedback": [],
                "citations": [],
                "memory_proposals": [],
                "memory_clarifications": [],
                "collaborative_note_proposals": [],
                "collaborative_note_events": [],
                "adaptations": [],
                "completed_at": NOW - timedelta(seconds=1),
            }
        )
    return data


def user_message_document(
    text: str = "Remember one logical turn.",
) -> dict[str, object]:
    return {"role": "user", "text": text, "timestamp": NOW}


def proposal_action_document() -> dict[str, str]:
    return {
        "action_name": "propose_memory_signal",
        "status": "completed",
    }


def proposal_receipt_document() -> dict[str, object]:
    return {
        "proposal_id": "response_length--proposal-1",
        "category": "response_length",
        "proposed_value": "concise",
        "expires_at": NOW + timedelta(hours=24),
    }


def continuity_receipt_document() -> dict[str, object]:
    return {
        "receipt_id": "continuity--note-1--rev-2",
        "source_kind": "collaborative_note",
        "source_id": "note-1",
        "display_label": "Used note: Export workflow requirements",
        "match_reason": "exact_title",
        "source_updated_at": NOW,
    }


def continuity_choice_document() -> dict[str, object]:
    return {
        "choice_id": "choice-1",
        "source_kind": "collaborative_note",
        "source_id": "note-1",
        "display_label": "Export workflow requirements",
        "match_reason": "bounded_relevance",
    }


def clarification_receipt_document() -> dict[str, object]:
    return {
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
        "expires_at": NOW + timedelta(minutes=15),
    }


def note_decision_request(
    *,
    decision: str = "approve",
) -> CollaborativeNoteDecisionRequest:
    return CollaborativeNoteDecisionRequest(
        proposal_id="note-proposal-1",
        decision=decision,
    )


def note_event_document(event_type: str = "approved") -> dict[str, object]:
    return {
        "note_contract_version": "1.0",
        "event_id": f"note-1--{event_type}--note-proposal-1",
        "note_id": "note-1",
        "proposal_id": "note-proposal-1",
        "owner_user_id": "user-1",
        "workspace_id": "agent-col",
        "event_type": event_type,
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "source_session_id": "session-1",
        "source_message_ids": ["turn-message-1"],
        "revision": 1,
        "previous_revision": None,
        "created_at": NOW,
    }


def active_clarification_envelope_document(
    *, status: str = "open", expires_at: datetime | None = None
) -> dict[str, object]:
    return MemoryClarificationEnvelope.model_validate(
        {
            "clarification_id": derive_memory_clarification_id(
                user_id="user-1",
                session_id="session-1",
                evidence_message_id="message-1",
                clarification_turn_id="a" * 64,
            ),
            "user_id": "user-1",
            "session_id": "session-1",
            "workspace_id": "agent-col",
            "evidence_message_id": "message-1",
            "clarification_turn_id": "a" * 64,
            "candidates": [
                {
                    "category": "response_length",
                    "canonical_value": "detailed",
                },
                {
                    "category": "explanation_structure",
                    "canonical_value": "step_by_step",
                },
            ],
            "created_at": NOW - timedelta(minutes=5),
            "expires_at": expires_at or NOW + timedelta(minutes=10),
            "status": status,
            **(
                {
                    "consuming_turn_id": "b" * 64,
                    "consuming_message_id": "message-2",
                    "selected_candidate_index": 0,
                }
                if status == "consumed"
                else {}
            ),
        }
    ).model_dump(mode="python", exclude_none=True)


def chat_session_detail_store(
    *, clarification_document: dict[str, object]
) -> SimpleNamespace:
    client = MagicMock()
    sessions = MagicMock()
    session = MagicMock()
    messages = MagicMock()
    query = MagicMock()
    clarifications = MagicMock()
    clarification = MagicMock()
    client.collection.return_value = sessions
    sessions.document.return_value = session

    def session_collection(name: str) -> MagicMock:
        if name == "messages":
            return messages
        if name == "memory_clarifications":
            return clarifications
        raise AssertionError(f"Unexpected collection: {name}")

    async def empty_stream():
        if False:
            yield None

    session.collection.side_effect = session_collection
    session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "user_id": "user-1",
                "project_id": "agent-col",
                "active_memory_clarification_id": (
                    clarification_document["clarification_id"]
                ),
            },
        )
    )
    messages.order_by.return_value = query
    query.limit.return_value = query
    query.stream.side_effect = empty_stream
    clarifications.document.return_value = clarification
    clarification.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=clarification_document,
        )
    )
    return SimpleNamespace(
        client=client,
        clarification=clarification,
    )


@pytest.mark.asyncio
async def test_get_working_state_returns_current_session_snapshot() -> None:
    expected = make_working_state_snapshot()
    store = working_state_store(
        state_data=expected.model_dump(mode="python")
    )

    result = await MemoryEngine(store.client).get_working_state(
        user_id="user-1",
        project_id="agent-col",
        session_id="session-1",
    )

    assert result == expected
    store.session.collection.assert_called_once_with("working_state")
    store.working_state.document.assert_called_once_with("current")


@pytest.mark.asyncio
async def test_get_working_state_returns_none_when_session_state_absent() -> None:
    store = working_state_store(state_exists=False)

    result = await MemoryEngine(store.client).get_working_state(
        user_id="user-1",
        project_id="agent-col",
        session_id="session-1",
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_working_state_rejects_session_ownership_mismatch() -> None:
    store = working_state_store(
        session_data={"project_id": "other-project", "user_id": "other-user"},
    )

    with pytest.raises(ChatSessionOwnershipError):
        await MemoryEngine(store.client).get_working_state(
            user_id="user-1",
            project_id="agent-col",
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_get_working_state_rejects_invalid_stored_state() -> None:
    invalid = make_working_state_snapshot().model_dump(mode="python")
    invalid["request_summary"] = "x" * 201
    store = working_state_store(state_data=invalid)

    with pytest.raises(ValueError, match="Stored working state is invalid."):
        await MemoryEngine(store.client).get_working_state(
            user_id="user-1",
            project_id="agent-col",
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_save_working_state_writes_current_session_snapshot() -> None:
    expected = make_working_state_snapshot(updated_at=None)
    store = working_state_store(state_exists=False)

    await MemoryEngine(store.client).save_working_state(
        expected,
        observed_at=NOW,
    )

    store.session.get.assert_awaited_once()
    store.session.collection.assert_called_once_with("working_state")
    store.working_state.document.assert_called_once_with("current")
    store.current.set.assert_awaited_once()
    written_data = store.current.set.await_args.args[0]
    assert written_data["schema_version"] == "1.0"
    assert written_data["authority"] == "non_authoritative"
    assert written_data["user_id"] == "user-1"
    assert written_data["project_id"] == "agent-col"
    assert written_data["session_id"] == "session-1"
    assert written_data["updated_at"] == NOW


@pytest.mark.asyncio
async def test_chat_session_detail_recovers_owned_active_clarification(
) -> None:
    store = chat_session_detail_store(
        clarification_document=active_clarification_envelope_document()
    )

    result = await MemoryEngine(store.client).get_chat_session_detail(
        user_id="user-1",
        project_id="agent-col",
        session_id="session-1",
        limit=100,
        observed_at=NOW,
    )

    expected = clarification_receipt_document()
    expected["clarification_id"] = active_clarification_envelope_document()[
        "clarification_id"
    ]
    expected["expires_at"] = NOW + timedelta(minutes=10)
    assert result.active_memory_clarification == MemoryClarificationReceipt(
        **expected
    )


@pytest.mark.asyncio
async def test_chat_session_detail_omits_expired_active_clarification(
) -> None:
    store = chat_session_detail_store(
        clarification_document=active_clarification_envelope_document(
            expires_at=NOW - timedelta(minutes=1)
        )
    )

    result = await MemoryEngine(store.client).get_chat_session_detail(
        user_id="user-1",
        project_id="agent-col",
        session_id="session-1",
        limit=100,
        observed_at=NOW,
    )

    assert result.active_memory_clarification is None


def blueprint_action_document() -> dict[str, str]:
    return {
        "action_name": "synthesize_project",
        "status": "completed",
    }


def blueprint_reference_document(
    ids: ChatTurnIds,
) -> dict[str, str]:
    return {
        "artifact_type": "synthesis_blueprint",
        "project_id": "agent-col",
        "artifact_id": f"blueprint--{ids.turn_id}",
        "schema_version": "2.0",
        "display_label": "Agent Col blueprint",
    }


def adaptation_receipt_document(
    *,
    value: str = "micro_steps",
) -> dict[str, str]:
    return {
        "signal_id": "planning-granularity-signal-1",
        "category": "planning_granularity",
        "value": value,
        "source_event_id": "planning-granularity-signal-1--approved",
        "status": "provided_to_model",
    }


def feedback_action_document() -> dict[str, str]:
    return {
        "action_name": "record_blueprint_feedback",
        "status": "completed",
    }


def feedback_reference_document(
    ids: ChatTurnIds,
    *,
    created_at: datetime = NOW,
) -> dict[str, object]:
    return {
        "feedback_id": f"feedback--{ids.turn_id}",
        "artifact_id": "blueprint-1",
        "target_id": "target--0123456789abcdef01234567",
        "target_kind": "whole_blueprint",
        "decision": "accepted",
        "schema_version": "2.0",
        "created_at": created_at,
    }


def stored_blueprint_effect_document(
    ids: ChatTurnIds,
    *,
    originating_turn_id: str | None = None,
) -> dict[str, object]:
    return {
        "artifact_contract_version": "1.0",
        "artifact_type": "synthesis_blueprint",
        "created_at": NOW,
        "originating_session_id": "session-1",
        "originating_turn_id": originating_turn_id or ids.turn_id,
        "user_id": "user-1",
        "model_name": "gemini-3.6-flash",
        "schema_version": "2.0",
        "parent_artifact_id": None,
        "feedback_counts": {
            "accepted": 0,
            "rejected": 0,
            "edited": 0,
        },
        "adaptation_receipts": [],
        "applied_feedback_ids": [],
        "blueprint": {
            "synthesized_conceptual_model": {
                "project_name": "Bounded Collaboration",
            }
        },
    }


def artifact_feedback_request(
    *,
    decision: str = "accepted",
    feedback_text: str = "This boundary is correct.",
    supersedes_feedback_id: str | None = None,
) -> ArtifactFeedbackDecisionRequest:
    return ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision=decision,
        feedback_text=feedback_text,
        expected_schema_version="2.0",
        supersedes_feedback_id=supersedes_feedback_id,
    )


def feedback_turn_claim() -> tuple[FeedbackEffectStore, ChatTurnClaim]:
    ids = derive_chat_turn_ids("artifact-feedback-request-1")
    store = FeedbackEffectStore(ids)
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="I accept this blueprint boundary.",
        artifact_feedback_decision=artifact_feedback_request(),
    )
    claim = ChatTurnClaim(
        request=request,
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    stored_turn = turn_document(
        ids,
        owner="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    stored_turn["artifact_feedback_decision"] = (
        artifact_feedback_request().model_dump(mode="json")
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **stored_blueprint_effect_document(ids),
                "originating_turn_id": "different-origin-turn",
                "originating_session_id": "artifact-origin-session",
                "feedback_counts": {
                    "accepted": 0,
                    "rejected": 1,
                    "edited": 0,
                },
            },
        )
    )
    store.feedback_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    return store, claim


@pytest.mark.asyncio
async def test_record_chat_turn_feedback_effect_is_atomic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = feedback_turn_claim()

    result = await MemoryEngine(
        store.client
    ).record_chat_turn_artifact_feedback_effect(
        claim,
        target_kind="whole_blueprint",
        observed_at=NOW,
    )

    expected_action = AgentActionReceipt(
        action_name="record_blueprint_feedback",
        status="completed",
    )
    expected_feedback = ArtifactFeedbackReference(
        feedback_id=f"feedback--{claim.ids.turn_id}",
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        target_kind="whole_blueprint",
        decision="accepted",
        schema_version="2.0",
        created_at=NOW,
    )
    assert result.action == expected_action
    assert result.feedback == expected_feedback
    assert result.claim.precompleted_actions == (expected_action,)
    assert result.claim.precompleted_artifact_feedback == (
        expected_feedback,
    )
    feedback_document = store.transaction.set.call_args_list[1].args[1]
    assert feedback_document == {
        "feedback_contract_version": "1.0",
        "feedback_id": f"feedback--{claim.ids.turn_id}",
        "artifact_id": "blueprint-1",
        "target_id": "target--0123456789abcdef01234567",
        "target_kind": "whole_blueprint",
        "decision": "accepted",
        "feedback_text": "This boundary is correct.",
        "correction_text": None,
        "originating_session_id": "session-1",
        "source_message_id": claim.ids.user_message_id,
        "originating_turn_id": claim.ids.turn_id,
        "user_id": "user-1",
        "schema_version": "2.0",
        "created_at": NOW,
        "status": "active",
        "supersedes_feedback_id": None,
    }
    assert store.transaction.set.call_args_list[2] == call(
        store.blueprint_ref,
        {
            "feedback_counts": {
                "accepted": 1,
                "rejected": 1,
                "edited": 0,
            }
        },
        merge=True,
    )
    assert store.transaction.set.call_args_list[3] == call(
        store.turn_ref,
        {
            "actions": [expected_action.model_dump(mode="python")],
            "artifact_feedback": [
                expected_feedback.model_dump(mode="python")
            ],
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_record_chat_turn_feedback_supersession_is_immutable_and_atomic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("artifact-feedback-supersession-1")
    store = FeedbackEffectStore(ids)
    prior_feedback_id = "feedback--prior-event"
    feedback_request = artifact_feedback_request(
        decision="rejected",
        feedback_text="I am reversing my earlier acceptance.",
        supersedes_feedback_id=prior_feedback_id,
    )
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-2",
            user_id="user-1",
            message="Reverse my earlier artifact feedback.",
            artifact_feedback_decision=feedback_request,
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    stored_turn = turn_document(
        ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["artifact_feedback_decision"] = (
        feedback_request.model_dump(mode="json")
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **stored_blueprint_effect_document(ids),
                "user_id": "user-1",
                "feedback_counts": {
                    "accepted": 1,
                    "rejected": 0,
                    "edited": 0,
                },
            },
        )
    )
    store.feedback_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.prior_feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "feedback_contract_version": "1.0",
                "feedback_id": prior_feedback_id,
                "artifact_id": "blueprint-1",
                "target_id": "target--0123456789abcdef01234567",
                "target_kind": "whole_blueprint",
                "decision": "accepted",
                "feedback_text": "This boundary is correct.",
                "correction_text": None,
                "originating_session_id": "session-1",
                "source_message_id": "message-1",
                "originating_turn_id": "prior-turn",
                "user_id": "user-1",
                "schema_version": "2.0",
                "created_at": NOW - timedelta(minutes=10),
                "status": "active",
                "supersedes_feedback_id": None,
            },
        )
    )
    store.supersession_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    result = await MemoryEngine(
        store.client
    ).record_chat_turn_artifact_feedback_effect(
        claim,
        target_kind="whole_blueprint",
        observed_at=NOW,
    )

    assert result.feedback.decision == "rejected"
    assert store.supersessions_collection.document.call_args == call(
        prior_feedback_id
    )
    assert store.transaction.set.call_args_list[1].args[1][
        "supersedes_feedback_id"
    ] == prior_feedback_id
    assert store.transaction.set.call_args_list[2] == call(
        store.supersession_ref,
        {
            "supersession_contract_version": "1.0",
            "supersedes_feedback_id": prior_feedback_id,
            "superseded_by_feedback_id": f"feedback--{ids.turn_id}",
            "created_at": NOW,
        },
    )
    assert store.transaction.set.call_args_list[3] == call(
        store.blueprint_ref,
        {
            "feedback_counts": {
                "accepted": 0,
                "rejected": 1,
                "edited": 0,
            }
        },
        merge=True,
    )
    assert all(
        item.args[0] is not store.prior_feedback_ref
        for item in store.transaction.set.call_args_list
    )


@pytest.mark.asyncio
async def test_record_chat_turn_feedback_effect_reuses_original_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = feedback_turn_claim()
    original_created_at = NOW - timedelta(minutes=5)
    stored_turn = turn_document(
        claim.ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["artifact_feedback_decision"] = (
        artifact_feedback_request().model_dump(mode="json")
    )
    stored_turn["actions"] = [feedback_action_document()]
    stored_turn["artifact_feedback"] = [
        feedback_reference_document(
            claim.ids,
            created_at=original_created_at,
        )
    ]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "feedback_contract_version": "1.0",
                "feedback_id": f"feedback--{claim.ids.turn_id}",
                "artifact_id": "blueprint-1",
                "target_id": "target--0123456789abcdef01234567",
                "target_kind": "whole_blueprint",
                "decision": "accepted",
                "feedback_text": "This boundary is correct.",
                "correction_text": None,
                "originating_session_id": "session-1",
                "source_message_id": claim.ids.user_message_id,
                "originating_turn_id": claim.ids.turn_id,
                "user_id": "user-1",
                "schema_version": "2.0",
                "created_at": original_created_at,
                "status": "active",
                "supersedes_feedback_id": None,
            },
        )
    )

    result = await MemoryEngine(
        store.client
    ).record_chat_turn_artifact_feedback_effect(
        claim,
        target_kind="whole_blueprint",
        observed_at=NOW,
    )

    assert result.feedback.created_at == original_created_at
    assert result.claim.precompleted_artifact_feedback == (result.feedback,)
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_chat_turn_feedback_effect_rejects_changed_turn_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = feedback_turn_claim()
    changed = artifact_feedback_request().model_copy(
        update={"feedback_text": "Stored request is different."}
    )
    stored_turn = turn_document(
        claim.ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["artifact_feedback_decision"] = changed.model_dump(mode="json")
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(
            store.client
        ).record_chat_turn_artifact_feedback_effect(
            claim,
            target_kind="whole_blueprint",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


def claimed_store(
    *,
    owner: str = "owner-token",
    lease_expires_at: datetime = NOW + timedelta(seconds=30),
) -> tuple[ChatTurnStore, ChatTurnClaim]:
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )
    claim = ChatTurnClaim(
        request=request,
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=turn_document(
                ids,
                owner=owner,
                lease_expires_at=lease_expires_at,
            ),
        )
    )
    return store, claim


@pytest.mark.asyncio
async def test_claim_chat_turn_atomically_creates_turn_and_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.session_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    token_hex = MagicMock(return_value="owner-token")
    monkeypatch.setattr(
        database,
        "secrets",
        SimpleNamespace(token_hex=token_hex),
        raising=False,
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    claim = await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert claim.owner_token == "owner-token"
    assert claim.resumed is False
    assert claim.lease_expires_at == NOW + timedelta(seconds=120)
    assert claim.ids == ids
    token_hex.assert_called_once_with(16)
    assert store.transaction.set.call_args_list == [
        call(
            store.session_ref,
            {
                "project_id": "agent-col",
                "user_id": "user-1",
                "updated_at": firestore.SERVER_TIMESTAMP,
                "last_message_preview": "Remember one logical turn.",
                "last_message_role": "user",
            },
            merge=True,
        ),
        call(
            store.turn_ref,
            {
                "schema_version": "1.0",
                "status": "in_progress",
                "project_id": "agent-col",
                "user_id": "user-1",
                "memory_decision": None,
                "user_message_id": ids.user_message_id,
                "model_message_id": ids.model_message_id,
                "lease_owner": "owner-token",
                "lease_expires_at": NOW + timedelta(seconds=120),
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        ),
        call(
            store.user_message_ref,
            {
                "role": "user",
                "text": "Remember one logical turn.",
                "timestamp": firestore.SERVER_TIMESTAMP,
            },
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_session",
    (
        {"project_id": "agent-col", "user_id": "different-user"},
        {"project_id": "different-project", "user_id": "user-1"},
    ),
)
async def test_claim_chat_turn_rejects_session_ownership_mismatch_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    stored_session: dict[str, object],
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.session_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_session)
    )
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    with pytest.raises(RuntimeError) as exc_info:
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    assert type(exc_info.value).__name__ == "ChatSessionOwnershipError"
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_session",
    (
        None,
        {},
        {"project_id": "agent-col", "user_id": ""},
        {"project_id": 7, "user_id": "user-1"},
    ),
)
async def test_claim_chat_turn_rejects_malformed_session_ownership_state(
    monkeypatch: pytest.MonkeyPatch,
    stored_session: object,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.session_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_session)
    )
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_preserves_matching_existing_session_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.session_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"project_id": "agent-col", "user_id": "user-1"},
        )
    )
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="request-1",
        observed_at=NOW,
    )

    store.session_ref.get.assert_awaited_once_with(
        transaction=store.transaction
    )
    session_write = store.transaction.set.call_args_list[0]
    assert session_write.args[0] is store.session_ref
    assert "project_id" not in session_write.args[1]
    assert "user_id" not in session_write.args[1]


@pytest.mark.asyncio
async def test_claim_chat_turn_establishes_new_session_owner_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.session_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="request-1",
        observed_at=NOW,
    )

    store.session_ref.get.assert_awaited_once_with(
        transaction=store.transaction
    )
    assert store.transaction.set.call_args_list[0] == call(
        store.session_ref,
        {
            "project_id": "agent-col",
            "user_id": "user-1",
            "updated_at": firestore.SERVER_TIMESTAMP,
            "last_message_preview": "Remember one logical turn.",
            "last_message_role": "user",
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_claim_chat_turn_persists_structured_feedback_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("artifact-feedback-request-1")
    store = ChatTurnStore(ids)
    store.session_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    monkeypatch.setattr(database.secrets, "token_hex", lambda _: "owner-token")
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="I accept this blueprint boundary.",
        artifact_feedback_decision=artifact_feedback_request(),
    )

    await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="artifact-feedback-request-1",
        observed_at=NOW,
    )

    stored_turn = store.transaction.set.call_args_list[1].args[1]
    assert stored_turn["artifact_feedback_decision"] == (
        artifact_feedback_request().model_dump(mode="json")
    )


@pytest.mark.asyncio
async def test_claim_chat_turn_persists_clarification_selection_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("clarification-selection-request-1")
    store = ChatTurnStore(ids)
    store.session_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    selection = MemoryClarificationSelectionRequest(
        clarification_id="memory-clarification--clarification-1",
        selected_candidate_index=1,
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Save the explanation structure preference.",
        memory_clarification_selection=selection,
    )

    await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="clarification-selection-request-1",
        observed_at=NOW,
    )

    stored_turn = store.transaction.set.call_args_list[1].args[1]
    assert stored_turn["memory_clarification_selection"] == (
        selection.model_dump(mode="json")
    )


@pytest.mark.asyncio
async def test_claim_chat_turn_persists_collaborative_note_decision_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("note-decision-request-1")
    store = ChatTurnStore(ids)
    store.session_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    monkeypatch.setattr(database.secrets, "token_hex", lambda _: "owner-token")
    decision = note_decision_request()
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Approve that note.",
        collaborative_note_decision=decision,
    )

    await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="note-decision-request-1",
        observed_at=NOW,
    )

    stored_turn = store.transaction.set.call_args_list[1].args[1]
    assert stored_turn["collaborative_note_decision"] == (
        decision.model_dump(mode="json")
    )


@pytest.mark.asyncio
async def test_claim_chat_turn_persists_continuity_selection_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("continuity-selection-request-1")
    store = ChatTurnStore(ids)
    store.session_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(return_value=snapshot(exists=False))
    selection = ContinuitySelectionRequest(
        choice_id="choice-1",
        source_kind="collaborative_note",
        source_id="note-1",
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Use the selected note.",
        continuity_selection=selection,
    )

    await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="continuity-selection-request-1",
        observed_at=NOW,
    )

    stored_turn = store.transaction.set.call_args_list[1].args[1]
    assert stored_turn["continuity_selection"] == selection.model_dump(
        mode="json"
    )


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_request_mismatch_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document(ids))
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=user_message_document("different message"),
        )
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    with pytest.raises(ChatTurnConflictError):
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_changed_feedback_with_same_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(ids)
    stored_turn["artifact_feedback_decision"] = (
        artifact_feedback_request().model_dump(mode="json")
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    changed = artifact_feedback_request().model_copy(
        update={"feedback_text": "This is a changed decision."}
    )

    with pytest.raises(ChatTurnConflictError):
        await MemoryEngine(store.client).claim_chat_turn(
            ChatTurnRequest(
                project_id="agent-col",
                session_id="session-1",
                user_id="user-1",
                message="Remember one logical turn.",
                artifact_feedback_decision=changed,
            ),
            idempotency_key="request-1",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_changed_clarification_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(ids)
    stored_turn["memory_clarification_selection"] = {
        "clarification_id": "memory-clarification--clarification-1",
        "selected_candidate_index": 0,
    }
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )

    with pytest.raises(ChatTurnConflictError):
        await MemoryEngine(store.client).claim_chat_turn(
            ChatTurnRequest(
                project_id="agent-col",
                session_id="session-1",
                user_id="user-1",
                message="Remember one logical turn.",
                memory_clarification_selection=(
                    MemoryClarificationSelectionRequest(
                        clarification_id=(
                            "memory-clarification--clarification-1"
                        ),
                        selected_candidate_index=1,
                    )
                ),
            ),
            idempotency_key="request-1",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_unexpired_lease_with_retry_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document(ids))
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=user_message_document(),
        )
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    with pytest.raises(ChatTurnInProgressError) as caught:
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW + timedelta(milliseconds=500),
        )

    assert caught.value.retry_after_seconds == 30
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_reclaims_expired_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=turn_document(
                ids,
                lease_expires_at=NOW - timedelta(seconds=1),
            ),
        )
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    monkeypatch.setattr(database.secrets, "token_hex", lambda _: "new-owner")
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    claim = await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert claim.resumed is True
    assert claim.owner_token == "new-owner"
    store.transaction.set.assert_called_once_with(
        store.turn_ref,
        {
            "lease_owner": "new-owner",
            "lease_expires_at": NOW + timedelta(seconds=120),
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_reclaimed_chat_turn_recovers_precompleted_proposal_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(
        ids,
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    stored_turn["actions"] = [proposal_action_document()]
    stored_turn["memory_proposals"] = [proposal_receipt_document()]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    monkeypatch.setattr(database.secrets, "token_hex", lambda _: "new-owner")

    claim = await MemoryEngine(store.client).claim_chat_turn(
        ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Remember one logical turn.",
        ),
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert claim.precompleted_actions == (
        AgentActionReceipt(
            action_name="propose_memory_signal",
            status="completed",
        ),
    )
    assert claim.precompleted_memory_proposals == (
        MemoryProposalReceipt.model_validate(proposal_receipt_document()),
    )


@pytest.mark.asyncio
async def test_reclaimed_chat_turn_recovers_precompleted_clarification_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(
        ids,
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    stored_turn["memory_clarifications"] = [
        clarification_receipt_document()
    ]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    monkeypatch.setattr(database.secrets, "token_hex", lambda _: "new-owner")

    claim = await MemoryEngine(store.client).claim_chat_turn(
        ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Remember one logical turn.",
        ),
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert claim.precompleted_memory_clarifications == (
        MemoryClarificationReceipt.model_validate(
            clarification_receipt_document()
        ),
    )


@pytest.mark.asyncio
async def test_reclaimed_chat_turn_recovers_precompleted_artifact_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(
        ids,
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    stored_turn["actions"] = [blueprint_action_document()]
    stored_turn["artifacts"] = [blueprint_reference_document(ids)]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    monkeypatch.setattr(database.secrets, "token_hex", lambda _: "new-owner")

    claim = await MemoryEngine(store.client).claim_chat_turn(
        ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Remember one logical turn.",
        ),
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert claim.precompleted_actions == (
        AgentActionReceipt.model_validate(blueprint_action_document()),
    )
    assert claim.precompleted_artifacts == (
        ArtifactReference.model_validate(blueprint_reference_document(ids)),
    )


@pytest.mark.asyncio
async def test_reclaimed_chat_turn_recovers_precompleted_feedback_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(
        ids,
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    stored_turn["artifact_feedback_decision"] = (
        artifact_feedback_request().model_dump(mode="json")
    )
    stored_turn["actions"] = [feedback_action_document()]
    stored_turn["artifact_feedback"] = [feedback_reference_document(ids)]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    monkeypatch.setattr(database.secrets, "token_hex", lambda _: "new-owner")

    claim = await MemoryEngine(store.client).claim_chat_turn(
        ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Remember one logical turn.",
            artifact_feedback_decision=artifact_feedback_request(),
        ),
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert claim.precompleted_actions == (
        AgentActionReceipt.model_validate(feedback_action_document()),
    )
    assert claim.precompleted_artifact_feedback == (
        ArtifactFeedbackReference.model_validate(
            feedback_reference_document(ids)
        ),
    )


@pytest.mark.asyncio
async def test_claim_chat_turn_replays_completed_response_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=turn_document(ids, status="completed"),
        )
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"role": "model", "text": "Durable answer.", "timestamp": NOW},
        )
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    result = await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert result == ChatTurnReplay(
        response=ChatResponse(response="Durable answer.")
    )
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_completed_chat_turn_replay_preserves_feedback_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(ids, status="completed")
    stored_turn["artifact_feedback_decision"] = (
        artifact_feedback_request().model_dump(mode="json")
    )
    stored_turn["actions"] = [feedback_action_document()]
    stored_turn["artifact_feedback"] = [feedback_reference_document(ids)]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"role": "model", "text": "Recorded.", "timestamp": NOW},
        )
    )

    result = await MemoryEngine(store.client).claim_chat_turn(
        ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Remember one logical turn.",
            artifact_feedback_decision=artifact_feedback_request(),
        ),
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert isinstance(result, ChatTurnReplay)
    assert result.response.artifact_feedback == [
        ArtifactFeedbackReference.model_validate(
            feedback_reference_document(ids)
        )
    ]
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_completed_chat_turn_replay_preserves_memory_proposal_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(ids, status="completed")
    stored_turn["actions"] = [proposal_action_document()]
    stored_turn["memory_proposals"] = [proposal_receipt_document()]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"role": "model", "text": "Durable answer.", "timestamp": NOW},
        )
    )

    result = await MemoryEngine(store.client).claim_chat_turn(
        ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Remember one logical turn.",
        ),
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert isinstance(result, ChatTurnReplay)
    assert result.response.actions == [
        AgentActionReceipt(
            action_name="propose_memory_signal",
            status="completed",
        )
    ]
    assert result.response.memory_proposals == [
        MemoryProposalReceipt.model_validate(proposal_receipt_document())
    ]
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_completed_chat_turn_replay_preserves_clarification_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(ids, status="completed")
    stored_turn["memory_clarifications"] = [
        clarification_receipt_document()
    ]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "role": "model",
                "text": "Which preference did you mean?",
                "timestamp": NOW,
            },
        )
    )

    result = await MemoryEngine(store.client).claim_chat_turn(
        ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Remember one logical turn.",
        ),
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert isinstance(result, ChatTurnReplay)
    assert result.response.memory_clarifications == [
        MemoryClarificationReceipt.model_validate(
            clarification_receipt_document()
        )
    ]
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_completed_chat_turn_replay_preserves_note_event_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(ids, status="completed")
    stored_turn["collaborative_note_decision"] = (
        note_decision_request().model_dump(mode="json")
    )
    stored_turn["actions"] = [
        {
            "action_name": "approve_collaborative_note",
            "status": "completed",
        }
    ]
    stored_turn["collaborative_note_events"] = [note_event_document()]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"role": "model", "text": "Recorded.", "timestamp": NOW},
        )
    )

    result = await MemoryEngine(store.client).claim_chat_turn(
        ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Remember one logical turn.",
            collaborative_note_decision=note_decision_request(),
        ),
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert isinstance(result, ChatTurnReplay)
    assert result.response.actions == [
        AgentActionReceipt(
            action_name="approve_collaborative_note",
            status="completed",
        )
    ]
    assert result.response.collaborative_note_events == [
        CollaborativeNoteEvent.model_validate(note_event_document())
    ]
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_completed_chat_turn_replay_preserves_continuity_receipts_and_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(ids, status="completed")
    stored_turn["continuity_receipts"] = [continuity_receipt_document()]
    stored_turn["continuity_choices"] = [continuity_choice_document()]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"role": "model", "text": "Use the saved note.", "timestamp": NOW},
        )
    )

    result = await MemoryEngine(store.client).claim_chat_turn(
        ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Remember one logical turn.",
        ),
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert isinstance(result, ChatTurnReplay)
    assert result.response.continuity_receipts == [
        ContinuitySourceReceipt.model_validate(continuity_receipt_document())
    ]
    assert result.response.continuity_choices == [
        ContinuityChoice.model_validate(continuity_choice_document())
    ]
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_orphaned_turn_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document(ids))
    )
    store.user_message_ref.get = AsyncMock(return_value=snapshot(exists=False))
    request = ChatTurnRequest("agent-col", "session-1", "user-1", "message")

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_missing_lease_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(ids)
    stored_turn.pop("lease_owner")
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    request = ChatTurnRequest(
        "agent-col",
        "session-1",
        "user-1",
        "Remember one logical turn.",
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_validates_before_firestore_access() -> None:
    client = MagicMock()
    request = ChatTurnRequest("agent-col", "session-1", "user-1", "message")

    with pytest.raises(ValueError, match="observed_at"):
        await MemoryEngine(client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=datetime(2026, 8, 20),
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "turn_request",
    [
        ChatTurnRequest("project/1", "session-1", "user-1", "message"),
        ChatTurnRequest("agent-col", "session 1", "user-1", "message"),
        ChatTurnRequest("agent-col", "session-1", "user.1", "message"),
        ChatTurnRequest(
            "agent-col",
            "session-1",
            "user-1",
            "message",
            cast(MemoryDecisionRequest, object()),
        ),
    ],
)
async def test_claim_chat_turn_rejects_invalid_request_before_firestore(
    turn_request: ChatTurnRequest,
) -> None:
    client = MagicMock()

    with pytest.raises(ValueError):
        await MemoryEngine(client).claim_chat_turn(
            turn_request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_two_structured_decisions_before_firestore(
) -> None:
    client = MagicMock()
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Apply both decisions.",
        memory_decision=MemoryDecisionRequest(
            proposal_id="response_length--proposal-1",
            decision="approve",
        ),
        artifact_feedback_decision=artifact_feedback_request(),
    )

    with pytest.raises(ValueError):
        await MemoryEngine(client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_preserves_firestore_failure_as_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    provider_error = ServiceUnavailable("private provider detail")
    store.turn_ref.get = AsyncMock(side_effect=provider_error)
    request = ChatTurnRequest("agent-col", "session-1", "user-1", "message")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    assert caught.value.__cause__ is provider_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_effect",
    (
        "invalid_action",
        "proposal_without_action",
        "artifact_without_action",
        "synthesis_without_artifact",
        "feedback_without_action",
    ),
)
async def test_chat_turn_operations_reject_invalid_claim_effects_before_firestore(
    monkeypatch: pytest.MonkeyPatch,
    invalid_effect: str,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    if invalid_effect == "invalid_action":
        invalid_claim = replace(
            claim,
            precompleted_actions=(cast(AgentActionReceipt, object()),),
        )
    elif invalid_effect == "proposal_without_action":
        invalid_claim = replace(
            claim,
            precompleted_memory_proposals=(
                MemoryProposalReceipt.model_validate(
                    proposal_receipt_document()
                ),
            ),
        )
    elif invalid_effect == "artifact_without_action":
        invalid_claim = replace(
            claim,
            precompleted_artifacts=(
                ArtifactReference.model_validate(
                    blueprint_reference_document(claim.ids)
                ),
            ),
        )
    elif invalid_effect == "synthesis_without_artifact":
        invalid_claim = replace(
            claim,
            precompleted_actions=(
                AgentActionReceipt.model_validate(
                    blueprint_action_document()
                ),
            ),
        )
    else:
        invalid_claim = replace(
            claim,
            precompleted_artifact_feedback=(
                ArtifactFeedbackReference.model_validate(
                    feedback_reference_document(claim.ids)
                ),
            ),
        )

    with pytest.raises(ValueError, match="claim effects"):
        await MemoryEngine(store.client).renew_chat_turn_lease(
            invalid_claim,
            observed_at=NOW,
        )

    store.turn_ref.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_renew_chat_turn_lease_extends_matching_unexpired_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()

    renewed = await MemoryEngine(store.client).renew_chat_turn_lease(
        claim,
        observed_at=NOW,
    )

    assert renewed.owner_token == claim.owner_token
    assert renewed.lease_expires_at == NOW + timedelta(seconds=120)
    store.transaction.set.assert_called_once_with(
        store.turn_ref,
        {
            "lease_expires_at": NOW + timedelta(seconds=120),
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_renew_chat_turn_lease_rejects_expired_owner_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(
        lease_expires_at=NOW - timedelta(seconds=1)
    )

    with pytest.raises(ChatTurnOwnershipError):
        await MemoryEngine(store.client).renew_chat_turn_lease(
            claim,
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_release_chat_turn_expires_matching_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()

    await MemoryEngine(store.client).release_chat_turn(
        claim,
        observed_at=NOW,
    )

    store.transaction.set.assert_called_once_with(
        store.turn_ref,
        {
            "lease_expires_at": NOW,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_release_chat_turn_recovers_completed_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    stored_turn = turn_document(
        claim.ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["actions"] = [proposal_action_document()]
    stored_turn["memory_proposals"] = [proposal_receipt_document()]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )

    released = await MemoryEngine(store.client).release_chat_turn(
        claim,
        observed_at=NOW,
    )

    assert released.precompleted_actions == (
        AgentActionReceipt.model_validate(proposal_action_document()),
    )
    assert released.precompleted_memory_proposals == (
        MemoryProposalReceipt.model_validate(proposal_receipt_document()),
    )


@pytest.mark.asyncio
async def test_release_chat_turn_recovers_feedback_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = feedback_turn_claim()
    stored_turn = turn_document(
        claim.ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["artifact_feedback_decision"] = (
        artifact_feedback_request().model_dump(mode="json")
    )
    stored_turn["actions"] = [feedback_action_document()]
    stored_turn["artifact_feedback"] = [
        feedback_reference_document(claim.ids)
    ]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )

    released = await MemoryEngine(store.client).release_chat_turn(
        claim,
        observed_at=NOW,
    )

    assert released.precompleted_artifact_feedback == (
        ArtifactFeedbackReference.model_validate(
            feedback_reference_document(claim.ids)
        ),
    )


@pytest.mark.asyncio
async def test_release_chat_turn_recovers_note_decision_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("note-decision-request-1")
    store = ChatTurnStore(ids)
    decision = note_decision_request()
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Approve that note.",
            collaborative_note_decision=decision,
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    stored_turn = turn_document(
        ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["collaborative_note_decision"] = decision.model_dump(mode="json")
    stored_turn["actions"] = [
        {
            "action_name": "approve_collaborative_note",
            "status": "completed",
        }
    ]
    stored_turn["collaborative_note_events"] = [note_event_document()]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )

    released = await MemoryEngine(store.client).release_chat_turn(
        claim,
        observed_at=NOW,
    )

    assert released.precompleted_collaborative_note_events == (
        CollaborativeNoteEvent.model_validate(note_event_document()),
    )


@pytest.mark.asyncio
async def test_release_chat_turn_is_idempotent_for_expired_matching_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(lease_expires_at=NOW)

    await MemoryEngine(store.client).release_chat_turn(
        claim,
        observed_at=NOW,
    )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_release_chat_turn_rejects_reclaimed_owner_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(owner="new-owner")

    with pytest.raises(ChatTurnOwnershipError):
        await MemoryEngine(store.client).release_chat_turn(
            claim,
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_chat_turn_blueprint_effect_writes_artifact_and_ledger_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ArtifactEffectStore(ids)
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Create a bounded collaboration blueprint.",
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=turn_document(
                ids,
                owner=claim.owner_token,
                lease_expires_at=claim.lease_expires_at,
            ),
        )
    )
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    blueprint = {
        "synthesized_conceptual_model": {
            "project_name": "Bounded Collaboration",
        }
    }
    adaptation = AdaptationReceipt.model_validate(
        adaptation_receipt_document()
    )

    result = await MemoryEngine(
        store.client
    ).record_chat_turn_blueprint_effect(
        claim,
        model_name="gemini-3.6-flash",
        schema_version="2.0",
        blueprint=blueprint,
        display_label="Bounded Collaboration",
        adaptations=(adaptation,),
        observed_at=NOW,
    )

    artifact = ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id="agent-col",
        artifact_id=f"blueprint--{ids.turn_id}",
        schema_version="2.0",
        display_label="Bounded Collaboration",
    )
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    assert result.artifact == artifact
    assert result.claim.precompleted_actions == (action,)
    assert result.claim.precompleted_artifacts == (artifact,)
    store.blueprints.document.assert_called_once_with(artifact.artifact_id)
    assert store.transaction.set.call_args_list == [
        call(
            store.project_ref,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            store.blueprint_ref,
            {
                "artifact_contract_version": "1.0",
                "artifact_type": "synthesis_blueprint",
                "created_at": firestore.SERVER_TIMESTAMP,
                "originating_session_id": "session-1",
                "originating_turn_id": ids.turn_id,
                "user_id": "user-1",
                "model_name": "gemini-3.6-flash",
                "schema_version": "2.0",
                "parent_artifact_id": None,
                "feedback_counts": {
                    "accepted": 0,
                    "rejected": 0,
                    "edited": 0,
                },
                "adaptation_receipts": [
                    adaptation.model_dump(mode="python")
                ],
                "applied_feedback_ids": [],
                "blueprint": blueprint,
            },
        ),
        call(
            store.turn_ref,
            {
                "actions": [action.model_dump(mode="python")],
                "artifacts": [artifact.model_dump(mode="python")],
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
    ]


@pytest.mark.asyncio
async def test_record_chat_turn_single_file_artifact_effect_writes_artifact_and_ledger_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-generic-artifact-1")
    store = ArtifactEffectStore(ids)
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Create a Python password generator artifact.",
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=turn_document(
                ids,
                owner=claim.owner_token,
                lease_expires_at=claim.lease_expires_at,
            ),
        )
    )
    store.artifact_ref.get = AsyncMock(return_value=snapshot(exists=False))
    artifact_document = {
        "artifact_family": "code",
        "format": "python",
        "filename": "password_generator.py",
        "content": "import secrets\nprint(secrets.token_urlsafe(12))\n",
        "summary": "Password Generator",
    }

    result = await MemoryEngine(
        store.client
    ).record_chat_turn_single_file_artifact_effect(
        claim,
        model_name="gemini-3.6-flash",
        artifact=artifact_document,
        display_label="Password Generator",
        observed_at=NOW,
    )

    artifact = ArtifactReference(
        artifact_type="single_file_artifact",
        project_id="agent-col",
        artifact_id=f"artifact--{ids.turn_id}",
        schema_version="1.0",
        display_label="Password Generator",
    )
    action = AgentActionReceipt(
        action_name="create_artifact",
        status="completed",
    )
    assert result.artifact == artifact
    assert result.claim.precompleted_actions == (action,)
    assert result.claim.precompleted_artifacts == (artifact,)
    store.artifacts.document.assert_called_once_with(artifact.artifact_id)
    assert store.transaction.set.call_args_list == [
        call(
            store.project_ref,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            store.artifact_ref,
            {
                "artifact_contract_version": "1.0",
                "artifact_type": "single_file_artifact",
                "created_at": firestore.SERVER_TIMESTAMP,
                "originating_session_id": "session-1",
                "originating_turn_id": ids.turn_id,
                "user_id": "user-1",
                "model_name": "gemini-3.6-flash",
                    "schema_version": "1.0",
                    "display_label": "Password Generator",
                    "lifecycle_status": "active",
                    "filename": "password_generator.py",
                "artifact_family": "code",
                "format": "python",
                "byte_size": 48,
                "content": "import secrets\nprint(secrets.token_urlsafe(12))\n",
                "summary": "Password Generator",
            },
        ),
        call(
            store.turn_ref,
            {
                "actions": [action.model_dump(mode="python")],
                "artifacts": [artifact.model_dump(mode="python")],
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
    ]


@pytest.mark.asyncio
async def test_record_chat_turn_blueprint_effect_rejects_feedback_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-feedback-conflict")
    store = ArtifactEffectStore(ids)
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Create a bounded collaboration blueprint.",
            artifact_feedback_decision=artifact_feedback_request(),
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    stored_turn = turn_document(
        ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["artifact_feedback_decision"] = (
        artifact_feedback_request().model_dump(mode="json")
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.blueprint_ref.get = AsyncMock(return_value=snapshot(exists=False))

    with pytest.raises(
        ValueError,
        match="artifact turns cannot contain artifact-feedback decisions",
    ):
        await MemoryEngine(store.client).record_chat_turn_blueprint_effect(
            claim,
            model_name="gemini-3.6-flash",
            schema_version="2.0",
            blueprint={
                "synthesized_conceptual_model": {
                    "project_name": "Bounded Collaboration",
                }
            },
            display_label="Bounded Collaboration",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_chat_turn_blueprint_effect_rejects_mismatched_stored_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ArtifactEffectStore(ids)
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Create a bounded collaboration blueprint.",
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=True,
        precompleted_actions=(
            AgentActionReceipt.model_validate(blueprint_action_document()),
        ),
        precompleted_artifacts=(
            ArtifactReference.model_validate(
                blueprint_reference_document(ids)
            ),
        ),
    )
    stored_turn = turn_document(
        ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["actions"] = [blueprint_action_document()]
    stored_turn["artifacts"] = [blueprint_reference_document(ids)]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=stored_blueprint_effect_document(
                ids,
                originating_turn_id="different-turn",
            ),
        )
    )

    with pytest.raises(ChatTurnStateError, match="blueprint document"):
        await MemoryEngine(store.client).record_chat_turn_blueprint_effect(
            claim,
            model_name="gemini-3.6-flash",
            schema_version="2.0",
            blueprint={
                "synthesized_conceptual_model": {
                    "project_name": "Bounded Collaboration",
                }
            },
            display_label="Bounded Collaboration",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_chat_turn_blueprint_effect_reuses_owned_effect_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ArtifactEffectStore(ids)
    artifact = ArtifactReference.model_validate(
        blueprint_reference_document(ids)
    )
    action = AgentActionReceipt.model_validate(blueprint_action_document())
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Create a bounded collaboration blueprint.",
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=True,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    stored_turn = turn_document(
        ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["actions"] = [blueprint_action_document()]
    stored_turn["artifacts"] = [blueprint_reference_document(ids)]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    stored_document = stored_blueprint_effect_document(ids)
    stored_document["adaptation_receipts"] = [
        adaptation_receipt_document()
    ]
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=stored_document,
        )
    )
    adaptation = AdaptationReceipt.model_validate(
        adaptation_receipt_document()
    )

    result = await MemoryEngine(
        store.client
    ).record_chat_turn_blueprint_effect(
        claim,
        model_name="gemini-3.6-flash",
        schema_version="2.0",
        blueprint={"retry_payload": "must not overwrite durable work"},
        display_label="Regenerated label must not replace the receipt",
        observed_at=NOW,
        adaptations=(adaptation,),
    )

    assert result.artifact == artifact
    assert result.claim.precompleted_actions == (action,)
    assert result.claim.precompleted_artifacts == (artifact,)
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_chat_turn_blueprint_effect_rejects_receipt_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-receipt-conflict")
    store = ArtifactEffectStore(ids)
    artifact = ArtifactReference.model_validate(
        blueprint_reference_document(ids)
    )
    action = AgentActionReceipt.model_validate(blueprint_action_document())
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Create a bounded collaboration blueprint.",
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=True,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    stored_turn = turn_document(
        ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["actions"] = [blueprint_action_document()]
    stored_turn["artifacts"] = [blueprint_reference_document(ids)]
    stored_document = stored_blueprint_effect_document(ids)
    stored_document["adaptation_receipts"] = [
        adaptation_receipt_document(value="micro_steps")
    ]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_document)
    )
    conflicting_receipt = AdaptationReceipt.model_validate(
        adaptation_receipt_document(value="tasks")
    )

    with pytest.raises(ChatTurnStateError, match="receipt"):
        await MemoryEngine(
            store.client
        ).record_chat_turn_blueprint_effect(
            claim,
            model_name="gemini-3.6-flash",
            schema_version="2.0",
            blueprint={"retry_payload": "must not replace durable work"},
            display_label="Regenerated label",
            observed_at=NOW,
            adaptations=(conflicting_receipt,),
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_omitted_precompleted_artifact_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    artifact = ArtifactReference.model_validate(
        blueprint_reference_document(claim.ids)
    )
    action = AgentActionReceipt.model_validate(blueprint_action_document())
    stored_turn = turn_document(
        claim.ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["actions"] = [blueprint_action_document()]
    stored_turn["artifacts"] = [artifact.model_dump(mode="python")]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(ChatTurnStateError, match="stored turn effects"):
        await MemoryEngine(store.client).complete_chat_turn(
            replace(
                claim,
                precompleted_actions=(action,),
                precompleted_artifacts=(artifact,),
            ),
            ChatResponse(response="Unsafe omission."),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_atomically_stores_response_and_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    response = ChatResponse(response="A durable answer.")

    await MemoryEngine(store.client).complete_chat_turn(
        claim,
        response,
        observed_at=NOW,
    )

    assert store.transaction.set.call_args_list == [
        call(
            store.session_ref,
            {
                "updated_at": firestore.SERVER_TIMESTAMP,
                "last_message_preview": "A durable answer.",
                "last_message_role": "model",
                "last_completed_turn_id": claim.ids.turn_id,
            },
            merge=True,
        ),
        call(
            store.model_message_ref,
            {
                "role": "model",
                "text": "A durable answer.",
                "timestamp": firestore.SERVER_TIMESTAMP,
            },
        ),
        call(
            store.turn_ref,
            {
                "status": "completed",
                "actions": [],
                "artifacts": [],
                "artifact_feedback": [],
                "citations": [],
                "memory_proposals": [],
                "memory_clarifications": [],
                "collaborative_note_proposals": [],
                "collaborative_note_events": [],
                "continuity_receipts": [],
                "continuity_choices": [],
                "adaptations": [],
                "completed_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "lease_owner": firestore.DELETE_FIELD,
                "lease_expires_at": firestore.DELETE_FIELD,
            },
            merge=True,
        ),
    ]


@pytest.mark.asyncio
async def test_record_chat_turn_decision_action_persists_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    decision = MemoryDecisionRequest(
        proposal_id="response_length--proposal-1",
        decision="approve",
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Yes, remember it.",
        memory_decision=decision,
    )
    claim = ChatTurnClaim(
        request=request,
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    stored_turn = turn_document(
        ids,
        owner="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    stored_turn["memory_decision"] = decision.model_dump(mode="json")
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    action = AgentActionReceipt(
        action_name="approve_memory_signal",
        status="completed",
    )

    refreshed = await MemoryEngine(
        store.client
    ).record_chat_turn_decision_action(
        claim,
        action,
        observed_at=NOW,
    )

    assert refreshed.precompleted_actions == (action,)
    assert refreshed.precompleted_memory_proposals == ()
    store.transaction.set.assert_called_once_with(
        store.turn_ref,
        {
            "actions": [action.model_dump(mode="python")],
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_record_chat_turn_note_decision_effect_persists_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("note-decision-request-1")
    store = ChatTurnStore(ids)
    decision = note_decision_request()
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Approve that note.",
            collaborative_note_decision=decision,
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    stored_turn = turn_document(
        ids,
        owner="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    stored_turn["collaborative_note_decision"] = decision.model_dump(mode="json")
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    event = CollaborativeNoteEvent.model_validate(note_event_document())

    result = await MemoryEngine(
        store.client
    ).record_chat_turn_collaborative_note_decision_effect(
        claim,
        event,
        observed_at=NOW,
    )

    expected_action = AgentActionReceipt(
        action_name="approve_collaborative_note",
        status="completed",
    )
    assert result.action == expected_action
    assert result.event == event
    assert result.claim.precompleted_actions == (expected_action,)
    assert result.claim.precompleted_collaborative_note_events == (event,)
    store.transaction.set.assert_called_once_with(
        store.turn_ref,
        {
            "actions": [expected_action.model_dump(mode="python")],
            "collaborative_note_events": [event.model_dump(mode="python")],
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_omitted_note_event_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    decision = note_decision_request()
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message="Approve that note.",
            collaborative_note_decision=decision,
        ),
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    stored_turn = turn_document(
        ids,
        owner="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    stored_turn["collaborative_note_decision"] = decision.model_dump(mode="json")
    stored_turn["actions"] = [
        {
            "action_name": "approve_collaborative_note",
            "status": "completed",
        }
    ]
    stored_turn["collaborative_note_events"] = [note_event_document()]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.model_message_ref.get = AsyncMock(return_value=snapshot(exists=False))

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(
                response="Recorded.",
                actions=[
                    AgentActionReceipt(
                        action_name="approve_collaborative_note",
                        status="completed",
                    )
                ],
            ),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.parametrize("final_effect", ("omitted", "conflicting"))
@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_changed_precompleted_proposal_effect(
    monkeypatch: pytest.MonkeyPatch,
    final_effect: str,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    stored_turn = turn_document(
        claim.ids,
        owner=claim.owner_token,
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    stored_turn["actions"] = [proposal_action_document()]
    stored_turn["memory_proposals"] = [proposal_receipt_document()]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    if final_effect == "omitted":
        response = ChatResponse(response="Unsafe omission.")
    else:
        conflicting_receipt = proposal_receipt_document()
        conflicting_receipt["proposed_value"] = "detailed"
        response = ChatResponse(
            response="Unsafe substitution.",
            actions=[proposal_action_document()],
            memory_proposals=[conflicting_receipt],
        )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            response,
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_omitted_feedback_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, initial_claim = feedback_turn_claim()
    action = AgentActionReceipt.model_validate(feedback_action_document())
    feedback = ArtifactFeedbackReference.model_validate(
        feedback_reference_document(initial_claim.ids)
    )
    claim = replace(
        initial_claim,
        precompleted_actions=(action,),
        precompleted_artifact_feedback=(feedback,),
    )
    stored_turn = turn_document(
        claim.ids,
        owner=claim.owner_token,
        lease_expires_at=claim.lease_expires_at,
    )
    stored_turn["artifact_feedback_decision"] = (
        artifact_feedback_request().model_dump(mode="json")
    )
    stored_turn["actions"] = [feedback_action_document()]
    stored_turn["artifact_feedback"] = [
        feedback_reference_document(claim.ids)
    ]
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(
                response="Unsafe omission.",
                actions=[action],
            ),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_expired_lease_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(
        lease_expires_at=NOW - timedelta(seconds=1)
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(ChatTurnOwnershipError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_reclaimed_owner_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(owner="new-owner")
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(ChatTurnOwnershipError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_preexisting_model_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"role": "model", "text": "Existing", "timestamp": NOW},
        )
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_invalid_claim_before_firestore(
) -> None:
    client = MagicMock()
    request = ChatTurnRequest("agent-col", "session-1", "user-1", "message")
    invalid_claim = ChatTurnClaim(
        request=request,
        ids=ChatTurnIds(
            turn_id="invalid",
            user_message_id="wrong-user-message",
            model_message_id="wrong-model-message",
        ),
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )

    with pytest.raises(ValueError, match="claim"):
        await MemoryEngine(client).complete_chat_turn(
            invalid_claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_mismatched_stored_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    stored_turn = turn_document(
        claim.ids,
        project_id="different-project",
        owner=claim.owner_token,
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()
