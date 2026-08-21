from dataclasses import dataclass
from typing import Mapping


class VertexAIConfigurationError(RuntimeError):
    """Raised when Agent_Col's Vertex AI settings are incomplete."""


@dataclass(frozen=True, slots=True)
class VertexAISettings:
    """Validated settings shared by Agent_Col model clients."""

    project: str
    location: str

    def client_kwargs(self) -> dict[str, str | bool]:
        """Return explicit Google GenAI SDK Vertex client arguments."""
        return {
            "enterprise": True,
            "project": self.project,
            "location": self.location,
        }


def load_vertex_ai_settings(
    environment: Mapping[str, str],
) -> VertexAISettings:
    """Load Agent_Col's Vertex AI provider settings."""
    project = environment.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project:
        raise VertexAIConfigurationError(
            "GOOGLE_CLOUD_PROJECT is not configured."
        )

    location = environment.get("GOOGLE_CLOUD_LOCATION", "").strip()
    if location != "global":
        raise VertexAIConfigurationError(
            "GOOGLE_CLOUD_LOCATION must be global."
        )

    enterprise_enabled = environment.get(
        "GOOGLE_GENAI_USE_ENTERPRISE",
        "",
    ).strip().lower()
    if enterprise_enabled != "true":
        raise VertexAIConfigurationError(
            "GOOGLE_GENAI_USE_ENTERPRISE must be True."
        )

    return VertexAISettings(
        project=project,
        location=location,
    )
