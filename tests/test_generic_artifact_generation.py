import asyncio
import json
from types import SimpleNamespace

import pytest


class FakeModels:
    def __init__(
        self,
        response_text: str,
        error: Exception | None = None,
    ) -> None:
        self.response_text = response_text
        self.error = error
        self.arguments: dict[str, object] = {}

    async def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.arguments = kwargs
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.response_text)


def fake_genai_client(
    response_text: str,
    error: Exception | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        aio=SimpleNamespace(models=FakeModels(response_text, error))
    )


def python_artifact_payload() -> dict[str, object]:
    return {
        "artifact_family": "code",
        "format": "python",
        "filename": "password_generator.py",
        "content": "import secrets\nprint(secrets.token_hex(8))\n",
        "summary": "Password Generator",
    }


@pytest.mark.asyncio
async def test_generate_generic_artifact_uses_structured_untrusted_context(
) -> None:
    import generic_artifact_generation as generation
    from schemas import SingleFileArtifact

    client = fake_genai_client(json.dumps(python_artifact_payload()))

    artifact = await generation.generate_generic_artifact(
        client,
        generation.GenericArtifactGenerationRequest(
            artifact_family="code",
            artifact_format="python",
            filename="password_generator.py",
            source_text="Create a password generator using secrets.",
            context_messages=(
                "User prefers Linux and macOS development.",
            ),
        ),
    )

    assert isinstance(artifact, SingleFileArtifact)
    assert artifact.filename == "password_generator.py"
    assert artifact.format == "python"
    arguments = client.aio.models.arguments
    assert arguments["model"] == generation.GENERIC_ARTIFACT_MODEL_NAME
    config = arguments["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None
    assert (
        config.response_json_schema
        == generation.build_generic_artifact_response_schema()
    )
    assert config.temperature == 0.2
    assert config.max_output_tokens == 16_384
    assert config.automatic_function_calling.disable is True
    instruction = " ".join(config.system_instruction.split())
    assert "single-file artifact provider" in instruction
    assert "summary" in instruction
    assert "presentation metadata" in instruction
    assert "500 characters or fewer" in instruction
    contents = arguments["contents"]
    prompt = contents[0].parts[0].text
    assert "[GENERIC_ARTIFACT_REQUEST]" in prompt
    assert "[/GENERIC_ARTIFACT_REQUEST]" in prompt
    assert "[RECENT_CONTEXT_MESSAGES]" in prompt
    assert "[/RECENT_CONTEXT_MESSAGES]" in prompt
    assert "Create a password generator" in prompt
    assert "Linux and macOS" in prompt
    assert "python" in prompt
    assert "password_generator.py" in prompt


@pytest.mark.asyncio
async def test_generate_generic_artifact_accepts_document_summary_metadata(
) -> None:
    import generic_artifact_generation as generation

    long_summary = "A" * 300
    client = fake_genai_client(
        json.dumps(
            {
                "artifact_family": "document",
                "format": "text",
                "filename": "algebraic_rules.txt",
                "content": "Fundamental algebraic rules.\n",
                "summary": long_summary,
            }
        )
    )

    artifact = await generation.generate_generic_artifact(
        client,
        generation.GenericArtifactGenerationRequest(
            artifact_family="document",
            artifact_format="text",
            filename="algebraic_rules.txt",
            source_text="Create a text document containing algebraic rules.",
        ),
    )

    assert artifact.summary == long_summary
    assert artifact.content == "Fundamental algebraic rules.\n"


@pytest.mark.asyncio
async def test_generate_generic_artifact_rejects_mismatched_output() -> None:
    import generic_artifact_generation as generation

    payload = python_artifact_payload()
    payload["format"] = "javascript"
    payload["filename"] = "password_generator.js"
    client = fake_genai_client(json.dumps(payload))

    with pytest.raises(generation.GenericArtifactGenerationError):
        await generation.generate_generic_artifact(
            client,
            generation.GenericArtifactGenerationRequest(
                artifact_family="code",
                artifact_format="python",
                filename="password_generator.py",
                source_text="Create a Python password generator.",
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("response_text", ("", "{", "{}"))
async def test_generate_generic_artifact_rejects_invalid_response(
    response_text: str,
) -> None:
    import generic_artifact_generation as generation

    client = fake_genai_client(response_text)

    with pytest.raises(generation.GenericArtifactGenerationError):
        await generation.generate_generic_artifact(
            client,
            generation.GenericArtifactGenerationRequest(
                artifact_family="document",
                artifact_format="markdown",
                filename="notes.md",
                source_text="Create markdown notes.",
            ),
        )


@pytest.mark.asyncio
async def test_generate_generic_artifact_wraps_provider_error_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import generic_artifact_generation as generation

    provider_error = RuntimeError("provider leaked private-source")
    client = fake_genai_client("", error=provider_error)
    caplog.set_level("ERROR", logger="generic_artifact_generation")

    with pytest.raises(generation.GenericArtifactGenerationError) as caught:
        await generation.generate_generic_artifact(
            client,
            generation.GenericArtifactGenerationRequest(
                artifact_family="code",
                artifact_format="bash",
                filename="setup.sh",
                source_text="private-source",
            ),
        )

    assert caught.value.__cause__ is provider_error
    assert "RuntimeError" in caplog.text
    assert "private-source" not in caplog.text
    assert "provider leaked" not in caplog.text


@pytest.mark.asyncio
async def test_generate_generic_artifact_translates_timeout_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import generic_artifact_generation as generation

    client = fake_genai_client("")

    async def never_returns(**kwargs: object) -> SimpleNamespace:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    client.aio.models.generate_content = never_returns
    monkeypatch.setattr(
        generation,
        "GENERIC_ARTIFACT_TIMEOUT_SECONDS",
        0.01,
        raising=False,
    )

    with pytest.raises(generation.GenericArtifactGenerationTimeoutError):
        await asyncio.wait_for(
            generation.generate_generic_artifact(
                client,
                generation.GenericArtifactGenerationRequest(
                    artifact_family="data",
                    artifact_format="json",
                    filename="settings.json",
                    source_text="Create JSON settings.",
                ),
            ),
            timeout=0.2,
        )
