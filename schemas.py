import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from collaborative_note_policy import (
    CollaborativeNoteKind,
    CollaborativeNoteProposalStatus,
    CollaborativeNoteStatus,
    normalize_note_body,
    normalize_note_title,
)
from memory_policy import (
    ConfirmationChannel,
    AccessibilitySupport,
    DevelopmentEnvironment,
    DomainExperienceDomain,
    DomainExperienceLevel,
    ExplanationPace,
    MEMORY_POLICY_VERSION,
    MEMORY_POLICY_VERSION_V2,
    MEMORY_SCHEMA_VERSION,
    MEMORY_SCHEMA_VERSION_V2,
    IdentityContextCategory,
    IdentityContextCategoryV2,
    LearningApproach,
    MemoryCategory,
    MemoryCategoryV2,
    MemoryDecision,
    MemoryEventType,
    MemoryValue,
    PreferenceCategory,
    PreferenceCategoryV2,
    UserRequestedMemoryStr,
    validate_memory_value,
    validate_memory_value_for_policy,
)


SYNTHESIS_BLUEPRINT_SCHEMA_VERSION = "2.0"
ARTIFACT_CONTRACT_VERSION = "1.0"


NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
ChatMessageText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=10_000,
    ),
]
IdentifierStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]
SourceText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=10_000,
    ),
]
DisplayLabelStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
ProjectDisplayNameStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
GeneratedLabelStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
GeneratedTextStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_500),
]
ArtifactFeedbackText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_500),
]
ArtifactFilenameStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._ -]*$",
    ),
]
ArtifactContentStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=200_000),
]
VerificationStepStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentActionReceipt(StrictModel):
    action_name: Literal[
        "synthesize_project",
        "create_artifact",
        "google_search",
        "url_context",
        "run_computation",
        "verify_requirements",
        "record_blueprint_feedback",
        "propose_memory_signal",
        "approve_memory_signal",
        "reject_memory_signal",
        "revoke_memory_signal",
        "delete_memory_signal",
    ]
    status: Literal["completed"]


class ArtifactReference(StrictModel):
    artifact_type: Literal["synthesis_blueprint", "single_file_artifact"]
    project_id: IdentifierStr
    artifact_id: IdentifierStr
    schema_version: Literal["1.0", "2.0"]
    display_label: DisplayLabelStr

    @model_validator(mode="after")
    def validate_type_schema_pair(self) -> Self:
        if (
            self.artifact_type == "synthesis_blueprint"
            and self.schema_version != SYNTHESIS_BLUEPRINT_SCHEMA_VERSION
        ):
            raise ValueError(
                "Synthesis blueprint artifacts require schema version 2.0."
            )
        if (
            self.artifact_type == "single_file_artifact"
            and self.schema_version != "1.0"
        ):
            raise ValueError(
                "Single-file artifacts require schema version 1.0."
            )
        return self


SingleFileArtifactFamily = Literal["code", "document", "data"]
SingleFileArtifactFormat = Literal[
    "assembly",
    "bash",
    "c",
    "cpp",
    "csharp",
    "css",
    "go",
    "html",
    "java",
    "javascript",
    "json",
    "kotlin",
    "markdown",
    "objective_c",
    "php",
    "python",
    "ruby",
    "rust",
    "sql",
    "swift",
    "text",
    "toml",
    "typescript",
    "yaml",
    "zsh",
]

_CODE_ARTIFACT_FORMATS = {
    "assembly",
    "bash",
    "c",
    "cpp",
    "csharp",
    "css",
    "go",
    "html",
    "java",
    "javascript",
    "kotlin",
    "objective_c",
    "php",
    "python",
    "ruby",
    "rust",
    "sql",
    "swift",
    "typescript",
    "zsh",
}
_DOCUMENT_ARTIFACT_FORMATS = {"markdown", "text", "html"}
_DATA_ARTIFACT_FORMATS = {"json", "yaml", "toml"}


def _allowed_single_file_artifact_formats(
    artifact_family: SingleFileArtifactFamily,
) -> set[str]:
    return {
        "code": _CODE_ARTIFACT_FORMATS,
        "document": _DOCUMENT_ARTIFACT_FORMATS,
        "data": _DATA_ARTIFACT_FORMATS,
    }[artifact_family]


class SingleFileArtifact(StrictModel):
    artifact_family: SingleFileArtifactFamily
    format: SingleFileArtifactFormat
    filename: ArtifactFilenameStr
    content: ArtifactContentStr
    summary: DisplayLabelStr | None = None

    @field_validator("content")
    @classmethod
    def reject_unsafe_content_control_characters(cls, value: str) -> str:
        if any(
            (ord(character) < 32 and character not in "\t\n\r")
            or ord(character) == 127
            for character in value
        ):
            raise ValueError("Artifact content contains control characters.")
        return value

    @model_validator(mode="after")
    def validate_family_format_pair(self) -> Self:
        allowed_formats = _allowed_single_file_artifact_formats(
            self.artifact_family
        )
        if self.format not in allowed_formats:
            raise ValueError("Artifact family and format do not match.")
        if self.format == "json":
            try:
                json.loads(self.content)
            except json.JSONDecodeError as exc:
                raise ValueError("JSON artifact content is invalid.") from exc
        return self


