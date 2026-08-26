"""Deterministic note-first continuity resolution."""

import re
from dataclasses import dataclass
from typing import Protocol

from continuity import (
    ContinuityChoice,
    ContinuityResolution,
    ContinuitySelectionRequest,
    ContinuitySourceReceipt,
    ContinuitySourceText,
)
from schemas import CollaborativeNote


_PRIOR_REFERENCE_RE = re.compile(
    r"\b(previous|prior|earlier|last|before|decided|agreed|note|notes|"
    r"requirement|requirements|constraint|constraints|task|workspace)\b",
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
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "use",
        "we",
        "were",
        "what",
        "with",
    }
)


class ContinuityNoteReader(Protocol):
    async def list_active_collaborative_notes_for_continuity(
        self,
        *,
        user_id: str,
        workspace_id: str,
        limit: int,
    ) -> tuple[CollaborativeNote, ...]: ...


@dataclass(frozen=True, slots=True)
class ContinuityResolutionCommand:
    user_id: str
    workspace_id: str
    message: str
    selection: ContinuitySelectionRequest | None = None


class ContinuityService:
    def __init__(self, *, note_reader: ContinuityNoteReader) -> None:
        self._note_reader = note_reader

    async def resolve(
        self,
        command: ContinuityResolutionCommand,
    ) -> ContinuityResolution:
        if command.selection is None and not _should_resolve(command.message):
            return ContinuityResolution(status="none")
        notes = await self._note_reader.list_active_collaborative_notes_for_continuity(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            limit=50,
        )
        active_notes = tuple(note for note in notes if note.status == "active")
        if command.selection is not None:
            selected = next(
                (
                    note
                    for note in active_notes
                    if note.note_id == command.selection.source_id
                ),
                None,
            )
            if selected is None:
                return ContinuityResolution(status="none")
            return _resolved_note(selected, "user_selected")

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


def _should_resolve(message: str) -> bool:
    return bool(_PRIOR_REFERENCE_RE.search(message))


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
