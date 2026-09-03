from datetime import UTC, datetime

import pytest

from continuity import ContinuitySelectionRequest, ContinuitySourceReceipt
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
    owner_user_id: str = "user-1",
) -> CollaborativeNote:
    return CollaborativeNote(
        note_id=note_id,
        owner_user_id=owner_user_id,
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
        recent_receipts: tuple[ContinuitySourceReceipt, ...] = (),
    ) -> None:
        self.notes = notes
        self.sessions = sessions
        self.details = details or {}
        self.recent_receipts = recent_receipts
        self.calls: list[tuple[str, str, int]] = []
        self.session_list_calls: list[tuple[str, str, int]] = []
        self.session_detail_calls: list[tuple[str, str, str, int]] = []
        self.recent_receipt_calls: list[tuple[str, str, str, int]] = []

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

    async def list_recent_session_continuity_receipts(
        self,
        *,
        user_id: str,
        project_id: str,
        session_id: str,
        limit: int,
    ) -> tuple[ContinuitySourceReceipt, ...]:
        self.recent_receipt_calls.append(
            (user_id, project_id, session_id, limit)
        )
        return self.recent_receipts[:limit]


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
async def test_resolver_does_not_treat_multi_intent_new_work_prompt_as_continuity() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-shell",
                "Shell environment",
                "Use zsh shell for project work.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message=(
                "create a workspace note that we are going to build project "
                "zero for macOS and we are using a zsh shell environment. "
                "also remember that i prefer pancakes on saturday mornings "
                "for breakfast. then write me a C program that prints, "
                "'hello! i love pancakes!'"
            ),
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []
    assert store.calls == []
    assert store.session_list_calls == []
    assert store.session_detail_calls == []


@pytest.mark.asyncio
async def test_resolver_does_not_treat_explicit_memory_request_as_continuity() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-breakfast",
                "Breakfast preference",
                "The user prefers oatmeal on weekday mornings.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message=(
                "Remember that I prefer pancakes on Saturday mornings for "
                "breakfast."
            ),
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []
    assert store.calls == []
    assert store.session_list_calls == []
    assert store.session_detail_calls == []


@pytest.mark.asyncio
async def test_resolver_treats_remind_me_to_do_work_as_new_instruction() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-api",
                "API decision",
                "We decided the API should be implemented first.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="Remind me to write tests after the API implementation.",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []
    assert store.calls == []
    assert store.session_list_calls == []
    assert store.session_detail_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "What is a project name in software?",
        "What do you call a project manager?",
    ),
)
async def test_resolver_does_not_read_notes_for_ordinary_explanatory_project_name_questions(
    message: str,
) -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Project Name: NetView",
                "The project name is NetView.",
            ),
        )
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

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []
    assert store.calls == []
    assert store.session_list_calls == []


@pytest.mark.asyncio
async def test_resolver_does_not_read_notes_for_ordinary_explanatory_language_question(
) -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-language",
                "Project Language: TypeScript",
                "The project will be written in TypeScript.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="What is a programming language?",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []
    assert store.calls == []
    assert store.session_list_calls == []


@pytest.mark.asyncio
async def test_resolver_reuses_recent_note_anchor_for_anaphoric_follow_up() -> None:
    note = active_note(
        "note-project",
        "Project Name: NetView",
        "NetView is a network monitor written in TypeScript.",
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-project--rev-2",
        source_kind="collaborative_note",
        source_id="note-project",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=NOW,
    )
    store = FakeContinuityStore((note,), recent_receipts=(receipt,))
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was it about",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "collaborative_note"
    assert result.receipts[0].source_id == "note-project"
    assert result.receipts[0].match_reason == "recent_continuity"
    assert result.source_texts[0].title == "Project Name: NetView"
    assert "network monitor" in result.source_texts[0].body
    assert store.recent_receipt_calls == [
        ("user-1", "workspace-1", "session-current", 5)
    ]
    assert store.calls == [("user-1", "workspace-1", 50)]
    assert store.session_list_calls == []