class SingleFileArtifactMetadata(StrictModel):
    reference: ArtifactReference
    created_at: datetime
    originating_session_id: IdentifierStr
    originating_turn_id: IdentifierStr | None = None
    parent_artifact_id: IdentifierStr | None = None
    filename: ArtifactFilenameStr
    artifact_family: SingleFileArtifactFamily
    format: SingleFileArtifactFormat
    byte_size: int = Field(ge=1, le=1_000_000)
    lifecycle_status: Literal["active", "archived"] = "active"

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone aware.")
        return value

    @model_validator(mode="after")
    def require_single_file_reference(self) -> Self:
        if self.reference.artifact_type != "single_file_artifact":
            raise ValueError("Metadata requires a single-file reference.")
        return self


class SingleFileArtifactListResponse(StrictModel):
    artifact_contract_version: Literal["1.0"] = ARTIFACT_CONTRACT_VERSION
    artifacts: list[SingleFileArtifactMetadata] = Field(max_length=50)
    next_before: IdentifierStr | None = None


class SingleFileArtifactCreateRequest(StrictModel):
    session_id: IdentifierStr
    user_id: IdentifierStr
    artifact_family: SingleFileArtifactFamily
    format: SingleFileArtifactFormat
    filename: ArtifactFilenameStr
    source_text: SourceText
    display_label: DisplayLabelStr | None = None
    context_messages: list[SourceText] = Field(
        default_factory=list,
        max_length=10,
    )

    @model_validator(mode="after")
    def validate_family_format_pair(self) -> Self:
        if self.format not in _allowed_single_file_artifact_formats(
            self.artifact_family
        ):
            raise ValueError("Artifact family and format do not match.")
        return self


class SingleFileArtifactCreateResponse(StrictModel):
    artifact_contract_version: Literal["1.0"] = ARTIFACT_CONTRACT_VERSION
    reference: ArtifactReference
    artifact: SingleFileArtifact


class SingleFileArtifactLifecycleResponse(StrictModel):
    artifact_contract_version: Literal["1.0"] = ARTIFACT_CONTRACT_VERSION
    metadata: SingleFileArtifactMetadata


class SingleFileArtifactMetadataUpdateRequest(StrictModel):
    display_label: DisplayLabelStr | None = None
    filename: ArtifactFilenameStr | None = None

    @model_validator(mode="after")
    def require_metadata_change(self) -> Self:
        if self.display_label is None and self.filename is None:
            raise ValueError("At least one metadata field is required.")
        return self


class SingleFileArtifactEditRequest(StrictModel):
    session_id: IdentifierStr
    user_id: IdentifierStr
    content: ArtifactContentStr
    filename: ArtifactFilenameStr | None = None
    display_label: DisplayLabelStr | None = None
    summary: DisplayLabelStr | None = None
    originating_turn_id: IdentifierStr | None = None


class ArtifactFeedbackCounts(StrictModel):
    accepted: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)
    edited: int = Field(default=0, ge=0)


ArtifactFeedbackDecision = Literal["accepted", "rejected", "edited"]
ArtifactFeedbackTargetKind = Literal[
    "whole_blueprint",
    "architectural_decision",
    "socratic_question",
    "roadmap_milestone",
    "diagnostic_warning",
]


class ArtifactFeedbackTarget(StrictModel):
    target_id: IdentifierStr
    target_kind: ArtifactFeedbackTargetKind
    display_label: DisplayLabelStr


