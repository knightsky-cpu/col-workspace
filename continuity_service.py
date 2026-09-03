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
RECENT_CONTINUITY_RECEIPT_LIMIT = 5


_PRIOR_REFERENCE_RE = re.compile(
    r"\b(previous|prior|earlier|last|before|decide|decided|agreed|note|notes|"
    r"requirement|requirements|constraint|constraints|task|workspace|"
    r"recent|recently|talk|talked|spoke|discuss|discussed|settled|"
    r"wanted|remind|leave|left|again|remember|recall)\b",
    re.IGNORECASE,
)
_QUESTION_SHAPE_RE = re.compile(
    r"\b(what|which|where|who|when|how)\s+"
    r"(?:[a-z0-9]+\s+){0,4}(was|were|is|are|did|do|does|had|have)\b",
    re.IGNORECASE,
)
_CONTINUITY_PROMPT_RE = re.compile(
    r"\b(what|which|where|who|when|how|do|did|does|have|had|remind|recall|"
    r"remember|tell)\b",
    re.IGNORECASE,
)
_PERSONAL_REFERENCE_RE = re.compile(
    r"\b(i|me|my|we|our|us|you|your|together)\b",
    re.IGNORECASE,
)
_VAGUE_REFERENCE_RE = re.compile(
    r"\b(it|that|this|they|those|one|thing|stuff|idea|plan|project|app|"
    r"application|work|context)\b",
    re.IGNORECASE,
)
_PAST_CONTEXT_RE = re.compile(
    r"\b(was|were|did|had|already|again|before|earlier|previous|prior|last|"
    r"recent|recently|back|settled|decided|agreed|picked|chose|selected|"
    r"mentioned|talked|discussed|said|wanted|needed|leave|left)\b",
    re.IGNORECASE,
)
_CONTINUITY_ACTION_RE = re.compile(
    r"\b(want|wanted|need|needed|say|said|mention|mentioned|talk|talked|"
    r"discuss|discussed|pick|picked|choose|chose|chosen|select|selected|"
    r"decide|decided|agree|agreed|settle|settled|name|named|called|call|"
    r"write|written|writing|build|built|building|use|using|going|thinking|"
    r"supposed|should|leave|left|doing|working)\b",
    re.IGNORECASE,
)
_COLLABORATIVE_DECISION_QUESTION_RE = re.compile(
    r"\b(?:did|do|does|have|had)\s+(?:we|i|you)\b.*\b(?:"
    r"pick|picked|choose|chose|chosen|select|selected|settle|settled|"
    r"decide|decided|agree|agreed|already"
    r")\b",
    re.IGNORECASE,
)
_COLLABORATIVE_REFERENCE_RE = re.compile(
    r"\b(we|our|us|together)\b",
    re.IGNORECASE,
)
_CONTEXT_TOPIC_RE = re.compile(
    r"\b(name|named|called|title|project|app|application|requirement|"
    r"requirements|constraint|constraints|task|decision|decide|decided|"
    r"agree|agreed|pick|picked|choose|chose|chosen|select|selected|"
    r"wanted|want|said|say|working|doing|leave|left|language|write|writing|"
    r"written|build|building|built|implemented|programming|stack|framework|"
    r"platform|runtime|tool|library|goal|scope|purpose|about|needed|need|"
    r"should|supposed|using|use)\b",
    re.IGNORECASE,
)
_ANAPHORIC_FOLLOW_UP_RE = re.compile(
    r"\b("
    r"what\s+(?:was|is)\s+(?:it|that|this)\s+about|"
    r"what\s+(?:was|is)\s+(?:it|that|this)\s+going\s+to\s+be\s+written\s+in|"
    r"what\s+language\s+(?:was|is)\s+(?:it|that|this)\b|"
    r"what\s+(?:tech\s+stack|stack|framework)\s+(?:was|is)\s+(?:it|that|this)\b|"
    r"tell\s+me\s+more\s+about\s+(?:it|that|this)|"
    r"what\s+(?:did|does)\s+(?:it|that|this)\s+(?:mean|refer\s+to)|"
    r"what\s+else\s+about\s+(?:it|that|this)"
    r")\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9]+")
