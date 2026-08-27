"""Deterministic note-first continuity resolution."""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from google.genai import types

from continuity import (
    ContinuityChoice,
    ContinuityResolution,
    ContinuitySelectionRequest,
    ContinuitySourceReceipt,
    ContinuitySourceText,
)
from schemas import (
    ChatSessionDetailResponse,
    ChatSessionListResponse,
    ChatSessionSummary,
    CollaborativeNote,
)


CONTINUITY_TERM_EXPANSION_MODEL = "gemini-3.6-flash"
CONTINUITY_TERM_EXPANSION_TIMEOUT_SECONDS = 8.0
CHAT_SESSION_SEARCH_LIMIT = 20
CHAT_SESSION_DETAIL_LIMIT = 40


_PRIOR_REFERENCE_RE = re.compile(
    r"\b(previous|prior|earlier|last|before|decided|agreed|note|notes|"
    r"requirement|requirements|constraint|constraints|task|workspace|"
    r"recent|recently|talk|talked|spoke|discuss|discussed)\b",
    re.IGNORECASE,
)
_CHAT_REFERENCE_RE = re.compile(
    r"\b("
    r"last|previous|prior|earlier|recent|recently|"
    r"chat|session|conversation|"
    r"talk|talked|spoke|discuss|discussed"
    r")\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "about",
        "chat",
        "conversation",
        "did",
        "discuss",
        "discussed",
        "for",
        "in",
        "last",
        "of",
        "on",
        "or",
        "prior",
        "recent",
        "recently",
        "session",
        "spoke",
        "talk",
        "talked",
        "the",
        "to",
        "use",
        "was",
        "we",
        "were",
        "what",
        "with",
    }
)


class ContinuityStore(Protocol):
    async def list_active_collaborative_notes_for_continuity(
        self,
        *,
        user_id: str,
        workspace_id: str,
        limit: int,
    ) -> tuple[CollaborativeNote, ...]: ...

    async def list_chat_sessions(
        self,
        *,
        user_id: str,
        project_id: str,
        limit: int,
    ) -> ChatSessionListResponse: ...

    async def get_chat_session_detail(
        self,
        *,
        user_id: str,
        project_id: str,
        session_id: str,
        limit: int,
        observed_at: datetime,
    ) -> ChatSessionDetailResponse: ...


class ContinuityTermExpander(Protocol):
    async def expand_terms(self, terms: tuple[str, ...]) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class ContinuityResolutionCommand:
    user_id: str
    workspace_id: str
    session_id: str
    message: str
    selection: ContinuitySelectionRequest | None = None


class GeminiContinuityTermExpander:
    def __init__(
        self,
        *,
        client: object,
        model_name: str = CONTINUITY_TERM_EXPANSION_MODEL,
        timeout_seconds: float = CONTINUITY_TERM_EXPANSION_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self._client = client
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds

    async def expand_terms(self, terms: tuple[str, ...]) -> tuple[str, ...]:
        safe_terms = _sanitize_terms(terms, maximum=5)
        if not safe_terms:
            return ()
        prompt = (
            "Return JSON with a terms array containing at most three lowercase "
            "single-word search synonyms or closely related words for these "
            f"chat-history search terms: {', '.join(safe_terms)}. Do not "
            "include secrets, operators, phrases, explanations, or duplicates."
        )
        response = await asyncio.wait_for(
            self._client.aio.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "terms": {
                                "type": "array",
                                "maxItems": 3,
                                "items": {
                                    "type": "string",
                                    "minLength": 3,
                                    "maxLength": 32,
                                },
                            }
                        },
                        "required": ["terms"],
                    },
                ),
            ),
            timeout=self._timeout_seconds,
        )
        try:
            payload = json.loads(response.text)
        except (AttributeError, TypeError, json.JSONDecodeError):
            return ()
        if not isinstance(payload, dict):
            return ()
        raw_terms = payload.get("terms")
        if not isinstance(raw_terms, list):
            return ()
        return _sanitize_terms(tuple(raw_terms), maximum=3)