@pytest.mark.asyncio
async def test_resolver_uses_recent_anchor_to_find_related_about_note() -> None:
    name_note = active_note(
        "note-name",
        "Project Name: NetView",
        "The project name is NetView.",
        status="active",
    )
    requirements_note = active_note(
        "note-requirements",
        "Project Requirements: Local Network Monitor TUI for Bash",
        (
            "NetView is a local network monitor TUI application built to run "
            "in a bash shell environment."
        ),
        status="active",
    )
    language_note = active_note(
        "note-language",
        "Project Language: TypeScript",
        "The project will be written in TypeScript.",
        status="active",
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-name--rev-2",
        source_kind="collaborative_note",
        source_id="note-name",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=NOW,
    )
    store = FakeContinuityStore(
        (requirements_note, name_note, language_note),
        recent_receipts=(receipt,),
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was it about",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "note-requirements"
    assert result.receipts[0].match_reason == "recent_continuity"
    assert result.source_texts[0].title == (
        "Project Requirements: Local Network Monitor TUI for Bash"
    )
    assert "local network monitor TUI" in result.source_texts[0].body


@pytest.mark.asyncio
async def test_resolver_uses_recent_anchor_to_find_related_language_note() -> None:
    name_note = active_note(
        "note-name",
        "Project Name: NetView",
        "The project name is NetView.",
        status="active",
    )
    language_note = active_note(
        "note-language",
        "Project Language: TypeScript",
        "The project will be written in TypeScript.",
        status="active",
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-name--rev-2",
        source_kind="collaborative_note",
        source_id="note-name",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=NOW,
    )
    store = FakeContinuityStore(
        (name_note, language_note),
        recent_receipts=(receipt,),
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was it going to be written in?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "note-language"
    assert result.receipts[0].match_reason == "recent_continuity"
    assert result.source_texts[0].title == "Project Language: TypeScript"
    assert result.source_texts[0].body == (
        "The project will be written in TypeScript."
    )


@pytest.mark.asyncio
async def test_resolver_prefers_explicit_language_note_over_requirements_anchor_overlap(
) -> None:
    name_note = active_note(
        "note-name",
        "Project Name: NetView",
        "The project name is NetView.",
        status="active",
    )
    requirements_note = active_note(
        "note-requirements",
        "Project Requirements: Local Network Monitor TUI for Bash",
        (
            "NetView is a local network monitor TUI application built to run "
            "in a Bash shell environment."
        ),
        status="active",
    )
    language_note = active_note(
        "note-language",
        "Project Language: TypeScript",
        "The project will be written in TypeScript.",
        status="active",
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-name--rev-2",
        source_kind="collaborative_note",
        source_id="note-name",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=NOW,
    )
    store = FakeContinuityStore(
        (requirements_note, name_note, language_note),
        recent_receipts=(receipt,),
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="did we decide what language we would write it in",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "note-language"
    assert result.receipts[0].match_reason == "recent_continuity"
    assert result.source_texts[0].body == (
        "The project will be written in TypeScript."
    )


@pytest.mark.asyncio
async def test_resolver_aggressively_resolves_collaborative_language_decision_question(
) -> None:
    name_note = active_note(
        "note-name",
        "Project Name: NetView",
        "The project name is NetView.",
        status="active",
    )
    language_note = active_note(
        "note-language",
        "Project Language: TypeScript",
        "The project will be written in TypeScript.",
        status="active",
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-name--rev-2",
        source_kind="collaborative_note",
        source_id="note-name",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=NOW,
    )
    store = FakeContinuityStore(
        (name_note, language_note),
        recent_receipts=(receipt,),
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="did we pick a language to write it in already?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "note-language"
    assert result.receipts[0].match_reason == "recent_continuity"
    assert result.source_texts[0].title == "Project Language: TypeScript"
    assert result.source_texts[0].body == (
        "The project will be written in TypeScript."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "what language did i want to write it in?",
        "what were we going to build it with?",
        "what were we using for the stack?",
        "what did we say it should use?",
        "what did i want it built in?",
        "what tool were we going with for it?",
        "do we already have a language picked for this?",
        "what was i thinking for the framework?",
    ),
)
async def test_resolver_opens_retrieval_for_broad_ambiguous_language_references(
    message: str,
) -> None:
    name_note = active_note(
        "note-name",
        "Project Name: NetView",
        "The project name is NetView.",
        status="active",
    )
    language_note = active_note(
        "note-language",
        "Project Language: TypeScript",
        "The project will be written in TypeScript.",
        status="active",
    )
    requirements_note = active_note(
        "note-requirements",
        "Project Requirements: Local Network Monitor TUI for Bash",
        "NetView is a local network monitor TUI application.",
        status="active",
    )
    store = FakeContinuityStore((name_note, requirements_note, language_note))
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
    assert result.receipts[0].source_id == "note-language"
    assert result.source_texts[0].body == (
        "The project will be written in TypeScript."
    )
    assert store.calls == [("user-1", "workspace-1", 50)]
    assert store.session_list_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "what was that project we were working on together?",
        "what was that thing called again?",
        "do we already have a name for it?",
        "what did you say the project was called?",
        "remind me what we named this",
        "what was the app name?",
    ),
)
async def test_resolver_opens_retrieval_for_broad_ambiguous_name_references(
    message: str,
) -> None:
    name_note = active_note(
        "note-name",
        "Project Name: NetView",
        "The project name is NetView.",
        status="active",
    )
    language_note = active_note(
        "note-language",
        "Project Language: TypeScript",
        "The project will be written in TypeScript.",
        status="active",
    )
    store = FakeContinuityStore((language_note, name_note))
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
    assert result.receipts[0].source_id == "note-name"
    assert result.source_texts[0].body == "The project name is NetView."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "what was that thing supposed to do?",
        "what did i want for this?",
        "what did we say it needed?",
        "what was the goal again?",
        "what was the scope for it?",
        "where did we leave off on this?",
    ),
)
async def test_resolver_opens_retrieval_for_broad_ambiguous_requirement_references(
    message: str,
) -> None:
    name_note = active_note(
        "note-name",
        "Project Name: NetView",
        "The project name is NetView.",
        status="active",
    )
    requirements_note = active_note(
        "note-requirements",
        "Project Requirements: Local Network Monitor TUI for Bash",
        (
            "NetView should monitor local network devices from a Bash terminal "
            "UI."
        ),
        status="active",
    )
    store = FakeContinuityStore((name_note, requirements_note))
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
    assert result.receipts[0].source_id == "note-requirements"
    assert "monitor local network devices" in result.source_texts[0].body


