import pytest


@pytest.mark.asyncio
async def test_run_smoke_verifies_deterministic_executor_offline() -> None:
    from smoke_test_agent_col_expert_executor import run_smoke

    result = await run_smoke()

    assert result == (
        "r3.3b deterministic-expert-executor pass routes=4 "
        "max_experts=1 research_cleanup=true"
    )


def test_main_prints_content_safe_executor_summary(capsys) -> None:
    from smoke_test_agent_col_expert_executor import main

    main()

    captured = capsys.readouterr()
    assert captured.out == (
        "r3.3b deterministic-expert-executor pass routes=4 "
        "max_experts=1 research_cleanup=true\n"
    )
    assert captured.err == ""
