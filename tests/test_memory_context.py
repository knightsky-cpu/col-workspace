from datetime import UTC, datetime

import pytest


def test_renderer_returns_empty_result_for_empty_profile() -> None:
    from memory_context import MemoryContextRenderer
    from schemas import CollaborationProfile

    rendered = MemoryContextRenderer.render(CollaborationProfile())

    assert rendered.instruction_text == ""
    assert rendered.adaptations == ()


def test_renderer_orders_sections_and_builds_matching_receipts() -> None:
    from memory_context import MemoryContextRenderer
    from schemas import ActiveMemorySignal, CollaborationProfile

    now = datetime(2026, 8, 20, tzinfo=UTC)

    def signal(
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
                "approved_at": now,
            }
        )

    profile = CollaborationProfile(
        memory_revision=4,
        identity_context={
            "broad_roles": signal(
                "roles-signal",
                "broad_roles",
                ["researcher", "student"],
            ),
            "preferred_name": signal(
                "name-signal",
                "preferred_name",
                "Avery",
            ),
        },
        active_preferences={
            "example_usage": signal(
                "example-signal",
                "example_usage",
                "always_practical",
            ),
            "response_length": signal(
                "length-signal",
                "response_length",
                "concise",
            ),
        },
    )

    rendered = MemoryContextRenderer.render(profile)

    assert rendered.instruction_text == (
        "[APPROVED_IDENTITY_CONTEXT]\n"
        "- preferred_name=Avery: Address the user by their approved preferred "
        "name when natural; do not repeat it mechanically or treat it as "
        "verified legal identity.\n"
        "- broad_roles=[student, researcher]: Use the approved broad role "
        "context only to calibrate examples and explanations; do not infer "
        "expertise, employer, school, seniority, or credentials.\n"
        "[/APPROVED_IDENTITY_CONTEXT]\n"
        "[APPROVED_COLLABORATION_PREFERENCES]\n"
        "- response_length=concise: Keep the response compact while preserving "
        "information required to complete the request.\n"
        "- example_usage=always_practical: Include one practical example when "
        "the task permits it.\n"
        "[/APPROVED_COLLABORATION_PREFERENCES]"
    )
    assert [
        receipt.model_dump(mode="json")
        for receipt in rendered.adaptations
    ] == [
        {
            "signal_id": "name-signal",
            "category": "preferred_name",
            "value": "Avery",
            "source_event_id": "name-signal--approved",
            "status": "provided_to_model",
        },
        {
            "signal_id": "roles-signal",
            "category": "broad_roles",
            "value": ["student", "researcher"],
            "source_event_id": "roles-signal--approved",
            "status": "provided_to_model",
        },
        {
            "signal_id": "length-signal",
            "category": "response_length",
            "value": "concise",
            "source_event_id": "length-signal--approved",
            "status": "provided_to_model",
        },
        {
            "signal_id": "example-signal",
            "category": "example_usage",
            "value": "always_practical",
            "source_event_id": "example-signal--approved",
            "status": "provided_to_model",
        },
    ]


def test_renderer_rejects_raw_profile_mapping() -> None:
    from memory_context import MemoryContextRenderer

    with pytest.raises(TypeError, match="CollaborationProfile"):
        MemoryContextRenderer.render(
            {
                "identity_context": {"preferred_name": "unvalidated"},
                "legacy_private_field": "must-not-render",
            }
        )


@pytest.mark.parametrize(
    ("profile_field", "map_key", "category", "value", "expected_marker"),
    (
        (
            "identity_context",
            "preferred_name",
            "preferred_name",
            "Avery",
            "[APPROVED_IDENTITY_CONTEXT]",
        ),
        (
            "active_preferences",
            "response_length",
            "response_length",
            "concise",
            "[APPROVED_COLLABORATION_PREFERENCES]",
        ),
    ),
)
def test_renderer_emits_only_nonempty_section(
    profile_field: str,
    map_key: str,
    category: str,
    value: object,
    expected_marker: str,
) -> None:
    from memory_context import MemoryContextRenderer
    from schemas import ActiveMemorySignal, CollaborationProfile

    signal = ActiveMemorySignal(
        signal_id="signal-1",
        category=category,
        value=value,
        policy_version="1.0",
        source_event_id="signal-1--approved",
        approved_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    profile = CollaborationProfile.model_validate(
        {profile_field: {map_key: signal}}
    )

    first = MemoryContextRenderer.render(profile)
    second = MemoryContextRenderer.render(profile)

    assert expected_marker in first.instruction_text
    assert first == second
    assert len(first.adaptations) == 1
    other_marker = (
        "[APPROVED_COLLABORATION_PREFERENCES]"
        if expected_marker == "[APPROVED_IDENTITY_CONTEXT]"
        else "[APPROVED_IDENTITY_CONTEXT]"
    )
    assert other_marker not in first.instruction_text
