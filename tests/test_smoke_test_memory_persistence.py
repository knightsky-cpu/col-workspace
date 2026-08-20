from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from smoke_test_memory_persistence import exercise_memory_proposal


NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_exercise_memory_proposal_retries_identical_candidate() -> None:
    fake_engine = MagicMock()

    async def return_candidate(user_id, candidate, *, observed_at):
        return candidate

    fake_engine.create_memory_proposal = AsyncMock(
        side_effect=return_candidate
    )

    result = await exercise_memory_proposal(
        fake_engine,
        user_id="memory-m2-smoke-user",
        proposal_id="response_length--smoke-proposal",
        observed_at=NOW,
    )

    assert result.proposal_id == "response_length--smoke-proposal"
    assert fake_engine.create_memory_proposal.await_count == 2
    assert all(
        awaited_call.kwargs["observed_at"] == NOW
        for awaited_call in (
            fake_engine.create_memory_proposal.await_args_list
        )
    )


@pytest.mark.asyncio
async def test_run_memory_persistence_smoke_is_offline_injected() -> None:
    from smoke_test_memory_persistence import run_memory_persistence_smoke

    fake_engine = MagicMock()

    async def return_candidate(user_id, candidate, *, observed_at):
        return candidate

    fake_engine.create_memory_proposal = AsyncMock(
        side_effect=return_candidate
    )

    output = await run_memory_persistence_smoke(
        engine_factory=lambda: fake_engine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: NOW,
    )

    assert output == (
        "trusted-memory-m2 pass "
        "user_id=memory-m2-smoke-fixed-id "
        "category=response_length"
    )
    assert fake_engine.create_memory_proposal.await_count == 2
    fake_engine.close.assert_called_once_with()


def test_main_prints_copy_safe_smoke_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import smoke_test_memory_persistence as smoke_module

    output = (
        "trusted-memory-m2 pass "
        "user_id=memory-m2-smoke-fixed-id "
        "category=response_length"
    )
    run_smoke = AsyncMock(return_value=output)
    monkeypatch.setattr(
        smoke_module,
        "run_memory_persistence_smoke",
        run_smoke,
    )

    smoke_module.main()

    assert capsys.readouterr().out == f"{output}\n"
    run_smoke.assert_awaited_once_with()