class ArtifactFeedbackDecisionRequest(StrictModel):
    artifact_id: IdentifierStr
    target_id: IdentifierStr
    decision: ArtifactFeedbackDecision
    feedback_text: ArtifactFeedbackText
    correction_text: ArtifactFeedbackText | None = None
    expected_schema_version: Literal["2.0"]
    supersedes_feedback_id: IdentifierStr | None = None

    @field_validator("feedback_text", "correction_text")
    @classmethod
    def reject_unsafe_control_characters(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None and any(
            (ord(character) < 32 and character not in "\t\n\r")
            or ord(character) == 127
            for character in value
        ):
            raise ValueError("Feedback text contains control characters.")
        return value

    @model_validator(mode="after")
    def require_decision_specific_correction(self) -> Self:
        if self.decision == "edited" and self.correction_text is None:
            raise ValueError("Edited feedback requires correction text.")
        if self.decision != "edited" and self.correction_text is not None:
            raise ValueError(
                "Correction text is allowed only for edited feedback."
            )
        return self


class ArtifactFeedbackReference(StrictModel):
    feedback_id: IdentifierStr
    artifact_id: IdentifierStr
    target_id: IdentifierStr
    target_kind: ArtifactFeedbackTargetKind
    decision: ArtifactFeedbackDecision
    schema_version: Literal["2.0"]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone aware.")
        return value


ArtifactFeedbackStatus = Literal["active", "superseded"]


class ArtifactFeedbackEvent(StrictModel):
    reference: ArtifactFeedbackReference
    feedback_text: ArtifactFeedbackText
    correction_text: ArtifactFeedbackText | None = None
    originating_session_id: IdentifierStr
    source_message_id: IdentifierStr
    originating_turn_id: IdentifierStr
    status: ArtifactFeedbackStatus
    supersedes_feedback_id: IdentifierStr | None = None
    superseded_by_feedback_id: IdentifierStr | None = None

    @model_validator(mode="after")
    def validate_derived_lifecycle(self) -> Self:
        feedback_id = self.reference.feedback_id
        if (
            self.supersedes_feedback_id == feedback_id
            or self.superseded_by_feedback_id == feedback_id
        ):
            raise ValueError("Feedback lifecycle cannot reference itself.")
        if (
            self.status == "active"
            and self.superseded_by_feedback_id is not None
        ):
            raise ValueError("Active feedback cannot have a successor.")
        if (
            self.status == "superseded"
            and self.superseded_by_feedback_id is None
        ):
            raise ValueError("Superseded feedback requires a successor.")
        return self


class BlueprintArtifactFeedbackListResponse(StrictModel):
    feedback_contract_version: Literal["1.0"] = "1.0"
    artifact_id: IdentifierStr
    events: list[ArtifactFeedbackEvent] = Field(max_length=50)
    next_before: IdentifierStr | None = None


class BlueprintArtifactMetadata(StrictModel):
    reference: ArtifactReference
    created_at: datetime
    originating_session_id: IdentifierStr
    originating_turn_id: IdentifierStr | None = None
    parent_artifact_id: IdentifierStr | None = None
    feedback_counts: ArtifactFeedbackCounts = Field(
        default_factory=ArtifactFeedbackCounts
    )
    adaptation_categories: list[PreferenceCategoryV2] = Field(
        default_factory=list,
        max_length=8,
    )


class BlueprintArtifactListResponse(StrictModel):
    artifact_contract_version: Literal["1.0"] = ARTIFACT_CONTRACT_VERSION
    artifacts: list[BlueprintArtifactMetadata] = Field(max_length=50)
    next_before: IdentifierStr | None = None


class CitationReference(StrictModel):
    uri: HttpUrl
    label: DisplayLabelStr


def _normalize_memory_model_value(
    data: object,
    value_field: str,
) -> object:
    if not isinstance(data, Mapping):
        return data
    if "category" not in data or value_field not in data:
        return data
    normalized = dict(data)
    normalized[value_field] = validate_memory_value(
        data["category"],
        data[value_field],
    )
    return normalized


def _normalize_memory_model_value_for_policy(
    data: object,
    value_field: str,
    policy_version: str,
) -> object:
    if not isinstance(data, Mapping):
        return data
    if "category" not in data or value_field not in data:
        return data
    normalized = dict(data)
    normalized[value_field] = validate_memory_value_for_policy(
        policy_version,
        data["category"],
        data[value_field],
    )
    return normalized


def _normalize_collaborative_note_text(data: object) -> object:
    if not isinstance(data, Mapping):
        return data
    normalized = dict(data)
    if "title" in normalized:
        normalized["title"] = normalize_note_title(normalized["title"])
    if "body" in normalized:
        normalized["body"] = normalize_note_body(normalized["body"])
    return normalized


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone aware.")


def _require_unique_source_message_ids(source_message_ids: list[str]) -> None:
    if len(source_message_ids) != len(set(source_message_ids)):
        raise ValueError("Source message IDs must be unique.")


class MemoryDecisionRequest(StrictModel):
    proposal_id: IdentifierStr
    decision: MemoryDecision


class MemoryClarificationSelectionRequest(StrictModel):
    clarification_id: IdentifierStr
    selected_candidate_index: int = Field(strict=True, ge=0, le=4)


class CollaborativeNoteProposal(StrictModel):
    proposal_id: IdentifierStr
    note_kind: CollaborativeNoteKind
    title: str
    body: str
    source_session_id: IdentifierStr
    source_message_ids: list[IdentifierStr] = Field(min_length=1, max_length=5)
    expected_note_id: IdentifierStr | None
    expected_revision: StrictInt | None = Field(ge=1)
    policy_version: Literal["1.0"]
    status: CollaborativeNoteProposalStatus
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_text(cls, data: object) -> object:
        return _normalize_collaborative_note_text(data)

    @model_validator(mode="after")
    def validate_proposal_invariants(self) -> Self:
        _require_unique_source_message_ids(self.source_message_ids)
        if (self.expected_note_id is None) != (self.expected_revision is None):
            raise ValueError(
                "Expected note ID and expected revision must be paired."
            )
        _require_aware_datetime(self.created_at, "created_at")
        _require_aware_datetime(self.expires_at, "expires_at")
        elapsed = self.expires_at.astimezone(UTC) - self.created_at.astimezone(UTC)
        if elapsed != timedelta(hours=24):
            raise ValueError("Proposal timestamps must be exactly 24 elapsed hours apart.")
        return self


class CollaborativeNote(StrictModel):
    note_id: IdentifierStr
    owner_user_id: IdentifierStr
    workspace_id: IdentifierStr
    note_kind: CollaborativeNoteKind
    title: str
    body: str
    status: CollaborativeNoteStatus
    revision: StrictInt = Field(ge=1)
    source_session_id: IdentifierStr
    source_message_ids: list[IdentifierStr] = Field(min_length=1, max_length=5)
    source_event_id: IdentifierStr
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_text(cls, data: object) -> object:
        return _normalize_collaborative_note_text(data)

    @model_validator(mode="after")
    def validate_active_note_invariants(self) -> Self:
        _require_unique_source_message_ids(self.source_message_ids)
        _require_aware_datetime(self.created_at, "created_at")
        _require_aware_datetime(self.updated_at, "updated_at")
        if self.updated_at.astimezone(UTC) < self.created_at.astimezone(UTC):
            raise ValueError("updated_at must not be earlier than created_at.")
        return self


class AdaptationReceipt(StrictModel):
    signal_id: IdentifierStr
    category: MemoryCategory
    value: MemoryValue
    source_event_id: IdentifierStr
    status: Literal["provided_to_model"]

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "value")