_TOKEN_CONCEPTS = {
    "app": "project",
    "application": "project",
    "build": "implementation",
    "building": "implementation",
    "built": "implementation",
    "call": "name",
    "called": "name",
    "choose": "decide",
    "chosen": "decide",
    "chose": "decide",
    "decided": "decide",
    "decision": "decide",
    "finalized": "decide",
    "framework": "language",
    "frameworks": "language",
    "implemented": "implementation",
    "library": "language",
    "libraries": "language",
    "need": "requirement",
    "needed": "requirement",
    "named": "name",
    "naming": "name",
    "pick": "decide",
    "picked": "decide",
    "platform": "language",
    "platforms": "language",
    "programming": "language",
    "purpose": "purpose",
    "required": "requirement",
    "require": "requirement",
    "requirements": "requirement",
    "selected": "decide",
    "settle": "decide",
    "settled": "decide",
    "stack": "language",
    "supposed": "requirement",
    "tech": "language",
    "thing": "project",
    "tool": "language",
    "tools": "language",
    "title": "name",
    "runtime": "language",
    "runtimes": "language",
    "write": "language",
    "written": "language",
    "writing": "language",
}
_CONTEXT_FACET_CONCEPTS = frozenset(
    {
        "constraint",
        "decide",
        "description",
        "goal",
        "implementation",
        "language",
        "name",
        "purpose",
        "requirement",
        "scope",
        "task",
    }
)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "again",
        "are",
        "as",
        "about",
        "chat",
        "col",
        "conversation",
        "did",
        "do",
        "discuss",
        "discussed",
        "for",
        "hey",
        "i",
        "in",
        "is",
        "it",
        "last",
        "left",
        "me",
        "my",
        "of",
        "off",
        "on",
        "or",
        "prior",
        "recent",
        "recently",
        "recall",
        "remind",
        "remember",
        "session",
        "spoke",
        "talk",
        "talked",
        "that",
        "the",
        "this",
        "to",
        "use",
        "was",
        "we",
        "were",
        "where",
        "what",
        "with",
        "working",
        "you",
        "your",
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

    async def list_recent_session_continuity_receipts(
        self,
        *,
        user_id: str,
        project_id: str,
        session_id: str,
        limit: int,
    ) -> tuple[ContinuitySourceReceipt, ...]: ...

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
        should_resolve = _should_resolve(command.message)
        is_anaphoric_follow_up = _is_anaphoric_follow_up(command.message)
        if (
            command.selection is None
            and not should_resolve
            and not is_anaphoric_follow_up
        ):
            return ContinuityResolution(status="none")
        if command.selection is not None:
            if command.selection.source_kind == "chat_session":
                return await self._resolve_selected_chat(command)
            return await self._resolve_selected_note(command)
        if is_anaphoric_follow_up:
            recent_resolution = await self._resolve_recent_continuity_anchor(
                command
            )
            if recent_resolution.status != "none":
                return recent_resolution
            if not should_resolve:
                return ContinuityResolution(status="none")
        note_resolution = await self._resolve_active_notes(command)
        if note_resolution.status != "none":
            return note_resolution
        return await self._resolve_prior_chat(command)

    async def _resolve_recent_continuity_anchor(
        self,
        command: ContinuityResolutionCommand,
    ) -> ContinuityResolution:
        receipts = await self._store.list_recent_session_continuity_receipts(
            user_id=command.user_id,
            project_id=command.workspace_id,
            session_id=command.session_id,
            limit=RECENT_CONTINUITY_RECEIPT_LIMIT,
        )
        if not receipts:
            return ContinuityResolution(status="none")

        active_notes: tuple[CollaborativeNote, ...] | None = None
        for receipt in receipts:
            if receipt.source_kind == "collaborative_note":
                if active_notes is None:
                    notes = (
                        await self._store.list_active_collaborative_notes_for_continuity(
                            user_id=command.user_id,
                            workspace_id=command.workspace_id,
                            limit=50,
                        )
                    )
                    active_notes = tuple(
                        note for note in notes if note.status == "active"
                    )
                note = next(
                    (
                        note
                        for note in active_notes
                        if note.note_id == receipt.source_id
                    ),
                    None,
                )
                if note is not None:
                    related_resolution = _resolve_related_note_from_anchor(
                        active_notes,
                        note,
                        command.message,
                    )
                    if related_resolution.status != "none":
                        return related_resolution
                    return _resolved_note(note, "recent_continuity")
            elif receipt.source_kind == "chat_session":
                detail = await self._store.get_chat_session_detail(
                    user_id=command.user_id,
                    project_id=command.workspace_id,
                    session_id=receipt.source_id,
                    limit=CHAT_SESSION_DETAIL_LIMIT,
                    observed_at=datetime.now(UTC),
                )
                if detail.session_id != command.session_id and detail.messages:
                    summary = _summary_from_detail(detail)
                    return _resolved_chat_session(
                        summary,
                        detail,
                        "recent_continuity",
                    )
        return ContinuityResolution(status="none")

    async def _resolve_active_notes(
        self,
        command: ContinuityResolutionCommand,
    ) -> ContinuityResolution:
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

        scored_candidates = _score_note_matches(
            active_notes,
            command.message,
            allow_single_facet_match=_has_historical_reference_intent(
                command.message
            ),
        )
        if len(scored_candidates) == 1:
            return _resolved_note(scored_candidates[0][1], "bounded_relevance")
        if len(scored_candidates) > 1:
            top_score = scored_candidates[0][0]
            top_notes = tuple(
                note for score, note in scored_candidates if score == top_score
            )
            if len(top_notes) == 1:
                return _resolved_note(top_notes[0], "bounded_relevance")
            return _ambiguous_notes(top_notes[:5])
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
    normalized = " ".join(_WORD_RE.findall(message.casefold()))
    if _is_imperative_new_work_prompt(normalized):
        return False
    return bool(
        _PRIOR_REFERENCE_RE.search(message)
        or _has_historical_question_shape(message)
        or _has_collaborative_decision_question_shape(message)
        or _has_broad_continuity_intent(message)
    )


