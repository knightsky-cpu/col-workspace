import asyncio
import time

import pytest

from expert_contracts import ExpertCapability


@pytest.mark.asyncio
async def test_registry_token_claims_the_registered_turn_budget() -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationRegistry,
    )

    budget = ExpertDelegationBudget()
    registry = ExpertDelegationRegistry()
    token = registry.register_turn(
        budget=budget,
        deadline=time.monotonic() + 90,
    )

    research_claim = await budget.claim(
        ExpertCapability.RESEARCH,
        depth=1,
    )
    source_claim = await registry.claim(
        token,
        ExpertCapability.SOURCE,
        depth=1,
        minimum_remaining_seconds=45,
    )

    assert research_claim.attempt_number == 1
    assert source_claim.attempt_number == 2


@pytest.mark.asyncio
async def test_registry_preserves_duplicate_and_third_attempt_denials() -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
        ExpertDelegationRegistry,
    )

    registry = ExpertDelegationRegistry()
    token = registry.register_turn(
        budget=ExpertDelegationBudget(),
        deadline=time.monotonic() + 90,
    )

    await registry.claim(
        token,
        ExpertCapability.SOURCE,
        depth=1,
        minimum_remaining_seconds=45,
    )
    with pytest.raises(ExpertDelegationDeniedError) as duplicate:
        await registry.claim(
            token,
            ExpertCapability.SOURCE,
            depth=1,
            minimum_remaining_seconds=45,
        )
    await registry.claim(
        token,
        ExpertCapability.RESEARCH,
        depth=1,
        minimum_remaining_seconds=45,
    )
    with pytest.raises(ExpertDelegationDeniedError) as third:
        await registry.claim(
            token,
            ExpertCapability.COMPUTATION,
            depth=1,
            minimum_remaining_seconds=45,
        )

    assert duplicate.value.reason is (
        ExpertDelegationDenialReason.CAPABILITY_ALREADY_CLAIMED
    )
    assert third.value.reason is (
        ExpertDelegationDenialReason.ATTEMPT_BUDGET_EXHAUSTED
    )


@pytest.mark.asyncio
async def test_registry_denies_claim_when_turn_time_is_insufficient() -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
        ExpertDelegationRegistry,
    )

    now = 100.0
    registry = ExpertDelegationRegistry(clock=lambda: now)
    token = registry.register_turn(
        budget=ExpertDelegationBudget(),
        deadline=144.0,
    )

    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await registry.claim(
            token,
            ExpertCapability.SOURCE,
            depth=1,
            minimum_remaining_seconds=45,
        )

    assert exc_info.value.reason is (
        ExpertDelegationDenialReason.INSUFFICIENT_TIME_REMAINING
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("released", [False, True])
async def test_registry_denies_unknown_or_released_turn_tokens(
    released: bool,
) -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
        ExpertDelegationRegistry,
    )

    registry = ExpertDelegationRegistry()
    token = "unknown-server-token"
    if released:
        token = registry.register_turn(
            budget=ExpertDelegationBudget(),
            deadline=time.monotonic() + 90,
        )
        registry.release_turn(token)

    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await registry.claim(
            token,
            ExpertCapability.SOURCE,
            depth=1,
            minimum_remaining_seconds=45,
        )

    assert exc_info.value.reason is (
        ExpertDelegationDenialReason.TURN_NOT_REGISTERED
    )


@pytest.mark.asyncio
async def test_delegation_budget_allows_two_attempts_and_denies_third() -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
    )

    budget = ExpertDelegationBudget()

    first = await budget.claim(ExpertCapability.RESEARCH, depth=1)
    second = await budget.claim(ExpertCapability.COMPUTATION, depth=1)

    assert first.capability is ExpertCapability.RESEARCH
    assert first.attempt_number == 1
    assert second.capability is ExpertCapability.COMPUTATION
    assert second.attempt_number == 2

    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await budget.claim(ExpertCapability.SOURCE, depth=1)

    assert exc_info.value.reason is (
        ExpertDelegationDenialReason.ATTEMPT_BUDGET_EXHAUSTED
    )
    assert str(exc_info.value) == "Expert delegation denied."


