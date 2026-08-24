from dataclasses import dataclass, field

import pytest


@dataclass
class FakeGenericArtifactWriter:
    calls: list[dict[str, object]] = field(default_factory=list)

    async def save_single_file_artifact(
        self,
        *,
        project_id: str,
        session_id: str,
        user_id: str,
        model_name: str,
        artifact: dict[str, object],
        display_label: str,
        originating_turn_id: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "project_id": project_id,
                "session_id": session_id,
                "user_id": user_id,
                "model_name": model_name,
                "artifact": artifact,
                "display_label": display_label,
                "originating_turn_id": originating_turn_id,
            }
        )
        return "artifact--abc"


@pytest.mark.asyncio
async def test_create_artifact_validates_persists_and_returns_reference(
) -> None:
    from generic_artifact_creation_service import (
        GENERIC_ARTIFACT_MODEL_NAME,
        GenericArtifactCreationCommand,
        GenericArtifactCreationService,
    )

    writer = FakeGenericArtifactWriter()

    result = await GenericArtifactCreationService(
        artifact_writer=writer
    ).create_artifact(
        GenericArtifactCreationCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            artifact={
                "artifact_family": "code",
                "format": "python",
                "filename": "password_generator.py",
                "content": "print('generated')\n",
                "summary": "Password Generator",
            },
            display_label="Secure Password Generator",
            originating_turn_id="turn-1",
        )
    )

    assert result.reference.artifact_type == "single_file_artifact"
    assert result.reference.project_id == "project-1"
    assert result.reference.artifact_id == "artifact--abc"
    assert result.reference.schema_version == "1.0"
    assert result.reference.display_label == "Secure Password Generator"
    assert result.artifact.filename == "password_generator.py"
    assert writer.calls == [
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "model_name": GENERIC_ARTIFACT_MODEL_NAME,
            "artifact": {
                "artifact_family": "code",
                "format": "python",
                "filename": "password_generator.py",
                "content": "print('generated')\n",
                "summary": "Password Generator",
            },
            "display_label": "Secure Password Generator",
            "originating_turn_id": "turn-1",
        }
    ]


@pytest.mark.asyncio
async def test_create_artifact_uses_summary_as_default_display_label() -> None:
    from generic_artifact_creation_service import (
        GenericArtifactCreationCommand,
        GenericArtifactCreationService,
    )

    writer = FakeGenericArtifactWriter()

    result = await GenericArtifactCreationService(
        artifact_writer=writer
    ).create_artifact(
        GenericArtifactCreationCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            artifact={
                "artifact_family": "document",
                "format": "markdown",
                "filename": "setup.md",
                "content": "# Setup\n",
                "summary": "Setup Guide",
            },
        )
    )

    assert result.reference.display_label == "Setup Guide"
    assert writer.calls[0]["display_label"] == "Setup Guide"


@pytest.mark.asyncio
async def test_create_artifact_uses_filename_when_summary_is_absent() -> None:
    from generic_artifact_creation_service import (
        GenericArtifactCreationCommand,
        GenericArtifactCreationService,
    )

    writer = FakeGenericArtifactWriter()

    result = await GenericArtifactCreationService(
        artifact_writer=writer
    ).create_artifact(
        GenericArtifactCreationCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            artifact={
                "artifact_family": "data",
                "format": "json",
                "filename": "settings.json",
                "content": "{\"enabled\": true}",
            },
        )
    )

    assert result.reference.display_label == "settings.json"
    assert writer.calls[0]["display_label"] == "settings.json"


@pytest.mark.asyncio
async def test_create_artifact_rejects_invalid_artifact_before_persistence(
) -> None:
    from pydantic import ValidationError

    from generic_artifact_creation_service import (
        GenericArtifactCreationCommand,
        GenericArtifactCreationService,
    )

    writer = FakeGenericArtifactWriter()

    with pytest.raises(ValidationError, match="JSON artifact content"):
        await GenericArtifactCreationService(
            artifact_writer=writer
        ).create_artifact(
            GenericArtifactCreationCommand(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                artifact={
                    "artifact_family": "data",
                    "format": "json",
                    "filename": "settings.json",
                    "content": "{not json}",
                },
            )
        )

    assert writer.calls == []
