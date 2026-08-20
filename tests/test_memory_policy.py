import pytest


@pytest.mark.parametrize(
    ("category", "value"),
    (
        ("response_length", "concise"),
        ("response_length", "balanced"),
        ("response_length", "detailed"),
        ("explanation_structure", "direct_then_steps"),
        ("explanation_structure", "step_by_step"),
        ("explanation_structure", "concept_then_example"),
        ("example_usage", "none"),
        ("example_usage", "when_helpful"),
        ("example_usage", "always_practical"),
        ("question_style", "ask_before_assuming"),
        ("question_style", "recommend_then_ask"),
        ("question_style", "minimal_follow_up"),
        ("planning_granularity", "milestones"),
        ("planning_granularity", "tasks"),
        ("planning_granularity", "micro_steps"),
        ("progress_check_ins", "only_when_blocked"),
        ("progress_check_ins", "at_milestones"),
        ("progress_check_ins", "frequent"),
        ("tool_use_style", "ask_before_external_tools"),
        ("tool_use_style", "use_when_needed"),
        ("tool_use_style", "minimize_tools"),
        ("formatting_style", "prose"),
        ("formatting_style", "bullets"),
        ("formatting_style", "mixed"),
    ),
)
def test_preference_policy_accepts_only_owned_category_values(
    category: str,
    value: str,
) -> None:
    from memory_policy import PreferencePolicy

    assert PreferencePolicy.validate(category, value) == value


@pytest.mark.parametrize(
    ("category", "value"),
    (
        ("formatting_style", "concise"),
        ("unknown_category", "concise"),
        ("response_length", "arbitrary"),
        ("response_length", ["concise"]),
        ("response_length", 1),
        ("response_length", True),
    ),
)
def test_preference_policy_rejects_invalid_category_value_pairs(
    category: object,
    value: object,
) -> None:
    from memory_policy import PreferencePolicy

    with pytest.raises(ValueError):
        PreferencePolicy.validate(category, value)


def test_identity_policy_normalizes_and_grounds_preferred_name() -> None:
    from memory_policy import IdentityContextPolicy

    value = IdentityContextPolicy.validate(
        "preferred_name",
        "  Jose\u0301   O’Neil  ",
        current_message="My name is José O’Neil.",
        require_grounding=True,
    )

    assert value == "José O’Neil"


def test_identity_policy_canonicalizes_broad_role_order() -> None:
    from memory_policy import IdentityContextPolicy

    value = IdentityContextPolicy.validate(
        "broad_roles",
        ["researcher", "student"],
    )

    assert value == ["student", "researcher"]


@pytest.mark.parametrize(
    "value",
    (
        "",
        "   ",
        "A" * 81,
        ".-'’",
        "Avery1",
        "avery@example.com",
        "https://example.com/Avery",
        "555-123-4567",
        "Avery_Name",
        "Avery\nName",
    ),
)
def test_identity_policy_rejects_invalid_preferred_names(value: str) -> None:
    from memory_policy import IdentityContextPolicy

    with pytest.raises(ValueError):
        IdentityContextPolicy.validate("preferred_name", value)


@pytest.mark.parametrize(
    ("name", "message"),
    (
        ("Avery", "The user did not provide a name."),
        ("Ann", "My preferred name is Anna."),
    ),
)
def test_identity_policy_requires_exact_current_message_grounding(
    name: str,
    message: str,
) -> None:
    from memory_policy import IdentityContextPolicy

    with pytest.raises(ValueError):
        IdentityContextPolicy.validate(
            "preferred_name",
            name,
            current_message=message,
            require_grounding=True,
        )


@pytest.mark.parametrize(
    "value",
    (
        [],
        ["student", "student"],
        ["student", "professional", "educator", "researcher"],
        ["administrator"],
        [["student"]],
        [1],
        [None],
        "student",
    ),
)
def test_identity_policy_rejects_invalid_broad_roles(value: object) -> None:
    from memory_policy import IdentityContextPolicy

    with pytest.raises(ValueError):
        IdentityContextPolicy.validate("broad_roles", value)


