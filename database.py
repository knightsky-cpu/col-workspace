import logging
import re
from datetime import datetime, timedelta
from typing import NoReturn

from google.api_core.exceptions import GoogleAPIError
from google.cloud import firestore
from google.cloud.firestore import AsyncClient, AsyncTransaction

from schemas import MemoryProposal


logger = logging.getLogger(__name__)


class MemoryEngineError(RuntimeError):
    """Raised when a Firestore memory operation fails."""


class MemoryProposalConflictError(RuntimeError):
    """Raised when an unexpired proposal owns a category slot."""


class MemoryEngine:
    """Provide asynchronous persistence for chat messages and user profiles."""

    def __init__(self, client: AsyncClient | None = None) -> None:
        self._client = client if client is not None else AsyncClient()

    async def save_message(
        self, session_id: str, role: str, text: str
    ) -> None:
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
    def _validate_memory_proposal_creation(
        user_id: object,
        proposal: object,
        observed_at: object,
    ) -> None:
        if not isinstance(user_id, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            user_id,
        ) is None:
            raise ValueError("user_id must be a valid identifier.")
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
