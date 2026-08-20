import json

from schemas import SynthesisBlueprint


MAX_BLUEPRINT_BYTES = 128 * 1024


class BlueprintValidationError(ValueError):
    """Raised when a blueprint violates a local semantic invariant."""


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _has_duplicates(values: list[str]) -> bool:
    normalized = [_normalize(value) for value in values]
    return len(normalized) != len(set(normalized))


def validate_blueprint(
    blueprint: SynthesisBlueprint,
    profile_context: dict[str, object],
) -> None:
    """Validate semantic invariants not expressible in JSON Schema."""
    conceptual_model = blueprint.synthesized_conceptual_model
    duplicate_groups = [
        conceptual_model.in_scope,
        conceptual_model.out_of_scope,
        conceptual_model.assumptions,
        [
            decision.component_name
            for decision in blueprint.architectural_decisions
        ],
        [
            milestone.phase_name
            for milestone in blueprint.step_by_step_execution_roadmap
        ],
        [
            warning.risk_identified
            for warning in blueprint.diagnostic_warnings
        ],
    ]
    duplicate_groups.extend(
        [alternative.option_name for alternative in decision.alternatives]
        for decision in blueprint.architectural_decisions
    )
    duplicate_groups.extend(
        [option.label for option in question.suggested_options]
        for question in blueprint.socratic_clarifying_questions
    )
    duplicate_groups.extend(
        [task.task_description for task in milestone.micro_tasks]
        for milestone in blueprint.step_by_step_execution_roadmap
    )
    duplicate_groups.extend(
        task.verification_steps
        for milestone in blueprint.step_by_step_execution_roadmap
        for task in milestone.micro_tasks
    )
    if any(_has_duplicates(group) for group in duplicate_groups):
        raise BlueprintValidationError(
            "Blueprint contains duplicate values."
        )

    adaptations = blueprint.personalization_trace.adaptations
    normalized_adaptations = [
        (
            _normalize(adaptation.profile_key),
            _normalize(adaptation.architecture_change),
            _normalize(adaptation.reason),
        )
        for adaptation in adaptations
    ]
    if len(normalized_adaptations) != len(set(normalized_adaptations)):
        raise BlueprintValidationError(
            "Blueprint contains duplicate values."
        )
    if any(
        adaptation.profile_key not in profile_context
        for adaptation in adaptations
    ):
        raise BlueprintValidationError(
            "Blueprint personalization is unsupported."
        )

    in_scope = {_normalize(value) for value in conceptual_model.in_scope}
    out_of_scope = {
        _normalize(value) for value in conceptual_model.out_of_scope
    }
    if in_scope & out_of_scope:
        raise BlueprintValidationError(
            "Blueprint scope entries overlap."
        )

    serialized = json.dumps(
        blueprint.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(serialized) > MAX_BLUEPRINT_BYTES:
        raise BlueprintValidationError(
            "Blueprint exceeds the storage limit."
        )
