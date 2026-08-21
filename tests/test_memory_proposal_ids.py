import pytest


def test_derive_proposal_origin_ids_is_stable_and_domain_separated() -> None:
    from memory_proposals import derive_proposal_origin_ids

    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        "message-1",
        "response_length",
    )

    assert ids.origin_id == "e82366f7699ee2e39bff6a68154e09b7"
    assert ids.proposal_id == (
        "response_length--e82366f7699ee2e39bff6a68154e09b7"
    )
    other_session = derive_proposal_origin_ids(
        "user-1",
        "session-2",
        "message-1",
        "response_length",
    )
    assert other_session.origin_id != ids.origin_id


def test_derive_proposal_origin_ids_binds_category_without_rehashing() -> None:
    from memory_proposals import derive_proposal_origin_ids

    concise = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        "message-1",
        "response_length",
    )
    formatting = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        "message-1",
        "formatting_style",
    )

    assert formatting.origin_id == concise.origin_id
    assert formatting.proposal_id == (
        "formatting_style--e82366f7699ee2e39bff6a68154e09b7"
    )


@pytest.mark.parametrize(
    ("signal_id", "expected_origin_id"),
    (
        (
            "response_length--e82366f7699ee2e39bff6a68154e09b7",
            "e82366f7699ee2e39bff6a68154e09b7",
        ),
        ("response_length--proposal-1", None),
        ("response_length--E82366F7699EE2E39BFF6A68154E09B7", None),
    ),
)
def test_proposal_origin_id_from_signal_id_recognizes_v1_ids(
    signal_id: str,
    expected_origin_id: str | None,
) -> None:
    from memory_proposals import proposal_origin_id_from_signal_id

    assert proposal_origin_id_from_signal_id(
        "response_length",
        signal_id,
    ) == expected_origin_id


@pytest.mark.parametrize(
    ("user_id", "session_id", "message_id", "category"),
    (
        ("", "session-1", "message-1", "response_length"),
        ("user/1", "session-1", "message-1", "response_length"),
        ("user-1", "", "message-1", "response_length"),
        ("user-1", "session-1", "message/1", "response_length"),
        ("user-1", "session-1", "message-1", "unknown"),
    ),
)
def test_derive_proposal_origin_ids_rejects_invalid_inputs(
    user_id: str,
    session_id: str,
    message_id: str,
    category: str,
) -> None:
    from memory_proposals import derive_proposal_origin_ids

    with pytest.raises(ValueError):
        derive_proposal_origin_ids(
            user_id,
            session_id,
            message_id,
            category,
        )


@pytest.mark.parametrize(
    ("turn_id", "owner_token"),
    (
        ("not-a-digest", "owner-1"),
        ("a" * 64, ""),
        ("a" * 64, "owner token"),
    ),
)
def test_proposal_turn_lease_rejects_invalid_metadata(
    turn_id: str,
    owner_token: str,
) -> None:
    from memory_proposals import ProposalTurnLease

    with pytest.raises(ValueError):
        ProposalTurnLease(turn_id=turn_id, owner_token=owner_token)
