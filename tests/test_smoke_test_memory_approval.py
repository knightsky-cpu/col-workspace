from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from database import MemoryApprovalResult
from schemas import ActiveMemorySignal, CollaborationProfile, MemoryEvent
from smoke_test_memory_approval import run_memory_approval_smoke


NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def event(
    *,
    event_id: str,
    event_type: str,
    signal_id: str,
    value: str,
    revision: int,
    related_signal_id: str | None,
) -> MemoryEvent:
    return MemoryEvent.model_validate(
        {
            "event_id": event_id,
            "event_type": event_type,
            "signal_id": signal_id,
            "category": "response_length",
            "value": value,
            "policy_version": "1.0",
            "source_type": "explicit_user_feedback",
            "source_session_id": "source-session",
            "source_message_id": "source-message",
            "confirmation_channel": "memory_api",
            "confirmation_session_id": None,
            "confirmation_message_id": None,
            "related_signal_id": related_signal_id,
            "memory_revision": revision,
            "created_at": NOW,
        }
    )


def profile(
    *,
    revision: int,
    signal_id: str,
    value: str,
    source_event_id: str,
) -> CollaborationProfile:
    signal = ActiveMemorySignal(
        signal_id=signal_id,
        category="response_length",
        value=value,
        source_event_id=source_event_id,
        approved_at=NOW,
    )
    return CollaborationProfile(
        memory_revision=revision,
        active_preferences={"response_length": signal},
    )


class FakeMemoryEngine:
    def __init__(self) -> None:
        initial_signal_id = "response_length--fixed-id-initial"
        corrected_signal_id = "response_length--fixed-id-correction"
        approved_event = event(
            event_id=f"{initial_signal_id}--approved",
            event_type="approved",
            signal_id=initial_signal_id,
            value="concise",
            revision=1,
            related_signal_id=None,
        )
        corrected_event = event(
            event_id=f"{corrected_signal_id}--corrected",
            event_type="corrected",
            signal_id=corrected_signal_id,
            value="detailed",
            revision=2,
            related_signal_id=initial_signal_id,
        )
        superseded_event = event(
            event_id=f"{initial_signal_id}--superseded",
            event_type="superseded",
            signal_id=initial_signal_id,
            value="concise",
            revision=2,
            related_signal_id=corrected_signal_id,
        )
        initial_profile = profile(
            revision=1,
            signal_id=initial_signal_id,
            value="concise",
            source_event_id=approved_event.event_id,
        )
        corrected_profile = profile(
            revision=2,
            signal_id=corrected_signal_id,
            value="detailed",
            source_event_id=corrected_event.event_id,
        )
        self.approval_results = [
            MemoryApprovalResult(initial_profile, approved_event),
            MemoryApprovalResult(initial_profile, approved_event),
            MemoryApprovalResult(
                corrected_profile,
                corrected_event,
                superseded_event,
            ),
        ]
        self.final_profile = corrected_profile
        self.operations: list[tuple[str, object]] = []

    async def create_memory_proposal(
        self,
        user_id,
        proposal,
        *,
        observed_at,
    ):
        self.operations.append(("create", proposal))
        return proposal

    async def approve_memory_proposal(self, *args, **kwargs):
        self.operations.append(("approve", args[2]))
        return self.approval_results.pop(0)

    async def get_collaboration_profile(self, user_id):
        self.operations.append(("load", user_id))
        return self.final_profile

    def close(self) -> None:
        self.operations.append(("close", None))


@pytest.mark.asyncio
async def test_run_memory_approval_smoke_exercises_full_lifecycle_offline(
) -> None:
    fake_engine = FakeMemoryEngine()

    result = await run_memory_approval_smoke(
        engine_factory=lambda: fake_engine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: NOW,
    )

    assert result.user_id == "memory-m3-smoke-fixed-id"
    assert result.initial_revision == 1
    assert result.retry_revision == 1
    assert result.correction_revision == 2
    assert result.approved_event_id.endswith("--approved")
    assert result.corrected_event_id.endswith("--corrected")
    assert result.superseded_event_id.endswith("--superseded")
    assert result.final_signal_id == (
        "response_length--fixed-id-correction"
    )
    assert result.final_active_value == "detailed"
    assert [operation for operation, _ in fake_engine.operations] == [
        "create",
        "approve",
        "approve",
        "create",
        "approve",
        "load",
        "close",
    ]
    initial_proposal = fake_engine.operations[0][1]
    correction_proposal = fake_engine.operations[3][1]
    assert correction_proposal.expected_signal_id == initial_proposal.proposal_id


@pytest.mark.asyncio
async def test_memory_approval_smoke_summary_excludes_memory_value() -> None:
    fake_engine = FakeMemoryEngine()

    result = await run_memory_approval_smoke(
        engine_factory=lambda: fake_engine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: NOW,
    )
    summary = result.safe_summary()

    assert "trusted-memory-m3 pass" in summary
    assert "user_id=memory-m3-smoke-fixed-id" in summary
    assert "initial_revision=1" in summary
    assert "retry_revision=1" in summary
    assert "correction_revision=2" in summary
    assert "concise" not in summary
    assert "detailed" not in summary
