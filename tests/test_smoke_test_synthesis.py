from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_main_prints_blueprint_using_loaded_environment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import smoke_test_synthesis

    events: list[str] = []
    client = MagicMock()
    client.aio.aclose = AsyncMock()
    client.close = MagicMock()
    blueprint = SimpleNamespace(
        model_dump_json=MagicMock(return_value='{"status": "valid"}')
    )
    generate_blueprint = AsyncMock(return_value=blueprint)

    def load_environment() -> None:
        events.append("environment-loaded")

    def create_client() -> MagicMock:
        assert events == ["environment-loaded"]
        return client

    monkeypatch.setattr(smoke_test_synthesis, "load_dotenv", load_environment)
    monkeypatch.setattr(
        smoke_test_synthesis.genai,
        "Client",
        create_client,
    )
    monkeypatch.setattr(
        smoke_test_synthesis,
        "generate_blueprint",
        generate_blueprint,
    )

    await smoke_test_synthesis.main()

    assert capsys.readouterr().out == '{"status": "valid"}\n'
    generate_blueprint.assert_awaited_once()
    arguments = generate_blueprint.await_args.args
    assert arguments[0] is client
    assert set(arguments[1]) == {
        "experience_level",
        "preferred_languages",
        "preferred_frameworks",
        "learning_style",
        "response_detail",
        "accessibility_preferences",
    }
    assert arguments[2] == []
    assert "command-line study planner" in arguments[3]
    blueprint.model_dump_json.assert_called_once_with(indent=2)


@pytest.mark.asyncio
async def test_main_closes_client_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import smoke_test_synthesis

    client = MagicMock()
    client.aio.aclose = AsyncMock()
    client.close = MagicMock()
    blueprint = SimpleNamespace(
        model_dump_json=MagicMock(return_value="{}")
    )
    monkeypatch.setattr(smoke_test_synthesis, "load_dotenv", MagicMock())
    monkeypatch.setattr(
        smoke_test_synthesis.genai,
        "Client",
        MagicMock(return_value=client),
    )
    monkeypatch.setattr(
        smoke_test_synthesis,
        "generate_blueprint",
        AsyncMock(return_value=blueprint),
    )

    await smoke_test_synthesis.main()

    client.aio.aclose.assert_awaited_once_with()
    client.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_main_closes_client_when_generation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import smoke_test_synthesis

    generation_error = RuntimeError("generation failed")
    client = MagicMock()
    client.aio.aclose = AsyncMock()
    client.close = MagicMock()
    monkeypatch.setattr(smoke_test_synthesis, "load_dotenv", MagicMock())
    monkeypatch.setattr(
        smoke_test_synthesis.genai,
        "Client",
        MagicMock(return_value=client),
    )
    monkeypatch.setattr(
        smoke_test_synthesis,
        "generate_blueprint",
        AsyncMock(side_effect=generation_error),
    )

    with pytest.raises(RuntimeError) as caught:
        await smoke_test_synthesis.main()

    assert caught.value is generation_error
    client.aio.aclose.assert_awaited_once_with()
    client.close.assert_called_once_with()
