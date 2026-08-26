import pytest


def test_policy_registry_preserves_v1_and_exposes_v2() -> None:
    from memory_policy import (
        MEMORY_POLICY_REGISTRY,
        validate_memory_value_for_policy,
    )

    assert tuple(MEMORY_POLICY_REGISTRY) == ("1.0", "2.0")
    assert validate_memory_value_for_policy(
        "1.0", "response_length", "concise"
    ) == "concise"
    assert validate_memory_value_for_policy(
        "2.0", "response_length", "concise"
    ) == "concise"

    with pytest.raises(ValueError, match="Unsupported memory policy version"):
        validate_memory_value_for_policy(
            "3.0", "response_length", "concise"
        )


@pytest.mark.parametrize(
    ("category", "value", "expected"),
    (
        ("explanation_pace", "deliberate", "deliberate"),
        ("learning_approach", "example_first", "example_first"),
        (
            "accessibility_support",
            ["keyboard_first", "plain_language"],
            ["plain_language", "keyboard_first"],
        ),
        (
            "development_environments",
            ["windows", "macos", "linux"],
            ["macos", "linux", "windows"],
        ),
        (
            "domain_experience",
            [
                {"domain": "writing", "level": "experienced"},
                {"domain": "software_development", "level": "learning"},
            ],
            [
                {"domain": "software_development", "level": "learning"},
                {"domain": "writing", "level": "experienced"},
            ],
        ),
    ),
)
def test_v2_policy_canonicalizes_new_values(
    category: str,
    value: object,
    expected: object,
) -> None:
    from memory_policy import validate_memory_value_for_policy

    assert validate_memory_value_for_policy("2.0", category, value) == expected


def test_v2_policy_accepts_explicit_user_requested_memory() -> None:
    from memory_policy import (
        memory_instruction_for_policy,
        validate_memory_value_for_policy,
    )

    value = validate_memory_value_for_policy(
        "2.0",
        "user_requested_memory",
        "  I like security focused software projects.  ",
    )

    assert value == "I like security focused software projects."
    assert memory_instruction_for_policy(
        "2.0",
        "user_requested_memory",
        value,
    ) == (
        "Use this approved user-requested memory when it is relevant to the "
        "current conversation, without overriding explicit user instructions, "
        "project requirements, or safety policy: I like security focused "
        "software projects."
    )


@pytest.mark.parametrize(
    "value",
    (
        "my password is synthetic-example-secret",
        "my api key is sk-abc123456789",
        "my social security number is 123-45-6789",
        "my email is wifiknight@example.com",
        "remember everything I say",
    ),
)
def test_v2_policy_rejects_prohibited_user_requested_memory(
    value: str,
) -> None:
    from memory_policy import validate_memory_value_for_policy

    with pytest.raises(ValueError, match="User-requested memory"):
        validate_memory_value_for_policy(
            "2.0",
            "user_requested_memory",
            value,
        )


@pytest.mark.parametrize(
    ("category", "value"),
    (
        ("explanation_pace", "slow"),
        ("learning_approach", "lecture_first"),
        ("accessibility_support", []),
        (
            "accessibility_support",
            ["plain_language", "plain_language"],
        ),
        (
            "development_environments",
            ["macos", "linux", "windows", "bsd"],
        ),
        (
            "domain_experience",
            [
                {"domain": "writing", "level": "learning"},
                {"domain": "writing", "level": "experienced"},
            ],
        ),
        (
            "domain_experience",
            [{"domain": "writing", "level": "expert"}],
        ),
        (
            "domain_experience",
            [{"domain": "writing", "level": "learning", "extra": True}],
        ),
    ),
)
def test_v2_policy_rejects_unowned_or_noncanonical_values(
    category: str,
    value: object,
) -> None:
    from memory_policy import validate_memory_value_for_policy

    with pytest.raises(ValueError):
        validate_memory_value_for_policy("2.0", category, value)


