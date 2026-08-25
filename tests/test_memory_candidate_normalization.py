import pytest


@pytest.mark.parametrize(
    ("category", "user_value", "expected"),
    (
        (
            "response_length",
            "long, detailed, informative answers",
            "detailed",
        ),
        (
            "explanation_structure",
            "give me the answer first and steps after",
            "direct_then_steps",
        ),
        ("explanation_pace", "take explanations slowly", "deliberate"),
        (
            "learning_approach",
            "show me an example before the theory",
            "example_first",
        ),
        (
            "accessibility_support",
            "format it so it works well with a screen reader",
            ["screen_reader_friendly"],
        ),
        (
            "development_environments",
            "favor macOS and Linux development environments",
            ["macos", "linux"],
        ),
        (
            "domain_experience",
            "I am learning software development",
            [{"domain": "software_development", "level": "learning"}],
        ),
    ),
)
def test_versioned_aliases_normalize_to_owned_canonical_candidates(
    category: str,
    user_value: str,
    expected: object,
) -> None:
    from memory_candidate_normalization import normalize_memory_candidate

    assert normalize_memory_candidate("2.0", category, user_value) == expected


def test_canonical_values_pass_through_policy_validation() -> None:
    from memory_candidate_normalization import normalize_memory_candidate

    assert normalize_memory_candidate(
        "2.0", "development_environments", ["linux", "macos"]
    ) == ["macos", "linux"]
    assert normalize_memory_candidate(
        "1.0", "response_length", "concise"
    ) == "concise"


@pytest.mark.parametrize(
    ("category", "user_value"),
    (
        ("development_environments", "favor FreeBSD"),
        ("domain_experience", "I write software"),
        ("accessibility_support", "I have a medical condition"),
        ("response_length", "whatever feels right"),
    ),
)
def test_alias_normalization_does_not_infer_unowned_values(
    category: str,
    user_value: str,
) -> None:
    from memory_candidate_normalization import normalize_memory_candidate

    with pytest.raises(ValueError, match="recognized canonical value"):
        normalize_memory_candidate("2.0", category, user_value)


def test_alias_normalization_is_not_durable_intent_classification() -> None:
    from memory_candidate_normalization import normalize_memory_candidate

    assert normalize_memory_candidate(
        "2.0", "response_length", "detailed answers"
    ) == "detailed"