@pytest.mark.parametrize(
    ("category", "value", "expected"),
    (
        (
            "response_length",
            "concise",
            "Keep the response compact while preserving information required "
            "to complete the request.",
        ),
        (
            "response_length",
            "balanced",
            "Use moderate detail, covering the answer and its most important "
            "supporting context.",
        ),
        (
            "response_length",
            "detailed",
            "Provide thorough context, explicit steps, and important "
            "limitations without exposing hidden reasoning.",
        ),
        (
            "explanation_structure",
            "direct_then_steps",
            "Lead with the outcome, then give ordered steps when the task "
            "requires them.",
        ),
        (
            "explanation_structure",
            "step_by_step",
            "Explain complex work as ordered, independently checkable steps.",
        ),
        (
            "explanation_structure",
            "concept_then_example",
            "Explain the governing concept before demonstrating it with an "
            "example.",
        ),
        (
            "example_usage",
            "none",
            "Do not add examples unless the current request requires one for "
            "correctness.",
        ),
        (
            "example_usage",
            "when_helpful",
            "Add a concise example when it materially improves understanding.",
        ),
        (
            "example_usage",
            "always_practical",
            "Include one practical example when the task permits it.",
        ),
        (
            "question_style",
            "ask_before_assuming",
            "Ask one concise question before making a consequential "
            "unsupported assumption.",
        ),
        (
            "question_style",
            "recommend_then_ask",
            "Give the safest bounded recommendation, then ask one question "
            "that could materially change it.",
        ),
        (
            "question_style",
            "minimal_follow_up",
            "Ask a follow-up only when missing information prevents safe or "
            "correct progress.",
        ),
        (
            "planning_granularity",
            "milestones",
            "Organize plans around outcomes and major milestones.",
        ),
        (
            "planning_granularity",
            "tasks",
            "Organize plans into independently reviewable tasks with clear "
            "outcomes.",
        ),
        (
            "planning_granularity",
            "micro_steps",
            "Break complex plans into small sequential actions with explicit "
            "verification.",
        ),
        (
            "progress_check_ins",
            "only_when_blocked",
            "Request a check-in only when progress is blocked or authority is "
            "required.",
        ),
        (
            "progress_check_ins",
            "at_milestones",
            "Request confirmation at consequential milestone boundaries.",
        ),
        (
            "progress_check_ins",
            "frequent",
            "Offer brief progress check-ins during longer collaborative work.",
        ),
        (
            "tool_use_style",
            "ask_before_external_tools",
            "Ask before using an external information tool unless the current "
            "request already authorizes it.",
        ),
        (
            "tool_use_style",
            "use_when_needed",
            "Use a tool only when it materially improves correctness, evidence, "
            "or completion.",
        ),
        (
            "tool_use_style",
            "minimize_tools",
            "Prefer the fewest tool calls that can reliably complete the "
            "request.",
        ),
        (
            "formatting_style",
            "prose",
            "Prefer compact prose unless another format is necessary for "
            "clarity.",
        ),
        (
            "formatting_style",
            "bullets",
            "Prefer concise bullets for multiple facts, options, or actions.",
        ),
        (
            "formatting_style",
            "mixed",
            "Use short prose for conclusions and lists for comparisons or "
            "sequential work.",
        ),
    ),
)
def test_preference_policy_returns_exact_owned_instruction(
    category: str,
    value: str,
    expected: str,
) -> None:
    from memory_policy import PreferencePolicy

    assert PreferencePolicy.instruction(category, value) == expected


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    (
        (
            "preferred_name",
            "Avery",
            "Address the user by their approved preferred name when natural; "
            "do not repeat it mechanically or treat it as verified legal "
            "identity.",
        ),
        (
            "broad_roles",
            ["student", "researcher"],
            "Use the approved broad role context only to calibrate examples "
            "and explanations; do not infer expertise, employer, school, "
            "seniority, or credentials.",
        ),
    ),
)
def test_identity_policy_returns_exact_owned_instruction(
    field: str,
    value: object,
    expected: str,
) -> None:
    from memory_policy import IdentityContextPolicy

    assert IdentityContextPolicy.instruction(field, value) == expected


def test_generic_memory_validation_dispatches_by_category() -> None:
    from memory_policy import validate_memory_value

    assert validate_memory_value("response_length", "concise") == "concise"
    assert validate_memory_value("preferred_name", "  Avery  ") == "Avery"
    assert validate_memory_value(
        "broad_roles",
        ["researcher", "student"],
    ) == ["student", "researcher"]

    with pytest.raises(ValueError):
        validate_memory_value("response_length", "student")


def test_memory_signal_sort_key_is_policy_defined() -> None:
    from memory_policy import memory_signal_sort_key

    categories = [
        "formatting_style",
        "example_usage",
        "broad_roles",
        "preferred_name",
        "response_length",
    ]

    assert sorted(categories, key=memory_signal_sort_key) == [
        "preferred_name",
        "broad_roles",
        "response_length",
        "example_usage",
        "formatting_style",
    ]