@pytest.mark.parametrize(
    ("category", "value", "expected"),
    (
        (
            "explanation_pace",
            "deliberate",
            "When the current request permits, introduce concepts gradually "
            "and separate consequential stages so the user can follow each "
            "transition.",
        ),
        (
            "explanation_pace",
            "balanced",
            "When the current request permits, use a steady explanatory pace "
            "with enough transition to connect the main ideas.",
        ),
        (
            "explanation_pace",
            "brisk",
            "When the current request permits, move quickly to the result and "
            "minimize transitional explanation without omitting required "
            "evidence or limitations.",
        ),
        (
            "learning_approach",
            "concept_first",
            "For instructional requests, explain the governing concept before "
            "applying it.",
        ),
        (
            "learning_approach",
            "example_first",
            "For instructional requests, begin with one concrete example "
            "before explaining the governing rule.",
        ),
        (
            "learning_approach",
            "practice_first",
            "For instructional requests, begin with one small guided exercise "
            "when practice is appropriate.",
        ),
        (
            "learning_approach",
            "question_guided",
            "For instructional requests, use at most one bounded guiding "
            "question at a time when it helps the user reason without "
            "blocking a requested direct answer.",
        ),
    ),
)
def test_v2_policy_renders_every_scalar_instruction_exactly(
    category: str,
    value: str,
    expected: str,
) -> None:
    from memory_policy import memory_instruction_for_policy

    assert memory_instruction_for_policy("2.0", category, value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (
            "plain_language",
            "Prefer plain language and define necessary technical terms.",
        ),
        (
            "screen_reader_friendly",
            "Use linear headings, descriptive link text, and text "
            "equivalents; do not rely on spatial position alone.",
        ),
        (
            "low_visual_density",
            "Keep sections visually separated and avoid unnecessarily dense "
            "presentation.",
        ),
        (
            "reduced_motion",
            "When producing interface specifications or UI code, avoid "
            "nonessential motion and include reduced-motion behavior.",
        ),
        (
            "keyboard_first",
            "When producing interface specifications or UI code, include "
            "complete keyboard operation.",
        ),
    ),
)
def test_v2_policy_renders_every_accessibility_instruction_exactly(
    value: str,
    expected: str,
) -> None:
    from memory_policy import memory_instruction_for_policy

    assert memory_instruction_for_policy(
        "2.0", "accessibility_support", [value]
    ) == expected


@pytest.mark.parametrize(
    ("values", "expected_list"),
    (
        (["macos"], "macOS"),
        (["linux", "macos"], "macOS and Linux"),
        (["windows", "linux", "macos"], "macOS, Linux, and Windows"),
    ),
)
def test_v2_policy_renders_environment_list_cardinality_exactly(
    values: list[str],
    expected_list: str,
) -> None:
    from memory_policy import memory_instruction_for_policy

    assert memory_instruction_for_policy(
        "2.0", "development_environments", values
    ) == (
        "When platform-specific commands or paths are needed and the current "
        "task does not specify another target, prefer guidance compatible "
        f"with {expected_list}."
    )


@pytest.mark.parametrize(
    ("domain", "domain_label"),
    (
        ("software_development", "Software Development"),
        ("data_science", "Data Science"),
        ("cybersecurity", "Cybersecurity"),
        ("research", "Research"),
        ("writing", "Writing"),
        ("education", "Education"),
        ("project_management", "Project Management"),
        ("design", "Design"),
        ("mathematics", "Mathematics"),
        ("science", "Science"),
        ("business", "Business"),
        ("creative_work", "Creative Work"),
    ),
)
def test_v2_policy_renders_every_domain_label_exactly(
    domain: str,
    domain_label: str,
) -> None:
    from memory_policy import memory_instruction_for_policy

    assert memory_instruction_for_policy(
        "2.0",
        "domain_experience",
        [{"domain": domain, "level": "learning"}],
    ) == (
        f"For {domain_label} material, calibrate vocabulary and examples to "
        "the user's explicitly self-reported Learning experience; do not "
        "treat it as verified expertise."
    )


@pytest.mark.parametrize(
    ("level", "level_label"),
    (
        ("exploring", "Exploring"),
        ("learning", "Learning"),
        ("practicing", "Practicing"),
        ("experienced", "Experienced"),
    ),
)
def test_v2_policy_renders_every_domain_level_exactly(
    level: str,
    level_label: str,
) -> None:
    from memory_policy import memory_instruction_for_policy

    assert memory_instruction_for_policy(
        "2.0",
        "domain_experience",
        [{"domain": "software_development", "level": level}],
    ) == (
        "For Software Development material, calibrate vocabulary and examples "
        f"to the user's explicitly self-reported {level_label} experience; "
        "do not treat it as verified expertise."
    )


def test_v2_policy_renders_structured_values_in_canonical_order() -> None:
    from memory_policy import memory_instruction_for_policy

    assert memory_instruction_for_policy(
        "2.0",
        "accessibility_support",
        ["keyboard_first", "plain_language"],
    ) == (
        "Prefer plain language and define necessary technical terms. "
        "When producing interface specifications or UI code, include "
        "complete keyboard operation."
    )
    assert memory_instruction_for_policy(
        "2.0",
        "domain_experience",
        [
            {"domain": "writing", "level": "experienced"},
            {"domain": "software_development", "level": "learning"},
        ],
    ) == (
        "For Software Development material, calibrate vocabulary and examples "
        "to the user's explicitly self-reported Learning experience; do not "
        "treat it as verified expertise. For Writing material, calibrate "
        "vocabulary and examples to the user's explicitly self-reported "
        "Experienced experience; do not treat it as verified expertise."
    )


def test_v2_registry_has_the_approved_serialization_order() -> None:
    from memory_policy import memory_category_order_for_policy

    assert memory_category_order_for_policy("2.0") == (
        "preferred_name",
        "broad_roles",
        "domain_experience",
        "response_length",
        "explanation_structure",
        "explanation_pace",
        "example_usage",
        "learning_approach",
        "question_style",
        "planning_granularity",
        "progress_check_ins",
        "tool_use_style",
        "formatting_style",
        "accessibility_support",
        "development_environments",
        "user_requested_memory",
    )
