def test_memory_policy_smoke_runner_is_offline_and_content_safe(
    capsys,
) -> None:
    from smoke_test_memory_policy import run_smoke

    assert run_smoke() == 0
    assert capsys.readouterr().out == (
        "trusted-memory-m1 pass signals=4\n"
    )
