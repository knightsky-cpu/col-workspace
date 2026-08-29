# Internal Working State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hidden current-session working state that helps Agent Col track what it currently thinks is happening, what remains unresolved, and what next step is likely useful, without exposing that state in the user-facing app.

**Architecture:** Introduce a small internal `working_state` domain, persist exactly one current working-state record per chat session, inject a bounded hidden context block into the responder model context on later turns, and update the record through a separate internal provider after eligible turns. The first pass is same-session only and does not change public Notes, Memory, artifact taxonomy, routing policy, or cross-chat continuity.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, Google GenAI/ADK context objects, Firestore-backed `MemoryEngine`, pytest.

## Global Constraints

- The internal state is non-authoritative: current user messages, approved memory, workspace notes, artifacts, and higher-priority instructions remain authoritative.
- The state must not be returned in `ChatResponse`, rendered in the frontend, listed in Notes, listed in Memory, or surfaced as continuity receipts.
- The persistent naming convention must not use `notes`; use `working_state`.
- Do not store raw hidden chain-of-thought. Store bounded structured conclusions and rationale summaries only.
- The first pass is current-session only. Cross-chat continuity participation is excluded.
- The first pass must improve responder behavior and later same-session continuity, but does not need to change routing taxonomy or artifact intent policy.
- Use TDD. No production behavior change before a failing regression test.
- Preserve strict validation and safe public error handling.

---

## Planning Baseline

Current source shows that public chat output is explicitly receipt-based through `ChatResponse`; memory proposals, collaborative note proposals/events, artifacts, artifact feedback, and continuity receipts are all public response fields. Hidden working state must not be added to that model.

Current model context is assembled in `main.py` from approved memory, session history, and resolved continuity context before calling `AgentColTurnService.run_turn`. That is the correct orchestration surface for same-session working-state injection.

Current routing, artifact routing, expert execution, artifact execution, and responder handoff converge inside `AgentColTurnService`. A first pass can safely inject hidden context for the responder. A later pass would be needed if working state must influence router decisions before the route is chosen.

Current `AgentColTurnResult` contains only public response text and public receipts. It does not have a source for hidden working-state updates. Therefore this plan must not ask the public responder to return hidden state in `ChatResponse`; it needs a separate internal working-state provider that consumes bounded public turn data and produces validated internal state.

Current collaborative notes are user-facing, workspace-scoped, proposal/approval-based records. They are not suitable for private model working state.

Current continuity uses public receipts and choices. Hidden working state should not enter that path in this pass.

## Expected Files

- Create: `working_state.py`
  - Owns internal Pydantic contracts, context rendering, and deterministic eligibility/update helpers.
- Create: `working_state_service.py`
  - Owns internal provider prompting, structured provider output validation, and update orchestration.
- Modify: `database.py`
  - Adds internal Firestore read/write methods for `sessions/{session_id}/working_state/current`.
- Modify: `agent_col_turn_service.py`
  - Accepts a current working-state context block and passes it to the responder without exposing it as public receipts.
- Modify: `main.py`
  - Loads working state after chat turn claim and before `turn_service.run_turn`; asks the internal working-state service for an update after successful turn completion; persists the validated update.
- Test: `tests/test_working_state.py`
  - Covers schema bounds, context rendering, non-authoritative wording, and trigger/update helpers.
- Test: `tests/test_chat_turn_database.py`
  - Covers internal persistence path, ownership validation, and same-session scoping.
- Test: `tests/test_agent_col_turn_service.py`
  - Covers hidden context delivery to responder with no public result fields.
- Test: `tests/test_main.py`
  - Covers end-to-end chat orchestration: hidden state is loaded, injected, updated, and absent from `ChatResponse`.

## Proposed Internal Contract

```python
WorkingStateStatus = Literal["active", "empty"]
WorkingStateConfidence = Literal["low", "medium", "high"]
WorkingStateClarificationStatus = Literal["none", "useful", "blocking"]
WorkingStateBlockingStatus = Literal["not_blocking", "useful", "blocking"]

class WorkingStateQuestion(StrictModel):
    question: str = Field(min_length=1, max_length=240)
    why_it_matters: str = Field(min_length=1, max_length=300)
    blocking_status: WorkingStateBlockingStatus

class WorkingStateSnapshot(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    status: WorkingStateStatus = "active"
    authority: Literal["non_authoritative"] = "non_authoritative"
    user_id: IdentifierStr
    project_id: IdentifierStr
    session_id: IdentifierStr
    source_message_id: IdentifierStr | None = None
    request_summary: str = Field(min_length=1, max_length=200)
    current_goal: str = Field(min_length=1, max_length=300)
    intent_hypothesis: str = Field(min_length=1, max_length=500)
    active_constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=6)
    unresolved_questions: tuple[WorkingStateQuestion, ...] = Field(default_factory=tuple, max_length=5)
    clarification_status: WorkingStateClarificationStatus
    next_step_hypothesis: str = Field(min_length=1, max_length=400)
    confidence: WorkingStateConfidence
    updated_at: datetime | None = None
```