@pytest.mark.asyncio
async def test_capability_can_be_claimed_only_once_without_consuming_slot() -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
    )

    budget = ExpertDelegationBudget()

    first = await budget.claim(ExpertCapability.RESEARCH, depth=1)

    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await budget.claim(ExpertCapability.RESEARCH, depth=1)

    second = await budget.claim(ExpertCapability.SOURCE, depth=1)

    assert first.attempt_number == 1
    assert exc_info.value.reason is (
        ExpertDelegationDenialReason.CAPABILITY_ALREADY_CLAIMED
    )
    assert second.attempt_number == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_depth", [0, 2, -1, True, "1", None])
async def test_invalid_delegation_depth_is_denied_without_consuming_slot(
    invalid_depth: object,
) -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
    )

    budget = ExpertDelegationBudget()

    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await budget.claim(
            ExpertCapability.RESEARCH,
            depth=invalid_depth,  # type: ignore[arg-type]
        )

    first = await budget.claim(ExpertCapability.RESEARCH, depth=1)

    assert exc_info.value.reason is (
        ExpertDelegationDenialReason.INVALID_DEPTH
    )
    assert str(exc_info.value) == "Expert delegation denied."
    assert first.attempt_number == 1


@pytest.mark.asyncio
async def test_concurrent_distinct_claims_preserve_two_attempt_limit() -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationClaim,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
    )

    budget = ExpertDelegationBudget()

    outcomes = await asyncio.gather(
        budget.claim(ExpertCapability.RESEARCH, depth=1),
        budget.claim(ExpertCapability.SOURCE, depth=1),
        budget.claim(ExpertCapability.COMPUTATION, depth=1),
        return_exceptions=True,
    )

    claims = [
        outcome
        for outcome in outcomes
        if isinstance(outcome, ExpertDelegationClaim)
    ]
    denials = [
        outcome
        for outcome in outcomes
        if isinstance(outcome, ExpertDelegationDeniedError)
    ]

    assert sorted(claim.attempt_number for claim in claims) == [1, 2]
    assert len(denials) == 1
    assert denials[0].reason is (
        ExpertDelegationDenialReason.ATTEMPT_BUDGET_EXHAUSTED
    )


@pytest.mark.asyncio
async def test_concurrent_duplicate_claims_allow_exactly_one_attempt() -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationClaim,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
    )

    budget = ExpertDelegationBudget()

    outcomes = await asyncio.gather(
        budget.claim(ExpertCapability.RESEARCH, depth=1),
        budget.claim(ExpertCapability.RESEARCH, depth=1),
        return_exceptions=True,
    )

    claims = [
        outcome
        for outcome in outcomes
        if isinstance(outcome, ExpertDelegationClaim)
    ]
    denials = [
        outcome
        for outcome in outcomes
        if isinstance(outcome, ExpertDelegationDeniedError)
    ]

    assert len(claims) == 1
    assert claims[0].attempt_number == 1
    assert len(denials) == 1
    assert denials[0].reason is (
        ExpertDelegationDenialReason.CAPABILITY_ALREADY_CLAIMED
    )


@pytest.mark.asyncio
async def test_unapproved_capability_is_denied_without_consuming_slot() -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
    )

    budget = ExpertDelegationBudget()

    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await budget.claim("browser", depth=1)  # type: ignore[arg-type]

    first = await budget.claim(ExpertCapability.RESEARCH, depth=1)

    assert exc_info.value.reason is (
        ExpertDelegationDenialReason.INVALID_CAPABILITY
    )
    assert str(exc_info.value) == "Expert delegation denied."
    assert first.attempt_number == 1


@pytest.mark.asyncio
async def test_claimed_attempt_is_not_refunded_after_caller_failure() -> None:
    from expert_delegation import (
        ExpertDelegationBudget,
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
    )

    budget = ExpertDelegationBudget()

    await budget.claim(ExpertCapability.RESEARCH, depth=1)
    try:
        raise TimeoutError
    except TimeoutError:
        pass

    second = await budget.claim(ExpertCapability.SOURCE, depth=1)

    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await budget.claim(ExpertCapability.COMPUTATION, depth=1)

    assert second.attempt_number == 2
    assert exc_info.value.reason is (
        ExpertDelegationDenialReason.ATTEMPT_BUDGET_EXHAUSTED
    )
