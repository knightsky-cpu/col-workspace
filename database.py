import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn

from google.api_core.exceptions import GoogleAPIError
from google.cloud import firestore
from google.cloud.firestore import (
    AsyncClient,
    AsyncCollectionReference,
    AsyncDocumentReference,
    AsyncTransaction,
)
from google.cloud.firestore_v1.field_path import FieldPath

from memory_policy import (
    MEMORY_CATEGORY_ORDER,
    ConfirmationChannel,
    MemoryCategory,
)
from schemas import (
    ActiveMemorySignal,
    CollaborationProfile,
    MemoryEvent,
    MemoryProposal,
)


logger = logging.getLogger(__name__)


class MemoryEngineError(RuntimeError):
    """Raised when a Firestore memory operation fails."""


class MemoryProposalConflictError(RuntimeError):
    """Raised when an unexpired proposal owns a category slot."""


class MemoryProposalNotFoundError(RuntimeError):
    """Raised when a requested proposal slot does not exist."""


class MemoryProposalExpiredError(RuntimeError):
    """Raised when a requested pending proposal has expired."""


class MemorySignalNotFoundError(RuntimeError):
    """Raised when a governed memory signal cannot be revoked."""


class MemorySignalConflictError(RuntimeError):
    """Raised when stored signal state conflicts with a memory mutation."""


class MemoryEventCursorNotFoundError(RuntimeError):
    """Raised when a memory-event pagination cursor cannot be resolved."""


@dataclass(frozen=True, slots=True)
class MemoryApprovalResult:
    """Return the governed state created by a memory approval."""

    profile: CollaborationProfile
    event: MemoryEvent
    superseded_event: MemoryEvent | None = None


@dataclass(frozen=True, slots=True)
class MemoryRevocationResult:
    """Return the governed state created by a memory revocation."""

    profile: CollaborationProfile
    event: MemoryEvent


@dataclass(frozen=True, slots=True)
class MemoryDeletionResult:
    """Return the governed state after bounded hard deletion."""

    profile: CollaborationProfile
    artifacts_deleted: bool


@dataclass(frozen=True, slots=True)
class MemoryRejectionResult:
    """Return governed state after rejecting a pending proposal."""

    profile: CollaborationProfile
    proposal: MemoryProposal


@dataclass(frozen=True, slots=True)
class MemoryInspectionPage:
    """Return one bounded page of governed collaboration memory."""

    profile: CollaborationProfile
    unresolved_proposals: tuple[MemoryProposal, ...]
    events: tuple[MemoryEvent, ...]
    next_event_id: str | None


