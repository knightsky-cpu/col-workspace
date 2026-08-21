import pytest


def test_vertex_settings_load_explicit_global_vertex_configuration() -> None:
    from vertex_config import load_vertex_ai_settings

    settings = load_vertex_ai_settings(
        {
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        }
    )

    assert settings.project == "project-1"
    assert settings.location == "global"
    assert settings.client_kwargs() == {
        "enterprise": True,
        "project": "project-1",
        "location": "global",
    }


@pytest.mark.parametrize(
    "environment",
    (
        {
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        },
        {
            "GOOGLE_CLOUD_PROJECT": "   ",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        },
        {
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "us-central1",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        },
        {
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "global",
        },
        {
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_ENTERPRISE": "false",
        },
        {
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_VERTEXAI": "True",
        },
    ),
)
def test_vertex_settings_reject_incomplete_or_non_vertex_configuration(
    environment: dict[str, str],
) -> None:
    from vertex_config import (
        VertexAIConfigurationError,
        load_vertex_ai_settings,
    )

    with pytest.raises(VertexAIConfigurationError):
        load_vertex_ai_settings(environment)