class MemoryProposalReceipt(StrictModel):
    proposal_id: IdentifierStr
    category: MemoryCategory
    proposed_value: MemoryValue
    expires_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_proposed_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "proposed_value")


class ChatRequest(StrictModel):
    project_id: IdentifierStr
    session_id: IdentifierStr
    user_id: IdentifierStr
    message: ChatMessageText
    memory_decision: MemoryDecisionRequest | None = None
    memory_clarification_selection: (
        MemoryClarificationSelectionRequest | None
    ) = None
    artifact_feedback_decision: ArtifactFeedbackDecisionRequest | None = None

    @model_validator(mode="after")
    def allow_only_one_structured_decision(self) -> Self:
        decisions = (
            self.memory_decision,
            self.memory_clarification_selection,
            self.artifact_feedback_decision,
        )
        if sum(item is not None for item in decisions) > 1:
            raise ValueError(
                "Structured decisions are mutually exclusive."
            )
        return self


class ChatResponse(StrictModel):
    response: NonEmptyStr
    actions: list[AgentActionReceipt] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    artifact_feedback: list[ArtifactFeedbackReference] = Field(
        default_factory=list,
        max_length=1,
    )
    citations: list[CitationReference] = Field(default_factory=list)
    memory_proposals: list[VersionedMemoryProposalReceipt] = Field(
        default_factory=list,
        max_length=1,
    )
    memory_clarifications: list[MemoryClarificationReceipt] = Field(
        default_factory=list,
        max_length=1,
    )
    adaptations: list[VersionedAdaptationReceipt] = Field(
        default_factory=list,
        max_length=10,
    )


ChatRole = Literal["user", "model"]


class ChatSessionSummary(StrictModel):
    session_id: IdentifierStr
    project_id: IdentifierStr
    user_id: IdentifierStr
    updated_at: datetime | None = None
    last_message_preview: str | None = Field(default=None, max_length=180)
    last_message_role: ChatRole | None = None


class ChatSessionListResponse(StrictModel):
    chat_contract_version: Literal["1.0"] = "1.0"
    sessions: list[ChatSessionSummary] = Field(max_length=50)


class ChatMessageRecord(StrictModel):
    message_id: IdentifierStr
    role: ChatRole
    text: ChatMessageText
    timestamp: datetime | None = None


class ChatSessionDetailResponse(StrictModel):
    chat_contract_version: Literal["1.0"] = "1.0"
    session_id: IdentifierStr
    project_id: IdentifierStr
    user_id: IdentifierStr
    messages: list[ChatMessageRecord] = Field(max_length=100)
    active_memory_clarification: MemoryClarificationReceipt | None = None


class WorkspaceSummary(StrictModel):
    workspace_id: IdentifierStr
    display_name: ProjectDisplayNameStr
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_default: bool = False