@pytest.mark.asyncio
async def test_resolver_ambiguously_returns_equal_broad_requirement_matches() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-requirements-a",
                "Project Requirements: Terminal UI",
                "The project should provide a terminal interface.",
            ),
            active_note(
                "note-requirements-b",
                "Project Requirements: Network Monitoring",
                "The project should monitor local network devices.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what did we say it should do?",
        )
    )

    assert result.status == "ambiguous"
    assert {choice.source_id for choice in result.choices} == {
        "note-requirements-a",
        "note-requirements-b",
    }
    assert result.source_texts == []


@pytest.mark.asyncio
async def test_resolver_returns_ambiguous_choices_for_broad_language_decision_question(
) -> None:
    name_note = active_note(
        "note-name",
        "Project Name: NetView",
        "The project name is NetView.",
        status="active",
    )
    language_note = active_note(
        "note-language",
        "Project Language: TypeScript",
        "The project will be written in TypeScript.",
        status="active",
    )
    stack_note = active_note(
        "note-stack",
        "Project Stack: TypeScript and Ink",
        "The project stack uses TypeScript with Ink for terminal UI.",
        status="active",
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-name--rev-2",
        source_kind="collaborative_note",
        source_id="note-name",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=NOW,
    )
    store = FakeContinuityStore(
        (name_note, language_note, stack_note),
        recent_receipts=(receipt,),
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="did we already choose the stack for it?",
        )
    )

    assert result.status == "ambiguous"
    assert {choice.source_id for choice in result.choices} == {
        "note-language",
        "note-stack",
    }
    assert result.source_texts == []


@pytest.mark.asyncio
async def test_resolver_matches_direct_language_note_request_without_magic_word() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-language",
                "Project Language: TypeScript",
                "The project will be written in TypeScript.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was the language note?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "note-language"
    assert result.receipts[0].match_reason == "bounded_relevance"
    assert result.source_texts[0].body == (
        "The project will be written in TypeScript."
    )


