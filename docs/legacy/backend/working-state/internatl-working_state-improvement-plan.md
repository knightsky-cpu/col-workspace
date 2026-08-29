# Internal Working State Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement each approved pass. This document contains two separated implementation passes. Do not implement both from one approval unless the user explicitly approves both.

**Goal:** Improve current-session working-state reliability by hardening responder behavior around unresolved questions and adding backend-only debug visibility for hidden working-state integrity.

**Architecture:** Keep the current hidden, same-session working-state pipeline. Pass 1 changes only responder policy so unresolved working-state questions cannot silently become confident factual claims. Pass 2 adds safe metadata-only backend logs so developers can distinguish missing state, wrong state, and responder misuse without exposing private state content.

**Tech Stack:** Python, FastAPI, Google ADK responder prompt, Firestore-backed persistence, pytest, standard Python logging.

**Spec:** User request from 2026-08-27: source-backed plan covering responder policy hardening plus backend internal working-state log visibility, with working state still same-session only.

## Global Constraints

- Keep working state current-chat/session scoped.
- Do not add cross-chat continuity.
- Do not expand the working-state schema in these passes.
- Do not expose working state through public API responses, frontend UI, receipts, artifacts, notes, or memory.
- Do not log raw working-state JSON, hidden context, user prompt content, model response content, private reasoning, or generated artifact content.
- Do not change routing taxonomy, artifact behavior, Notes behavior, Memory behavior, or general chat error handling.
- Use TDD for each source-changing pass.
- Stop after each implementation pass as implemented, pending manual verification.

---

## Source-Backed Findings

### Current Working-State Shape

`working_state.py` defines a hidden context block:

- `WORKING_STATE_CONTEXT_START = "[SERVER_VALIDATED_WORKING_STATE]"`
- `WORKING_STATE_CONTEXT_END = "[/SERVER_VALIDATED_WORKING_STATE]"`
- `WORKING_STATE_CONTEXT_MAX_CHARS = 5_000`

`WorkingStateSnapshot` already includes the collaboration fields needed for
this improvement:

- `request_summary`
- `current_goal`
- `intent_hypothesis`
- `active_constraints`
- `unresolved_questions`
- `clarification_status`
- `next_step_hypothesis`
- `confidence`

The renderer says the state is hidden, non-authoritative, may be stale, and is
overridden by current user messages, approved memory, workspace notes,
persisted artifacts, and higher-priority instructions.

Conclusion: no schema expansion is needed for these two passes.

### Current Responder Policy

`agent_col_responder.py` now contains a `SERVER_VALIDATED_WORKING_STATE`
paragraph. It instructs the responder to:

- treat working state as hidden same-session collaboration state;
- treat it as non-authoritative and possibly stale;
- use current goal, active constraints, unresolved questions, clarification
  status, and next-step hypothesis;
- ask one concise clarifying question for blocking clarification;
- proceed with assumptions or options for non-blocking clarification;
- avoid exposing working-state internals.

Gap: it does not explicitly state that unresolved working-state questions are
not facts. The observed Cloud Run response answered a browser-disconnect topic
with too much confidence even though backend working state later preserved that
disconnect handling was still unresolved/non-blocking.

Conclusion: responder policy can be hardened without touching routing or
working-state persistence.

### Current Working-State Orchestration

`main.py`:

- computes `working_state_enabled = should_update_working_state(payload.message)`;
- calls `database.get_working_state(...)`;
- builds `working_state_context` when a snapshot exists;
- passes that context into `AgentColTurnCommand`;
- after successful public response completion, calls
  `working_state_service.update(...)`;
- saves the updated snapshot when `update_required` is true.

Existing logs only report failures:

- `"Hidden working state context unavailable (%s)."`
- `"Hidden working state update failed (%s)."`

Gap: successful load/inject/update/save behavior is invisible without ad hoc
Firestore inspection. There is no safe backend trail showing whether state was
absent, injected, updated, skipped, or saved.

Conclusion: metadata-only backend logs are the smallest observability pass.

### Current Privacy Boundary

`schemas.py` defines `ChatResponse` public fields for response, actions,
artifacts, artifact feedback, citations, memory proposals/clarifications,
collaborative note proposals/events, continuity receipts/choices, and
adaptations. It has no working-state or model-thoughts field.

