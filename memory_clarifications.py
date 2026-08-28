import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal, Self

from pydantic import Field, model_validator

from memory_policy import (
    DEVELOPMENT_ENVIRONMENT_LABELS,
    MemoryCategoryV2,
    validate_memory_value_for_policy,
)
from schemas import (
    IdentifierStr,
    MemoryClarificationChoice,
    MemoryClarificationReceipt,
    StrictModel,
)


CLARIFICATION_SCHEMA_VERSION = "1.0"
MAX_CLARIFICATION_LIFETIME = timedelta(minutes=15)


_CATEGORY_LABELS: dict[str, str] = {
    "preferred_name": "Preferred name",
    "broad_roles": "Broad roles",
    "domain_experience": "Domain experience",
    "response_length": "Response length",
    "explanation_structure": "Explanation structure",
    "explanation_pace": "Explanation pace",
    "example_usage": "Example usage",
    "learning_approach": "Learning approach",
    "question_style": "Question style",
    "planning_granularity": "Planning granularity",
    "progress_check_ins": "Progress check-ins",
    "tool_use_style": "Tool use style",
    "formatting_style": "Formatting style",
    "accessibility_support": "Accessibility support",
    "development_environments": "Development environments",
}


class _ClarificationIdentity(StrictModel):
    user_id: IdentifierStr
    session_id: IdentifierStr
    evidence_message_id: IdentifierStr
    clarification_turn_id: IdentifierStr


class MemoryClarificationCandidate(StrictModel):
    kind: Literal["memory_candidate", "no_save"] = "memory_candidate"
    category: MemoryCategoryV2 | None = None
    canonical_value: object | None = None

    @model_validator(mode="after")
    def validate_canonical_value(self) -> Self:
        if self.kind == "no_save":
            if self.category is not None or self.canonical_value is not None:
                raise ValueError(
                    "Do-not-save clarification choices cannot contain "
                    "memory values."
                )
            return self
        if self.category is None:
            raise ValueError("Memory clarification candidate requires a category.")
        if self.canonical_value is None:
            raise ValueError("Memory clarification candidate requires a value.")
        normalized = validate_memory_value_for_policy(
            "2.0",
            self.category,
            self.canonical_value,
        )
        object.__setattr__(self, "canonical_value", normalized)
        return self


