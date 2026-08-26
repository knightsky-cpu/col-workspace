import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from collaborative_note_policy import CollaborativeNoteKind

CollaborativeNoteEventTypeName = Literal[
    "approved",
    "corrected",
    "superseded",
    "archived",
    "restored",
    "deleted",
]


@dataclass(frozen=True, slots=True)
class NoteProposalIds:
    proposal_id: str
    note_id: str
    seed: str

    def event_id(self, event_type: CollaborativeNoteEventTypeName) -> str:
        return f"{self.note_id}--{event_type}--{self.seed}"


def _stable_digest(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]


def derive_note_proposal_ids(
    *,
    user_id: str,
    workspace_id: str,
    session_id: str,
    source_message_ids: tuple[str, ...],
    note_kind: CollaborativeNoteKind,
    title: str,
    body: str,
    idempotency_key: str,
    expected_note_id: str | None,
    expected_revision: int | None,
) -> NoteProposalIds:
    seed = _stable_digest(
        {
            "user_id": user_id,
            "workspace_id": workspace_id,
            "session_id": session_id,
            "source_message_ids": list(source_message_ids),
            "note_kind": note_kind,
            "title": title,
            "body": body,
            "idempotency_key": idempotency_key,
            "expected_note_id": expected_note_id,
            "expected_revision": expected_revision,
        }
    )
    return NoteProposalIds(
        proposal_id=f"note_proposal--{seed}",
        note_id=expected_note_id or f"note--{seed}",
        seed=seed,
    )
