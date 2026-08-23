from datetime import UTC, datetime

import pytest


NOW = datetime(2026, 8, 23, 21, 0, tzinfo=UTC)


def planning_signal():
    from schemas import ActiveMemorySignal

    return ActiveMemorySignal(
        signal_id="planning-granularity-signal-1",
        category="planning_granularity",
        value="micro_steps",
        policy_version="1.0",
        source_event_id="planning-granularity-signal-1--approved",
        approved_at=NOW,
    )


def blueprint_with_adaptations(adaptations: list[dict[str, str]]):
    from schemas import SynthesisBlueprint

    return SynthesisBlueprint.model_validate(
        {
            "synthesized_conceptual_model": {
                "project_name": "Study Partner",
                "core_value_proposition": "Turns goals into a study plan.",
                "in_scope": ["Study planning"],
            },
            "personalization_trace": {"adaptations": adaptations},
            "architectural_decisions": [
                {
                    "component_name": "Planning boundary",
                    "proposed_solution": "Use explicit plan stages.",
                    "rationale": "Keeps progress verifiable.",
                    "alternatives": [
                        {
                            "option_name": "Unstructured notes",
                            "tradeoff": "Faster but less verifiable.",
                            "reason_not_selected": "Lacks clear outcomes.",
                        }
                    ],
                }
            ],
            "socratic_clarifying_questions": [
                {
                    "question_text": "What is the target date?",
                    "why_this_matters": "It determines plan pacing.",
                    "suggested_options": [
                        {"label": "Two weeks", "impact": "Intensive."},
                        {"label": "One month", "impact": "Moderate."},
                    ],
                }
            ],
            "step_by_step_execution_roadmap": [
                {
                    "phase_name": "Phase 1",
                    "objective": "Establish the learning baseline.",
                    "expected_deliverable": "A verified baseline result.",
                    "micro_tasks": [
                        {
                            "task_description": "Complete a baseline quiz.",
                            "complexity_level": "Low",
                            "verification_steps": ["Record the score."],
                        }
                    ],
                }
            ],
        }
    )


def test_adapter_projects_only_approved_planning_granularity() -> None:
    from schemas import ActiveMemorySignal, CollaborationProfile
    from synthesis_personalization import SynthesisPersonalizationAdapter

    signal = ActiveMemorySignal(
        signal_id="planning-granularity-signal-1",
        category="planning_granularity",
        value="micro_steps",
        policy_version="1.0",
        source_event_id="planning-granularity-signal-1--approved",
        approved_at=NOW,
    )
    profile = CollaborationProfile(
        memory_revision=4,
        active_preferences={"planning_granularity": signal},
    )

    projection = SynthesisPersonalizationAdapter.project(profile)

    assert projection.model_context == {
        "planning_granularity": {
            "value": "micro_steps",
            "instruction": (
                "Break complex plans into small sequential actions with "
                "explicit verification."
            ),
        }
    }
    assert projection.supplied_signals == (signal,)


def test_adapter_returns_empty_projection_without_planning_signal() -> None:
    from schemas import CollaborationProfile
    from synthesis_personalization import SynthesisPersonalizationAdapter

    projection = SynthesisPersonalizationAdapter.project(
        CollaborationProfile(memory_revision=3)
    )

    assert projection.model_context == {}
    assert projection.supplied_signals == ()


def test_adapter_rejects_unvalidated_profile_mapping() -> None:
    from synthesis_personalization import SynthesisPersonalizationAdapter

    with pytest.raises(TypeError, match="CollaborationProfile"):
        SynthesisPersonalizationAdapter.project(
            {
                "active_preferences": {
                    "planning_granularity": {
                        "value": "micro_steps",
                    }
                },
                "legacy_private_field": "must-not-enter-synthesis",
            }
        )