class WorkspaceListResponse(StrictModel):
    workspace_contract_version: Literal["1.0"] = "1.0"
    workspaces: list[WorkspaceSummary] = Field(max_length=50)


class WorkspaceCreateRequest(StrictModel):
    display_name: ProjectDisplayNameStr


class WorkspaceCreateResponse(StrictModel):
    workspace_contract_version: Literal["1.0"] = "1.0"
    workspace: WorkspaceSummary


class ChatPartialFailureResponse(StrictModel):
    detail: Literal[
        "Agent_Col response failed after a completed action.",
        "Agent_Col response timed out after a completed action.",
    ]
    actions: list[AgentActionReceipt]
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    artifact_feedback: list[ArtifactFeedbackReference] = Field(
        default_factory=list,
        max_length=1,
    )
    memory_proposals: list[VersionedMemoryProposalReceipt] = Field(
        default_factory=list,
        max_length=1,
    )
    memory_clarifications: list[MemoryClarificationReceipt] = Field(
        default_factory=list,
        max_length=1,
    )
    adaptations: list[VersionedAdaptationReceipt] = Field(
        default_factory=list,
        max_length=10,
    )


class MemoryProposal(StrictModel):
    proposal_id: IdentifierStr
    category: MemoryCategory
    proposed_value: MemoryValue
    expected_signal_id: IdentifierStr | None
    policy_version: Literal["1.0"] = MEMORY_POLICY_VERSION
    status: Literal["pending", "approved", "rejected"]
    source_session_id: IdentifierStr
    source_message_id: IdentifierStr
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_proposed_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "proposed_value")


class ActiveMemorySignal(StrictModel):
    signal_id: IdentifierStr
    category: MemoryCategory
    value: MemoryValue
    policy_version: Literal["1.0"] = MEMORY_POLICY_VERSION
    source_event_id: IdentifierStr
    approved_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "value")


class CollaborationProfile(StrictModel):
    memory_schema_version: Literal["1.0"] = MEMORY_SCHEMA_VERSION
    memory_revision: int = Field(default=0, ge=0)
    identity_context: dict[
        IdentityContextCategory,
        ActiveMemorySignal,
    ] = Field(default_factory=dict, max_length=2)
    active_preferences: dict[
        PreferenceCategory,
        ActiveMemorySignal,
    ] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def validate_projection_keys(self) -> Self:
        for key, signal in self.identity_context.items():
            if key != signal.category:
                raise ValueError(
                    "Identity-context key must match signal category."
                )
        for key, signal in self.active_preferences.items():
            if key != signal.category:
                raise ValueError(
                    "Preference key must match signal category."
                )
        return self


class MemoryEvent(StrictModel):
    event_id: IdentifierStr
    event_type: MemoryEventType
    signal_id: IdentifierStr
    category: MemoryCategory
    value: MemoryValue
    policy_version: Literal["1.0"] = MEMORY_POLICY_VERSION
    source_type: Literal["explicit_user_feedback"]
    source_session_id: IdentifierStr
    source_message_id: IdentifierStr
    confirmation_channel: ConfirmationChannel
    confirmation_session_id: IdentifierStr | None
    confirmation_message_id: IdentifierStr | None
    related_signal_id: IdentifierStr | None
    memory_revision: int = Field(ge=1)
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "value")

    @model_validator(mode="after")
    def validate_confirmation_channel(self) -> Self:
        if self.confirmation_channel == "chat_decision":
            valid = (
                self.confirmation_session_id is not None
                and self.confirmation_message_id is not None
            )
        else:
            valid = (
                self.confirmation_session_id is None
                and self.confirmation_message_id is None
            )
        if not valid:
            raise ValueError(
                "Confirmation identifiers do not match the channel."
            )
        return self


class DomainExperienceEntry(StrictModel):
    domain: DomainExperienceDomain
    level: DomainExperienceLevel


MemoryValueV2Schema = (
    MemoryValue
    | ExplanationPace
    | LearningApproach
    | list[AccessibilitySupport]
    | list[DevelopmentEnvironment]
    | list[DomainExperienceEntry]
    | UserRequestedMemoryStr
)


class MemoryProposalReceiptV2(StrictModel):
    proposal_id: IdentifierStr
    category: MemoryCategoryV2
    proposed_value: MemoryValueV2Schema
    policy_version: Literal["2.0"] = MEMORY_POLICY_VERSION_V2
    expires_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_proposed_value(cls, data: object) -> object:
        return _normalize_memory_model_value_for_policy(
            data,
            "proposed_value",
            MEMORY_POLICY_VERSION_V2,
        )


