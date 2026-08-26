import re
import unicodedata
from typing import Literal

from memory_policy import USER_REQUESTED_MEMORY_PROHIBITED_PATTERNS


COLLABORATIVE_NOTE_POLICY_VERSION = "1.0"
COLLABORATIVE_NOTE_CONTRACT_VERSION = "1.0"

CollaborativeNoteKind = Literal[
    "decision",
    "requirement",
    "constraint",
    "task_state",
    "working_context",
]
CollaborativeNoteProposalStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "expired",
]
CollaborativeNoteStatus = Literal["active", "archived"]
CollaborativeNoteEventType = Literal[
    "approved",
    "corrected",
    "superseded",
    "archived",
    "restored",
    "deleted",
]

_NOTE_KINDS = frozenset(
    {
        "decision",
        "requirement",
        "constraint",
        "task_state",
        "working_context",
    }
)
_PROPOSAL_STATUSES = frozenset({"pending", "approved", "rejected", "expired"})
_ACTIVE_NOTE_STATUSES = frozenset({"active", "archived"})
_EVENT_TYPES = frozenset(
    {"approved", "corrected", "superseded", "archived", "restored", "deleted"}
)
_NOTE_EVERYTHING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bnote\s+everything\b", re.IGNORECASE),
)


def _validate_vocabulary(value: object, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError("Value is not supported by the collaborative-note policy.")
    return value


def validate_note_kind(value: object) -> str:
    return _validate_vocabulary(value, _NOTE_KINDS)


def validate_proposal_status(value: object) -> str:
    return _validate_vocabulary(value, _PROPOSAL_STATUSES)


def validate_active_note_status(value: object) -> str:
    return _validate_vocabulary(value, _ACTIVE_NOTE_STATUSES)


def validate_note_event_type(value: object) -> str:
    return _validate_vocabulary(value, _EVENT_TYPES)


def validate_policy_version(value: object) -> str:
    if value != COLLABORATIVE_NOTE_POLICY_VERSION or not isinstance(value, str):
        raise ValueError("Collaborative-note policy version must be exactly 1.0.")
    return value


def validate_note_contract_version(value: object) -> str:
    if value != COLLABORATIVE_NOTE_CONTRACT_VERSION or not isinstance(value, str):
        raise ValueError("Collaborative-note contract version must be exactly 1.0.")
    return value


def _require_string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Collaborative-note text must be a string.")
    return value


def _reject_prohibited_controls(value: str, *, allow_line_controls: bool) -> None:
    allowed = frozenset({"\t", "\n", "\r"}) if allow_line_controls else frozenset()
    if any(
        unicodedata.category(character).startswith("C")
        and character not in allowed
        for character in value
    ):
        raise ValueError("Collaborative-note text contains prohibited controls.")


def _require_length(value: str, *, maximum: int) -> str:
    if not 1 <= len(value) <= maximum:
        raise ValueError("Collaborative-note text is outside its permitted bounds.")
    return value


def normalize_note_title(value: object) -> str:
    raw_value = _require_string(value)
    _reject_prohibited_controls(raw_value, allow_line_controls=False)
    normalized = unicodedata.normalize("NFC", raw_value)
    return _require_length(" ".join(normalized.split()), maximum=120)


def normalize_note_body(value: object) -> str:
    raw_value = _require_string(value)
    _reject_prohibited_controls(raw_value, allow_line_controls=True)
    normalized = raw_value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = unicodedata.normalize("NFC", normalized).strip()
    return _require_length(normalized, maximum=2_000)


def validate_note_storage_text(value: object) -> str:
    normalized = normalize_note_body(value)
    if not any(character.isalpha() for character in normalized):
        raise ValueError("Collaborative-note text must contain a letter.")
    for pattern in (
        *USER_REQUESTED_MEMORY_PROHIBITED_PATTERNS,
        *_NOTE_EVERYTHING_PATTERNS,
    ):
        if pattern.search(normalized):
            raise ValueError("Collaborative-note text contains prohibited content.")
    return normalized