def _is_anaphoric_follow_up(message: str) -> bool:
    normalized = " ".join(_WORD_RE.findall(message.casefold()))
    return bool(
        _ANAPHORIC_FOLLOW_UP_RE.search(normalized)
        or _has_pronoun_facet_follow_up(normalized)
    )


def _has_pronoun_facet_follow_up(normalized_message: str) -> bool:
    if not re.search(r"\b(it|that|this)\b", normalized_message):
        return False
    if not _has_collaborative_decision_question_shape(normalized_message):
        return False
    return bool(_follow_up_facet_concepts(normalized_message))


def _has_historical_question_shape(message: str) -> bool:
    normalized = " ".join(_WORD_RE.findall(message.casefold()))
    if not _QUESTION_SHAPE_RE.search(normalized):
        return False
    return bool(
        _COLLABORATIVE_REFERENCE_RE.search(normalized)
        and _CONTEXT_TOPIC_RE.search(normalized)
    )


def _has_collaborative_decision_question_shape(message: str) -> bool:
    normalized = " ".join(_WORD_RE.findall(message.casefold()))
    if not _COLLABORATIVE_DECISION_QUESTION_RE.search(normalized):
        return False
    return bool(_CONTEXT_TOPIC_RE.search(normalized))


def _has_broad_continuity_intent(message: str) -> bool:
    normalized = " ".join(_WORD_RE.findall(message.casefold()))
    if not normalized or not _CONTINUITY_PROMPT_RE.search(normalized):
        return False
    if _is_imperative_new_work_prompt(normalized):
        return False
    if re.search(r"\b(what|which|how)\s+(?:is|are)\s+(?:a|an)\b", normalized):
        return False
    if re.search(r"\bwhat\s+do\s+you\s+call\s+(?:a|an)\b", normalized):
        return False
    has_topic = bool(_CONTEXT_TOPIC_RE.search(normalized))
    has_reference = bool(_VAGUE_REFERENCE_RE.search(normalized))
    has_personal = bool(_PERSONAL_REFERENCE_RE.search(normalized))
    has_past = bool(_PAST_CONTEXT_RE.search(normalized))
    has_action = bool(_CONTINUITY_ACTION_RE.search(normalized))
    if re.search(r"\b(remind|recall|remember)\b", normalized) and (
        has_topic or has_reference or has_personal
    ):
        return True
    if has_topic and has_past and (has_reference or has_personal):
        return True
    if has_topic and has_action and (has_reference or has_personal):
        return True
    if has_reference and has_personal and has_action:
        return True
    if has_topic and re.search(r"\b(was|were|did|had|have)\b", normalized):
        return True
    return False