class AdaptationReceiptV2(StrictModel):
    signal_id: IdentifierStr
    category: MemoryCategoryV2
    value: MemoryValueV2Schema
    policy_version: Literal["2.0"] = MEMORY_POLICY_VERSION_V2
    source_event_id: IdentifierStr
    status: Literal["provided_to_model"]

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: object) -> object:
        return _normalize_memory_model_value_for_policy(
            data,
            "value",
            MEMORY_POLICY_VERSION_V2,
        )


VersionedAdaptationReceipt = AdaptationReceipt | AdaptationReceiptV2
VersionedMemoryProposalReceipt = MemoryProposalReceipt | MemoryProposalReceiptV2


class MemoryClarificationChoice(StrictModel):
    candidate_index: int = Field(ge=0, le=4)
    category_label: str = Field(min_length=1, max_length=80)
    value_label: str = Field(min_length=1, max_length=240)


class MemoryClarificationReceipt(StrictModel):
    clarification_id: IdentifierStr
    choices: list[MemoryClarificationChoice] = Field(
        min_length=2,
        max_length=5,
    )
    expires_at: datetime


class MemorySourceProvenanceV2(StrictModel):
    source_message_id: IdentifierStr
    evidence_message_id: IdentifierStr
    clarification_id: IdentifierStr | None = None

    @model_validator(mode="after")
    def validate_direct_or_clarified_provenance(self) -> Self:
        if self.clarification_id is None:
            if self.evidence_message_id != self.source_message_id:
                raise ValueError(
                    "Direct memory evidence must match the source message."
                )
        elif self.evidence_message_id == self.source_message_id:
            raise ValueError(
                "Clarified memory evidence must precede the source message."
            )
        return self


class MemoryProposalV2(StrictModel):
    proposal_id: IdentifierStr
    category: MemoryCategoryV2
    proposed_value: MemoryValueV2Schema
    expected_signal_id: IdentifierStr | None
    policy_version: Literal["2.0"] = MEMORY_POLICY_VERSION_V2
    status: Literal["pending", "approved", "rejected"]
    source_session_id: IdentifierStr
    source_message_id: IdentifierStr
    evidence_message_id: IdentifierStr
    clarification_id: IdentifierStr | None = None
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_proposed_value(cls, data: object) -> object:
        return _normalize_memory_model_value_for_policy(
            data,
            "proposed_value",
            MEMORY_POLICY_VERSION_V2,
        )

    @model_validator(mode="after")
    def validate_evidence_provenance(self) -> Self:
        MemorySourceProvenanceV2(
            source_message_id=self.source_message_id,
            evidence_message_id=self.evidence_message_id,
            clarification_id=self.clarification_id,
        )
        return self


class ActiveMemorySignalV2(StrictModel):
    signal_id: IdentifierStr
    category: MemoryCategoryV2
    value: MemoryValueV2Schema
    policy_version: Literal["2.0"] = MEMORY_POLICY_VERSION_V2
    source_event_id: IdentifierStr
    approved_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: object) -> object:
        return _normalize_memory_model_value_for_policy(
            data,
            "value",
            MEMORY_POLICY_VERSION_V2,
        )


VersionedActiveMemorySignal = Annotated[
    ActiveMemorySignal | ActiveMemorySignalV2,
    Field(discriminator="policy_version"),
]


class CollaborationProfileV2(StrictModel):
    memory_schema_version: Literal["2.0"] = MEMORY_SCHEMA_VERSION_V2
    memory_revision: int = Field(default=0, ge=0)
    identity_context: dict[
        IdentityContextCategoryV2,
        VersionedActiveMemorySignal,
    ] = Field(default_factory=dict, max_length=3)
    active_preferences: dict[
        PreferenceCategoryV2,
        VersionedActiveMemorySignal,
    ] = Field(default_factory=dict, max_length=12)

    @model_validator(mode="after")
    def validate_projection_keys_and_capacity(self) -> Self:
        for key, signal in self.identity_context.items():
            if key != signal.category:
                raise ValueError(
                    "Identity-context key must match signal category."
                )
        for key, signal in self.active_preferences.items():
            if key != signal.category:
                raise ValueError(
                    "Preference key must match signal category."
                )
        if len(self.identity_context) + len(self.active_preferences) > 10:
            raise ValueError(
                "A collaboration profile may contain at most 10 signals."
            )
        return self


