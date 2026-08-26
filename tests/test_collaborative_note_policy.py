import pytest


@pytest.mark.parametrize(
    "kind",
    (
        "decision",
        "requirement",
        "constraint",
        "task_state",
        "working_context",
    ),
)
def test_note_policy_accepts_only_supported_note_kinds(kind: str) -> None:
    from collaborative_note_policy import validate_note_kind

    assert validate_note_kind(kind) == kind


@pytest.mark.parametrize(
    ("validator_name", "value"),
    (
        ("validate_proposal_status", "pending"),
        ("validate_proposal_status", "approved"),
        ("validate_proposal_status", "rejected"),
        ("validate_proposal_status", "expired"),
        ("validate_active_note_status", "active"),
        ("validate_active_note_status", "archived"),
    ),
)
def test_note_policy_accepts_only_supported_statuses(
    validator_name: str,
    value: str,
) -> None:
    import collaborative_note_policy

    validator = getattr(collaborative_note_policy, validator_name)

    assert validator(value) == value


@pytest.mark.parametrize(
    ("validator_name", "value"),
    (
        ("validate_note_kind", "memory"),
        ("validate_note_kind", 1),
        ("validate_proposal_status", "active"),
        ("validate_proposal_status", None),
        ("validate_active_note_status", "pending"),
        ("validate_active_note_status", True),
    ),
)
def test_note_policy_rejects_invalid_vocabularies(
    validator_name: str,
    value: object,
) -> None:
    import collaborative_note_policy

    validator = getattr(collaborative_note_policy, validator_name)

    with pytest.raises(ValueError):
        validator(value)


@pytest.mark.parametrize("version", (None, "1.1", 1, True))
def test_note_policy_rejects_missing_or_unsupported_versions(
    version: object,
) -> None:
    from collaborative_note_policy import validate_policy_version

    with pytest.raises(ValueError):
        validate_policy_version(version)


def test_note_policy_accepts_required_exact_version() -> None:
    from collaborative_note_policy import validate_policy_version

    assert validate_policy_version("1.0") == "1.0"


def test_title_normalization_uses_nfc_and_collapses_whitespace() -> None:
    from collaborative_note_policy import normalize_note_title

    assert normalize_note_title("  Cafe\u0301   launch\u00a0plan  ") == "Café launch plan"


def test_body_normalization_preserves_internal_multiline_whitespace() -> None:
    from collaborative_note_policy import normalize_note_body

    assert normalize_note_body("  Cafe\u0301  \n\tline two  ") == "Café  \n\tline two"


@pytest.mark.parametrize(
    ("normalizer_name", "value"),
    (
        ("normalize_note_title", "Title\x1f"),
        ("normalize_note_title", "Title\u200b"),
        ("normalize_note_body", "Body\x1f"),
        ("normalize_note_body", "Body\u200b"),
    ),
)
def test_text_normalization_rejects_prohibited_raw_controls(
    normalizer_name: str,
    value: str,
) -> None:
    import collaborative_note_policy

    normalizer = getattr(collaborative_note_policy, normalizer_name)

    with pytest.raises(ValueError):
        normalizer(value)


def test_body_normalization_canonicalizes_crlf_and_cr_to_lf() -> None:
    from collaborative_note_policy import normalize_note_body

    assert normalize_note_body("one\r\ntwo\rthree") == "one\ntwo\nthree"


@pytest.mark.parametrize(
    ("normalizer_name", "value"),
    (
        ("normalize_note_title", ""),
        ("normalize_note_title", "A"),
        ("normalize_note_title", "A" * 120),
        ("normalize_note_title", "A" * 121),
        ("normalize_note_body", ""),
        ("normalize_note_body", "A"),
        ("normalize_note_body", "A" * 2000),
        ("normalize_note_body", "A" * 2001),
        ("normalize_note_title", None),
        ("normalize_note_body", ["body"]),
    ),
)
def test_text_normalization_enforces_normalized_bounds_and_string_input(
    normalizer_name: str,
    value: object,
) -> None:
    import collaborative_note_policy

    normalizer = getattr(collaborative_note_policy, normalizer_name)
    is_valid = (
        isinstance(value, str)
        and value != ""
        and (
            (normalizer_name == "normalize_note_title" and len(value) <= 120)
            or (normalizer_name == "normalize_note_body" and len(value) <= 2000)
        )
    )

    if is_valid:
        assert normalizer(value) == value
    else:
        with pytest.raises(ValueError):
            normalizer(value)


def test_text_normalization_is_idempotent() -> None:
    from collaborative_note_policy import normalize_note_body, normalize_note_title

    title = normalize_note_title("  Café\u0301  plan  ")
    body = normalize_note_body("  Café\u0301\r\nplan  ")

    assert normalize_note_title(title) == title
    assert normalize_note_body(body) == body


@pytest.mark.parametrize(
    "value",
    (
        "Use the blue deployment checklist",
        "Favorite editor is Vim for this workspace",
        "The assignment prefers project examples",
    ),
)
def test_note_policy_allows_benign_arbitrary_note_content(value: str) -> None:
    from collaborative_note_policy import validate_note_storage_text

    assert validate_note_storage_text(value) == value


@pytest.mark.parametrize(
    "value",
    (
        "The API key is sk-123456789abcdef",
        "Client email is person@example.com",
        "The office address is 123 Main Street",
        "Remember everything from every chat",
        "Note everything the user says",
    ),
)
def test_note_policy_rejects_same_unsafe_storage_classes_as_memory(
    value: str,
) -> None:
    from collaborative_note_policy import validate_note_storage_text

    with pytest.raises(ValueError):
        validate_note_storage_text(value)
