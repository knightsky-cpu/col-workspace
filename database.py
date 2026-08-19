import logging
from typing import NoReturn

from google.api_core.exceptions import GoogleAPIError
from google.cloud import firestore
from google.cloud.firestore import AsyncClient


logger = logging.getLogger(__name__)


class MemoryEngineError(RuntimeError):
    """Raised when a Firestore memory operation fails."""


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

    def close(self) -> None:
        """Close the Firestore client's transport."""
        self._client.close()

    @staticmethod
    def _validate_string(value: object, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string.")

    @staticmethod
    def _validate_updates(updates: object) -> None:
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a non-empty dictionary.")

    @staticmethod
    def _raise_firestore_error(
        operation: str, error: GoogleAPIError
    ) -> NoReturn:
        logger.error("Firestore %s operation failed.", operation)
        raise MemoryEngineError(
            f"Firestore {operation} operation failed."
        ) from error
