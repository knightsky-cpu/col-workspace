from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator, model_validator

from collaborative_note_policy import (
    CollaborativeNoteKind,
    normalize_note_title,
    validate_note_storage_text,
)
from memory_candidate_decisions import ProhibitedMemoryReason
from schemas import StrictModel


class NoNoteDecision(StrictModel):
    kind: Literal["no_note"] = "no_note"


class NoteCandidateDecision(StrictModel):
    kind: Literal["note_candidate"] = "note_candidate"
    note_kind: CollaborativeNoteKind
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=2_000)
    evidence_text: str = Field(min_length=1, max_length=500)

    @field_validator("evidence_text")
    @classmethod
    def require_unicode_scalar_evidence(cls, value: str) -> str:
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("Evidence text must contain Unicode scalars.")
        return value

    @model_validator(mode="after")
    def normalize_note_text(self) -> "NoteCandidateDecision":
        object.__setattr__(self, "title", normalize_note_title(self.title))
        object.__setattr__(self, "body", validate_note_storage_text(self.body))
        return self


class ProhibitedNoteDecision(StrictModel):
    kind: Literal["prohibited"] = "prohibited"
    reason_code: ProhibitedMemoryReason


NaturalCollaborativeNoteDecision = Annotated[
    NoNoteDecision | NoteCandidateDecision | ProhibitedNoteDecision,
    Field(discriminator="kind"),
]
ProviderCollaborativeNoteDecision = NaturalCollaborativeNoteDecision

_PROVIDER_NOTE_DECISION_ADAPTER = TypeAdapter(ProviderCollaborativeNoteDecision)


def validate_provider_collaborative_note_decision(
    value: object,
) -> NaturalCollaborativeNoteDecision:
    return _PROVIDER_NOTE_DECISION_ADAPTER.validate_python(value)


def validate_note_candidate_evidence(
    decision: NaturalCollaborativeNoteDecision,
    source_message: str,
) -> None:
    if type(source_message) is not str:
        raise ValueError("Source message must be a string.")
    if not isinstance(decision, NoteCandidateDecision):
        return
    if decision.evidence_text not in source_message:
        raise ValueError(
            "Collaborative-note evidence must be an exact substring of the "
            "source message."
        )
