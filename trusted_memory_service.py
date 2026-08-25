import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from database import MemoryEngine
from memory_candidate_decisions import (
    ClarifyDecision,
    NaturalMemoryDecision,
    NoMemoryDecision,
    ProfileCandidateDecision,
    is_natural_memory_decision,
    validate_decision_evidence,
)
from memory_clarifications import (
    MemoryClarificationEnvelope,
    MemoryClarificationReceipt,
    MemoryClarificationSelection,
    clarification_receipt,
    derive_memory_clarification_id,
)
from memory_proposals import (
    ProposalTurnLease,
    derive_proposal_origin_ids,
    derive_proposal_origin_ids_v2,
)
from memory_policy import (
    MEMORY_CATEGORY_ORDER,
    MEMORY_CATEGORY_ORDER_V2,
    ConfirmationChannel,
    IdentityContextPolicy,
    MemoryCategory,
    MemoryCategoryV2,
    MemoryDecision,
    validate_memory_value,
)
from schemas import (
    AgentActionReceipt,
    CollaborationProfile,
    MemoryEvent,
    MemoryProposal,
    MemoryProposalReceipt,
    MemoryProposalReceiptV2,
    VersionedCollaborationProfile,
    VersionedMemoryEvent,
    VersionedMemoryProposal,
)


@dataclass(frozen=True, slots=True)
class MemoryDecisionCommand:
    """Describe one explicit decision about a pending memory proposal."""

    user_id: str
    proposal_id: str
    decision: MemoryDecision
    confirmation_channel: ConfirmationChannel
    confirmation_session_id: str | None
    confirmation_message_id: str | None


@dataclass(frozen=True, slots=True)
class RevokeMemorySignalCommand:
    """Describe one explicit request to stop using a memory signal."""

    user_id: str
    signal_id: str


@dataclass(frozen=True, slots=True)
class DeleteMemorySignalCommand:
    """Describe one explicit hard-deletion request for a memory signal."""

    user_id: str
    signal_id: str


@dataclass(frozen=True, slots=True)
class InspectMemoryCommand:
    """Describe one bounded governed-memory inspection request."""

    user_id: str
    after_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProposeMemorySignalCommand:
    """Describe one untrusted candidate with server-owned provenance."""

    user_id: str
    session_id: str
    source_message_id: str
    source_message_text: str
    memory_decision_present: bool
    category: MemoryCategory
    proposed_value: object
    turn_lease: ProposalTurnLease | None = None


@dataclass(frozen=True, slots=True)
class NaturalMemoryCommand:
    """Describe one semantic memory decision with server-owned provenance."""

    user_id: str
    workspace_id: str
    session_id: str
    source_message_id: str
    source_message_text: str
    memory_decision_present: bool
    decision: NaturalMemoryDecision
    clarification_selection: MemoryClarificationSelection | None = None
    turn_lease: ProposalTurnLease | None = None


@dataclass(frozen=True, slots=True)
class TrustedMemoryMutationResult:
    """Return a completed deterministic memory action and profile."""

    action: AgentActionReceipt
    profile: VersionedCollaborationProfile


@dataclass(frozen=True, slots=True)
class TrustedMemoryProposalResult:
    """Return one completed pending-proposal action and receipt."""

    action: AgentActionReceipt
    proposal: MemoryProposalReceipt


@dataclass(frozen=True, slots=True)
class NaturalMemoryProposalResult:
    """Return an application-owned pending version-2 proposal receipt."""

    status: str
    action: AgentActionReceipt
    proposal: MemoryProposalReceiptV2


@dataclass(frozen=True, slots=True)
class NaturalMemoryClarificationResult:
    """Return an application-owned clarification receipt."""

    status: str
    clarification: MemoryClarificationReceipt


@dataclass(frozen=True, slots=True)
class NaturalMemoryNoEffectResult:
    """Return a truthful non-persistent semantic memory outcome."""

    status: str


