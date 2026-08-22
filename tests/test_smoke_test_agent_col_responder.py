def test_run_smoke_verifies_real_responder_boundary_offline() -> None:
    from smoke_test_agent_col_responder import run_smoke

    result = run_smoke()

    assert result == (
        "r3.3a responder-boundary pass tools=memory-only "
        "subagents=0 routes=direct,clarify"
    )


def test_main_prints_content_safe_smoke_summary(capsys) -> None:
    from smoke_test_agent_col_responder import main

    main()

    captured = capsys.readouterr()
    assert captured.out == (
        "r3.3a responder-boundary pass tools=memory-only "
        "subagents=0 routes=direct,clarify\n"
    )
    assert captured.err == ""