class MemoryClarificationEnvelope(StrictModel):
    clarification_schema_version: Literal["1.0"] = (
        CLARIFICATION_SCHEMA_VERSION
    )
    clarification_id: IdentifierStr
    user_id: IdentifierStr
    session_id: IdentifierStr
    workspace_id: IdentifierStr
    evidence_message_id: IdentifierStr
    clarification_turn_id: IdentifierStr
    candidates: list[MemoryClarificationCandidate] = Field(
        min_length=2,
        max_length=5,
    )
    created_at: datetime
    expires_at: datetime
    status: Literal["open", "consumed", "expired"]
    consuming_turn_id: IdentifierStr | None = None
    consuming_message_id: IdentifierStr | None = None
    selected_candidate_index: int | None = Field(default=None, ge=0, le=4)

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
        ):
            raise ValueError("Clarification timestamps must be timezone aware.")
        lifetime = self.expires_at - self.created_at
        if lifetime <= timedelta(0) or lifetime > MAX_CLARIFICATION_LIFETIME:
            raise ValueError(
                "Clarification lifetime must be greater than zero and no "
                "longer than 15 minutes."
            )

        identities = [
            (
                candidate.kind,
                candidate.category,
                json.dumps(
                    candidate.canonical_value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            for candidate in self.candidates
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("Clarification candidates must be unique.")

        consumption_values = (
            self.consuming_turn_id,
            self.consuming_message_id,
            self.selected_candidate_index,
        )
        if self.status == "consumed":
            if any(value is None for value in consumption_values):
                raise ValueError(
                    "Consumed clarification requires a selected candidate "
                    "and consuming turn and message."
                )
            if self.selected_candidate_index >= len(self.candidates):
                raise ValueError(
                    "Consumed clarification selected candidate is out of "
                    "range."
                )
        elif any(value is not None for value in consumption_values):
            state_label = "Open" if self.status == "open" else "Expired"
            raise ValueError(
                f"{state_label} clarification cannot contain consumption "
                "fields."
            )
        return self


class MemoryClarificationSelection(StrictModel):
    selected_candidate_index: int = Field(ge=0, le=4)


def derive_memory_clarification_id(
    *,
    user_id: object,
    session_id: object,
    evidence_message_id: object,
    clarification_turn_id: object,
) -> str:
    identity = _ClarificationIdentity.model_validate(
        {
            "user_id": user_id,
            "session_id": session_id,
            "evidence_message_id": evidence_message_id,
            "clarification_turn_id": clarification_turn_id,
        }
    )
    material = json.dumps(
        {
            "namespace": "agent-col-memory-clarification-v1",
            **identity.model_dump(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"memory-clarification--{hashlib.sha256(material).hexdigest()}"


def _human_value_label(category: str, value: object) -> str:
    if category == "development_environments":
        labels = [DEVELOPMENT_ENVIRONMENT_LABELS[item] for item in value]
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} and {labels[1]}"
        return f"{', '.join(labels[:-1])}, and {labels[-1]}"
    if category == "domain_experience":
        return "; ".join(
            f"{item['domain'].replace('_', ' ')}: "
            f"{item['level'].replace('_', ' ')}"
            for item in value
        )
    if type(value) is list:
        labels = [str(item).replace("_", " ") for item in value]
        return ", ".join(labels)
    return str(value).replace("_", " ")


def clarification_receipt(
    envelope: MemoryClarificationEnvelope,
) -> MemoryClarificationReceipt:
    if envelope.status != "open":
        raise ValueError("Only an open clarification has selectable choices.")
    return MemoryClarificationReceipt(
        clarification_id=envelope.clarification_id,
        choices=[
            MemoryClarificationChoice(
                candidate_index=index,
                category_label=(
                    "Do not save"
                    if candidate.kind == "no_save"
                    else _CATEGORY_LABELS[candidate.category]
                ),
                value_label=(
                    "Keep this as feedback only"
                    if candidate.kind == "no_save"
                    else _human_value_label(
                        candidate.category,
                        candidate.canonical_value,
                    )
                ),
            )
            for index, candidate in enumerate(envelope.candidates)
        ],
        expires_at=envelope.expires_at,
    )


def validate_memory_clarification_selection(
    *,
    envelope: MemoryClarificationEnvelope,
    selection: MemoryClarificationSelection,
    user_id: str,
    session_id: str,
    workspace_id: str,
    selecting_turn_id: str,
    selecting_message_id: str,
    is_first_subsequent_turn: bool,
    observed_at: datetime,
) -> MemoryClarificationCandidate:
    if envelope.status != "open":
        raise ValueError("Memory clarification is not open.")
    if (
        user_id != envelope.user_id
        or session_id != envelope.session_id
        or workspace_id != envelope.workspace_id
    ):
        raise ValueError(
            "Memory clarification is not owned by this user, session, and "
            "workspace."
        )
    if (
        selecting_turn_id == envelope.clarification_turn_id
        or selecting_message_id == envelope.evidence_message_id
    ):
        raise ValueError(
            "Memory clarification may only be selected on a subsequent turn."
        )
    if type(is_first_subsequent_turn) is not bool:
        raise ValueError(
            "First-subsequent-turn determination must be a boolean."
        )
    if not is_first_subsequent_turn:
        raise ValueError(
            "Memory clarification is valid only on the first subsequent "
            "user turn."
        )
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("Selection timestamp must be timezone aware.")
    if observed_at <= envelope.created_at:
        raise ValueError(
            "Memory clarification may only be selected on a subsequent turn."
        )
    if observed_at >= envelope.expires_at:
        raise ValueError("Memory clarification has expired.")
    index = selection.selected_candidate_index
    if index >= len(envelope.candidates):
        raise ValueError("Memory clarification selected candidate is invalid.")
    return envelope.candidates[index]