def test_matching_trace_derives_receipt_from_approved_signal() -> None:
    from schemas import CollaborationProfile
    from synthesis_personalization import SynthesisPersonalizationAdapter

    signal = planning_signal()
    projection = SynthesisPersonalizationAdapter.project(
        CollaborationProfile(
            memory_revision=4,
            active_preferences={"planning_granularity": signal},
        )
    )
    blueprint = blueprint_with_adaptations(
        [
            {
                "profile_key": "planning_granularity",
                "architecture_change": (
                    "The roadmap uses smaller sequenced actions."
                ),
                "reason": "The supplied preference favors micro-steps.",
            }
        ]
    )

    receipts = SynthesisPersonalizationAdapter.validate_and_derive_receipts(
        projection,
        blueprint,
    )

    assert [receipt.model_dump(mode="json") for receipt in receipts] == [
        {
            "signal_id": "planning-granularity-signal-1",
            "category": "planning_granularity",
            "value": "micro_steps",
            "source_event_id": (
                "planning-granularity-signal-1--approved"
            ),
            "status": "provided_to_model",
        }
    ]


def test_trace_rejects_category_not_supplied_by_adapter() -> None:
    from schemas import CollaborationProfile
    from synthesis_personalization import (
        SynthesisPersonalizationAdapter,
        SynthesisPersonalizationError,
    )

    projection = SynthesisPersonalizationAdapter.project(
        CollaborationProfile()
    )
    blueprint = blueprint_with_adaptations(
        [
            {
                "profile_key": "planning_granularity",
                "architecture_change": "The roadmap uses micro-steps.",
                "reason": "A preference supposedly requested it.",
            }
        ]
    )

    with pytest.raises(
        SynthesisPersonalizationError,
        match="unsupplied",
    ):
        SynthesisPersonalizationAdapter.validate_and_derive_receipts(
            projection,
            blueprint,
        )


def test_trace_rejects_duplicate_adaptation_category() -> None:
    from schemas import CollaborationProfile
    from synthesis_personalization import (
        SynthesisPersonalizationAdapter,
        SynthesisPersonalizationError,
    )

    projection = SynthesisPersonalizationAdapter.project(
        CollaborationProfile(
            active_preferences={
                "planning_granularity": planning_signal(),
            }
        )
    )
    blueprint = blueprint_with_adaptations(
        [
            {
                "profile_key": "planning_granularity",
                "architecture_change": "The roadmap uses micro-steps.",
                "reason": "The preference requests smaller steps.",
            },
            {
                "profile_key": "planning_granularity",
                "architecture_change": "Verification is more explicit.",
                "reason": "The same preference affects verification.",
            },
        ]
    )

    with pytest.raises(
        SynthesisPersonalizationError,
        match="duplicate",
    ):
        SynthesisPersonalizationAdapter.validate_and_derive_receipts(
            projection,
            blueprint,
        )


def test_adapter_excludes_identity_and_unrelated_preferences() -> None:
    from schemas import ActiveMemorySignal, CollaborationProfile
    from synthesis_personalization import SynthesisPersonalizationAdapter

    name_signal = ActiveMemorySignal(
        signal_id="preferred-name-signal-1",
        category="preferred_name",
        value="Avery",
        policy_version="1.0",
        source_event_id="preferred-name-signal-1--approved",
        approved_at=NOW,
    )
    length_signal = ActiveMemorySignal(
        signal_id="response-length-signal-1",
        category="response_length",
        value="concise",
        policy_version="1.0",
        source_event_id="response-length-signal-1--approved",
        approved_at=NOW,
    )
    planning = planning_signal()
    profile = CollaborationProfile(
        identity_context={"preferred_name": name_signal},
        active_preferences={
            "response_length": length_signal,
            "planning_granularity": planning,
        },
    )

    projection = SynthesisPersonalizationAdapter.project(profile)

    assert tuple(projection.model_context) == ("planning_granularity",)
    assert projection.supplied_signals == (planning,)


def test_adapter_does_not_mutate_profile_or_expose_mutable_context() -> None:
    from schemas import CollaborationProfile
    from synthesis_personalization import SynthesisPersonalizationAdapter

    profile = CollaborationProfile(
        memory_revision=7,
        active_preferences={
            "planning_granularity": planning_signal(),
        },
    )
    original = profile.model_dump(mode="json")
    projection = SynthesisPersonalizationAdapter.project(profile)

    context = projection.model_context
    context["planning_granularity"] = {"value": "milestones"}

    assert profile.model_dump(mode="json") == original
    assert projection.model_context["planning_granularity"] == {
        "value": "micro_steps",
        "instruction": (
            "Break complex plans into small sequential actions with "
            "explicit verification."
        ),
    }


