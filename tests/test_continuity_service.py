from datetime import UTC, datetime

import pytest

from continuity import ContinuitySelectionRequest
from continuity_service import (
    ContinuityResolutionCommand,
    ContinuityService,
)
from schemas import (
    ChatMessageRecord,
    ChatSessionDetailResponse,
    ChatSessionListResponse,
    ChatSessionSummary,
    CollaborativeNote,
)


NOW = datetime(2026, 8, 26, 18, 30, tzinfo=UTC)


def active_note(
    note_id: str,
    title: str,
    body: str,
    *,
    status: str = "active",
    workspace_id: str = "workspace-1",
) -> CollaborativeNote:
    return CollaborativeNote(
        note_id=note_id,
        owner_user_id="user-1",
        workspace_id=workspace_id,
        note_kind="constraint",
        title=title,
        body=body,
        status=status,
        revision=2,
        source_session_id="session-1",
        source_message_ids=["message-1"],
        source_event_id=f"{note_id}--approved",
        created_at=NOW,
        updated_at=NOW,
    )


class FakeContinuityStore:
    def __init__(
        self,
        notes: tuple[CollaborativeNote, ...] = (),
        *,
        sessions: tuple[ChatSessionSummary, ...] = (),
        details: dict[str, ChatSessionDetailResponse] | None = None,
    ) -> None:
        self.notes = notes
        self.sessions = sessions
        self.details = details or {}
        self.calls: list[tuple[str, str, int]] = []
        self.session_list_calls: list[tuple[str, str, int]] = []
        self.session_detail_calls: list[tuple[str, str, str, int]] = []

    async def list_active_collaborative_notes_for_continuity(
        self,
        *,
        user_id: str,
        workspace_id: str,
        limit: int,
    ) -> tuple[CollaborativeNote, ...]:
        self.calls.append((user_id, workspace_id, limit))
        return tuple(
            note
            for note in self.notes
            if note.owner_user_id == user_id
            and note.workspace_id == workspace_id
            and note.status == "active"
        )[:limit]

    async def list_chat_sessions(
        self,
        *,
        user_id: str,
        project_id: str,
        limit: int,
    ) -> ChatSessionListResponse:
        self.session_list_calls.append((user_id, project_id, limit))
        return ChatSessionListResponse(
            sessions=[
                session
                for session in self.sessions
                if session.user_id == user_id
                and session.project_id == project_id
            ][:limit]
        )

    async def get_chat_session_detail(
        self,
        *,
        user_id: str,
        project_id: str,
        session_id: str,
        limit: int,
        observed_at: datetime,
    ) -> ChatSessionDetailResponse:
        self.session_detail_calls.append(
            (user_id, project_id, session_id, limit)
        )
        detail = self.details.get(session_id)
        if detail is None:
            return ChatSessionDetailResponse(
                session_id=session_id,
                project_id=project_id,
                user_id=user_id,
                messages=[],
            )
        return detail


class FakeTermExpander:
    def __init__(self, terms: tuple[str, ...]) -> None:
        self.terms = terms
        self.calls: list[tuple[str, ...]] = []

    async def expand_terms(self, terms: tuple[str, ...]) -> tuple[str, ...]:
        self.calls.append(terms)
        return self.terms


def chat_summary(
    session_id: str,
    preview: str,
    *,
    minutes_ago: int,
    project_id: str = "workspace-1",
    user_id: str = "user-1",
) -> ChatSessionSummary:
    return ChatSessionSummary(
        session_id=session_id,
        project_id=project_id,
        user_id=user_id,
        updated_at=NOW.replace(minute=NOW.minute - minutes_ago),
        last_message_preview=preview,
        last_message_role="model",
    )


def chat_detail(
    session_id: str,
    messages: tuple[tuple[str, str], ...],
    *,
    project_id: str = "workspace-1",
    user_id: str = "user-1",
) -> ChatSessionDetailResponse:
    return ChatSessionDetailResponse(
        session_id=session_id,
        project_id=project_id,
        user_id=user_id,
        messages=[
            ChatMessageRecord(
                message_id=f"{session_id}-{index}",
                role=role,
                text=text,
                timestamp=NOW,
            )
            for index, (role, text) in enumerate(messages, start=1)
        ],
    )