def _is_imperative_new_work_prompt(normalized_message: str) -> bool:
    if not normalized_message:
        return False
    if _QUESTION_SHAPE_RE.search(normalized_message):
        return False
    if _COLLABORATIVE_DECISION_QUESTION_RE.search(normalized_message):
        return False
    if _ANAPHORIC_FOLLOW_UP_RE.search(normalized_message):
        return False
    if re.search(
        r"\b(previous|prior|earlier|last|before|decided|agreed|settled|"
        r"left\s+off|talked|discussed|mentioned|said)\b",
        normalized_message,
    ):
        return False
    if _is_explicit_new_memory_instruction(normalized_message):
        return True
    return bool(
        re.search(
            r"\b(create|add|write|build|make|generate|draft|record|save)\b",
            normalized_message,
        )
        and re.search(
            r"\b(workspace|note|artifact|program|code|project|app|"
            r"application)\b",
            normalized_message,
        )
    )


def _is_explicit_new_memory_instruction(normalized_message: str) -> bool:
    return bool(
        re.search(
            r"^(?:please\s+)?remember\s+that\s+(?:i|me|my|we|our|us)\b",
            normalized_message,
        )
        or re.search(
            r"^(?:please\s+)?remind\s+me\s+to\s+[a-z0-9]+\b",
            normalized_message,
        )
    )


def _has_historical_reference_intent(message: str) -> bool:
    normalized = " ".join(_WORD_RE.findall(message.casefold()))
    if _is_imperative_new_work_prompt(normalized):
        return False
    return bool(
        _PRIOR_REFERENCE_RE.search(message)
        or _has_historical_question_shape(message)
        or _has_collaborative_decision_question_shape(message)
        or _is_anaphoric_follow_up(message)
        or _has_broad_continuity_intent(message)
    )


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


def _concepts(value: str) -> set[str]:
    return {_TOKEN_CONCEPTS.get(token, token) for token in _tokens(value)}


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


def _note_matches_message_tokens(
    note: CollaborativeNote,
    message: str,
    *,
    allow_single_facet_match: bool = False,
) -> bool:
    note_concepts = _concepts(f"{note.title} {note.body}")
    message_concepts = _concepts(message)
    if not note_concepts or not message_concepts:
        return False
    overlap = note_concepts & message_concepts
    if "note" in _tokens(message) and overlap:
        return True
    if allow_single_facet_match and overlap & _CONTEXT_FACET_CONCEPTS:
        return True
    if _score_note_match(note, message, allow_single_facet_match) > 0:
        return True
    return len(overlap) >= min(2, len(note_concepts))


def _score_note_matches(
    notes: tuple[CollaborativeNote, ...],
    message: str,
    *,
    allow_single_facet_match: bool,
) -> tuple[tuple[int, CollaborativeNote], ...]:
    scored = tuple(
        (score, note)
        for note in notes
        if (
            score := _score_note_match(
                note,
                message,
                allow_single_facet_match,
            )
        )
        > 0
    )
    return tuple(sorted(scored, key=lambda item: item[0], reverse=True))