class MemoryEventV2(StrictModel):
    event_id: IdentifierStr
    event_type: MemoryEventType
    signal_id: IdentifierStr
    category: MemoryCategoryV2
    value: MemoryValueV2Schema
    policy_version: Literal["2.0"] = MEMORY_POLICY_VERSION_V2
    source_type: Literal["explicit_user_feedback"]
    source_session_id: IdentifierStr
    source_message_id: IdentifierStr
    evidence_message_id: IdentifierStr
    clarification_id: IdentifierStr | None = None
    confirmation_channel: ConfirmationChannel
    confirmation_session_id: IdentifierStr | None
    confirmation_message_id: IdentifierStr | None
    related_signal_id: IdentifierStr | None
    memory_revision: int = Field(ge=1)
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: object) -> object:
        return _normalize_memory_model_value_for_policy(
            data,
            "value",
            MEMORY_POLICY_VERSION_V2,
        )

    @model_validator(mode="after")
    def validate_event_provenance(self) -> Self:
        MemorySourceProvenanceV2(
            source_message_id=self.source_message_id,
            evidence_message_id=self.evidence_message_id,
            clarification_id=self.clarification_id,
        )
        if self.confirmation_channel == "chat_decision":
            valid_confirmation = (
                self.confirmation_session_id is not None
                and self.confirmation_message_id is not None
            )
        else:
            valid_confirmation = (
                self.confirmation_session_id is None
                and self.confirmation_message_id is None
            )
        if not valid_confirmation:
            raise ValueError(
                "Confirmation identifiers do not match the channel."
            )
        return self


VersionedMemoryProposal = Annotated[
    MemoryProposal | MemoryProposalV2,
    Field(discriminator="policy_version"),
]
VersionedMemoryEvent = Annotated[
    MemoryEvent | MemoryEventV2,
    Field(discriminator="policy_version"),
]
VersionedCollaborationProfile = CollaborationProfile | CollaborationProfileV2

MEMORY_SCHEMA_REGISTRY = MappingProxyType(
    {
        MEMORY_SCHEMA_VERSION: CollaborationProfile,
        MEMORY_SCHEMA_VERSION_V2: CollaborationProfileV2,
    }
)


def parse_collaboration_profile(
    document: object,
) -> VersionedCollaborationProfile:
    if not isinstance(document, Mapping):
        raise ValueError("Stored collaboration profile is invalid.")
    schema_version = document.get(
        "memory_schema_version",
        MEMORY_SCHEMA_VERSION,
    )
    if type(schema_version) is not str or schema_version not in (
        MEMORY_SCHEMA_REGISTRY
    ):
        raise ValueError("Unsupported memory schema version.")
    model = MEMORY_SCHEMA_REGISTRY[schema_version]
    return model.model_validate(dict(document))


def project_collaboration_profile_v2(
    profile: VersionedCollaborationProfile,
) -> CollaborationProfileV2:
    if isinstance(profile, CollaborationProfileV2):
        return profile.model_copy(deep=True)
    if not isinstance(profile, CollaborationProfile):
        raise TypeError("profile must be a versioned collaboration profile.")
    projected = profile.model_dump(mode="python")
    projected["memory_schema_version"] = MEMORY_SCHEMA_VERSION_V2
    return CollaborationProfileV2.model_validate(projected)


class MemoryInspectionResponse(StrictModel):
    profile: VersionedCollaborationProfile
    unresolved_proposals: list[VersionedMemoryProposal] = Field(max_length=10)
    events: list[VersionedMemoryEvent] = Field(max_length=50)
    next_event_id: IdentifierStr | None


class MemoryMutationResponse(StrictModel):
    action: AgentActionReceipt
    profile: VersionedCollaborationProfile


class ConceptualModel(StrictModel):
    project_name: ProjectDisplayNameStr = Field(
        description="A concise, human-readable project name."
    )
    core_value_proposition: GeneratedTextStr = Field(
        description=(
            "The primary user friction the project solves and the value it "
            "delivers."
        )
    )
    in_scope: list[GeneratedTextStr] = Field(
        min_length=1,
        max_length=10,
        description="Concrete capabilities included in this blueprint.",
    )
    out_of_scope: list[GeneratedTextStr] = Field(
        default_factory=list,
        max_length=10,
        description="Explicitly excluded capabilities or responsibilities.",
    )
    assumptions: list[GeneratedTextStr] = Field(
        default_factory=list,
        max_length=10,
        description="Material assumptions on which the blueprint depends.",
    )


class PersonalizationAdaptation(StrictModel):
    profile_key: GeneratedLabelStr = Field(
        description="The exact non-sensitive user-profile key used."
    )
    architecture_change: GeneratedTextStr = Field(
        description="The specific design change caused by the profile signal."
    )
    reason: GeneratedTextStr = Field(
        description="Why the profile signal justifies that design change."
    )


class PersonalizationTrace(StrictModel):
    adaptations: list[PersonalizationAdaptation] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "Profile-grounded adaptations; empty when no profile signal was "
            "used."
        ),
    )


class ArchitecturalAlternative(StrictModel):
    option_name: GeneratedLabelStr = Field(
        description="The name of an alternative technical option."
    )
    tradeoff: GeneratedTextStr = Field(
        description="The material benefits and costs of the alternative."
    )
    reason_not_selected: GeneratedTextStr = Field(
        description="Why the proposed solution is preferred over this option."
    )


