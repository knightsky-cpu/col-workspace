import _repo_path
import argparse
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from database import MemoryEngine
from memory_policy import MEMORY_CATEGORY_ORDER, MemoryCategory
from schemas import MemoryProposal


@dataclass(frozen=True, slots=True)
class MemoryRevocationSmokeResult:
    """Hold structural evidence from the M4 live revocation stage."""

    user_id: str
    category: MemoryCategory
    signal_id: str
    approval_revision: int
    revocation_revision: int
    retry_revision: int
    revoked_event_id: str

    def safe_summary(self) -> str:
        """Render the locators and revisions needed for manual inspection."""
        return (
            "trusted-memory-m4 revoke-pass "
            f"user_id={self.user_id} "
            f"category={self.category} "
            f"signal_id={self.signal_id} "
            f"approval_revision={self.approval_revision} "
            f"revocation_revision={self.revocation_revision} "
            f"retry_revision={self.retry_revision} "
            f"revoked_event={self.revoked_event_id}"
        )


@dataclass(frozen=True, slots=True)
class MemoryDeletionSmokeResult:
    """Hold structural evidence from the M4 live hard-deletion stage."""

    user_id: str
    category: MemoryCategory
    signal_id: str
    initial_revision: int
    deletion_revision: int
    retry_revision: int
    first_artifacts_deleted: bool
    retry_artifacts_deleted: bool

    def safe_summary(self) -> str:
        """Render deletion and retry evidence without memory content."""
        return (
            "trusted-memory-m4 delete-pass "
            f"user_id={self.user_id} "
            f"category={self.category} "
            f"signal_id={self.signal_id} "
            f"initial_revision={self.initial_revision} "
            f"deletion_revision={self.deletion_revision} "
            f"retry_revision={self.retry_revision} "
            "first_artifacts_deleted="
            f"{str(self.first_artifacts_deleted).lower()} "
            "retry_artifacts_deleted="
            f"{str(self.retry_artifacts_deleted).lower()}"
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def run_revocation_smoke(
    *,
    engine_factory: Callable[[], MemoryEngine] = MemoryEngine,
    id_factory: Callable[[], UUID] = uuid4,
    observed_at_factory: Callable[[], datetime] = _utc_now,
) -> MemoryRevocationSmokeResult:
    """Create, approve, revoke, retry, and reload one test signal."""
    suffix = id_factory().hex
    observed_at = observed_at_factory()
    user_id = f"memory-m4-smoke-{suffix}"
    category: MemoryCategory = "response_length"
    signal_id = f"{category}--{suffix}"
    proposal = MemoryProposal(
        proposal_id=signal_id,
        category=category,
        proposed_value="concise",
        expected_signal_id=None,
        status="pending",
        source_session_id=f"memory-m4-source-session-{suffix}",
        source_message_id=f"memory-m4-source-message-{suffix}",
        created_at=observed_at,
        expires_at=observed_at + timedelta(hours=24),
    )
    engine = engine_factory()
    try:
        await engine.create_memory_proposal(
            user_id,
            proposal,
            observed_at=observed_at,
        )
        approval = await engine.approve_memory_proposal(
            user_id,
            category,
            signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=observed_at,
        )
        revocation = await engine.revoke_memory_signal(
            user_id,
            category,
            signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=observed_at,
        )
        retry = await engine.revoke_memory_signal(
            user_id,
            category,
            signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=observed_at,
        )
        final_profile = await engine.get_collaboration_profile(user_id)

        if approval.profile.memory_revision != 1:
            raise RuntimeError("Memory approval revision check failed.")
        if (
            revocation.profile.memory_revision != 2
            or revocation.event.event_type != "revoked"
            or revocation.event.signal_id != signal_id
        ):
            raise RuntimeError("Memory revocation check failed.")
        if (
            retry.profile.memory_revision != 2
            or retry.event.event_id != revocation.event.event_id
        ):
            raise RuntimeError("Memory revocation retry check failed.")
        if (
            final_profile.memory_revision != 2
            or category in final_profile.active_preferences
            or category in final_profile.identity_context
        ):
            raise RuntimeError("Revoked profile projection check failed.")

        return MemoryRevocationSmokeResult(
            user_id=user_id,
            category=category,
            signal_id=signal_id,
            approval_revision=approval.profile.memory_revision,
            revocation_revision=revocation.profile.memory_revision,
            retry_revision=retry.profile.memory_revision,
            revoked_event_id=revocation.event.event_id,
        )
    finally:
        engine.close()


async def run_deletion_smoke(
    *,
    user_id: str,
    category: MemoryCategory,
    signal_id: str,
    engine_factory: Callable[[], MemoryEngine] = MemoryEngine,
) -> MemoryDeletionSmokeResult:
    """Delete one revoked test signal and verify an idempotent retry."""
    engine = engine_factory()
    try:
        initial_profile = await engine.get_collaboration_profile(user_id)
        deletion = await engine.delete_memory_signal(
            user_id,
            category,
            signal_id,
        )
        retry = await engine.delete_memory_signal(
            user_id,
            category,
            signal_id,
        )
        final_profile = await engine.get_collaboration_profile(user_id)

        expected_revision = initial_profile.memory_revision + 1
        if (
            not deletion.artifacts_deleted
            or deletion.profile.memory_revision != expected_revision
        ):
            raise RuntimeError("Memory hard-deletion check failed.")
        if (
            retry.artifacts_deleted
            or retry.profile.memory_revision != expected_revision
        ):
            raise RuntimeError("Memory deletion retry check failed.")
        if (
            final_profile.memory_revision != expected_revision
            or category in final_profile.active_preferences
            or category in final_profile.identity_context
        ):
            raise RuntimeError("Deleted profile projection check failed.")

        return MemoryDeletionSmokeResult(
            user_id=user_id,
            category=category,
            signal_id=signal_id,
            initial_revision=initial_profile.memory_revision,
            deletion_revision=deletion.profile.memory_revision,
            retry_revision=retry.profile.memory_revision,
            first_artifacts_deleted=deletion.artifacts_deleted,
            retry_artifacts_deleted=retry.artifacts_deleted,
        )
    finally:
        engine.close()


def build_parser() -> argparse.ArgumentParser:
    """Build the staged M4 live-smoke command-line parser."""
    parser = argparse.ArgumentParser(
        description="Exercise trusted-memory revocation and hard deletion.",
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)
    subparsers.add_parser(
        "revoke",
        help="Create, approve, and revoke a new test memory signal.",
    )
    delete_parser = subparsers.add_parser(
        "delete",
        help="Hard-delete the signal produced by the revoke stage.",
    )
    delete_parser.add_argument("--user-id", required=True)
    delete_parser.add_argument(
        "--category",
        required=True,
        choices=MEMORY_CATEGORY_ORDER,
    )
    delete_parser.add_argument("--signal-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run one M4 live-smoke stage and print copy-safe evidence."""
    args = build_parser().parse_args(argv)
    if args.stage == "revoke":
        result = asyncio.run(run_revocation_smoke())
    else:
        result = asyncio.run(
            run_deletion_smoke(
                user_id=args.user_id,
                category=args.category,
                signal_id=args.signal_id,
            )
        )
    print(result.safe_summary())


if __name__ == "__main__":
    main()