class ContinuityService:
    def __init__(
        self,
        *,
        store: ContinuityStore,
        term_expander: ContinuityTermExpander | None = None,
    ) -> None:
        self._store = store
        self._term_expander = term_expander

    async def resolve(
        self,
        command: ContinuityResolutionCommand,
    ) -> ContinuityResolution:
        if command.selection is None and not _should_resolve(command.message):
            return ContinuityResolution(status="none")
        if command.selection is not None:
            if command.selection.source_kind == "chat_session":
                return await self._resolve_selected_chat(command)
            return await self._resolve_selected_note(command)
        if _should_resolve_chat(command.message):
            chat_resolution = await self._resolve_prior_chat(command)
            if chat_resolution.status != "none":
                return chat_resolution
        notes = await self._store.list_active_collaborative_notes_for_continuity(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            limit=50,
        )
        active_notes = tuple(note for note in notes if note.status == "active")

        exact_matches = tuple(
            note
            for note in active_notes
            if _normalized_title(note.title) in _normalized_message(command.message)
        )
        if len(exact_matches) == 1:
            return _resolved_note(exact_matches[0], "exact_title")
        if len(exact_matches) > 1:
            return _ambiguous_notes(exact_matches[:5])

        candidates = tuple(
            note
            for note in active_notes
            if _note_matches_message_tokens(note, command.message)
        )
        if len(candidates) == 1:
            return _resolved_note(candidates[0], "bounded_relevance")
        if len(candidates) > 1:
            return _ambiguous_notes(candidates[:5])
        return ContinuityResolution(status="none")

    async def _resolve_selected_note(
        self,
        command: ContinuityResolutionCommand,
    ) -> ContinuityResolution:
        notes = await self._store.list_active_collaborative_notes_for_continuity(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            limit=50,
        )
        selected = next(
            (
                note
                for note in notes
                if note.status == "active"
                and note.note_id == command.selection.source_id
            ),
            None,
        )
        if selected is None:
            return ContinuityResolution(status="none")
        return _resolved_note(selected, "user_selected")

    async def _resolve_selected_chat(
        self,
        command: ContinuityResolutionCommand,
    ) -> ContinuityResolution:
        detail = await self._store.get_chat_session_detail(
            user_id=command.user_id,
            project_id=command.workspace_id,
            session_id=command.selection.source_id,
            limit=CHAT_SESSION_DETAIL_LIMIT,
            observed_at=datetime.now(UTC),
        )
        if detail.session_id == command.session_id or not detail.messages:
            return ContinuityResolution(status="none")
        return _resolved_chat_session(
            _summary_from_detail(detail),
            detail,
            "user_selected",
        )

    async def _resolve_prior_chat(
        self,
        command: ContinuityResolutionCommand,
    ) -> ContinuityResolution:
        sessions_response = await self._store.list_chat_sessions(
            user_id=command.user_id,
            project_id=command.workspace_id,
            limit=CHAT_SESSION_SEARCH_LIMIT,
        )
        sessions = tuple(
            session
            for session in sessions_response.sessions
            if session.session_id != command.session_id
        )
        if not sessions:
            return ContinuityResolution(status="none")
        base_terms = _extract_chat_search_terms(command.message)
        if not base_terms:
            detail = await self._store.get_chat_session_detail(
                user_id=command.user_id,
                project_id=command.workspace_id,
                session_id=sessions[0].session_id,
                limit=CHAT_SESSION_DETAIL_LIMIT,
                observed_at=datetime.now(UTC),
            )
            if not detail.messages:
                return ContinuityResolution(status="none")
            return _resolved_chat_session(sessions[0], detail, "previous_chat")
        search_terms = await self._expanded_terms(base_terms)
        matches = []
        for session in sessions:
            detail = await self._store.get_chat_session_detail(
                user_id=command.user_id,
                project_id=command.workspace_id,
                session_id=session.session_id,
                limit=CHAT_SESSION_DETAIL_LIMIT,
                observed_at=datetime.now(UTC),
            )
            if not detail.messages:
                continue
            score = _score_chat_session(session, detail, search_terms)
            if score > 0:
                matches.append((score, session, detail))
        if not matches:
            return ContinuityResolution(status="none")
        top_score = max(score for score, _, _ in matches)
        top_matches = [
            (session, detail)
            for score, session, detail in matches
            if score == top_score
        ]
        if len(top_matches) == 1:
            session, detail = top_matches[0]
            return _resolved_chat_session(session, detail, "previous_chat")
        return _ambiguous_chat_sessions(
            tuple(session for session, _ in top_matches[:5])
        )

    async def _expanded_terms(
        self,
        base_terms: tuple[str, ...],
    ) -> tuple[str, ...]:
        if self._term_expander is None:
            return base_terms
        try:
            expanded_terms = await self._term_expander.expand_terms(base_terms)
        except Exception:
            expanded_terms = ()
        return _dedupe_terms((*base_terms, *expanded_terms), maximum=8)


def _should_resolve(message: str) -> bool:
    return bool(_PRIOR_REFERENCE_RE.search(message))


def _should_resolve_chat(message: str) -> bool:
    return bool(_CHAT_REFERENCE_RE.search(message))


def _normalized_title(value: str) -> str:
    return " ".join(_tokens(value))


def _normalized_message(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _WORD_RE.findall(value.casefold())
        if token not in _STOP_WORDS
    )


def _sanitize_terms(terms: tuple[object, ...], *, maximum: int) -> tuple[str, ...]:
    safe_terms = []
    for raw_term in terms:
        if not isinstance(raw_term, str):
            continue
        token_match = _WORD_RE.fullmatch(raw_term.casefold().strip())
        if token_match is None:
            continue
        token = token_match.group(0)
        if token in _STOP_WORDS or not 3 <= len(token) <= 32:
            continue
        safe_terms.append(token)
    return _dedupe_terms(tuple(safe_terms), maximum=maximum)