@dataclass(frozen=True, slots=True)
class TrustedMemoryInspectionResult:
    """Return a bounded governed-memory inspection page."""

    profile: VersionedCollaborationProfile
    unresolved_proposals: tuple[VersionedMemoryProposal, ...]
    events: tuple[VersionedMemoryEvent, ...]
    next_event_id: str | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TrustedMemoryService:
    """Coordinate deterministic governed-memory persistence operations."""

    def __init__(
        self,
        *,
        database: MemoryEngine,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._database = database
        self._clock = clock

    async def inspect_memory(
        self,
        command: InspectMemoryCommand,
    ) -> TrustedMemoryInspectionResult:
        """Load one bounded page of governed collaboration memory."""
        result = await self._database.get_memory_inspection(
            command.user_id,
            observed_at=self._clock(),
            after_event_id=command.after_event_id,
        )
        return TrustedMemoryInspectionResult(
            profile=result.profile,
            unresolved_proposals=result.unresolved_proposals,
            events=result.events,
            next_event_id=result.next_event_id,
        )

    async def propose_memory_signal(
        self,
        command: ProposeMemorySignalCommand,
    ) -> TrustedMemoryProposalResult:
        """Validate and persist one pending governed-memory proposal."""
        self._validate_identifier(command.user_id, "user_id")
        self._validate_identifier(command.session_id, "session_id")
        self._validate_identifier(
            command.source_message_id,
            "source_message_id",
        )
        if (
            not isinstance(command.source_message_text, str)
            or not command.source_message_text.strip()
        ):
            raise ValueError("source_message_text must be non-empty.")
        if type(command.memory_decision_present) is not bool:
            raise ValueError("memory_decision_present must be a boolean.")
        if command.memory_decision_present:
            raise ValueError(
                "A memory-decision turn cannot create a new proposal."
            )
        if command.category not in MEMORY_CATEGORY_ORDER:
            raise ValueError("category must be a governed memory category.")
        category = cast(MemoryCategory, command.category)
        if category == "preferred_name":
            proposed_value = IdentityContextPolicy.validate(
                category,
                command.proposed_value,
                current_message=command.source_message_text,
                require_grounding=True,
            )
        else:
            proposed_value = validate_memory_value(
                category,
                command.proposed_value,
            )
        origin_ids = derive_proposal_origin_ids(
            command.user_id,
            command.session_id,
            command.source_message_id,
            category,
        )
        observed_at = self._clock()
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise ValueError("clock must return a timezone-aware datetime.")
        stored = await self._database.create_guarded_memory_proposal(
            user_id=command.user_id,
            session_id=command.session_id,
            source_message_id=command.source_message_id,
            origin_ids=origin_ids,
            category=category,
            proposed_value=proposed_value,
            observed_at=observed_at,
            turn_lease=command.turn_lease,
        )
        return TrustedMemoryProposalResult(
            action=AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            ),
            proposal=MemoryProposalReceipt(
                proposal_id=stored.proposal_id,
                category=stored.category,
                proposed_value=stored.proposed_value,
                expires_at=stored.expires_at,
            ),
        )

    async def handle_natural_memory_decision(
        self,
        command: NaturalMemoryCommand,
    ) -> (
        NaturalMemoryProposalResult
        | NaturalMemoryClarificationResult
        | NaturalMemoryNoEffectResult
    ):
        """Validate one semantic decision before its version-2 effect."""
        if not is_natural_memory_decision(command.decision):
            raise ValueError(
                "Natural memory command requires a canonical decision."
            )
        if (
            command.clarification_selection is not None
            and not isinstance(
                command.clarification_selection,
                MemoryClarificationSelection,
            )
        ):
            raise ValueError(
                "Natural memory command requires a canonical clarification "
                "selection."
            )
        self._validate_identifier(command.user_id, "user_id")
        self._validate_identifier(command.workspace_id, "workspace_id")
        self._validate_identifier(command.session_id, "session_id")
        self._validate_identifier(
            command.source_message_id,
            "source_message_id",
        )
        if (
            not isinstance(command.source_message_text, str)
            or not command.source_message_text.strip()
        ):
            raise ValueError("source_message_text must be non-empty.")
        if type(command.memory_decision_present) is not bool:
            raise ValueError("memory_decision_present must be a boolean.")
        if command.memory_decision_present:
            raise ValueError(
                "A memory-decision turn cannot create a new proposal."
            )
        if command.clarification_selection is not None:
            if not isinstance(command.decision, NoMemoryDecision):
                raise ValueError(
                    "A clarification selection cannot create another "
                    "memory decision."
                )
            if command.turn_lease is None:
                raise ValueError(
                    "A clarification selection requires retry-safe turn "
                    "ownership."
                )
            observed_at = self._clock()
            stored = (
                await self._database
                .consume_memory_clarification_to_proposal_v2(
                    user_id=command.user_id,
                    workspace_id=command.workspace_id,
                    session_id=command.session_id,
                    source_message_id=command.source_message_id,
                    selection=command.clarification_selection,
                    observed_at=observed_at,
                    turn_lease=command.turn_lease,
                )
            )
            return NaturalMemoryProposalResult(
                status="pending",
                action=AgentActionReceipt(
                    action_name="propose_memory_signal",
                    status="completed",
                ),
                proposal=MemoryProposalReceiptV2(
                    proposal_id=stored.proposal_id,
                    category=stored.category,
                    proposed_value=stored.proposed_value,
                    expires_at=stored.expires_at,
                ),
            )
        validate_decision_evidence(
            command.decision,
            command.source_message_text,
        )
        if isinstance(command.decision, ProfileCandidateDecision):
            origin_ids = derive_proposal_origin_ids_v2(
                command.user_id,
                command.session_id,
                command.source_message_id,
                command.decision.category,
            )
            observed_at = self._clock()
            stored = await self._database.create_guarded_memory_proposal_v2(
                user_id=command.user_id,
                session_id=command.session_id,
                source_message_id=command.source_message_id,
                evidence_message_id=command.source_message_id,
                clarification_id=None,
                origin_ids=origin_ids,
                category=command.decision.category,
                proposed_value=command.decision.canonical_value,
                observed_at=observed_at,
                turn_lease=command.turn_lease,
            )
            return NaturalMemoryProposalResult(
                status="pending",
                action=AgentActionReceipt(
                    action_name="propose_memory_signal",
                    status="completed",
                ),
                proposal=MemoryProposalReceiptV2(
                    proposal_id=stored.proposal_id,
                    category=stored.category,
                    proposed_value=stored.proposed_value,
                    expires_at=stored.expires_at,
                ),
            )
        if isinstance(command.decision, ClarifyDecision):
            if command.turn_lease is None:
                raise ValueError(
                    "A clarification requires retry-safe turn ownership."
                )
            observed_at = self._clock()
            envelope = MemoryClarificationEnvelope(
                clarification_id=derive_memory_clarification_id(
                    user_id=command.user_id,
                    session_id=command.session_id,
                    evidence_message_id=command.source_message_id,
                    clarification_turn_id=command.turn_lease.turn_id,
                ),
                user_id=command.user_id,
                session_id=command.session_id,
                workspace_id=command.workspace_id,
                evidence_message_id=command.source_message_id,
                clarification_turn_id=command.turn_lease.turn_id,
                candidates=[
                    {
                        "category": candidate.category,
                        "canonical_value": candidate.canonical_value,
                    }
                    for candidate in command.decision.candidates
                ],
                created_at=observed_at,
                expires_at=observed_at + timedelta(minutes=15),
                status="open",
            )
            stored = await self._database.create_memory_clarification(
                envelope=envelope,
                observed_at=observed_at,
                turn_lease=command.turn_lease,
            )
            return NaturalMemoryClarificationResult(
                status="clarification_required",
                clarification=clarification_receipt(stored),
            )
        return NaturalMemoryNoEffectResult(status=command.decision.kind)

    async def decide_memory_proposal(
        self,
        command: MemoryDecisionCommand,
    ) -> TrustedMemoryMutationResult:
        """Apply one structured approval or rejection decision."""
        self._validate_confirmation(command)
        category = self._category_from_identifier(command.proposal_id)
        observed_at = self._clock()
        if command.decision == "approve":
            result = await self._database.approve_memory_proposal(
                command.user_id,
                category,
                command.proposal_id,
                confirmation_channel=command.confirmation_channel,
                confirmation_session_id=command.confirmation_session_id,
                confirmation_message_id=command.confirmation_message_id,
                observed_at=observed_at,
            )
            action_name = "approve_memory_signal"
        elif command.decision == "reject":
            result = await self._database.reject_memory_proposal(
                command.user_id,
                category,
                command.proposal_id,
                observed_at=observed_at,
            )
            action_name = "reject_memory_signal"
        else:
            raise ValueError("Unsupported memory decision.")
        return TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name=action_name,
                status="completed",
            ),
            profile=result.profile,
        )

    async def revoke_memory_signal(
        self,
        command: RevokeMemorySignalCommand,
    ) -> TrustedMemoryMutationResult:
        """Revoke one active memory signal through the memory API."""
        category = self._category_from_identifier(command.signal_id)
        result = await self._database.revoke_memory_signal(
            command.user_id,
            category,
            command.signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=self._clock(),
        )
        return TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="revoke_memory_signal",
                status="completed",
            ),
            profile=result.profile,
        )

    async def delete_memory_signal(
        self,
        command: DeleteMemorySignalCommand,
    ) -> TrustedMemoryMutationResult:
        """Hard-delete one signal's bounded memory artifacts."""
        category = self._category_from_identifier(command.signal_id)
        result = await self._database.delete_memory_signal(
            command.user_id,
            category,
            command.signal_id,
        )
        return TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="delete_memory_signal",
                status="completed",
            ),
            profile=result.profile,
        )

    @staticmethod
    def _category_from_identifier(identifier: object) -> MemoryCategoryV2:
        if not isinstance(identifier, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            identifier,
        ) is None:
            raise ValueError("Memory identifier must be valid.")
        for category in MEMORY_CATEGORY_ORDER_V2:
            if identifier.startswith(f"{category}--"):
                return cast(MemoryCategoryV2, category)
        raise ValueError("Memory identifier has no governed category.")

    @staticmethod
    def _validate_identifier(value: object, field_name: str) -> None:
        if not isinstance(value, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            value,
        ) is None:
            raise ValueError(f"{field_name} must be a valid identifier.")

    @staticmethod
    def _validate_confirmation(command: MemoryDecisionCommand) -> None:
        if command.confirmation_channel == "chat_decision":
            for field_name, value in (
                (
                    "confirmation_session_id",
                    command.confirmation_session_id,
                ),
                (
                    "confirmation_message_id",
                    command.confirmation_message_id,
                ),
            ):
                if not isinstance(value, str) or re.fullmatch(
                    r"[A-Za-z0-9_-]{1,128}",
                    value,
                ) is None:
                    raise ValueError(
                        f"{field_name} must be a valid identifier."
                    )
            return
        if command.confirmation_channel == "memory_api":
            if (
                command.confirmation_session_id is not None
                or command.confirmation_message_id is not None
            ):
                raise ValueError(
                    "Memory API confirmation IDs must be omitted."
                )
            return
        raise ValueError("confirmation_channel is invalid.")