The exact field names can be revised during implementation if source inspection proves a smaller local pattern, but the semantics must stay: bounded, hidden, non-authoritative, current-session working state.

## Proposed Internal Provider Contract

```python
class WorkingStateUpdateInput(StrictModel):
    user_id: IdentifierStr
    project_id: IdentifierStr
    session_id: IdentifierStr
    source_message_id: IdentifierStr | None = None
    current_message: str = Field(min_length=1, max_length=10_000)
    model_response: str = Field(min_length=1, max_length=20_000)
    previous_state: WorkingStateSnapshot | None = None
    recent_user_messages: tuple[str, ...] = Field(default_factory=tuple, max_length=6)
    route: str | None = None

class WorkingStateUpdateResult(StrictModel):
    update_required: bool
    snapshot: WorkingStateSnapshot | None = None
```

The provider prompt must require bounded structured conclusions only. It must explicitly prohibit raw hidden chain-of-thought and instruct the model to summarize its rationale in the bounded public-safe fields.

## Task 1: Working State Domain Contract

**Files:**
- Create: `working_state.py`
- Test: `tests/test_working_state.py`

**Interfaces:**
- Produces: `WorkingStateSnapshot`, `WorkingStateQuestion`, `build_working_state_context(snapshot) -> str`, `should_update_working_state(message: str, route: str | None = None) -> bool`.
- Consumes: `IdentifierStr` and `StrictModel` from `schemas.py`.

- [ ] **Step 1: Write failing schema and rendering tests**

```python
def test_working_state_context_is_hidden_and_non_authoritative():
    snapshot = WorkingStateSnapshot(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_message_id="message-1",
        request_summary="Deployment plan with Cloud Run under consideration.",
        current_goal="Choose a deployment plan.",
        intent_hypothesis="The user likely wants a secure deployment plan and is unsure whether background workers are necessary.",
        active_constraints=("security matters more than speed",),
        unresolved_questions=(
            WorkingStateQuestion(
                question="Does artifact generation need to survive browser disconnects?",
                why_it_matters="This determines whether synchronous Cloud Run is enough.",
                blocking_status="useful",
            ),
        ),
        clarification_status="useful",
        next_step_hypothesis="Prefer a synchronous MVP unless durability becomes required.",
        confidence="medium",
    )

    context = build_working_state_context(snapshot)

    assert "[SERVER_VALIDATED_WORKING_STATE]" in context
    assert "non-authoritative" in context
    assert "security matters more than speed" in context
    assert "hidden reasoning" not in context.lower()
```

- [ ] **Step 2: Run RED**

Run: `venv/bin/pytest tests/test_working_state.py -q`

Expected: FAIL because `working_state.py` does not exist.

- [ ] **Step 3: Implement minimal domain contract**

Create the Pydantic models and context renderer. The renderer must label the block as hidden internal state, non-authoritative, and subordinate to user messages, approved memory, workspace notes, artifacts, and higher-priority instructions.

- [ ] **Step 4: Run GREEN**

Run: `venv/bin/pytest tests/test_working_state.py -q`

Expected: PASS.

## Task 2: Internal Persistence

**Files:**
- Modify: `database.py`
- Test: `tests/test_chat_turn_database.py`

**Interfaces:**
- Consumes: `WorkingStateSnapshot`.
- Produces:
  - `MemoryEngine.get_working_state(user_id: str, project_id: str, session_id: str) -> WorkingStateSnapshot | None`
  - `MemoryEngine.save_working_state(snapshot: WorkingStateSnapshot, *, observed_at: datetime) -> None`

- [ ] **Step 1: Write failing persistence tests**

Add tests proving:

- a stored current-session working state can be loaded;
- owner/project mismatch returns unavailable or raises the same safe ownership style used for chat sessions;
- saving writes under `sessions/{session_id}/working_state/current`;
- invalid stored data is rejected instead of leaking through to model context.

- [ ] **Step 2: Run RED**

Run: `venv/bin/pytest tests/test_chat_turn_database.py::test_get_working_state_returns_current_session_snapshot -q`

Expected: FAIL because methods do not exist.

- [ ] **Step 3: Implement minimal persistence**

Add only the two internal methods. Do not add public FastAPI endpoints. Do not add frontend access.

- [ ] **Step 4: Run GREEN**

Run the new focused persistence tests.

Expected: PASS.

## Task 3: Internal Working-State Provider

**Files:**
- Create: `working_state_service.py`
- Test: `tests/test_working_state_service.py`

**Interfaces:**
- Consumes: `WorkingStateUpdateInput`.
- Produces: `WorkingStateUpdateResult`.

- [ ] **Step 1: Write failing provider tests**

Add tests proving:

- provider output with a valid bounded snapshot is accepted;
- provider output that exceeds schema bounds fails validation;
- provider output that attempts to store raw hidden reasoning or unsupported fields fails validation;
- `update_required=False` returns no snapshot;
- the provider prompt labels the state as hidden, non-authoritative, current-session, and not user-facing.

