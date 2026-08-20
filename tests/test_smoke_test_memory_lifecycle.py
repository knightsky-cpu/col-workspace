from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from database import (
    MemoryApprovalResult,
    MemoryDeletionResult,
    MemoryRevocationResult,
)
from schemas import (
    ActiveMemorySignal,
    CollaborationProfile,
    MemoryEvent,
)
from smoke_test_memory_lifecycle import (
    run_deletion_smoke,
    run_revocation_smoke,
)


NOW = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
SIGNAL_ID = "response_length--fixed-id"
APPROVED_EVENT_ID = f"{SIGNAL_ID}--approved"
REVOKED_EVENT_ID = f"{SIGNAL_ID}--revoked"


def memory_event(event_type: str, revision: int) -> MemoryEvent:
    return MemoryEvent.model_validate(
        {
            "event_id": f"{SIGNAL_ID}--{event_type}",
            "event_type": event_type,
            "signal_id": SIGNAL_ID,
            "category": "response_length",
            "value": "concise",
            "policy_version": "1.0",
            "source_type": "explicit_user_feedback",
            "source_session_id": "private-source-session",
            "source_message_id": "private-source-message",
            "confirmation_channel": "memory_api",
            "confirmation_session_id": None,
            "confirmation_message_id": None,
            "related_signal_id": None,
            "memory_revision": revision,
            "created_at": NOW,
        }
    )


def active_profile() -> CollaborationProfile:
    return CollaborationProfile(
        memory_revision=1,
        active_preferences={
            "response_length": ActiveMemorySignal(
                signal_id=SIGNAL_ID,
                category="response_length",
                value="concise",
                source_event_id=APPROVED_EVENT_ID,
                approved_at=NOW,
            )
        },
    )


def empty_profile(revision: int) -> CollaborationProfile:
    return CollaborationProfile(memory_revision=revision)


class FakeRevocationEngine:
    def __init__(self) -> None:
        self.operations: list[tuple[str, object]] = []

    async def create_memory_proposal(self, user_id, proposal, *, observed_at):
        self.operations.append(("create", proposal))
        return proposal

    async def approve_memory_proposal(self, *args, **kwargs):
        self.operations.append(("approve", args[2]))
        return MemoryApprovalResult(
            profile=active_profile(),
            event=memory_event("approved", 1),
        )

    async def revoke_memory_signal(self, *args, **kwargs):
        self.operations.append(("revoke", args[2]))
        return MemoryRevocationResult(
            profile=empty_profile(2),
            event=memory_event("revoked", 2),
        )

    async def get_collaboration_profile(self, user_id):
        self.operations.append(("load", user_id))
        return empty_profile(2)

    def close(self) -> None:
        self.operations.append(("close", None))


class FakeDeletionEngine:
    def __init__(self) -> None:
        self.operations: list[tuple[str, object]] = []
        self.results = [
            MemoryDeletionResult(empty_profile(3), True),
            MemoryDeletionResult(empty_profile(3), False),
        ]

    async def get_collaboration_profile(self, user_id):
        self.operations.append(("load", user_id))
        if len(self.results) == 2:
            return empty_profile(2)
        return empty_profile(3)

    async def delete_memory_signal(self, *args, **kwargs):
        self.operations.append(("delete", args[2]))
        return self.results.pop(0)

    def close(self) -> None:
        self.operations.append(("close", None))


@pytest.mark.asyncio
async def test_run_revocation_smoke_exercises_approval_revocation_and_retry(
) -> None:
    fake_engine = FakeRevocationEngine()

    result = await run_revocation_smoke(
        engine_factory=lambda: fake_engine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: NOW,
    )

    assert result.user_id == "memory-m4-smoke-fixed-id"
    assert result.signal_id == SIGNAL_ID
    assert result.approval_revision == 1
    assert result.revocation_revision == 2
    assert result.retry_revision == 2
    assert result.revoked_event_id == REVOKED_EVENT_ID
    assert [operation for operation, _ in fake_engine.operations] == [
        "create",
        "approve",
        "revoke",
        "revoke",
        "load",
        "close",
    ]


@pytest.mark.asyncio
async def test_run_deletion_smoke_exercises_deletion_and_idempotent_retry(
) -> None:
    fake_engine = FakeDeletionEngine()

    result = await run_deletion_smoke(
        user_id="memory-m4-smoke-fixed-id",
        category="response_length",
        signal_id=SIGNAL_ID,
        engine_factory=lambda: fake_engine,
    )

    assert result.initial_revision == 2
    assert result.deletion_revision == 3
    assert result.retry_revision == 3
    assert result.first_artifacts_deleted is True
    assert result.retry_artifacts_deleted is False
    assert [operation for operation, _ in fake_engine.operations] == [
        "load",
        "delete",
        "delete",
        "load",
        "close",
    ]


@pytest.mark.asyncio
async def test_memory_lifecycle_smoke_summaries_exclude_private_content(
) -> None:
    revocation = await run_revocation_smoke(
        engine_factory=FakeRevocationEngine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: NOW,
    )
    deletion = await run_deletion_smoke(
        user_id=revocation.user_id,
        category="response_length",
        signal_id=revocation.signal_id,
        engine_factory=FakeDeletionEngine,
    )

    summaries = f"{revocation.safe_summary()} {deletion.safe_summary()}"
    assert "trusted-memory-m4 revoke-pass" in summaries
    assert "trusted-memory-m4 delete-pass" in summaries
    assert "concise" not in summaries
    assert "private-source-session" not in summaries
    assert "private-source-message" not in summaries