`tests/test_main.py::test_chat_uses_hidden_working_state_without_public_response_fields`
already verifies public chat responses omit `working_state` and
`model_thoughts`.

Conclusion: debug visibility must stay backend-only. Public schemas and
frontend surfaces should not change.

### Cloud Run Domain Claim Evidence

The questionable response said browser disconnects are automatically handled by
Cloud Run. Official Google Cloud documentation is more specific:

- Cloud Run troubleshooting says HTTP/1.1 client disconnect events are not
  propagated to the Cloud Run container, and WebSockets or HTTP/2 are needed
  when disconnect propagation matters.
  Source: https://docs.cloud.google.com/run/docs/troubleshooting
- Cloud Run request timeout docs say the network connection closes at timeout,
  but the serving container instance is not terminated and code may keep
  processing the terminated request.
  Source: https://docs.cloud.google.com/run/docs/configuring/request-timeout

Conclusion: this was mainly responder/model answer-quality risk on a
platform-specific claim, not a failure of working-state storage. Engineering
can reduce the risk by making the responder treat unresolved working-state
questions as unresolved, not as factual premises.

---

## Pass 1: Responder Policy Hardening for Unresolved Working-State Questions

### Pass Goal

Prevent unresolved working-state questions from being answered as confident
facts. Agent Col should either source-back current platform claims or frame
them as assumptions/options when the working state marks the topic unresolved.

### User-Visible Outcome

In same-session follow-ups, Agent Col should be more careful when a topic is
still unresolved. It should say what is assumed, give options, or ask one
blocking question instead of presenting platform-specific behavior as settled
fact.

### Expected Files

- Modify: `agent_col_responder.py`
- Modify: `tests/test_agent_col_turn_service.py`

### Invariants To Preserve

- Current user message remains highest-priority user intent.
- Routing context remains authoritative.
- Working state remains hidden, same-session, non-authoritative, and
  subordinate.
- No public API, frontend, schema, routing, artifacts, notes, or memory changes.
- No forced research route from this pass.

### Technical Approach

Add one sentence-level policy block to the existing
`SERVER_VALIDATED_WORKING_STATE` responder instruction:

```text
Unresolved working-state questions are not facts. Do not answer them as
settled platform, vendor, security, legal, medical, financial, or operational
claims unless the answer is source-backed by validated routing/expert context
or explicitly framed as an assumption, option, or open decision.
```

This deliberately avoids changing routing. If the current turn has no
validated source/research context, the responder may still answer, but it must
qualify unresolved factual claims as assumptions/options instead of asserting
them confidently.

### TDD Cycle

#### RED

Add this test to `tests/test_agent_col_turn_service.py`:

```python
def test_responder_instruction_treats_unresolved_working_state_questions_as_unsettled() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    instruction = " ".join(RESPONDER_INSTRUCTION.split())

    assert "Unresolved working-state questions are not facts" in instruction
    assert "settled platform" in instruction
    assert "source-backed" in instruction
    assert "validated routing" in instruction
    assert "assumption" in instruction
    assert "option" in instruction
    assert "open decision" in instruction
```

Run:

```bash
venv/bin/pytest tests/test_agent_col_turn_service.py::test_responder_instruction_treats_unresolved_working_state_questions_as_unsettled -q
```

Expected: FAIL because the hardened policy is not present yet.

#### GREEN

Add the minimal responder instruction text under the existing
`SERVER_VALIDATED_WORKING_STATE` paragraph.

Run:

```bash
venv/bin/pytest tests/test_agent_col_turn_service.py::test_responder_instruction_treats_unresolved_working_state_questions_as_unsettled -q
```

Expected: PASS.

### Focused Verification

Run:

```bash
venv/bin/pytest tests/test_agent_col_turn_service.py::test_responder_instruction_defines_hidden_working_state_policy -q
venv/bin/pytest tests/test_agent_col_turn_service.py::test_responder_instruction_treats_unresolved_working_state_questions_as_unsettled -q
venv/bin/pytest tests/test_agent_col_turn_service.py::test_turn_service_injects_hidden_working_state_for_responder -q
venv/bin/pytest tests/test_main.py::test_chat_uses_hidden_working_state_without_public_response_fields -q
git diff --check
```

