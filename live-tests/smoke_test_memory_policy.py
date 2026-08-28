import _repo_path
from datetime import UTC, datetime

from memory_context import MemoryContextRenderer
from schemas import ActiveMemorySignal, CollaborationProfile


def _signal(
    signal_id: str,
    category: str,
    value: object,
) -> ActiveMemorySignal:
    return ActiveMemorySignal.model_validate(
        {
            "signal_id": signal_id,
            "category": category,
            "value": value,
            "policy_version": "1.0",
            "source_event_id": f"{signal_id}--approved",
            "approved_at": datetime(2026, 8, 20, tzinfo=UTC),
        }
    )


def run_smoke() -> int:
    profile = CollaborationProfile(
        memory_revision=4,
        identity_context={
            "preferred_name": _signal(
                "name-signal",
                "preferred_name",
                "Avery",
            ),
            "broad_roles": _signal(
                "role-signal",
                "broad_roles",
                ["student", "researcher"],
            ),
        },
        active_preferences={
            "response_length": _signal(
                "length-signal",
                "response_length",
                "concise",
            ),
            "example_usage": _signal(
                "example-signal",
                "example_usage",
                "always_practical",
            ),
        },
    )
    rendered = MemoryContextRenderer.render(profile)
    assert "[APPROVED_IDENTITY_CONTEXT]" in rendered.instruction_text
    assert (
        "[APPROVED_COLLABORATION_PREFERENCES]"
        in rendered.instruction_text
    )
    assert len(rendered.adaptations) == 4
    print("trusted-memory-m1 pass signals=4")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_smoke())