class MemoryEngine:
    """Provide asynchronous persistence for chat messages and user profiles."""

    def __init__(self, client: AsyncClient | None = None) -> None:
        self._client = client if client is not None else AsyncClient()

    async def save_message(
        self, session_id: str, role: str, text: str
    ) -> str:
        """Atomically persist a session update and a new chat message."""
        self._validate_string(session_id, "session_id")
        self._validate_string(role, "role")
        self._validate_string(text, "text")

        try:
            session_ref = self._client.collection("sessions").document(
                session_id
            )
            message_ref = session_ref.collection("messages").document()
            batch = self._client.batch()
            batch.set(
                session_ref,
                {"updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            batch.set(
                message_ref,
                {
                    "role": role,
                    "text": text,
                    "timestamp": firestore.SERVER_TIMESTAMP,
                },
            )
            await batch.commit()
            return message_ref.id
        except GoogleAPIError as exc:
            self._raise_firestore_error("save_message", exc)

    async def save_blueprint(
        self,
        project_id: str,
        session_id: str,
        user_id: str,
        model_name: str,
        schema_version: str,
        blueprint: dict[str, object],
    ) -> str:
        """Atomically persist a project update and generated blueprint."""
        self._validate_string(project_id, "project_id")
        self._validate_string(session_id, "session_id")
        self._validate_string(user_id, "user_id")
        self._validate_string(model_name, "model_name")
        self._validate_string(schema_version, "schema_version")
        self._validate_blueprint(blueprint)

        try:
            project_ref = self._client.collection("projects").document(
                project_id
            )
            blueprint_ref = project_ref.collection("blueprints").document()
            batch = self._client.batch()
            batch.set(
                project_ref,
                {"updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            batch.set(
                blueprint_ref,
                {
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "originating_session_id": session_id,
                    "user_id": user_id,
                    "model_name": model_name,
                    "schema_version": schema_version,
                    "blueprint": blueprint,
                },
            )
            await batch.commit()
            return blueprint_ref.id
        except GoogleAPIError as exc:
            self._raise_firestore_error("save_blueprint", exc)

    async def get_chat_history(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """Return all or the newest session messages chronologically."""
        self._validate_string(session_id, "session_id")
        if limit is not None and (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be an integer between 1 and 100.")

        try:
            messages_ref = (
                self._client.collection("sessions")
                .document(session_id)
                .collection("messages")
            )
            direction = (
                firestore.Query.ASCENDING
                if limit is None
                else firestore.Query.DESCENDING
            )
            query = messages_ref.order_by(
                "timestamp",
                direction=direction,
            )
            if limit is not None:
                query = query.limit(limit)

            history: list[dict[str, object]] = []

            async for snapshot in query.stream():
                data = snapshot.to_dict()
                if data is not None:
                    history.append(data)

            if limit is not None:
                history.reverse()

            return history
        except GoogleAPIError as exc:
            self._raise_firestore_error("get_chat_history", exc)

    async def update_user_profile(
        self, user_id: str, updates: dict[str, object]
    ) -> None:
        """Merge fields into a user's profile document."""
        self._validate_string(user_id, "user_id")
        self._validate_updates(updates)

        try:
            user_ref = self._client.collection("users").document(user_id)
            await user_ref.set(updates, merge=True)
        except GoogleAPIError as exc:
            self._raise_firestore_error("update_user_profile", exc)

    async def get_user_profile(self, user_id: str) -> dict[str, object]:
        """Return a user's profile or an empty dictionary when absent."""
        self._validate_string(user_id, "user_id")

        try:
            user_ref = self._client.collection("users").document(user_id)
            snapshot = await user_ref.get()

            if not snapshot.exists:
                return {}

            return snapshot.to_dict() or {}
        except GoogleAPIError as exc:
            self._raise_firestore_error("get_user_profile", exc)

    async def get_collaboration_profile(
        self,
        user_id: str,
    ) -> CollaborationProfile:
        """Load only the governed active-memory projection."""
        self._validate_memory_user_id(user_id)

        try:
            user_ref = self._client.collection("users").document(user_id)
            snapshot = await user_ref.get()
            if not snapshot.exists:
                return CollaborationProfile()
            return self._collaboration_profile_from_document(
                snapshot.to_dict()
            )
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("get_collaboration_profile", exc)

    async def get_memory_inspection(
        self,
        user_id: str,
        *,
        observed_at: datetime,
        after_event_id: str | None = None,
    ) -> MemoryInspectionPage:
        """Load bounded governed memory without exposing source messages."""
        self._validate_memory_user_id(user_id)
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise ValueError(
                "observed_at must be a timezone-aware datetime."
            )
        if after_event_id is not None:
            self._validate_memory_identifier(
                after_event_id,
                "after_event_id",
            )

        try:
            user_ref = self._client.collection("users").document(user_id)
            profile_snapshot = await user_ref.get()
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )

            proposal_collection = user_ref.collection("memory_proposals")
            proposal_refs = [
                proposal_collection.document(category)
                for category in MEMORY_CATEGORY_ORDER
            ]
            unresolved_by_category: dict[str, MemoryProposal] = {}
            async for snapshot in self._client.get_all(proposal_refs):
                if not snapshot.exists:
                    continue
                proposal = self._proposal_from_document(snapshot.to_dict())
                if (
                    proposal.status == "pending"
                    and observed_at < proposal.expires_at
                ):
                    unresolved_by_category[proposal.category] = proposal
            unresolved_proposals = tuple(
                unresolved_by_category[category]
                for category in MEMORY_CATEGORY_ORDER
                if category in unresolved_by_category
            )

            events_ref = user_ref.collection("memory_events")
            query = events_ref.order_by(
                "created_at",
                direction=firestore.Query.DESCENDING,
            )
            query = query.order_by(
                FieldPath.document_id(),
                direction=firestore.Query.DESCENDING,
            )
            if after_event_id is not None:
                cursor_ref = events_ref.document(after_event_id)
                cursor_snapshot = await cursor_ref.get()
                if not cursor_snapshot.exists:
                    raise MemoryEventCursorNotFoundError(
                        "Memory event cursor was not found."
                    )
                self._memory_event_from_document(
                    after_event_id,
                    cursor_snapshot.to_dict(),
                )
                query = query.start_after(cursor_snapshot)
            query = query.limit(51)
            event_snapshots = [snapshot async for snapshot in query.stream()]
            events = tuple(
                self._memory_event_from_document(
                    snapshot.id,
                    snapshot.to_dict(),
                )
                for snapshot in event_snapshots[:50]
            )
            next_event_id = (
                events[-1].event_id if len(event_snapshots) > 50 else None
            )

            return MemoryInspectionPage(
                profile=profile,
                unresolved_proposals=unresolved_proposals,
                events=events,
                next_event_id=next_event_id,
            )
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("get_memory_inspection", exc)

    async def create_memory_proposal(
        self,
        user_id: str,
        proposal: MemoryProposal,
        *,
        observed_at: datetime,
    ) -> MemoryProposal:
        """Create one pending proposal in its deterministic category slot."""
        self._validate_memory_proposal_creation(
            user_id,
            proposal,
            observed_at,
        )
        user_ref = self._client.collection("users").document(user_id)
        proposal_ref = user_ref.collection("memory_proposals").document(
            proposal.category
        )
        transaction = self._client.transaction()

        async def create_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryProposal:
            snapshot = await proposal_ref.get(transaction=transaction)
            if not snapshot.exists:
                transaction.set(
                    proposal_ref,
                    self._proposal_document(proposal),
                )
                return proposal
            stored = self._proposal_from_document(snapshot.to_dict())
            if stored.status == "pending" and stored.expires_at > observed_at:
                if self._proposals_are_identical(stored, proposal):
                    return stored
                raise MemoryProposalConflictError(
                    "An unexpired memory proposal already occupies this "
                    "category."
                )
            transaction.set(
                proposal_ref,
                self._proposal_document(proposal),
            )
            return proposal

        run_transaction = firestore.async_transactional(
            create_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("create_memory_proposal", exc)

    async def approve_memory_proposal(
        self,
        user_id: str,
        category: MemoryCategory,
        proposal_id: str,
        *,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
        observed_at: datetime,
    ) -> MemoryApprovalResult:
        """Atomically approve one governed memory proposal."""
        self._validate_memory_approval_inputs(
            user_id,
            category,
            proposal_id,
            confirmation_channel,
            confirmation_session_id,
            confirmation_message_id,
            observed_at,
        )
        user_ref = self._client.collection("users").document(user_id)
        proposal_ref = user_ref.collection("memory_proposals").document(
            category
        )
        events_ref = user_ref.collection("memory_events")
        approved_event_id = f"{proposal_id}--approved"
        corrected_event_id = f"{proposal_id}--corrected"
        approved_event_ref = events_ref.document(approved_event_id)
        corrected_event_ref = events_ref.document(corrected_event_id)
        transaction = self._client.transaction()

        async def approve_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryApprovalResult:
            proposal_snapshot = await proposal_ref.get(transaction=transaction)
            profile_snapshot = await user_ref.get(transaction=transaction)
            approved_snapshot = await approved_event_ref.get(
                transaction=transaction
            )
            corrected_snapshot = await corrected_event_ref.get(
                transaction=transaction
            )

            if not proposal_snapshot.exists:
                raise MemoryProposalNotFoundError(
                    "Memory proposal does not exist."
                )
            proposal = self._proposal_from_document(
                proposal_snapshot.to_dict()
            )
            if (
                proposal.proposal_id != proposal_id
                or proposal.category != category
            ):
                raise MemoryProposalConflictError(
                    "Memory proposal no longer occupies this category."
                )
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            if approved_snapshot.exists and corrected_snapshot.exists:
                raise ValueError(
                    "Stored memory approval has conflicting events."
                )
            if approved_snapshot.exists:
                return self._existing_initial_approval_result(
                    proposal,
                    profile,
                    approved_event_id,
                    approved_snapshot.to_dict(),
                    confirmation_channel,
                    confirmation_session_id,
                    confirmation_message_id,
                )
            if corrected_snapshot.exists:
                corrected_event = self._memory_event_from_document(
                    corrected_event_id,
                    corrected_snapshot.to_dict(),
                )
                prior_signal_id = corrected_event.related_signal_id
                if prior_signal_id is None:
                    raise MemoryProposalConflictError(
                        "Stored correction has no prior signal."
                    )
                superseded_event_id = f"{prior_signal_id}--superseded"
                if len(superseded_event_id) > 128:
                    raise ValueError("Derived memory event ID is too long.")
                superseded_event_ref = events_ref.document(
                    superseded_event_id
                )
                superseded_snapshot = await superseded_event_ref.get(
                    transaction=transaction
                )
                if not superseded_snapshot.exists:
                    raise ValueError(
                        "Stored correction has no superseded event."
                    )
                superseded_event = self._memory_event_from_document(
                    superseded_event_id,
                    superseded_snapshot.to_dict(),
                )
                return self._existing_correction_result(
                    proposal,
                    profile,
                    corrected_event,
                    superseded_event,
                    confirmation_channel,
                    confirmation_session_id,
                    confirmation_message_id,
                )
            if proposal.status == "approved":
                raise ValueError(
                    "Approved memory proposal has no lifecycle event."
                )
            if proposal.status != "pending":
                raise MemoryProposalConflictError(
                    "Memory proposal has already been resolved."
                )
            if proposal.expires_at <= observed_at:
                raise MemoryProposalExpiredError("Memory proposal has expired.")

            active_signal = self._active_signal_for_category(profile, category)
            if active_signal is not None:
                if proposal.expected_signal_id != active_signal.signal_id:
                    raise MemoryProposalConflictError(
                        "Memory proposal does not match the active signal."
                    )
                return await self._approve_correction_in_transaction(
                    transaction=transaction,
                    events_ref=events_ref,
                    corrected_event_ref=corrected_event_ref,
                    user_ref=user_ref,
                    proposal_ref=proposal_ref,
                    proposal=proposal,
                    profile=profile,
                    active_signal=active_signal,
                    corrected_event_id=corrected_event_id,
                    confirmation_channel=confirmation_channel,
                    confirmation_session_id=confirmation_session_id,
                    confirmation_message_id=confirmation_message_id,
                    observed_at=observed_at,
                )

            if proposal.expected_signal_id is not None:
                raise MemoryProposalConflictError(
                    "Memory proposal does not match the active signal."
                )

            revision = profile.memory_revision + 1
            event = self._proposal_memory_event(
                proposal,
                event_id=approved_event_id,
                event_type="approved",
                confirmation_channel=confirmation_channel,
                confirmation_session_id=confirmation_session_id,
                confirmation_message_id=confirmation_message_id,
                related_signal_id=None,
                memory_revision=revision,
                created_at=observed_at,
            )
            signal = self._active_signal_from_event(
                proposal,
                event,
                observed_at,
            )
            updated_profile = self._profile_with_signal(
                profile,
                signal,
                revision,
            )

            transaction.set(
                approved_event_ref,
                self._memory_event_document(event),
            )
            transaction.set(
                user_ref,
                self._collaboration_profile_document(updated_profile),
                merge=True,
            )
            transaction.set(
                proposal_ref,
                {
                    "status": "approved",
                    "resolved_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return MemoryApprovalResult(
                profile=updated_profile,
                event=event,
            )

        run_transaction = firestore.async_transactional(
            approve_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("approve_memory_proposal", exc)

    async def reject_memory_proposal(
        self,
        user_id: str,
        category: MemoryCategory,
        proposal_id: str,
        *,
        observed_at: datetime,
    ) -> MemoryRejectionResult:
        """Atomically reject one pending governed-memory proposal."""
        self._validate_memory_signal_locator(
            user_id,
            category,
            proposal_id,
        )
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be a timezone-aware datetime.")

        user_ref = self._client.collection("users").document(user_id)
        proposal_ref = user_ref.collection("memory_proposals").document(
            category
        )
        transaction = self._client.transaction()

        async def reject_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryRejectionResult:
            proposal_snapshot = await proposal_ref.get(
                transaction=transaction
            )
            profile_snapshot = await user_ref.get(transaction=transaction)
            if not proposal_snapshot.exists:
                raise MemoryProposalNotFoundError(
                    "Memory proposal does not exist."
                )
            proposal = self._proposal_from_document(
                proposal_snapshot.to_dict()
            )
            if (
                proposal.proposal_id != proposal_id
                or proposal.category != category
            ):
                raise MemoryProposalConflictError(
                    "Memory proposal no longer occupies this category."
                )
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            if proposal.status == "rejected":
                return MemoryRejectionResult(
                    profile=profile,
                    proposal=proposal,
                )
            if proposal.status != "pending":
                raise MemoryProposalConflictError(
                    "Memory proposal has already been resolved."
                )
            if proposal.expires_at <= observed_at:
                raise MemoryProposalExpiredError(
                    "Memory proposal has expired."
                )

            rejected_proposal = proposal.model_copy(
                update={"status": "rejected"}
            )
            transaction.set(
                proposal_ref,
                {
                    "status": "rejected",
                    "resolved_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return MemoryRejectionResult(
                profile=profile,
                proposal=rejected_proposal,
            )

        run_transaction = firestore.async_transactional(
            reject_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("reject_memory_proposal", exc)

    async def revoke_memory_signal(
        self,
        user_id: str,
        category: MemoryCategory,
        signal_id: str,
        *,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
        observed_at: datetime,
    ) -> MemoryRevocationResult:
        """Atomically remove an active signal and retain its history."""
        self._validate_memory_approval_inputs(
            user_id,
            category,
            signal_id,
            confirmation_channel,
            confirmation_session_id,
            confirmation_message_id,
            observed_at,
        )
        user_ref = self._client.collection("users").document(user_id)
        events_ref = user_ref.collection("memory_events")
        revoked_event_id = f"{signal_id}--revoked"
        revoked_event_ref = events_ref.document(revoked_event_id)
        transaction = self._client.transaction()

        async def revoke_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryRevocationResult:
            profile_snapshot = await user_ref.get(transaction=transaction)
            revoked_snapshot = await revoked_event_ref.get(
                transaction=transaction
            )
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            active_signal = self._active_signal_for_category(
                profile,
                category,
            )
            if active_signal is None or active_signal.signal_id != signal_id:
                if revoked_snapshot.exists:
                    revoked_event = self._memory_event_from_document(
                        revoked_event_id,
                        revoked_snapshot.to_dict(),
                    )
                    same_action = (
                        revoked_event.event_type == "revoked"
                        and revoked_event.signal_id == signal_id
                        and revoked_event.category == category
                        and revoked_event.confirmation_channel
                        == confirmation_channel
                        and revoked_event.confirmation_session_id
                        == confirmation_session_id
                        and revoked_event.confirmation_message_id
                        == confirmation_message_id
                        and revoked_event.related_signal_id is None
                    )
                    if not same_action:
                        raise MemorySignalConflictError(
                            "Stored memory revocation cannot prove this "
                            "action."
                        )
                    if profile.memory_revision < revoked_event.memory_revision:
                        raise ValueError(
                            "Stored memory revision precedes revoked event."
                        )
                    return MemoryRevocationResult(
                        profile=profile,
                        event=revoked_event,
                    )
                raise MemorySignalNotFoundError(
                    "Memory signal is not active."
                )
            if revoked_snapshot.exists:
                raise ValueError(
                    "Active memory signal already has a revoked event."
                )

            source_event_ref = events_ref.document(
                active_signal.source_event_id
            )
            source_snapshot = await source_event_ref.get(
                transaction=transaction
            )
            if not source_snapshot.exists:
                raise ValueError("Active memory source event does not exist.")
            source_event = self._memory_event_from_document(
                active_signal.source_event_id,
                source_snapshot.to_dict(),
            )
            self._validate_active_signal_source(active_signal, source_event)

            revision = profile.memory_revision + 1
            revoked_event = MemoryEvent.model_validate(
                {
                    "event_id": revoked_event_id,
                    "event_type": "revoked",
                    "signal_id": active_signal.signal_id,
                    "category": active_signal.category,
                    "value": active_signal.value,
                    "policy_version": active_signal.policy_version,
                    "source_type": source_event.source_type,
                    "source_session_id": source_event.source_session_id,
                    "source_message_id": source_event.source_message_id,
                    "confirmation_channel": confirmation_channel,
                    "confirmation_session_id": confirmation_session_id,
                    "confirmation_message_id": confirmation_message_id,
                    "related_signal_id": None,
                    "memory_revision": revision,
                    "created_at": observed_at,
                }
            )
            identity_context = dict(profile.identity_context)
            active_preferences = dict(profile.active_preferences)
            identity_context.pop(category, None)
            active_preferences.pop(category, None)
            updated_profile = CollaborationProfile(
                memory_schema_version="1.0",
                memory_revision=revision,
                identity_context=identity_context,
                active_preferences=active_preferences,
            )
            transaction.set(
                revoked_event_ref,
                self._memory_event_document(revoked_event),
            )
            transaction.set(
                user_ref,
                self._collaboration_profile_document(
                    updated_profile,
                    refresh_approved_at=False,
                ),
                merge=True,
            )
            return MemoryRevocationResult(
                profile=updated_profile,
                event=revoked_event,
            )

        run_transaction = firestore.async_transactional(
            revoke_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("revoke_memory_signal", exc)

    async def delete_memory_signal(
        self,
        user_id: str,
        category: MemoryCategory,
        signal_id: str,
    ) -> MemoryDeletionResult:
        """Atomically remove every bounded artifact owned by a signal."""
        self._validate_memory_signal_locator(user_id, category, signal_id)
        user_ref = self._client.collection("users").document(user_id)
        proposal_ref = user_ref.collection("memory_proposals").document(
            category
        )
        events_ref = user_ref.collection("memory_events")
        event_types = ("approved", "corrected", "superseded", "revoked")
        event_refs = {
            event_type: events_ref.document(f"{signal_id}--{event_type}")
            for event_type in event_types
        }
        transaction = self._client.transaction()

        async def delete_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryDeletionResult:
            profile_snapshot = await user_ref.get(transaction=transaction)
            proposal_snapshot = await proposal_ref.get(
                transaction=transaction
            )
            event_snapshots = {
                event_type: await event_refs[event_type].get(
                    transaction=transaction
                )
                for event_type in event_types
            }
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            identity_context = dict(profile.identity_context)
            active_preferences = dict(profile.active_preferences)
            active_signal = self._active_signal_for_category(
                profile,
                category,
            )
            projection_owned = (
                active_signal is not None
                and active_signal.signal_id == signal_id
            )
            if projection_owned:
                identity_context.pop(category, None)
                active_preferences.pop(category, None)

            proposal_owned = False
            if proposal_snapshot.exists:
                proposal = self._proposal_from_document(
                    proposal_snapshot.to_dict()
                )
                proposal_owned = proposal.proposal_id == signal_id

            owned_event_types: list[str] = []
            for event_type, snapshot in event_snapshots.items():
                if not snapshot.exists:
                    continue
                event_id = f"{signal_id}--{event_type}"
                event = self._memory_event_from_document(
                    event_id,
                    snapshot.to_dict(),
                )
                if (
                    event.event_type != event_type
                    or event.signal_id != signal_id
                    or event.category != category
                ):
                    raise ValueError(
                        "Stored memory event does not match its path."
                    )
                owned_event_types.append(event_type)

            artifacts_deleted = bool(
                projection_owned or proposal_owned or owned_event_types
            )
            if not artifacts_deleted:
                return MemoryDeletionResult(
                    profile=profile,
                    artifacts_deleted=False,
                )

            updated_profile = CollaborationProfile(
                memory_schema_version="1.0",
                memory_revision=profile.memory_revision + 1,
                identity_context=identity_context,
                active_preferences=active_preferences,
            )
            transaction.set(
                user_ref,
                self._collaboration_profile_document(
                    updated_profile,
                    refresh_approved_at=False,
                ),
                merge=True,
            )
            if proposal_owned:
                transaction.delete(proposal_ref)
            for event_type in owned_event_types:
                transaction.delete(event_refs[event_type])
            return MemoryDeletionResult(
                profile=updated_profile,
                artifacts_deleted=True,
            )

        run_transaction = firestore.async_transactional(
            delete_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("delete_memory_signal", exc)

    def close(self) -> None:
        """Close the Firestore client's transport."""
        self._client.close()

    @staticmethod
    def _proposal_document(proposal: MemoryProposal) -> dict[str, object]:
        document = proposal.model_dump(mode="python")
        document["created_at"] = firestore.SERVER_TIMESTAMP
        document["resolved_at"] = None
        return document

    @staticmethod
    def _active_signal_for_category(
        profile: CollaborationProfile,
        category: MemoryCategory,
    ) -> ActiveMemorySignal | None:
        if category in profile.identity_context:
            return profile.identity_context[category]
        if category in profile.active_preferences:
            return profile.active_preferences[category]
        return None

    @classmethod
    def _existing_initial_approval_result(
        cls,
        proposal: MemoryProposal,
        profile: CollaborationProfile,
        event_id: str,
        event_document: object,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
    ) -> MemoryApprovalResult:
        event = cls._memory_event_from_document(event_id, event_document)
        active_signal = cls._active_signal_for_category(
            profile,
            proposal.category,
        )
        expected_event = MemoryEvent.model_validate(
            {
                "event_id": event_id,
                "event_type": "approved",
                "signal_id": proposal.proposal_id,
                "category": proposal.category,
                "value": proposal.proposed_value,
                "policy_version": proposal.policy_version,
                "source_type": "explicit_user_feedback",
                "source_session_id": proposal.source_session_id,
                "source_message_id": proposal.source_message_id,
                "confirmation_channel": confirmation_channel,
                "confirmation_session_id": confirmation_session_id,
                "confirmation_message_id": confirmation_message_id,
                "related_signal_id": None,
                "memory_revision": profile.memory_revision,
                "created_at": event.created_at,
            }
        )
        valid_signal = (
            active_signal is not None
            and active_signal.signal_id == proposal.proposal_id
            and active_signal.category == proposal.category
            and active_signal.value == proposal.proposed_value
            and active_signal.policy_version == proposal.policy_version
            and active_signal.source_event_id == event_id
        )
        if (
            proposal.status != "approved"
            or event != expected_event
            or not valid_signal
        ):
            raise MemoryProposalConflictError(
                "Stored memory approval differs from this decision."
            )
        return MemoryApprovalResult(profile=profile, event=event)

    async def _approve_correction_in_transaction(
        self,
        *,
        transaction: AsyncTransaction,
        events_ref: AsyncCollectionReference,
        corrected_event_ref: AsyncDocumentReference,
        user_ref: AsyncDocumentReference,
        proposal_ref: AsyncDocumentReference,
        proposal: MemoryProposal,
        profile: CollaborationProfile,
        active_signal: ActiveMemorySignal,
        corrected_event_id: str,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
        observed_at: datetime,
    ) -> MemoryApprovalResult:
        source_event_ref = events_ref.document(active_signal.source_event_id)
        superseded_event_id = f"{active_signal.signal_id}--superseded"
        if len(superseded_event_id) > 128:
            raise ValueError("Derived memory event ID is too long.")
        superseded_event_ref = events_ref.document(superseded_event_id)
        source_snapshot = await source_event_ref.get(transaction=transaction)
        superseded_snapshot = await superseded_event_ref.get(
            transaction=transaction
        )
        if not source_snapshot.exists:
            raise ValueError("Active memory source event does not exist.")
        source_event = self._memory_event_from_document(
            active_signal.source_event_id,
            source_snapshot.to_dict(),
        )
        self._validate_active_signal_source(active_signal, source_event)
        if superseded_snapshot.exists:
            raise MemoryProposalConflictError(
                "A differing superseded event already exists."
            )

        revision = profile.memory_revision + 1
        corrected_event = self._proposal_memory_event(
            proposal,
            event_id=corrected_event_id,
            event_type="corrected",
            confirmation_channel=confirmation_channel,
            confirmation_session_id=confirmation_session_id,
            confirmation_message_id=confirmation_message_id,
            related_signal_id=active_signal.signal_id,
            memory_revision=revision,
            created_at=observed_at,
        )
        superseded_event = MemoryEvent.model_validate(
            {
                "event_id": superseded_event_id,
                "event_type": "superseded",
                "signal_id": active_signal.signal_id,
                "category": active_signal.category,
                "value": active_signal.value,
                "policy_version": active_signal.policy_version,
                "source_type": source_event.source_type,
                "source_session_id": source_event.source_session_id,
                "source_message_id": source_event.source_message_id,
                "confirmation_channel": confirmation_channel,
                "confirmation_session_id": confirmation_session_id,
                "confirmation_message_id": confirmation_message_id,
                "related_signal_id": proposal.proposal_id,
                "memory_revision": revision,
                "created_at": observed_at,
            }
        )
        signal = self._active_signal_from_event(
            proposal,
            corrected_event,
            observed_at,
        )
        updated_profile = self._profile_with_signal(
            profile,
            signal,
            revision,
        )
        transaction.set(
            corrected_event_ref,
            self._memory_event_document(corrected_event),
        )
        transaction.set(
            superseded_event_ref,
            self._memory_event_document(superseded_event),
        )
        transaction.set(
            user_ref,
            self._collaboration_profile_document(updated_profile),
            merge=True,
        )
        transaction.set(
            proposal_ref,
            {
                "status": "approved",
                "resolved_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        return MemoryApprovalResult(
            profile=updated_profile,
            event=corrected_event,
            superseded_event=superseded_event,
        )

    @classmethod
    def _existing_correction_result(
        cls,
        proposal: MemoryProposal,
        profile: CollaborationProfile,
        corrected_event: MemoryEvent,
        superseded_event: MemoryEvent,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
    ) -> MemoryApprovalResult:
        prior_signal_id = corrected_event.related_signal_id
        active_signal = cls._active_signal_for_category(
            profile,
            proposal.category,
        )
        expected_corrected = cls._proposal_memory_event(
            proposal,
            event_id=corrected_event.event_id,
            event_type="corrected",
            confirmation_channel=confirmation_channel,
            confirmation_session_id=confirmation_session_id,
            confirmation_message_id=confirmation_message_id,
            related_signal_id=prior_signal_id,
            memory_revision=profile.memory_revision,
            created_at=corrected_event.created_at,
        )
        valid_active_signal = (
            active_signal is not None
            and active_signal.signal_id == proposal.proposal_id
            and active_signal.category == proposal.category
            and active_signal.value == proposal.proposed_value
            and active_signal.policy_version == proposal.policy_version
            and active_signal.source_event_id == corrected_event.event_id
        )
        valid_superseded = (
            prior_signal_id is not None
            and superseded_event.event_id
            == f"{prior_signal_id}--superseded"
            and superseded_event.event_type == "superseded"
            and superseded_event.signal_id == prior_signal_id
            and superseded_event.category == proposal.category
            and superseded_event.policy_version == proposal.policy_version
            and superseded_event.confirmation_channel == confirmation_channel
            and superseded_event.confirmation_session_id
            == confirmation_session_id
            and superseded_event.confirmation_message_id
            == confirmation_message_id
            and superseded_event.related_signal_id == proposal.proposal_id
            and superseded_event.memory_revision == profile.memory_revision
        )
        if (
            proposal.status != "approved"
            or proposal.expected_signal_id != prior_signal_id
            or corrected_event != expected_corrected
            or not valid_active_signal
            or not valid_superseded
        ):
            raise MemoryProposalConflictError(
                "Stored memory correction differs from this decision."
            )
        return MemoryApprovalResult(
            profile=profile,
            event=corrected_event,
            superseded_event=superseded_event,
        )

    @staticmethod
    def _proposal_memory_event(
        proposal: MemoryProposal,
        *,
        event_id: str,
        event_type: str,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
        related_signal_id: str | None,
        memory_revision: int,
        created_at: datetime,
    ) -> MemoryEvent:
        return MemoryEvent.model_validate(
            {
                "event_id": event_id,
                "event_type": event_type,
                "signal_id": proposal.proposal_id,
                "category": proposal.category,
                "value": proposal.proposed_value,
                "policy_version": proposal.policy_version,
                "source_type": "explicit_user_feedback",
                "source_session_id": proposal.source_session_id,
                "source_message_id": proposal.source_message_id,
                "confirmation_channel": confirmation_channel,
                "confirmation_session_id": confirmation_session_id,
                "confirmation_message_id": confirmation_message_id,
                "related_signal_id": related_signal_id,
                "memory_revision": memory_revision,
                "created_at": created_at,
            }
        )

    @staticmethod
    def _active_signal_from_event(
        proposal: MemoryProposal,
        event: MemoryEvent,
        approved_at: datetime,
    ) -> ActiveMemorySignal:
        return ActiveMemorySignal.model_validate(
            {
                "signal_id": proposal.proposal_id,
                "category": proposal.category,
                "value": proposal.proposed_value,
                "policy_version": proposal.policy_version,
                "source_event_id": event.event_id,
                "approved_at": approved_at,
            }
        )

    @staticmethod
    def _validate_active_signal_source(
        signal: ActiveMemorySignal,
        event: MemoryEvent,
    ) -> None:
        valid = (
            event.event_id == signal.source_event_id
            and event.signal_id == signal.signal_id
            and event.category == signal.category
            and event.value == signal.value
            and event.policy_version == signal.policy_version
            and event.event_type in ("approved", "corrected")
        )
        if not valid:
            raise ValueError(
                "Active memory signal does not match its source event."
            )

    @staticmethod
    def _profile_with_signal(
        profile: CollaborationProfile,
        signal: ActiveMemorySignal,
        revision: int,
    ) -> CollaborationProfile:
        identity_context = dict(profile.identity_context)
        active_preferences = dict(profile.active_preferences)
        if signal.category in ("preferred_name", "broad_roles"):
            identity_context[signal.category] = signal
        else:
            active_preferences[signal.category] = signal
        return CollaborationProfile(
            memory_schema_version="1.0",
            memory_revision=revision,
            identity_context=identity_context,
            active_preferences=active_preferences,
        )

    @staticmethod
    def _memory_event_document(event: MemoryEvent) -> dict[str, object]:
        document = event.model_dump(mode="python")
        document.pop("event_id")
        document["created_at"] = firestore.SERVER_TIMESTAMP
        return document

    @staticmethod
    def _memory_event_from_document(
        event_id: str,
        document: object,
    ) -> MemoryEvent:
        if not isinstance(document, dict):
            raise ValueError("Stored memory event is invalid.")
        event_fields = {
            field_name: document.get(field_name)
            for field_name in MemoryEvent.model_fields
            if field_name != "event_id"
        }
        event_fields["event_id"] = event_id
        return MemoryEvent.model_validate(event_fields)

    @staticmethod
    def _collaboration_profile_document(
        profile: CollaborationProfile,
        *,
        refresh_approved_at: bool = True,
    ) -> dict[str, object]:
        document = profile.model_dump(mode="python")
        if refresh_approved_at:
            for signals in (
                document["identity_context"],
                document["active_preferences"],
            ):
                for signal in signals.values():
                    signal["approved_at"] = firestore.SERVER_TIMESTAMP
        document["memory_updated_at"] = firestore.SERVER_TIMESTAMP
        return document

    @staticmethod
    def _validate_memory_proposal_creation(
        user_id: object,
        proposal: object,
        observed_at: object,
    ) -> None:
        MemoryEngine._validate_memory_user_id(user_id)
        if not isinstance(proposal, MemoryProposal):
            raise ValueError("proposal must be a MemoryProposal.")
        if proposal.status != "pending":
            raise ValueError("proposal status must be pending.")

        proposal_prefix = f"{proposal.category}--"
        proposal_suffix = proposal.proposal_id.removeprefix(proposal_prefix)
        if (
            not proposal.proposal_id.startswith(proposal_prefix)
            or not proposal_suffix
        ):
            raise ValueError("proposal_id must match its category.")

        timestamps = (
            ("observed_at", observed_at),
            ("created_at", proposal.created_at),
            ("expires_at", proposal.expires_at),
        )
        for field_name, value in timestamps:
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValueError(
                    f"{field_name} must be a timezone-aware datetime."
                )

        if not proposal.created_at <= observed_at < proposal.expires_at:
            raise ValueError("proposal timestamps are not currently valid.")
        if proposal.expires_at - proposal.created_at != timedelta(hours=24):
            raise ValueError("proposal lifetime must be exactly 24 hours.")

    @staticmethod
    def _validate_memory_approval_inputs(
        user_id: object,
        category: object,
        proposal_id: object,
        confirmation_channel: object,
        confirmation_session_id: object,
        confirmation_message_id: object,
        observed_at: object,
    ) -> None:
        MemoryEngine._validate_memory_user_id(user_id)
        if category not in MEMORY_CATEGORY_ORDER:
            raise ValueError("category must be a governed memory category.")
        if not isinstance(proposal_id, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}", proposal_id
        ) is None:
            raise ValueError("proposal_id must be a valid identifier.")
        if not proposal_id.startswith(f"{category}--"):
            raise ValueError("proposal_id must match its category.")
        for suffix in ("--approved", "--corrected", "--superseded"):
            if len(f"{proposal_id}{suffix}") > 128:
                raise ValueError("Derived memory event ID is too long.")
        if confirmation_channel == "chat_decision":
            MemoryEngine._validate_memory_identifier(
                confirmation_session_id,
                "confirmation_session_id",
            )
            MemoryEngine._validate_memory_identifier(
                confirmation_message_id,
                "confirmation_message_id",
            )
        elif confirmation_channel == "memory_api":
            if (
                confirmation_session_id is not None
                or confirmation_message_id is not None
            ):
                raise ValueError(
                    "Memory API confirmation IDs must be omitted."
                )
        else:
            raise ValueError("confirmation_channel is invalid.")
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be a timezone-aware datetime.")

    @staticmethod
    def _validate_memory_signal_locator(
        user_id: object,
        category: object,
        signal_id: object,
    ) -> None:
        MemoryEngine._validate_memory_user_id(user_id)
        if category not in MEMORY_CATEGORY_ORDER:
            raise ValueError("category must be a governed memory category.")
        if not isinstance(signal_id, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            signal_id,
        ) is None:
            raise ValueError("signal_id must be a valid identifier.")
        if not signal_id.startswith(f"{category}--"):
            raise ValueError("signal_id must match its category.")
        for suffix in (
            "--approved",
            "--corrected",
            "--superseded",
            "--revoked",
        ):
            if len(f"{signal_id}{suffix}") > 128:
                raise ValueError("Derived memory event ID is too long.")

    @staticmethod
    def _proposal_from_document(
        document: object,
    ) -> MemoryProposal:
        if not isinstance(document, dict):
            raise ValueError("Stored memory proposal is invalid.")
        proposal_fields = {
            field_name: document.get(field_name)
            for field_name in MemoryProposal.model_fields
        }
        return MemoryProposal.model_validate(proposal_fields)

    @staticmethod
    def _collaboration_profile_from_document(
        document: object,
    ) -> CollaborationProfile:
        if not isinstance(document, dict):
            raise ValueError("Stored collaboration profile is invalid.")
        profile_fields = {
            field_name: document[field_name]
            for field_name in CollaborationProfile.model_fields
            if field_name in document
        }
        return CollaborationProfile.model_validate(profile_fields)

    @staticmethod
    def _proposals_are_identical(
        stored: MemoryProposal,
        candidate: MemoryProposal,
    ) -> bool:
        stable_fields = (
            "proposal_id",
            "category",
            "proposed_value",
            "expected_signal_id",
            "policy_version",
            "source_session_id",
            "source_message_id",
            "expires_at",
        )
        return all(
            getattr(stored, field_name) == getattr(candidate, field_name)
            for field_name in stable_fields
        )

    @staticmethod
    def _validate_memory_user_id(user_id: object) -> None:
        if not isinstance(user_id, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            user_id,
        ) is None:
            raise ValueError("user_id must be a valid identifier.")

    @staticmethod
    def _validate_memory_identifier(value: object, field_name: str) -> None:
        if not isinstance(value, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            value,
        ) is None:
            raise ValueError(f"{field_name} must be a valid identifier.")

    @staticmethod
    def _validate_string(value: object, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string.")

    @staticmethod
    def _validate_updates(updates: object) -> None:
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a non-empty dictionary.")

    @staticmethod
    def _validate_blueprint(blueprint: object) -> None:
        if not isinstance(blueprint, dict) or not blueprint:
            raise ValueError("blueprint must be a non-empty dictionary.")

    @staticmethod
    def _raise_firestore_error(
        operation: str, error: Exception
    ) -> NoReturn:
        logger.error("Firestore %s operation failed.", operation)
        raise MemoryEngineError(
            f"Firestore {operation} operation failed."
        ) from error