Full suite is not required because this pass only changes responder instruction
text and directly related prompt/injection/privacy tests.

### Manual Verification Prompts

Use one new chat session in the same workspace:

1. `I want a Cloud Run deployment plan. Security matters more than speed, but I am not sure whether browser disconnects matter yet.`
2. `Artifact generation only takes 10 seconds, and I still want the architecture simple.`
3. `Can you explain the disconnect choice without deciding it for me?`

Expected:

- Agent Col continues the same plan.
- It does not state browser disconnect behavior as settled unless it cites or
  clearly frames the answer as an assumption/option.
- It preserves the disconnect topic as an open decision when appropriate.
- It asks at most one blocking clarifying question only if required.
- It does not expose working-state internals.

### Stop Conditions

Stop and revise the plan if source inspection during implementation shows:

- responder instructions are no longer the only consumer of hidden working
  state;
- the routing layer already has a deterministic unresolved-fact policy;
- tests need provider calls to prove this behavior.

---

## Pass 2: Backend-Only Working-State Debug Visibility

### Pass Goal

Make working-state pipeline integrity observable from backend logs without
exposing hidden state content.

### User-Visible Outcome

No UI/API behavior change. During local/manual tests, backend logs should show
whether working state was enabled, loaded, injected, update-skipped, updated,
or saved, using only safe metadata.

### Expected Files

- Modify: `main.py`
- Modify: `tests/test_main.py`

### Invariants To Preserve

- No public `working_state` or `model_thoughts` fields.
- No frontend display.
- No raw user message, model response, hidden context, raw state JSON, artifact
  content, note content, memory value, or private reasoning in logs.
- Existing failure behavior remains non-fatal for working-state load/update
  failures.
- Working-state save still happens only after successful chat completion.

### Technical Approach

Add small helper functions in `main.py`:

```python
def _working_state_log_fields(
    *,
    user_id: str,
    project_id: str,
    session_id: str,
    source_message_id: str | None = None,
    state: WorkingStateSnapshot | None = None,
) -> str:
    clarification_status = (
        state.clarification_status if state is not None else "none"
    )
    unresolved_count = (
        len(state.unresolved_questions) if state is not None else 0
    )
    return (
        f"user_id={user_id} project_id={project_id} session_id={session_id} "
        f"source_message_id={source_message_id or 'none'} "
        f"state_present={state is not None} "
        f"clarification_status={clarification_status} "
        f"unresolved_questions={unresolved_count}"
    )
```

Then log metadata-only events around existing orchestration:

- after `working_state_enabled` is computed;
- after `get_working_state`;
- after `build_working_state_context` decides whether injection is present;
- after `working_state_service.update`;
- after `database.save_working_state`;
- existing exception logs can append the safe metadata string without exception
  message content.

Suggested log messages:

```python
logger.info("Hidden working state checked: %s", fields)
logger.info("Hidden working state injected: %s", fields)
logger.info(
    "Hidden working state update completed: %s update_required=%s",
    fields,
    working_state_update.update_required,
)
logger.info("Hidden working state saved: %s", fields)
```

Use `logger.info` for successful observability. Keep existing error logs for
failure paths, but make them metadata-rich and content-safe.

### TDD Cycle

#### RED 1: Success Path Logs Metadata

Add this test to `tests/test_main.py`:

```python
@pytest.mark.asyncio
async def test_chat_logs_working_state_metadata_without_private_content(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    previous_state = make_working_state_snapshot(
        request_summary="private request summary",
        current_goal="private current goal",
        intent_hypothesis="private intent hypothesis",
        active_constraints=("private active constraint",),
        unresolved_questions=(
            {
                "question": "private unresolved question",
                "why_it_matters": "private rationale",
                "blocking_status": "useful",
            },
        ),
        clarification_status="useful",
        next_step_hypothesis="private next step",
    )
    updated_state = make_working_state_snapshot(
        request_summary="private updated summary",
        current_goal="private updated goal",
        clarification_status="blocking",
    )
    service_state.database.working_state = previous_state
    service_state.working_state_service.result = WorkingStateUpdateResult(
        update_required=True,
        snapshot=updated_state,
    )
    caplog.set_level("INFO", logger="main")

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "I want a deployment plan.",
        },
    )

    assert response.status_code == 200
    assert "Hidden working state checked" in caplog.text
    assert "Hidden working state injected" in caplog.text
    assert "Hidden working state update completed" in caplog.text
    assert "Hidden working state saved" in caplog.text
    assert "user_id=user-1" in caplog.text
    assert "project_id=project-1" in caplog.text
    assert "session_id=session-1" in caplog.text
    assert "source_message_id=user-message-1" in caplog.text
    assert "state_present=True" in caplog.text
    assert "unresolved_questions=1" in caplog.text
    for private_marker in (
        "private request summary",
        "private current goal",
        "private intent hypothesis",
        "private active constraint",
        "private unresolved question",
        "private rationale",
        "private next step",
        "private updated summary",
        "private updated goal",
        "I want a deployment plan.",
        "Generated answer",
    ):
        assert private_marker not in caplog.text
```

Run:

```bash
venv/bin/pytest tests/test_main.py::test_chat_logs_working_state_metadata_without_private_content -q
```

Expected: FAIL because success-path working-state logs do not exist yet.

#### GREEN 1

Add the helper and minimal success-path logs.

Run the same test. Expected: PASS.

#### RED 2: Failure Logs Stay Sanitized

Add this test to `tests/test_main.py`:

```python
@pytest.mark.asyncio
async def test_chat_logs_working_state_failures_without_private_content(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_state.database.working_state_error = main.MemoryEngineError(
        "private working state failure detail"
    )
    caplog.set_level("ERROR", logger="main")

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "I want a deployment plan.",
        },
    )

    assert response.status_code == 200
    assert "Hidden working state context unavailable" in caplog.text
    assert "MemoryEngineError" in caplog.text
    assert "user_id=user-1" in caplog.text
    assert "project_id=project-1" in caplog.text
    assert "session_id=session-1" in caplog.text
    assert "private working state failure detail" not in caplog.text
    assert "I want a deployment plan." not in caplog.text
    assert "Generated answer" not in caplog.text
```

Run:

```bash
venv/bin/pytest tests/test_main.py::test_chat_logs_working_state_failures_without_private_content -q
```

Expected: FAIL if failure logs do not include safe metadata, or PASS if the
first GREEN already covered it. If it passes immediately, do not change
production code for this behavior.

#### GREEN 2

If RED 2 fails, append safe metadata to existing working-state exception logs
without logging exception message text.

### Focused Verification

Run:

```bash
venv/bin/pytest tests/test_main.py::test_chat_logs_working_state_metadata_without_private_content -q
venv/bin/pytest tests/test_main.py::test_chat_logs_working_state_failures_without_private_content -q
venv/bin/pytest tests/test_main.py::test_chat_uses_hidden_working_state_without_public_response_fields -q
venv/bin/pytest tests/test_main.py::test_chat_does_not_update_working_state_when_completion_fails -q
git diff --check
```

Full suite is not required because this pass only touches `/api/chat`
working-state observability and directly related privacy/completion-failure
tests.

### Manual Verification Target

Run the same four-prompt same-session deployment flow under local uvicorn:

```bash
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Expected backend logs:

- a checked event for each triggerable user turn;
- `state_present=False` on the first relevant turn if no prior state exists;
- `state_present=True` and `unresolved_questions=N` on later turns when state
  exists;
- update completed and saved logs after successful responses;
- no raw working-state values, raw user prompts, raw model responses, hidden
  JSON, or private reasoning.

Expected frontend/API behavior:

- no visible working-state fields or hidden blocks;
- existing chat and artifact behavior unchanged.

### Stop Conditions

Stop and revise the plan if source inspection during implementation shows:

- existing production log policy forbids info-level chat metadata;
- tests cannot capture the relevant logger without broad fixture rewrites;
- safe metadata cannot distinguish load/inject/update/save without leaking
  content.

---

## Recommended Execution Order

1. Implement Pass 1 first. It directly addresses the observed Cloud Run
   overconfidence behavior and is the smallest behavior-hardening change.
2. After manual acceptance, implement Pass 2. It improves diagnosis for future
   working-state behavior without changing user-facing behavior.

Do not checkpoint either pass until the user manually accepts that pass.
