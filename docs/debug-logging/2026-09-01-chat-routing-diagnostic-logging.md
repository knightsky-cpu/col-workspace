# Chat Routing Diagnostic Logging Evidence - 2026-09-01

## Scope

This document records the accepted diagnostic logging pass for intermittent
Agent Col chat, routing, artifact, note, memory, and responder failures.

The pass came after repeated proposal/continuity behavior failures, note
retrieval fixes, responder instruction changes, and a governed durable-effect
guard for artifact plus note proposal conflicts.

## Implemented Diagnostic Boundaries

The pass added content-safe backend diagnostics at these boundaries:

- `main.py` route-level chat pipeline entry, continuity resolution, turn-service
  timeout, turn-service failure, and turn-service completion.
- `agent_col_turn_service.py` routing, artifact execution, expert execution,
  and responder success/failure boundaries.
- `main.py` STT/TTS provider failure logging, preserving provider error class,
  provider cause class, and provider code label.

The logs intentionally record only:

- stage name;
- route label;
- elapsed milliseconds;
- exception class;
- count of durable effects and receipts.

The logs intentionally do not record:

- user prompt text;
- model response text;
- user id;
- project/workspace id;
- session id;
- artifact labels;
- raw provider error content.

## Automated Verification

Focused tests passed after the implementation:

```text
venv/bin/python -m pytest tests/test_main.py::test_artifact_responder_failure_releases_refreshed_claim_and_receipts tests/test_agent_col_turn_service_artifacts.py::test_turn_service_logs_artifact_pipeline_without_private_content -v
```

Result: 2 passed, 1 warning.

```text
venv/bin/python -m pytest tests/test_main.py::test_speech_transcribe_logs_provider_cause_without_leaking_it_to_client tests/test_main.py::test_speech_synthesize_logs_provider_cause_without_leaking_it_to_client -v
```

Result: 2 passed, 1 warning.

```text
venv/bin/python -m pytest tests/test_agent_col_turn_service.py tests/test_agent_col_turn_service_artifacts.py tests/test_agent_col_turn_service_feedback.py tests/test_smoke_test_agent_col_turn_service.py -q
```

Result: 60 passed, 1 warning.

```text
venv/bin/python -m pytest tests/test_main.py -q
```

Result: 270 passed, 1 warning.

```text
venv/bin/python -m py_compile main.py agent_col_turn_service.py
```

Result: passed.

## Live Manual Evidence

The user ran the local server with Google OIDC:

```text
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Manual prompts exercised:

- artifact creation plus workspace note request;
- artifact creation plus memory proposal request;
- large Bash network-monitor artifact generation;
- revision request after artifact generation;
- ambiguous follow-up recall;
- combined idea/artifact/decision request;
- oversized combined implementation/documentation request;
- cross-session note continuity for project language and project description;
- shell-helper continuity recall.

No random route failure was reproduced during the live pass. The screenshots in
`docs/debug-logging/evidence/` record the successful manual behavior.

Important limitation: the pasted terminal output did not show
`Agent_Col chat pipeline` or `Agent_Col turn pipeline` lines. The automated
tests prove those module loggers emit the expected records under `caplog`, but
the live Uvicorn command appears not to display those module `INFO` records in
stdout with the current launch configuration.

## Evidence Files

- `evidence/2026-09-01-live-terminal-observation.md`
- `evidence/2026-09-01-debug-logging-live-01-artifact-note-request.png`
- `evidence/2026-09-01-debug-logging-live-02-artifact-memory-proposal.png`
- `evidence/2026-09-01-debug-logging-live-03-checkpoint-artifact-detail.png`
- `evidence/2026-09-01-debug-logging-live-04-large-network-monitor-artifact.png`
- `evidence/2026-09-01-debug-logging-live-05-network-monitor-detail-top.png`
- `evidence/2026-09-01-debug-logging-live-06-network-monitor-detail-middle.png`
- `evidence/2026-09-01-debug-logging-live-07-network-monitor-detail-bottom.png`
- `evidence/2026-09-01-debug-logging-live-08-revision-and-memory-status.png`
- `evidence/2026-09-01-debug-logging-live-09-follow-up-recall.png`
- `evidence/2026-09-01-debug-logging-live-10-routing-combined-request.png`
- `evidence/2026-09-01-debug-logging-live-11-combined-request-response.png`
- `evidence/2026-09-01-debug-logging-live-12-artifact-detail-combined-request.png`
- `evidence/2026-09-01-debug-logging-live-13-overlarge-request-clarification.png`
- `evidence/2026-09-01-debug-logging-live-14-continuity-language-note.png`
- `evidence/2026-09-01-debug-logging-live-15-continuity-project-about.png`
- `evidence/2026-09-01-debug-logging-live-16-continuity-shell-helper.png`

## Routing Queue Discussion Point

The live behavior reinforces a larger architecture issue: Agent Col still
mostly behaves as a single governed turn that produces one final response, even
when the user naturally asks for multiple coordinated outcomes such as:

- create an artifact;
- create or queue a workspace note proposal;
- create or queue a memory proposal;
- continue streaming status to the user.

Current repository docs already identify this limitation:

- `docs/current-state.md` says artifact execution is request-bound and that
  durable asynchronous/background execution is intentionally deferred.
- `docs/current-state.md` also says working state is hidden, same-session, and
  non-authoritative, not an action authority.
- `docs/legacy/backend/artifacts/2026-08-25-winning-core-phase-3-async-artifact-work.md`
  already sketches a queued artifact model with durable job receipts, immutable
  chat replay, and a Jobs/status surface instead of delayed assistant messages.

The current durable-turn guard prevents unsafe double durable effects in one
turn. That is correct for state safety, but it exposes a capability gap: a
single user request can reasonably contain multiple valid agent tasks.

A future design should evaluate a server-owned action queue where the initial
chat turn can enqueue independent governed follow-up actions, each with its own
idempotency, ownership, status, and user approval boundary. The chat stream
should report accepted/queued/completed/failed status without requiring every
background task to finish before the assistant can answer.

This is not implemented in the diagnostic logging pass.

## Open Follow-Up

The next narrow diagnostic pass should make the content-safe diagnostic logs
visible in local Uvicorn stdout and Cloud Run logs without relying on test-only
`caplog` capture.
