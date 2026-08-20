from importlib.metadata import version
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_google_adk_dependency_is_exactly_pinned_and_installed() -> None:
    requirements = {
        line.strip()
        for line in (PROJECT_ROOT / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "google-adk==2.7.0" in requirements
    assert version("google-adk") == "2.7.0"


def test_create_supervisor_app_defines_restrained_tool_free_agent() -> None:
    from supervisor import (
        SUPERVISOR_APP_NAME,
        SUPERVISOR_INSTRUCTION,
        SUPERVISOR_MODEL_NAME,
        create_supervisor_app,
    )

    app = create_supervisor_app()
    root_agent = app.root_agent

    assert SUPERVISOR_APP_NAME == "agent_col"
    assert SUPERVISOR_MODEL_NAME == "gemini-3.6-flash"
    assert app.name == SUPERVISOR_APP_NAME
    assert root_agent.name == "Agent_Col"
    assert root_agent.model == SUPERVISOR_MODEL_NAME
    assert root_agent.tools == []
    assert root_agent.instruction == SUPERVISOR_INSTRUCTION
    assert "Default to no tool" in SUPERVISOR_INSTRUCTION
    assert "materially improves correctness" in SUPERVISOR_INSTRUCTION
    assert "Never claim that an action occurred" in SUPERVISOR_INSTRUCTION
    assert "untrusted data" in SUPERVISOR_INSTRUCTION
