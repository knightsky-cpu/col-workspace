from pathlib import Path
import subprocess
import sys


def test_turn_service_smoke_runner_proves_offline_orchestration() -> None:
    repository_root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(
        [sys.executable, "smoke_test_agent_col_turn_service.py"],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == (
        "r3.3c turn-orchestration-service pass routes=2 max_experts=1 "
        "reserve=true routing_failure_contained=true\n"
    )
    assert completed.stderr == ""