- [ ] **Step 2: Run RED**

Run: `venv/bin/pytest tests/test_working_state_service.py -q`

Expected: FAIL because `working_state_service.py` does not exist.

- [ ] **Step 3: Implement minimal internal provider service**

Use the existing provider pattern from the repository: construct a bounded structured prompt, request a structured response, validate with Pydantic, and return only the normalized internal result. Do not return this provider result through `ChatResponse`.

- [ ] **Step 4: Run GREEN**

Run: `venv/bin/pytest tests/test_working_state_service.py -q`

Expected: PASS.

## Task 4: Turn-Service Hidden Context

**Files:**
- Modify: `agent_col_turn_service.py`
- Test: `tests/test_agent_col_turn_service.py`

**Interfaces:**
- Consumes: optional `working_state_context` in `AgentColTurnCommand`.
- Produces: no public result fields.

- [ ] **Step 1: Write failing turn-service tests**

Add tests proving:

- provided hidden working-state context is included in `SupervisorTurnContext.model_input_context`;
- the context is included before final responder execution;
- no public action, memory proposal, collaborative note event, artifact, or continuity receipt is created by working-state injection.

- [ ] **Step 2: Run RED**

Run the new targeted test in `tests/test_agent_col_turn_service.py`.

Expected: FAIL because the command/result has no working-state fields.

- [ ] **Step 3: Implement minimal turn-service wiring**

Add hidden context as an internal context content item. Keep routing contracts unchanged in this pass. If source inspection proves routing must consume the context for this pass to work, stop and revise this plan before implementation.

- [ ] **Step 4: Run GREEN**

Run the focused turn-service tests.

Expected: PASS.

## Task 5: Chat Orchestration

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `database.get_working_state`, `database.save_working_state`, `build_working_state_context`, `WorkingStateService`.
- Produces: hidden same-session working-state behavior during `/api/chat`.

- [ ] **Step 1: Write failing API orchestration tests**

Add tests proving:

- `/api/chat` loads current-session working state before `turn_service.run_turn`;
- hidden working state appears in `turn_command.model_input_context`;
- the JSON response does not contain `working_state`, `model_ideas`, or internal fields;
- after a successful turn, `main.py` asks `WorkingStateService` for a validated update and persists it when `update_required=True`;
- if working-state loading fails validation, the system safely omits the hidden context or returns a safe internal error according to the existing local error pattern selected during implementation.

- [ ] **Step 2: Run RED**

Run the new focused `tests/test_main.py` cases.

Expected: FAIL because `/api/chat` does not load or persist working state.

- [ ] **Step 3: Implement minimal orchestration**

Wire load/inject/save around the existing chat turn. Keep public response schema unchanged.

- [ ] **Step 4: Run GREEN**

Run the focused `tests/test_main.py` cases.

Expected: PASS.

## Task 6: Focused Regression Verification

**Files:**
- No additional source changes expected.

- [ ] **Step 1: Run focused tests**

Run:

```bash
venv/bin/pytest tests/test_working_state.py tests/test_working_state_service.py tests/test_chat_turn_database.py tests/test_agent_col_turn_service.py tests/test_main.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run artifact and continuity smoke tests**

Run:

```bash
venv/bin/pytest tests/test_generic_artifact_generation.py tests/test_generic_artifact_creation_service.py tests/test_agent_col_routing_v4.py tests/test_agent_col_turn_service.py tests/test_main.py -q
```

Expected: no regression in artifact generation, routing, turn orchestration, or public chat response behavior.

- [ ] **Step 3: Inspect diff**

Run:

```bash
git diff --check
git diff --stat
```

Expected: no whitespace errors; diff limited to the planned files.

## Manual Verification Targets

1. Start the local app and send a multi-turn planning prompt where the second turn updates an unresolved assumption. Expected: Agent Col responds as if it understands the current same-session collaboration state without exposing a hidden working-state block.
2. Check the Workspace Notes panel. Expected: no hidden working-state entries appear.
3. Check the Memory panel. Expected: no hidden working-state entries appear as durable profile memory.
4. Ask for an artifact after prior planning context. Expected: artifact behavior remains unchanged except that the natural response may better reflect the current state.
5. Reload the same chat session and continue. Expected: same-session working state informs the response without visible continuity receipts.

## Known Exclusions

- No cross-chat working-state continuity.
- No frontend display for working state.
- No public API for working state.
- No routing taxonomy redesign.
- No artifact taxonomy, artifact generation, synthesis, or versioning changes.
- No replacement for approved Memory or user-facing Workspace Notes.
- No storage of raw hidden chain-of-thought.

## Stop Conditions

Stop and revise this plan before implementation if source inspection proves any of the following:

- Working state cannot improve responder behavior without changing routing contracts.
- Existing idempotent chat-turn completion cannot safely coordinate the extra internal write.
- Hidden working-state context would be serialized through `ChatResponse` or rendered by the frontend.
- The only practical persistence path reuses collaborative Notes or Memory.
- Firestore tests require a broader persistence abstraction than the two-method internal API.
