# Working State Verification and Routing Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each approved source-changing pass. Do not implement Pass 2 until Pass 1 is manually accepted and the routing plan is re-reviewed against the updated source.

**Goal:** Improve Agent Col's same-session collaboration by preserving unresolved external factual claims as verification-needed working state, then later using that state to route source-backed follow-ups more reliably.

**Architecture:** Pass 1 changes only the hidden working-state provider instruction so unresolved external facts are classified as verification-needed/source-sensitive without changing schema or public surfaces. Pass 2, after Pass 1 acceptance and re-review, will add working-state-aware routing so follow-ups that ask to explain or finalize verification-needed external facts can route to Research/Source instead of direct responder guessing.

**Tech Stack:** Python, FastAPI, Google GenAI/ADK, Pydantic v2, pytest.

**Spec:** User request from 2026-08-27: broaden unresolved working-state classification for software, dependencies, operating systems, programs, websites, articles, books, networking, calculus, algebra, school subjects, documentation, platforms, vendors, and other external factual claims; then later use that classification to improve research/source routing.

## Global Constraints

- Keep working state current-chat/session scoped.
- Do not add cross-chat continuity.
- Do not expose working state through public API responses, frontend UI, receipts, artifacts, notes, or memory.
- Do not log raw working-state JSON, hidden context, user prompt content, model response content, private reasoning, or generated artifact content.
- Do not classify every uncertainty as an assumption.
- Distinguish user-owned decisions, temporary assumptions, and verification-needed external facts.
- Use TDD for each source-changing pass.
- Stop after each implementation pass as implemented, pending manual verification.

---

## Source-Backed Findings

`working_state_service.py` currently tells the hidden provider to track unresolved questions, clarification status, next-step hypothesis, and confidence, but it does not distinguish user-owned project decisions from external facts requiring verification.

`working_state.py` already has enough bounded fields for this improvement without schema changes: `WorkingStateQuestion.question`, `WorkingStateQuestion.why_it_matters`, `WorkingStateQuestion.blocking_status`, `WorkingStateSnapshot.intent_hypothesis`, `WorkingStateSnapshot.active_constraints`, and `WorkingStateSnapshot.next_step_hypothesis`.

`tests/test_working_state_service.py` already checks the provider system instruction through the fake GenAI client, so the provider policy can be tested without live model calls.

`main.py` loads working state before turn execution and passes it into `AgentColTurnCommand`, but `agent_col_turn_service.py` currently injects it only into responder model input. Routing input is built inside `AgentColTurnService` before responder context is assembled, so Pass 2 requires explicit re-review and likely routing-input/orchestration changes.

`agent_col_routing_provider_v4.py` already says to choose Research when current or externally verifiable public evidence is required, but it has no explicit access to working-state verification-needed unresolved facts.

## Pass 1: Working-State Provider Classification

### Pass Goal

Make hidden working state preserve unresolved external factual claims as verification-needed/source-sensitive, without classifying every uncertainty as an assumption.

### User-Visible Outcome

Later responses should be less likely to guess about Cloud Run, software behavior, dependencies, operating systems, programs, websites, articles, books, networking, calculus, algebra, school subjects, documentation, or similar external factual topics when the unresolved item needs source backing.

### Expected Files

- Modify: `working_state_service.py`
- Modify: `tests/test_working_state_service.py`

### Invariants To Preserve

- No working-state schema changes.
- No public API, frontend, routing, artifact, Notes, Memory, or persistence path changes.
- Do not store raw hidden chain-of-thought.
- Do not treat every unresolved item as a research fact; user-owned decisions remain user-owned decisions.

### Technical Approach

Update `WORKING_STATE_SYSTEM_INSTRUCTION` to require the provider to distinguish:

- user-owned decisions: choices the user must make;
- temporary assumptions: clearly labeled placeholders that keep discussion moving;
- verification-needed external facts: claims about software, dependencies, operating systems, programs, websites, articles, books, networking, calculus, algebra, school subjects, documentation, platforms, vendors, security, legal, medical, financial, or operational behavior.

Record verification-needed items in `unresolved_questions.why_it_matters` or `next_step_hypothesis`. Do not convert model-response speculation into working-state facts.

### TDD Cycle

#### RED

Add `tests/test_working_state_service.py::test_generate_working_state_update_marks_external_facts_as_verification_needed`.

Run:

```bash
venv/bin/pytest tests/test_working_state_service.py::test_generate_working_state_update_marks_external_facts_as_verification_needed -q
```

Expected: FAIL because the provider instruction does not yet contain the broader verification-needed/source-sensitive classification policy.

#### GREEN

Update only `WORKING_STATE_SYSTEM_INSTRUCTION`.

Run the RED command again.

Expected: PASS.

### Focused Verification

Run:

```bash
venv/bin/pytest tests/test_working_state_service.py::test_generate_working_state_update_marks_external_facts_as_verification_needed -q
venv/bin/pytest tests/test_working_state_service.py::test_generate_working_state_update_accepts_valid_snapshot -q
venv/bin/pytest tests/test_working_state_service.py::test_generate_working_state_update_rejects_raw_reasoning_field -q
venv/bin/pytest tests/test_main.py::test_chat_uses_hidden_working_state_without_public_response_fields -q
git diff --check
```

Full suite is not required because this pass only changes hidden provider prompt policy and directly related privacy coverage.

### Manual Verification Target

Re-run the Cloud Run disconnect flow. Expected: disconnect propagation is preserved as source-sensitive/platform-specific and should not be converted into a confident assumption.

## Pass 2: Working-State-Aware Research Routing

### Pass Goal

When a user asks to explain or finalize an unresolved verification-needed external fact, route to Research/Source more deterministically instead of letting the direct responder guess.

### Re-Review Requirement

Do not implement this pass from this document alone. After Pass 1 is manually accepted, re-review routing, turn orchestration, and provider behavior against the updated source and propose the concrete routing pass again for approval.

### Likely Expected Files

- Likely modify: `agent_col_turn_service.py`
- Likely modify: `agent_col_routing_provider_v4.py` or routing input/model files
- Likely test: `tests/test_agent_col_turn_service.py`
- Possibly test: `tests/test_agent_col_routing_provider_v4.py`

### Candidate Technical Approach

Add a bounded, content-safe working-state routing hint derived from `WorkingStateSnapshot`. Feed that hint into routing before `routing_request`. Update routing policy so verification-needed unresolved external facts can trigger Research when the current user asks to explain, decide, verify, source-back, or finalize them.

Avoid routing every assumption to Research. Only unresolved external factual claims in the broadened categories should qualify.

### Candidate TDD

```bash
venv/bin/pytest tests/test_agent_col_turn_service.py::test_turn_service_routes_verification_needed_working_state_followup_to_research -q
```

Expected RED before implementation: fails because current routing does not receive or use working-state verification hints.

### Stop Conditions

Stop and revise if Pass 1 manual verification shows the provider-policy change does not affect working-state quality, or if routing source inspection after Pass 1 shows a smaller or different integration point.