@pytest.mark.asyncio
async def test_resolver_does_not_read_notes_without_explicit_prior_reference() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export and require a preview step.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="Please explain export formats.",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []
    assert store.calls == []


@pytest.mark.asyncio
async def test_resolver_returns_exact_title_match_with_body_context_and_receipt() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export and require a preview step.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="What did we decide for Export workflow requirements?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].model_dump(mode="json") == {
        "receipt_id": "continuity--note-1--rev-2",
        "source_kind": "collaborative_note",
        "source_id": "note-1",
        "display_label": "Used note: Export workflow requirements",
        "match_reason": "exact_title",
        "source_updated_at": "2026-08-26T18:30:00Z",
    }
    assert result.source_texts[0].body == (
        "Use CSV export and require a preview step."
    )
    assert result.choices == []


@pytest.mark.asyncio
async def test_resolver_returns_ambiguous_choices_without_note_bodies() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export.",
            ),
            active_note(
                "note-2",
                "Export workflow constraints",
                "Require a preview step.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="What were the export workflow notes?",
        )
    )

    assert result.status == "ambiguous"
    assert [choice.source_id for choice in result.choices] == [
        "note-1",
        "note-2",
    ]
    assert [choice.display_label for choice in result.choices] == [
        "Export workflow requirements",
        "Export workflow constraints",
    ]
    assert result.receipts == []
    assert result.source_texts == []
    assert "CSV export" not in str(result.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_resolver_excludes_archived_notes_from_implicit_match() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export.",
                status="archived",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="What did we decide for Export workflow requirements?",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []


@pytest.mark.asyncio
async def test_resolver_uses_server_selected_note_without_trusting_body() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export.",
            ),
            active_note(
                "note-2",
                "Export workflow constraints",
                "Require a preview step.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="Use the selected note.",
            selection=ContinuitySelectionRequest(
                choice_id="choice-2",
                source_kind="collaborative_note",
                source_id="note-2",
            ),
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "note-2"
    assert result.receipts[0].match_reason == "user_selected"
    assert result.source_texts[0].body == "Require a preview step."


@pytest.mark.asyncio
async def test_resolver_uses_expanded_keywords_for_recent_prior_chat() -> None:
    store = FakeContinuityStore(
        sessions=(
            chat_summary(
                "session-current",
                "Current request",
                minutes_ago=0,
            ),
            chat_summary(
                "session-matching",
                "Router build details",
                minutes_ago=1,
            ),
            chat_summary(
                "session-unmatched",
                "Visual design review",
                minutes_ago=2,
            ),
        ),
        details={
            "session-matching": chat_detail(
                "session-matching",
                (
                    ("user", "How should we structure the router build?"),
                    (
                        "model",
                        "The feature should use a deterministic service.",
                    ),
                ),
            ),
            "session-unmatched": chat_detail(
                "session-unmatched",
                (("user", "Review the drawer layout."),),
            ),
        },
    )
    expander = FakeTermExpander(("build", "feature", "code"))
    service = ContinuityService(store=store, term_expander=expander)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="What was the implementation we talked about recently?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "chat_session"
    assert result.receipts[0].source_id == "session-matching"
    assert result.receipts[0].display_label == (
        "Used prior chat: Router build details"
    )
    assert result.receipts[0].match_reason == "previous_chat"
    assert result.source_texts[0].source_kind == "chat_session"
    assert "deterministic service" in result.source_texts[0].body
    assert store.session_list_calls == [("user-1", "workspace-1", 20)]
    assert "implementation" in expander.calls[0]
    assert "talked" not in expander.calls[0]


@pytest.mark.asyncio
async def test_resolver_sanitizes_expanded_chat_search_terms() -> None:
    store = FakeContinuityStore(
        sessions=(
            chat_summary("session-current", "Current request", minutes_ago=0),
            chat_summary("session-match", "Implementation build", minutes_ago=1),
            chat_summary("session-bad", "Private token", minutes_ago=2),
        ),
        details={
            "session-match": chat_detail(
                "session-match",
                (("user", "The build uses the continuity service."),),
            ),
            "session-bad": chat_detail(
                "session-bad",
                (("user", "The token phrase should not be searchable."),),
            ),
        },
    )
    expander = FakeTermExpander(
        ("build", "two words", "token:secret", "recently", "service")
    )
    service = ContinuityService(store=store, term_expander=expander)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="What was the implementation we spoke about recently?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "session-match"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "What was the implementation we talked about recently?",
        "What was the implementation we spoke about recently?",
    ),
)
async def test_resolver_detects_talked_and_spoke_prior_chat_phrases(
    message: str,
) -> None:
    store = FakeContinuityStore(
        sessions=(
            chat_summary("session-current", "Current request", minutes_ago=0),
            chat_summary("session-match", "Implementation plan", minutes_ago=1),
        ),
        details={
            "session-match": chat_detail(
                "session-match",
                (("user", "Implementation uses continuity receipts."),),
            ),
        },
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message=message,
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "session-match"


@pytest.mark.asyncio
async def test_resolver_uses_newest_prior_chat_for_last_chat_request() -> None:
    store = FakeContinuityStore(
        sessions=(
            chat_summary("session-current", "Current request", minutes_ago=0),
            chat_summary("session-newest", "Newest prior topic", minutes_ago=1),
            chat_summary("session-older", "Older prior topic", minutes_ago=2),
        ),
        details={
            "session-newest": chat_detail(
                "session-newest",
                (("user", "We discussed deployment status."),),
            ),
            "session-older": chat_detail(
                "session-older",
                (("user", "We discussed testing strategy."),),
            ),
        },
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="What did we talk about in the last chat?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "session-newest"
    assert result.source_texts[0].body == "User: We discussed deployment status."
    assert [call[2] for call in store.session_detail_calls] == [
        "session-newest"
    ]


@pytest.mark.asyncio
async def test_resolver_returns_body_free_choices_for_ambiguous_prior_chats() -> None:
    store = FakeContinuityStore(
        sessions=(
            chat_summary("session-current", "Current request", minutes_ago=0),
            chat_summary("session-a", "Implementation service", minutes_ago=1),
            chat_summary("session-b", "Implementation tests", minutes_ago=2),
        ),
        details={
            "session-a": chat_detail(
                "session-a",
                (("user", "Implementation used a service boundary."),),
            ),
            "session-b": chat_detail(
                "session-b",
                (("user", "Implementation tests covered receipts."),),
            ),
        },
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="What implementation did we discuss recently?",
        )
    )

    assert result.status == "ambiguous"
    assert [choice.source_kind for choice in result.choices] == [
        "chat_session",
        "chat_session",
    ]
    assert [choice.display_label for choice in result.choices] == [
        "Implementation service",
        "Implementation tests",
    ]
    assert result.receipts == []
    assert result.source_texts == []
    assert "service boundary" not in str(result.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_resolver_selected_prior_chat_bounds_detail_preview() -> None:
    long_model_message = "The selected prior chat discussed HIDS implementation. " * 8
    store = FakeContinuityStore(
        details={
            "session-selected": chat_detail(
                "session-selected",
                (
                    ("user", "What was the intrusion detection system?"),
                    ("model", long_model_message),
                ),
            ),
        },
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="Use the selected prior chat.",
            selection=ContinuitySelectionRequest(
                choice_id="choice-1",
                source_kind="chat_session",
                source_id="session-selected",
            ),
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "chat_session"
    assert result.receipts[0].source_id == "session-selected"
    assert len(result.receipts[0].display_label) <= 160
    assert len(result.source_texts[0].title) <= 160
    assert "HIDS implementation" in result.source_texts[0].body