def _dedupe_terms(terms: tuple[str, ...], *, maximum: int) -> tuple[str, ...]:
    result = []
    seen = set()
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        result.append(term)
        if len(result) >= maximum:
            break
    return tuple(result)


def _extract_chat_search_terms(message: str) -> tuple[str, ...]:
    return _sanitize_terms(_tokens(message), maximum=5)


def _note_matches_message_tokens(note: CollaborativeNote, message: str) -> bool:
    note_tokens = set(_tokens(note.title))
    message_tokens = set(_tokens(message))
    if not note_tokens or not message_tokens:
        return False
    return len(note_tokens & message_tokens) >= min(2, len(note_tokens))


def _receipt_for_note(
    note: CollaborativeNote,
    match_reason: str,
) -> ContinuitySourceReceipt:
    return ContinuitySourceReceipt(
        receipt_id=f"continuity--{note.note_id}--rev-{note.revision}",
        source_kind="collaborative_note",
        source_id=note.note_id,
        display_label=f"Used note: {note.title}",
        match_reason=match_reason,
        source_updated_at=note.updated_at,
    )


def _source_text_for_note(note: CollaborativeNote) -> ContinuitySourceText:
    return ContinuitySourceText(
        source_kind="collaborative_note",
        source_id=note.note_id,
        title=note.title,
        body=note.body,
        updated_at=note.updated_at,
    )


def _resolved_note(
    note: CollaborativeNote,
    match_reason: str,
) -> ContinuityResolution:
    return ContinuityResolution(
        status="resolved",
        receipts=[_receipt_for_note(note, match_reason)],
        source_texts=[_source_text_for_note(note)],
    )


def _ambiguous_notes(notes: tuple[CollaborativeNote, ...]) -> ContinuityResolution:
    return ContinuityResolution(
        status="ambiguous",
        choices=[
            ContinuityChoice(
                choice_id=f"choice-{index}",
                source_kind="collaborative_note",
                source_id=note.note_id,
                display_label=note.title,
                match_reason="bounded_relevance",
            )
            for index, note in enumerate(notes, start=1)
        ],
    )


def _score_chat_session(
    session: ChatSessionSummary,
    detail: ChatSessionDetailResponse,
    search_terms: tuple[str, ...],
) -> int:
    text = " ".join(
        (
            session.last_message_preview or "",
            *[message.text for message in detail.messages],
        )
    ).casefold()
    tokens = set(_tokens(text))
    return sum(1 for term in search_terms if term in tokens)


def _summary_from_detail(detail: ChatSessionDetailResponse) -> ChatSessionSummary:
    preview = next(
        (message.text for message in reversed(detail.messages) if message.text),
        detail.session_id,
    )
    preview = " ".join(preview.split())[:180]
    return ChatSessionSummary(
        session_id=detail.session_id,
        project_id=detail.project_id,
        user_id=detail.user_id,
        updated_at=None,
        last_message_preview=preview,
        last_message_role=None,
    )


def _receipt_for_chat_session(
    session: ChatSessionSummary,
    match_reason: str,
) -> ContinuitySourceReceipt:
    return ContinuitySourceReceipt(
        receipt_id=f"continuity--chat--{session.session_id}",
        source_kind="chat_session",
        source_id=session.session_id,
        display_label=f"Used prior chat: {_chat_session_label(session)}",
        match_reason=match_reason,
        source_updated_at=session.updated_at,
    )


def _source_text_for_chat_session(
    session: ChatSessionSummary,
    detail: ChatSessionDetailResponse,
) -> ContinuitySourceText:
    return ContinuitySourceText(
        source_kind="chat_session",
        source_id=session.session_id,
        title=f"Prior chat: {_chat_session_label(session)}",
        body=_chat_transcript_excerpt(detail),
        updated_at=session.updated_at,
    )


def _resolved_chat_session(
    session: ChatSessionSummary,
    detail: ChatSessionDetailResponse,
    match_reason: str,
) -> ContinuityResolution:
    return ContinuityResolution(
        status="resolved",
        receipts=[_receipt_for_chat_session(session, match_reason)],
        source_texts=[_source_text_for_chat_session(session, detail)],
    )


def _ambiguous_chat_sessions(
    sessions: tuple[ChatSessionSummary, ...],
) -> ContinuityResolution:
    return ContinuityResolution(
        status="ambiguous",
        choices=[
            ContinuityChoice(
                choice_id=f"choice-{index}",
                source_kind="chat_session",
                source_id=session.session_id,
                display_label=_chat_session_label(session),
                match_reason="previous_chat",
            )
            for index, session in enumerate(sessions, start=1)
        ],
    )


def _chat_session_label(session: ChatSessionSummary) -> str:
    preview = " ".join((session.last_message_preview or session.session_id).split())
    return preview[:120] or session.session_id


def _chat_transcript_excerpt(detail: ChatSessionDetailResponse) -> str:
    lines = []
    for message in detail.messages:
        role_label = "User" if message.role == "user" else "Agent Col"
        lines.append(f"{role_label}: {' '.join(message.text.split())}")
    return "\n".join(lines)[:2_000]