def test_absent_trace_emits_no_artifact_adaptation_receipt() -> None:
    from schemas import CollaborationProfile
    from synthesis_personalization import SynthesisPersonalizationAdapter

    projection = SynthesisPersonalizationAdapter.project(
        CollaborationProfile(
            active_preferences={
                "planning_granularity": planning_signal(),
            }
        )
    )

    receipts = SynthesisPersonalizationAdapter.validate_and_derive_receipts(
        projection,
        blueprint_with_adaptations([]),
    )

    assert receipts == ()


def test_trace_rejects_unsupported_profile_key() -> None:
    from schemas import CollaborationProfile
    from synthesis_personalization import (
        SynthesisPersonalizationAdapter,
        SynthesisPersonalizationError,
    )

    projection = SynthesisPersonalizationAdapter.project(
        CollaborationProfile(
            active_preferences={
                "planning_granularity": planning_signal(),
            }
        )
    )
    blueprint = blueprint_with_adaptations(
        [
            {
                "profile_key": "response_length",
                "architecture_change": "The blueprint is shorter.",
                "reason": "A response preference supposedly requested it.",
            }
        ]
    )

    with pytest.raises(
        SynthesisPersonalizationError,
        match="unsupplied",
    ):
        SynthesisPersonalizationAdapter.validate_and_derive_receipts(
            projection,
            blueprint,
        )


def test_trace_validator_rejects_raw_projection_mapping() -> None:
    from synthesis_personalization import (
        SynthesisPersonalizationAdapter,
    )

    with pytest.raises(TypeError, match="SynthesisPersonalizationProjection"):
        SynthesisPersonalizationAdapter.validate_and_derive_receipts(
            {"model_context": {}},
            blueprint_with_adaptations([]),
        )


def test_trace_validator_rejects_raw_blueprint_mapping() -> None:
    from schemas import CollaborationProfile
    from synthesis_personalization import SynthesisPersonalizationAdapter

    projection = SynthesisPersonalizationAdapter.project(
        CollaborationProfile()
    )

    with pytest.raises(TypeError, match="SynthesisBlueprint"):
        SynthesisPersonalizationAdapter.validate_and_derive_receipts(
            projection,
            {"personalization_trace": {"adaptations": []}},
        )


def test_projection_rejects_non_synthesis_memory_signal() -> None:
    from schemas import ActiveMemorySignal
    from synthesis_personalization import (
        SynthesisPersonalizationError,
        SynthesisPersonalizationProjection,
    )

    unrelated_signal = ActiveMemorySignal(
        signal_id="response-length-signal-1",
        category="response_length",
        value="concise",
        policy_version="1.0",
        source_event_id="response-length-signal-1--approved",
        approved_at=NOW,
    )

    with pytest.raises(
        SynthesisPersonalizationError,
        match="projection",
    ):
        SynthesisPersonalizationProjection(
            instructions=(),
            supplied_signals=(unrelated_signal,),
        )


def test_projection_rejects_invalid_planning_value_with_contract_error() -> None:
    from schemas import ActiveMemorySignal
    from synthesis_personalization import (
        SynthesisPersonalizationError,
        SynthesisPersonalizationInstruction,
        SynthesisPersonalizationProjection,
    )

    signal = ActiveMemorySignal.model_construct(
        signal_id="planning-granularity-signal-1",
        category="planning_granularity",
        value="invalid",
        policy_version="1.0",
        source_event_id="planning-granularity-signal-1--approved",
        approved_at=NOW,
    )

    with pytest.raises(
        SynthesisPersonalizationError,
        match="projection",
    ):
        SynthesisPersonalizationProjection(
            instructions=(
                SynthesisPersonalizationInstruction(
                    category="planning_granularity",
                    value="invalid",
                    instruction="An untrusted instruction.",
                ),
            ),
            supplied_signals=(signal,),
        )
