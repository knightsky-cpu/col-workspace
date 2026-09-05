#!/usr/bin/env python3
"""Evidence-only orchestrator for abuse retest TEST 10/11 recovery.

Does not modify application source. Writes evidence under this directory.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EV = Path("/Users/wifiknight/col-workspace/docs/abuse-testing-retest-evidence")
USER = "abuse-retest-20260905"
PROJECT = "agent-col"
SESSION = "session--3f7d5db0-da58-4003-a7d4-94a41ab1c823"
BASE = "http://127.0.0.1:8000"
JOBS_URL = f"{BASE}/api/users/{USER}/projects/{PROJECT}/agent/jobs?limit=50"
CHAT_URL = f"{BASE}/api/chat/stream"
WORKDIR = "/Users/wifiknight/col-workspace"
UVICORN_CMD = [
    f"{WORKDIR}/venv/bin/uvicorn",
    "main:app",
    "--reload",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(name: str, payload: object) -> None:
    (EV / name).write_text(json.dumps(payload, indent=2, default=str) + "\n")


def get_jobs(timeout: float = 5.0) -> list[dict]:
    with urllib.request.urlopen(JOBS_URL, timeout=timeout) as resp:
        return json.load(resp)["jobs"]


def health_ok(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{BASE}/", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def find_uvicorn_pids() -> list[int]:
    out = subprocess.check_output(["ps", "ax", "-o", "pid=,command="], text=True)
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if "uvicorn main:app" not in line:
            continue
        if "t10-t11-recovery-orchestrator" in line:
            continue
        pid_s, _, _cmd = line.partition(" ")
        try:
            pids.append(int(pid_s))
        except ValueError:
            continue
    return sorted(set(pids))


def stop_backend(reason: str) -> dict:
    pids = find_uvicorn_pids()
    info = {"ts": now(), "reason": reason, "pids_before": pids, "signals": []}
    for pid in pids:
        try:
            os.kill(pid, signal.SIGINT)
            info["signals"].append({"pid": pid, "signal": "SIGINT", "ok": True})
        except ProcessLookupError:
            info["signals"].append({"pid": pid, "signal": "SIGINT", "ok": False, "err": "gone"})
        except PermissionError as exc:
            info["signals"].append({"pid": pid, "signal": "SIGINT", "ok": False, "err": str(exc)})
    # Wait for exit; escalate to SIGTERM if needed
    deadline = time.time() + 8
    while time.time() < deadline:
        remaining = find_uvicorn_pids()
        if not remaining:
            break
        time.sleep(0.2)
    remaining = find_uvicorn_pids()
    if remaining:
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGTERM)
                info["signals"].append({"pid": pid, "signal": "SIGTERM", "ok": True})
            except Exception as exc:
                info["signals"].append({"pid": pid, "signal": "SIGTERM", "ok": False, "err": str(exc)})
        time.sleep(1.5)
    info["pids_after"] = find_uvicorn_pids()
    info["health_after"] = health_ok()
    write_json("t10-t11-stop-backend.json", info)
    return info


def start_backend() -> dict:
    env = os.environ.copy()
    env["AGENT_COL_AUTH_MODE"] = "local_dev"
    log_path = EV / "t10-t11-restart-uvicorn.log"
    log_f = open(log_path, "ab", buffering=0)
    proc = subprocess.Popen(
        UVICORN_CMD,
        cwd=WORKDIR,
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    info = {
        "ts": now(),
        "pid": proc.pid,
        "log": str(log_path),
        "cmd": UVICORN_CMD,
        "ready": False,
        "wait_s": None,
    }
    t0 = time.time()
    while time.time() - t0 < 45:
        if health_ok():
            info["ready"] = True
            info["wait_s"] = round(time.time() - t0, 2)
            break
        time.sleep(0.3)
    info["pids"] = find_uvicorn_pids()
    write_json("t10-t11-start-backend.json", info)
    return info


def start_chat_artifact() -> subprocess.Popen:
    body = json.dumps(
        {
            "user_id": USER,
            "project_id": PROJECT,
            "session_id": SESSION,
            "message": (
                "Create an Artifact titled 'Retest Recovery Artifact T11' with exactly "
                "two short markdown bullets about restart recovery. Queue it for "
                "background processing immediately; do not wait for completion in chat."
            ),
        }
    ).encode()
    # Use curl so we can background and later ignore abort
    return subprocess.Popen(
        [
            "curl",
            "-sS",
            "-N",
            "-X",
            "POST",
            CHAT_URL,
            "-H",
            "Content-Type: application/json",
            "-H",
            "Idempotency-Key: retest-t11-recovery-20260905-1",
            "--data-binary",
            "@-",
            "-o",
            str(EV / "t10-t11-chat-stream.out"),
            "-w",
            "%{http_code}",
        ],
        stdin=subprocess.PIPE,
        stdout=open(EV / "t10-t11-chat-http-code.txt", "w"),
        stderr=open(EV / "t10-t11-chat-curl.err", "w"),
    )


def main() -> int:
    timeline: list[dict] = []
    poll_samples: list[dict] = []

    def mark(event: str, **extra):
        row = {"ts": now(), "event": event, **extra}
        timeline.append(row)
        print(json.dumps(row), flush=True)

    if not health_ok():
        mark("abort", reason="backend_not_healthy")
        write_json("t10-t11-timeline.json", timeline)
        return 2

    baseline_jobs = get_jobs()
    baseline_refs = {j["job_ref"] for j in baseline_jobs}
    mark("baseline", count=len(baseline_jobs), refs=sorted(baseline_refs))

    chat = start_chat_artifact()
    # Feed body
    assert chat.stdin is not None
    chat.stdin.write(
        json.dumps(
            {
                "user_id": USER,
                "project_id": PROJECT,
                "session_id": SESSION,
                "message": (
                    "Create an Artifact titled 'Retest Recovery Artifact T11' with exactly "
                    "two short markdown bullets about restart recovery. Queue it for "
                    "background processing immediately; do not wait for completion in chat."
                ),
            }
        ).encode()
    )
    chat.stdin.close()
    mark("chat_started", pid=chat.pid)

    kill_job = None
    kill_status = None
    t0 = time.time()
    while time.time() - t0 < 120:
        try:
            jobs = get_jobs(timeout=2.0)
        except Exception as exc:
            poll_samples.append({"ts": now(), "error": str(exc)})
            time.sleep(0.05)
            continue
        new_jobs = [j for j in jobs if j["job_ref"] not in baseline_refs]
        arts = [j for j in new_jobs if j.get("action_kind") == "create_artifact"]
        sample = {
            "ts": now(),
            "elapsed": round(time.time() - t0, 3),
            "count": len(jobs),
            "new": [
                {
                    "job_ref": j["job_ref"],
                    "status": j["status"],
                    "action_kind": j.get("action_kind"),
                    "attempt_count": j.get("attempt_count"),
                    "lease_expires_at": j.get("lease_expires_at"),
                    "display_label": j.get("display_label"),
                }
                for j in new_jobs
            ],
        }
        poll_samples.append(sample)
        # Prefer queued for TEST 10; else running for TEST 11
        target = None
        for j in arts:
            if j["status"] == "queued":
                target = j
                break
        if target is None:
            for j in arts:
                if j["status"] == "running":
                    target = j
                    break
        if target is not None:
            kill_job = target
            kill_status = target["status"]
            mark(
                "nonterminal_seen",
                job_ref=target["job_ref"],
                status=kill_status,
                lease_expires_at=target.get("lease_expires_at"),
                attempt_count=target.get("attempt_count"),
            )
            break
        # Also stop if new artifact already terminal (missed window)
        if any(j["status"] in ("completed", "failed", "cancelled") for j in arts):
            mark(
                "missed_nonterminal_window",
                arts=[
                    {
                        "job_ref": j["job_ref"],
                        "status": j["status"],
                        "lease_expires_at": j.get("lease_expires_at"),
                    }
                    for j in arts
                ],
            )
            break
        time.sleep(0.05)

    write_json("t10-t11-prekill-poll.jsonl", poll_samples)

    if kill_job is None:
        mark("result", test10="NOT_EXECUTED", test11="NOT_EXECUTED", reason="no_nonterminal_caught")
        try:
            chat.kill()
        except Exception:
            pass
        write_json("t10-t11-timeline.json", timeline)
        return 1

    stop_info = stop_backend(reason=f"caught_{kill_status}_{kill_job['job_ref']}")
    mark("backend_stopped", **{k: stop_info[k] for k in ("pids_after", "health_after")})
    try:
        chat.kill()
    except Exception:
        pass

    # Brief pause then restart (minimize downtime; lease wait happens while up for TEST 11)
    time.sleep(1.0)
    start_info = start_backend()
    mark("backend_restarted", ready=start_info.get("ready"), wait_s=start_info.get("wait_s"))
    if not start_info.get("ready"):
        mark("result", test10="NOT_EXECUTED", test11="NOT_EXECUTED", reason="restart_failed")
        write_json("t10-t11-timeline.json", timeline)
        return 3

    # Observe post-restart state of the same job
    post = []
    target_ref = kill_job["job_ref"]
    recovered_terminal = None
    t_restart = time.time()

    if kill_status == "queued":
        # TEST 10: startup drain should discover and execute
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                jobs = get_jobs()
            except Exception as exc:
                post.append({"ts": now(), "error": str(exc)})
                time.sleep(0.5)
                continue
            match = next((j for j in jobs if j["job_ref"] == target_ref), None)
            row = {
                "ts": now(),
                "elapsed": round(time.time() - t_restart, 2),
                "job": match,
            }
            post.append(row)
            if match and match["status"] in ("completed", "failed", "cancelled"):
                recovered_terminal = match
                mark(
                    "test10_terminal",
                    status=match["status"],
                    attempt_count=match.get("attempt_count"),
                )
                break
            time.sleep(0.5)
        write_json("t10-post-restart-poll.json", post)
        if recovered_terminal and recovered_terminal["status"] == "completed":
            # single execution: attempt_count should remain 1 for recovery (same job)
            mark(
                "result",
                test10="PASS" if recovered_terminal.get("attempt_count") == 1 else "FAIL",
                test11="NOT_EXECUTED",
                job_ref=target_ref,
                note="killed_while_queued_then_drained",
            )
        elif recovered_terminal:
            mark(
                "result",
                test10="FAIL",
                test11="NOT_EXECUTED",
                job_ref=target_ref,
                terminal=recovered_terminal.get("status"),
            )
        else:
            mark(
                "result",
                test10="FAIL",
                test11="NOT_EXECUTED",
                job_ref=target_ref,
                reason="no_terminal_after_restart",
            )
    else:
        # TEST 11: job should remain running until real lease expiry, then recover once
        mark("test11_wait_for_lease", lease_expires_at=kill_job.get("lease_expires_at"))
        # Refresh lease from API
        try:
            jobs = get_jobs()
            match = next((j for j in jobs if j["job_ref"] == target_ref), None)
            mark("post_restart_job_state", job=match)
            lease_exp = None
            if match:
                lease_exp = match.get("lease_expires_at")
            write_json(
                "t11-post-restart-initial.json",
                {"ts": now(), "job": match, "kill_status": kill_status},
            )
        except Exception as exc:
            mark("post_restart_job_error", error=str(exc))
            lease_exp = kill_job.get("lease_expires_at")

        # Wait until lease expiry + drain interval buffer (60s + 30s)
        wait_until = None
        if isinstance(lease_exp, str):
            try:
                wait_until = datetime.fromisoformat(lease_exp.replace("Z", "+00:00")).timestamp() + 75
            except Exception:
                wait_until = None
        if wait_until is None:
            wait_until = time.time() + 195  # 120 lease + 75 buffer

        while time.time() < wait_until + 30:
            try:
                jobs = get_jobs()
            except Exception as exc:
                post.append({"ts": now(), "error": str(exc)})
                time.sleep(2)
                continue
            match = next((j for j in jobs if j["job_ref"] == target_ref), None)
            row = {
                "ts": now(),
                "elapsed": round(time.time() - t_restart, 2),
                "job": {
                    "job_ref": match.get("job_ref") if match else None,
                    "status": match.get("status") if match else None,
                    "attempt_count": match.get("attempt_count") if match else None,
                    "lease_expires_at": match.get("lease_expires_at") if match else None,
                    "updated_at": match.get("updated_at") if match else None,
                    "failure_summary": match.get("failure_summary") if match else None,
                }
                if match
                else None,
            }
            post.append(row)
            print(json.dumps({"poll": row["elapsed"], "status": row["job"]["status"] if row["job"] else None}), flush=True)
            if match and match["status"] in ("completed", "failed", "cancelled"):
                # Only accept terminal after lease should have expired
                if time.time() >= (wait_until - 75):
                    recovered_terminal = match
                    mark(
                        "test11_terminal",
                        status=match["status"],
                        attempt_count=match.get("attempt_count"),
                        failure=match.get("failure_summary"),
                    )
                    break
            time.sleep(2)

        write_json("t11-post-restart-poll.json", post)

        # Count duplicate create_artifact completions with same label after baseline
        try:
            jobs = get_jobs()
            same_label = [
                j
                for j in jobs
                if j.get("action_kind") == "create_artifact"
                and "Retest Recovery Artifact T11" in (j.get("display_label") or "")
                or (
                    j["job_ref"] == target_ref
                )
            ]
            # broader: all new artifact jobs since baseline
            new_arts = [
                j
                for j in jobs
                if j["job_ref"] not in baseline_refs and j.get("action_kind") == "create_artifact"
            ]
            write_json(
                "t11-artifact-lineage.json",
                {"target_ref": target_ref, "new_artifact_jobs": new_arts},
            )
        except Exception as exc:
            mark("lineage_error", error=str(exc))
            new_arts = []

        if recovered_terminal and recovered_terminal["status"] == "completed":
            single = len(new_arts) == 1 and recovered_terminal.get("attempt_count") == 1
            mark(
                "result",
                test10="NOT_EXECUTED",
                test11="PASS" if single else "FAIL",
                job_ref=target_ref,
                new_artifact_jobs=len(new_arts),
                attempt_count=recovered_terminal.get("attempt_count"),
                note="killed_while_running_waited_real_lease_then_drain",
            )
        elif recovered_terminal:
            mark(
                "result",
                test10="NOT_EXECUTED",
                test11="FAIL",
                job_ref=target_ref,
                terminal=recovered_terminal.get("status"),
                failure=recovered_terminal.get("failure_summary"),
            )
        else:
            # Check if still running past lease — drain may have failed
            try:
                jobs = get_jobs()
                match = next((j for j in jobs if j["job_ref"] == target_ref), None)
            except Exception:
                match = None
            mark(
                "result",
                test10="NOT_EXECUTED",
                test11="FAIL",
                job_ref=target_ref,
                reason="no_terminal_after_lease_wait",
                final_job=match,
            )

    write_json("t10-t11-timeline.json", timeline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