class ArchitecturalDecision(StrictModel):
    component_name: GeneratedLabelStr = Field(
        description="The component or architectural layer being decided."
    )
    proposed_solution: GeneratedTextStr = Field(
        description="The recommended implementation for this component."
    )
    rationale: GeneratedTextStr = Field(
        description="Why this solution best fits the stated project goals."
    )
    alternatives: list[ArchitecturalAlternative] = Field(
        min_length=1,
        max_length=3,
        description="Viable alternatives considered for this decision.",
    )


class ClarifyingOption(StrictModel):
    label: GeneratedLabelStr = Field(
        description="A short user-facing choice label."
    )
    impact: GeneratedTextStr = Field(
        description="How selecting this option changes the blueprint."
    )


class ClarifyingQuestion(StrictModel):
    question_text: GeneratedTextStr = Field(
        description="A Socratic question requiring a meaningful design choice."
    )
    why_this_matters: GeneratedTextStr = Field(
        description="How the answer affects the project or its implementation."
    )
    suggested_options: list[ClarifyingOption] = Field(
        min_length=2,
        max_length=3,
        description="Two or three concrete choices the user can evaluate.",
    )


class MicroTask(StrictModel):
    task_description: GeneratedTextStr = Field(
        description="One specific, independently executable implementation task."
    )
    complexity_level: Literal["Low", "Medium", "High"] = Field(
        description="The task's relative implementation complexity."
    )
    verification_steps: list[VerificationStepStr] = Field(
        min_length=1,
        max_length=5,
        description="Observable checks proving the task works as intended.",
    )


class RoadmapMilestone(StrictModel):
    phase_name: GeneratedLabelStr = Field(
        description="The ordered implementation phase name."
    )
    objective: GeneratedTextStr = Field(
        description="The outcome this milestone is intended to achieve."
    )
    expected_deliverable: GeneratedTextStr = Field(
        description="The concrete artifact or behavior produced by the phase."
    )
    micro_tasks: list[MicroTask] = Field(
        min_length=1,
        max_length=10,
        description="Sequential tasks required to complete this milestone.",
    )


class DiagnosticWarning(StrictModel):
    affected_component: GeneratedLabelStr = Field(
        description="The component or layer exposed to the risk."
    )
    severity: Literal["Low", "Medium", "High", "Critical"] = Field(
        description="The expected impact if the risk is not mitigated."
    )
    risk_identified: GeneratedTextStr = Field(
        description="A concrete technical, security, or delivery risk."
    )
    preventative_guidance: GeneratedTextStr = Field(
        description="A specific action that reduces or prevents the risk."
    )


class SynthesisBlueprint(StrictModel):
    synthesized_conceptual_model: ConceptualModel = Field(
        description="The distilled project identity, value, and scope boundary."
    )
    personalization_trace: PersonalizationTrace = Field(
        description="An auditable record of profile-grounded adaptations."
    )
    architectural_decisions: list[
        ArchitecturalDecision
    ] = Field(
        min_length=1,
        max_length=8,
        description="The blueprint's major technical decisions and trade-offs.",
    )
    socratic_clarifying_questions: list[ClarifyingQuestion] = Field(
        min_length=1,
        max_length=5,
        description="Unresolved choices that require the user's judgment.",
    )
    step_by_step_execution_roadmap: list[RoadmapMilestone] = Field(
        min_length=1,
        max_length=8,
        description="An ordered, verifiable implementation roadmap.",
    )
    diagnostic_warnings: list[DiagnosticWarning] = Field(
        default_factory=list,
        max_length=10,
        description="Material risks and concrete preventative guidance.",
    )


class BlueprintArtifactDetailResponse(StrictModel):
    artifact_contract_version: Literal["1.0"] = ARTIFACT_CONTRACT_VERSION
    metadata: BlueprintArtifactMetadata
    blueprint: SynthesisBlueprint
    feedback_targets: list[ArtifactFeedbackTarget] = Field(max_length=32)
    adaptations: list[VersionedAdaptationReceipt] = Field(
        default_factory=list,
        max_length=8,
    )
    applied_feedback_ids: list[IdentifierStr] = Field(
        default_factory=list,
        max_length=50,
    )


class SingleFileArtifactDetailResponse(StrictModel):
    artifact_contract_version: Literal["1.0"] = ARTIFACT_CONTRACT_VERSION
    metadata: SingleFileArtifactMetadata
    artifact: SingleFileArtifact


class SynthesisRequest(StrictModel):
    project_id: IdentifierStr
    session_id: IdentifierStr
    user_id: IdentifierStr
    source_text: SourceText


class SynthesisResponse(StrictModel):
    blueprint_id: NonEmptyStr
    blueprint: SynthesisBlueprint