@pytest.mark.asyncio
async def test_resolver_ignores_stale_note_anchor_when_note_is_archived() -> None:
    note = active_note(
        "note-project",
        "Project Name: NetView",
        "NetView is a network monitor written in TypeScript.",
        status="archived",
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-project--rev-2",
        source_kind="collaborative_note",
        source_id="note-project",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=NOW,
    )
    store = FakeContinuityStore((note,), recent_receipts=(receipt,))
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was it about",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.source_texts == []
    assert store.recent_receipt_calls == [
        ("user-1", "workspace-1", "session-current", 5)
    ]
    assert store.calls == [
        ("user-1", "workspace-1", 50),
        ("user-1", "workspace-1", 50),
    ]
    assert store.session_list_calls == [("user-1", "workspace-1", 20)]


@pytest.mark.asyncio
async def test_resolver_does_not_use_cross_workspace_recent_note_anchor() -> None:
    note = active_note(
        "note-project",
        "Project Name: NetView",
        "NetView is a network monitor written in TypeScript.",
        workspace_id="other-workspace",
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-project--rev-2",
        source_kind="collaborative_note",
        source_id="note-project",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=NOW,
    )
    store = FakeContinuityStore((note,), recent_receipts=(receipt,))
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was it about",
        )
    )

    assert result.status == "none"
    assert store.calls == [
        ("user-1", "workspace-1", 50),
        ("user-1", "workspace-1", 50),
    ]


@pytest.mark.asyncio
async def test_resolver_searches_notes_after_anaphoric_follow_up_without_recent_anchor() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-project",
                "Project Name: NetView",
                "NetView is a network monitor written in TypeScript.",
            ),
        ),
        recent_receipts=(),
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was it about",
        )
    )

    assert result.status == "none"
    assert store.recent_receipt_calls == [
        ("user-1", "workspace-1", "session-current", 5)
    ]
    assert store.calls == [("user-1", "workspace-1", 50)]
    assert store.session_list_calls == [("user-1", "workspace-1", 20)]


@pytest.mark.asyncio
async def test_resolver_reuses_recent_chat_anchor_for_anaphoric_follow_up() -> None:
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--chat--session-prior",
        source_kind="chat_session",
        source_id="session-prior",
        display_label="Used prior chat: NetView requirements",
        match_reason="previous_chat",
        source_updated_at=NOW,
    )
    detail = chat_detail(
        "session-prior",
        (
            ("user", "We decided NetView is a local network monitor."),
            ("model", "I recorded the NetView requirement."),
        ),
    )
    store = FakeContinuityStore(
        recent_receipts=(receipt,),
        details={"session-prior": detail},
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was it about",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "chat_session"
    assert result.receipts[0].source_id == "session-prior"
    assert result.receipts[0].match_reason == "recent_continuity"
    assert result.source_texts[0].title.startswith("Prior chat:")
    assert "local network monitor" in result.source_texts[0].body
    assert store.recent_receipt_calls == [
        ("user-1", "workspace-1", "session-current", 5)
    ]
    assert store.session_detail_calls == [
        ("user-1", "workspace-1", "session-prior", 40)
    ]
    assert store.calls == []
    assert store.session_list_calls == []


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
@pytest.mark.parametrize(
    "message",
    (
        "what was that name we settled on earlier?",
        "what did we decide about that?",
        "remind me what we decided about Project Zero",
        "what were we doing before?",
        "what did I say I wanted for this?",
        "remind me where we left off",
        "what was the requirement we agreed on?",
        "hey col what is the name of the project we are working on again?",
        "do you remember what the app is called?",
    ),
)
async def test_resolver_searches_notes_for_natural_historical_reference_phrases(
    message: str,
) -> None:
    store = FakeContinuityStore()
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message=message,
        )
    )

    assert result.status == "none"
    assert store.calls == [("user-1", "workspace-1", 50)]


@pytest.mark.asyncio
async def test_resolver_matches_live_project_name_note_request() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-netview",
                "Project Details: NetView",
                (
                    "The project is named NetView, a network monitor written "
                    "in TypeScript."
                ),
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message=(
                "hey col what is the name of the project we are working on "
                "again?"
            ),
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "collaborative_note"
    assert result.receipts[0].source_id == "note-netview"
    assert result.receipts[0].match_reason == "bounded_relevance"
    assert "NetView" in result.source_texts[0].body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "what was the name of the project we are working on together",
        "what was the name of the project we are working on again",
    ),
)
async def test_resolver_matches_project_name_note_without_requiring_magic_trigger_word(
    message: str,
) -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-netview",
                "Project Name: NetView",
                "The project name is NetView.",
            ),
        )
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
    assert result.receipts[0].source_kind == "collaborative_note"
    assert result.receipts[0].source_id == "note-netview"
    assert result.source_texts[0].body == "The project name is NetView."
    assert store.calls == [("user-1", "workspace-1", 50)]
    assert store.session_list_calls == []


