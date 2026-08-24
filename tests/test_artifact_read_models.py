from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


NOW = datetime(2026, 8, 23, 14, 0, tzinfo=UTC)


def artifact_metadata_payload() -> dict[str, object]:
    return {
        "reference": {
            "artifact_type": "synthesis_blueprint",
            "project_id": "project-1",
            "artifact_id": "blueprint-1",
            "schema_version": "2.0",
            "display_label": "Study Partner",
        },
        "created_at": NOW,
        "originating_session_id": "session-1",
        "originating_turn_id": None,
        "parent_artifact_id": None,
        "feedback_counts": {
            "accepted": 0,
            "rejected": 1,
            "edited": 2,
        },
        "adaptation_categories": ["planning_granularity"],
    }


def test_blueprint_artifact_list_models_expose_bounded_public_metadata() -> None:
    from schemas import (
        ARTIFACT_CONTRACT_VERSION,
        BlueprintArtifactListResponse,
    )

    response = BlueprintArtifactListResponse.model_validate(
        {
            "artifact_contract_version": "1.0",
            "artifacts": [artifact_metadata_payload()],
            "next_before": "blueprint-1",
        }
    )

    assert ARTIFACT_CONTRACT_VERSION == "1.0"
    assert response.artifacts[0].reference.display_label == "Study Partner"
    assert response.artifacts[0].feedback_counts.edited == 2
    assert response.next_before == "blueprint-1"


def test_blueprint_artifact_metadata_rejects_invalid_counts_and_categories() -> None:
    from schemas import BlueprintArtifactMetadata

    invalid_count = artifact_metadata_payload()
    invalid_count["feedback_counts"] = {
        "accepted": -1,
        "rejected": 0,
        "edited": 0,
    }
    with pytest.raises(ValidationError):
        BlueprintArtifactMetadata.model_validate(invalid_count)

    invalid_category = artifact_metadata_payload()
    invalid_category["adaptation_categories"] = ["private_inference"]
    with pytest.raises(ValidationError):
        BlueprintArtifactMetadata.model_validate(invalid_category)


def test_artifact_feedback_target_accepts_only_server_contract_kinds() -> None:
    from schemas import ArtifactFeedbackTarget

    target = ArtifactFeedbackTarget(
        target_id="target--0123456789abcdef",
        target_kind="architectural_decision",
        display_label="Persistence",
    )

    assert target.target_kind == "architectural_decision"

    with pytest.raises(ValidationError):
        ArtifactFeedbackTarget.model_validate(
            {
                "target_id": "$.architectural_decisions[0]",
                "target_kind": "json_path",
                "display_label": "Unsafe target",
            }
        )


def test_single_file_artifact_models_accept_common_code_document_and_data_formats(
) -> None:
    from schemas import (
        SingleFileArtifact,
        SingleFileArtifactDetailResponse,
        SingleFileArtifactListResponse,
        SingleFileArtifactMetadata,
    )

    code_artifact = SingleFileArtifact.model_validate(
        {
            "artifact_family": "code",
            "format": "python",
            "filename": "password_generator.py",
            "content": "import secrets\nprint(secrets.token_hex(8))\n",
            "summary": "Secure password generator script.",
        }
    )
    document_artifact = SingleFileArtifact.model_validate(
        {
            "artifact_family": "document",
            "format": "markdown",
            "filename": "setup-guide.md",
            "content": "# Setup\nRun the local server.\n",
        }
    )
    data_artifact = SingleFileArtifact.model_validate(
        {
            "artifact_family": "data",
            "format": "json",
            "filename": "timer-config.json",
            "content": '{"work_minutes":25,"break_minutes":5}',
        }
    )

    metadata = SingleFileArtifactMetadata.model_validate(
        {
            "reference": {
                "artifact_type": "single_file_artifact",
                "project_id": "project-1",
                "artifact_id": "artifact--abc",
                "schema_version": "1.0",
                "display_label": "Password Generator",
            },
            "created_at": NOW,
            "originating_session_id": "session-1",
            "originating_turn_id": "turn-1",
            "filename": "password_generator.py",
            "artifact_family": "code",
            "format": "python",
            "byte_size": 42,
        }
    )
    listing = SingleFileArtifactListResponse(
        artifacts=[metadata],
        next_before="artifact--abc",
    )
    detail = SingleFileArtifactDetailResponse(
        metadata=metadata,
        artifact=code_artifact,
    )

    assert code_artifact.format == "python"
    assert document_artifact.format == "markdown"
    assert data_artifact.format == "json"
    assert listing.artifacts[0].filename == "password_generator.py"
    assert detail.artifact.content.startswith("import secrets")


def test_single_file_artifact_models_reject_mismatched_family_and_format(
) -> None:
    from schemas import SingleFileArtifact

    with pytest.raises(ValidationError):
        SingleFileArtifact.model_validate(
            {
                "artifact_family": "code",
                "format": "pdf",
                "filename": "password_generator.py",
                "content": "print('not a pdf')",
            }
        )

    with pytest.raises(ValidationError):
        SingleFileArtifact.model_validate(
            {
                "artifact_family": "document",
                "format": "python",
                "filename": "notes.py",
                "content": "print('wrong family')",
            }
        )

    with pytest.raises(ValidationError):
        SingleFileArtifact.model_validate(
            {
                "artifact_family": "data",
                "format": "json",
                "filename": "bad.json",
                "content": "{not json}",
            }
        )
