from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from working_state import (
    WorkingStateQuestion,
    WorkingStateSnapshot,
    build_working_state_context,
    should_update_working_state,
)


def make_working_state_snapshot(**overrides):
    values = {
        "user_id": "user-1",
        "project_id": "project-1",
        "session_id": "session-1",
        "source_message_id": "message-1",
        "request_summary": "Deployment plan with Cloud Run under consideration.",
        "current_goal": "Choose a deployment plan.",
        "intent_hypothesis": (
            "The user likely wants a secure deployment plan and is unsure "
            "whether background workers are necessary."
        ),
        "active_constraints": ("security matters more than speed",),
        "unresolved_questions": (
            WorkingStateQuestion(
                question=(
                    "Does artifact generation need to survive browser "
                    "disconnects?"
                ),
                why_it_matters=(
                    "This determines whether synchronous Cloud Run is enough."
                ),
                blocking_status="useful",
            ),
        ),
        "clarification_status": "useful",
        "next_step_hypothesis": (
            "Prefer a synchronous MVP unless durability becomes required."
        ),
        "confidence": "medium",
        "updated_at": datetime(2026, 8, 27, tzinfo=UTC),
    }
    values.update(overrides)
    return WorkingStateSnapshot(**values)


def test_working_state_context_is_hidden_and_non_authoritative():
    snapshot = make_working_state_snapshot()

    context = build_working_state_context(snapshot)

    assert "[SERVER_VALIDATED_WORKING_STATE]" in context
    assert "[/SERVER_VALIDATED_WORKING_STATE]" in context
    assert "non-authoritative" in context
    assert "hidden internal working state" in context
    assert "security matters more than speed" in context
    assert "hidden reasoning" not in context.lower()


def test_working_state_rejects_raw_reasoning_field():
    with pytest.raises(ValidationError):
        WorkingStateSnapshot(
            **make_working_state_snapshot().model_dump(),
            reasoning="raw private reasoning must not be accepted",
        )


def test_working_state_enforces_bounded_fields():
    with pytest.raises(ValidationError):
        make_working_state_snapshot(request_summary="x" * 201)

    with pytest.raises(ValidationError):
        make_working_state_snapshot(
            active_constraints=tuple(f"constraint {index}" for index in range(7))
        )


@pytest.mark.parametrize(
    ("message", "route", "expected"),
    (
        ("I want a deployment plan but I am not sure about workers.", None, True),
        ("Actually, artifact generation only takes 10 seconds.", None, True),
        ("Create a markdown study guide for algebra rules.", "artifact", True),
        ("What did we decide about the deployment plan?", None, True),
        ("thanks", "direct", False),
    ),
)
def test_should_update_working_state_for_collaborative_turns(
    message,
    route,
    expected,
):
    assert should_update_working_state(message, route=route) is expected
