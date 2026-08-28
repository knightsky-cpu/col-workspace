from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_defines_cloud_run_uvicorn_startup_contract() -> None:
    dockerfile = ROOT / "Dockerfile"

    assert dockerfile.exists()
    content = dockerfile.read_text(encoding="utf-8")

    assert "FROM python:3.14-slim" in content
    assert "pip install --no-cache-dir -r requirements.txt" in content
    assert "USER appuser" in content
    assert "COPY . ." in content
    assert (
        'CMD ["sh", "-c", '
        '"exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]'
    ) in content
    assert "--reload" not in content
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in content


def test_dockerignore_excludes_credentials_and_workspace_debris() -> None:
    dockerignore = ROOT / ".dockerignore"

    assert dockerignore.exists()
    ignored_entries = {
        line.strip()
        for line in dockerignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    required_entries = {
        ".env",
        ".git",
        ".agents",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "scrnshot-evidence",
        "*.pyc",
        "*.json",
        "!.dockerignore",
        "!firestore.indexes.json",
    }

    assert required_entries <= ignored_entries