@pytest.mark.asyncio
async def test_resolver_matches_natural_project_name_variants() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-netview",
                "Project Details: NetView",
                (
                    "The project is named NetView, a network monitor written "
                    "in TypeScript."
                ),
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="do you remember what the app is called?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "collaborative_note"
    assert result.receipts[0].source_id == "note-netview"
    assert result.receipts[0].match_reason == "bounded_relevance"


@pytest.mark.asyncio
async def test_resolver_matches_note_body_content_for_natural_reference() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Project label",
                "The name we settled on is Aether Launch.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was that name we settled on earlier?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "collaborative_note"
    assert result.receipts[0].source_id == "note-1"
    assert result.receipts[0].match_reason == "bounded_relevance"
    assert result.source_texts[0].body == (
        "The name we settled on is Aether Launch."
    )


@pytest.mark.asyncio
async def test_resolver_prefers_relevant_note_before_prior_chat() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Product naming",
                "The name we settled on is Aether Launch.",
            ),
        ),
        sessions=(
            chat_summary("session-current", "Current request", minutes_ago=0),
            chat_summary("session-matching", "Aether Launch chat", minutes_ago=1),
        ),
        details={
            "session-matching": chat_detail(
                "session-matching",
                (("user", "We also discussed the Aether Launch name."),),
            ),
        },
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was that name we settled on earlier?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "collaborative_note"
    assert result.receipts[0].source_id == "note-1"
    assert store.session_list_calls == []
    assert store.session_detail_calls == []


@pytest.mark.asyncio
async def test_resolver_searches_prior_chat_when_notes_do_not_resolve() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-unrelated",
                "Export requirements",
                "Use CSV export and require a preview step.",
            ),
        ),
        sessions=(
            chat_summary("session-current", "Current request", minutes_ago=0),
            chat_summary("session-previous", "Workspace pause point", minutes_ago=1),
        ),
        details={
            "session-previous": chat_detail(
                "session-previous",
                (("model", "We left off implementing continuity receipts."),),
            ),
        },
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="remind me where we left off",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "chat_session"
    assert result.receipts[0].source_id == "session-previous"
    assert result.source_texts[0].source_kind == "chat_session"
    assert "continuity receipts" in result.source_texts[0].body


@pytest.mark.asyncio
async def test_resolver_searches_prior_chat_for_natural_project_name_request_when_no_note_matches() -> None:
    store = FakeContinuityStore(
        sessions=(
            chat_summary("session-current", "Current request", minutes_ago=0),
            chat_summary("session-previous", "Project setup", minutes_ago=1),
        ),
        details={
            "session-previous": chat_detail(
                "session-previous",
                (
                    ("user", "The project name is NetView."),
                    ("model", "I can help build NetView."),
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
            message="what was the name of the project we are working on together",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_kind == "chat_session"
    assert result.receipts[0].source_id == "session-previous"
    assert "The project name is NetView." in result.source_texts[0].body


@pytest.mark.asyncio
async def test_resolver_ignores_unrelated_notes_for_historical_reference() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-unrelated",
                "Color palette",
                "Use green action buttons with neutral surfaces.",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what did we decide about deployment?",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []


@pytest.mark.asyncio
async def test_resolver_excludes_archived_notes_from_body_match() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-archived",
                "Project label",
                "The name we settled on is Aether Launch.",
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
            message="what was that name we settled on earlier?",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []


@pytest.mark.asyncio
async def test_resolver_keeps_natural_note_lookup_workspace_and_owner_scoped() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-other-workspace",
                "Product naming",
                "The name we settled on is Aether Launch.",
                workspace_id="workspace-2",
            ),
            active_note(
                "note-other-owner",
                "Product naming",
                "The name we settled on is Aether Launch.",
                owner_user_id="user-2",
            ),
        )
    )
    service = ContinuityService(store=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-current",
            message="what was that name we settled on earlier?",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []
    assert store.calls == [("user-1", "workspace-1", 50)]


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