def _score_note_match(
    note: CollaborativeNote,
    message: str,
    allow_single_facet_match: bool,
) -> int:
    note_concepts = _concepts(f"{note.title} {note.body}")
    message_concepts = _concepts(message)
    if not note_concepts:
        return 0
    overlap = note_concepts & message_concepts
    requested_facets = _requested_facet_concepts(message)
    requested_overlap = note_concepts & requested_facets
    score = len(overlap) * 2
    score += len(requested_overlap) * 5
    if "note" in _tokens(message) and overlap:
        score += 4
    if "project" in note_concepts and _VAGUE_REFERENCE_RE.search(message):
        score += 1
    if allow_single_facet_match and requested_overlap:
        return score
    if len(overlap) >= min(2, len(note_concepts)):
        return score
    return 0


def _resolve_related_note_from_anchor(
    active_notes: tuple[CollaborativeNote, ...],
    anchor_note: CollaborativeNote,
    message: str,
) -> ContinuityResolution:
    facet_concepts = _follow_up_facet_concepts(message)
    if not facet_concepts:
        return ContinuityResolution(status="none")

    anchor_concepts = _concepts(f"{anchor_note.title} {anchor_note.body}")
    scored = []
    for note in active_notes:
        note_concepts = _concepts(f"{note.title} {note.body}")
        if not note_concepts:
            continue
        facet_score = len(note_concepts & facet_concepts)
        requested_title_score = _requested_title_facet_score(note, message)
        requested_score = len(note_concepts & _requested_facet_concepts(message))
        anchor_score = len(note_concepts & anchor_concepts)
        if note.note_id == anchor_note.note_id:
            continue
        score = (
            requested_title_score * 10
            + requested_score * 4
            + facet_score
            + min(anchor_score, 1)
        )
        if score > 0 and facet_score > 0:
            scored.append((score, note))
    if not scored:
        return ContinuityResolution(status="none")
    top_score = max(score for score, _ in scored)
    top_notes = tuple(note for score, note in scored if score == top_score)
    if len(top_notes) == 1:
        return _resolved_note(top_notes[0], "recent_continuity")
    return _ambiguous_notes(top_notes[:5])


def _follow_up_facet_concepts(message: str) -> set[str]:
    normalized = " ".join(_WORD_RE.findall(message.casefold()))
    concepts = _concepts(normalized)
    facets = _requested_facet_concepts(normalized)
    return concepts | facets


def _requested_title_facet_score(note: CollaborativeNote, message: str) -> int:
    title_concepts = _concepts(note.title)
    requested_facets = _requested_facet_concepts(message)
    return len(title_concepts & requested_facets)


def _requested_facet_concepts(message: str) -> set[str]:
    normalized = " ".join(_WORD_RE.findall(message.casefold()))
    facets: set[str] = set()
    if re.search(
        r"\b(name|named|called|call|title)\b",
        normalized,
    ) or re.search(
        r"\bwhat\s+(?:was|is)\s+(?:that|the)?\s*(?:project|app|application|"
        r"thing)\b",
        normalized,
    ):
        facets.update({"name"})
    has_language_facet = bool(
        re.search(
            r"\b(language|written|programming|tech|stack|framework|build|built|"
            r"building|write|writing|tool|tools|library|libraries|use|using)\b",
            normalized,
        )
    )
    has_contextual_left_off = bool(
        re.search(r"\b(?:leave|left)\s+off\b", normalized)
        and re.search(
            r"\b(it|that|this|project|app|application|thing|plan|idea|work)\b",
            normalized,
        )
    )
    has_requirement_facet = bool(
        has_contextual_left_off
        or re.search(
            r"\b(about|purpose|goal|scope|overview|description|needed|need|"
            r"requirements?|constraints?|supposed|"
            r"want(?:ed)?\b(?!.*\b(language|written|programming|tech|stack|"
            r"framework|build|built|building|write|writing|tool|tools|library|"
            r"libraries|use|using)\b)|should\s+(?:do|be|have|support))\b",
            normalized,
        )
    )
    if has_requirement_facet:
        facets.update({"requirement", "purpose", "scope", "goal", "description"})
    if has_language_facet:
        facets.update({"language", "implementation"})
    return facets


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
