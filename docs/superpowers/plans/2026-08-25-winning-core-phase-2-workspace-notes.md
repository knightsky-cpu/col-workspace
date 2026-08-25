# Winning Core Phase 2 Governed Workspace Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan one approved pass at a
> time. Repository `AGENTS.md` approval, TDD, manual-verification, and
> checkpoint gates remain controlling.

**Status:** Pending approval. Planning this phase does not authorize any
source change or any Phase 2 implementation pass.

**Goal:** Give Agent Col a separate, governed workspace-notes capability. A
user can review an exact proposed note before activation; inspect, correct,
archive, restore, or delete it; and later see authoritative proof when Agent
Col uses that note or one bounded immediately previous chat in another
conversation.

**Architecture:** Preserve four independent authorities: user-global profile
memory, user-and-workspace-scoped collaborative notes, canonical chat
archives, and application-derived continuity receipts. Firestore owns durable
state. FastAPI and deterministic services own identity, scope, provenance,
lifecycle, retrieval bounds, and public receipts. Gemini may propose bounded
note content from the current user message, but it cannot activate a note,
select owner/workspace IDs, mutate lifecycle state, or turn retrieved content
into authority. Agent Col remains the sole user-facing responder.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2, Google ADK, Gemini 3.6 Flash
through Vertex AI, Firestore, vanilla JavaScript ES modules, Node test runner,
pytest, Google OIDC.

**Governing references:**

- `AGENTS.md`
- `AGENT_COL_IDENTITY_AND_ALIGNMENT.md`
- `DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`
- `docs/aug-25-2026-final-checklist.md`
- `docs/superpowers/specs/2026-08-24-m9-cont-1-continuity-domain-and-collaborative-notes-design.md`
- `docs/superpowers/plans/2026-08-24-m9-note-1a-collaborative-note-proposal-active-projection-models.md`
- `docs/superpowers/plans/2026-08-25-winning-core-phase-1-remaining-work.md`

**Planning baseline:** Commit `541aa87` on `main`, with a clean worktree, was
inspected on August 25, 2026. Phase 1 Passes 1B-1D are still pending according
to the final checklist. Phase 2 implementation must not start until every
Phase 1 pass is accepted and checkpointed. Before approving Phase 2A for
implementation, re-audit this plan against that final Phase 1 checkpoint and
replace the planning baseline with the accepted commit.

The `docs/research/*.md` material was intentionally not used to design Phase
2. Per the repository owner's direction, Phase 2 is grounded in current source
and the already approved continuity design; research look-ahead material is
reserved for Phase 3 planning.

## Plain-language outcome

At the end of this phase:

1. Agent Col can notice a useful workspace-specific decision, requirement,
   constraint, task update, or working fact and offer one exact note.
2. The note remains pending until the user approves it.
3. The user can see where it came from and can reject, correct, archive,
   restore, or permanently delete it.
4. A new chat in the same workspace can use only approved, active notes or one
   specifically bounded prior chat.
5. The response visibly identifies the note or prior chat that was used.
6. Ambiguous references produce a choice instead of a guess.
7. Notes never become global profile preferences, and another user or
   workspace cannot inspect or retrieve them.

## Verified current source state

The following statements describe executable source at the planning baseline,
not projected behavior:

- `collaborative_note_policy.py` defines five note kinds, proposal and active
  statuses, policy version `1.0`, and bounded title/body normalization.
- `schemas.py` defines strict `CollaborativeNoteProposal` and
  `CollaborativeNote` models with source-session/message fields, revision
  pairing, and timestamp invariants.
- `tests/test_collaborative_note_policy.py` and
  `tests/test_collaborative_note_schemas.py` cover those isolated contracts.
- No production module persists note proposals, notes, or note events.
- `database.py` has no collaborative-note collections or lifecycle methods.
- `ChatRequest`, `ChatResponse`, `ChatPartialFailureResponse`,
  `ChatTurnRequest`, `ChatTurnClaim`, and `ChatTurnReplay` contain memory and
  artifact effects but no note decisions, note receipts, continuity choices,
  or continuity receipts.
- `memory_candidate_decisions.WorkspaceNoteDecision` contains only
  `kind="workspace_note"`. The current memory tool returns a truthful no-effect
  result, and `supervisor.py` tells Agent Col that workspace-note persistence
  is a separate, unavailable boundary.
- `main.py` supplies only bounded current-session history and approved profile
  memory to a turn. It does not project collaborative notes or unopened prior
  sessions.
- `database.py` now validates existing chat-session user/workspace ownership
  in turn claims, message writes, and history reads. That accepted security
  correction is a prerequisite pattern for note provenance and continuity.
- The browser has distinct Workspace, Artifacts, Memory, and Chats sections.
  It has no Notes state, API client, view, controls, or continuity receipt
  renderer.
- Firestore index configuration currently exempts blueprint payloads only; it
  has no note or prior-session query index.

## Phase pass outline

Phase 2 is deliberately split at durable authority and public-contract
boundaries. Implement, verify, manually accept, and checkpoint each pass before
requesting approval for the next.

| Pass | User-visible or reviewable outcome | Primary boundary |
| --- | --- | --- |
| 2A | Strict versioned note events, public receipts, IDs, and pending-proposal persistence exist with proven ownership/provenance bounds. | Contracts and persistence foundation; no routes or model tool. |
| 2B | Authorized note list/detail, correction proposal, archive, restore, and deletion operations work through deterministic services and FastAPI. | Read and direct lifecycle API. |
| 2C | Approval and rejection travel through the retry-safe chat ledger and survive replay, lease reclaim, timeout, and responder failure exactly once. | Structured chat decisions and durable effects. |
| 2D | An ordinary natural-language turn can create one reviewable workspace-note proposal, while memory and note effects remain mutually exclusive. | Gemini/ADK proposal boundary and orchestration. |
| 2E | A new chat can use bounded active notes, ask for a source choice when ambiguous, and return inspectable application-derived receipts. | Note-first continuity resolver. |
| 2F | An explicit reference to the immediately previous chat can use one ownership-validated bounded excerpt and return a prior-chat receipt. | Prior-session continuity. |
| 2G | The browser exposes the complete Notes lifecycle and continuity controls without conflating Notes with Memory. | Notes UI and receipt inspection. |
| 2H | Google OIDC live tests prove the full lifecycle, cross-chat continuity, ambiguity, and isolation; documentation records only observed claims. | Judge-grade evidence and phase closure. |

## Global constraints and preserved invariants

- Execute passes sequentially. Every source-changing pass requires separate
  explicit approval before its first RED test.
- Stop each source-changing pass at **implemented, pending manual
  verification**. Checkpoint only after the user accepts its manual targets.
- Profile memory remains user-global and allowlisted. Collaborative notes
  remain private to one authenticated user and one workspace.
- Only `decision`, `requirement`, `constraint`, `task_state`, and
  `working_context` are supported note kinds.
- Title remains 1-120 normalized Unicode characters; body remains 1-2,000;
  source messages remain 1-5 from one owned source session.
- Pending proposals expire after 24 elapsed hours. Store at most 10 unresolved
  proposals and 50 active notes per user/workspace. Return at most 50 list
  records.
- A proposal is not active. Approval is an explicit structured decision and
  creates the active projection exactly once.
- One ordinary turn may create at most one note proposal. A turn may not
  create both a note proposal and profile-memory proposal or clarification.
- A structured note-decision turn may not route to an expert, create an
  artifact, record artifact feedback, or create another durable proposal.
- The current user message is the only user authority for a proposal or new
  action. Model output, expert output, artifacts, retrieved notes, and prior
  transcripts are untrusted evidence only.
- User, workspace, session, message, proposal, note, event, revision, and
  receipt identifiers are application-owned. The model never authors them.
- Existing session ownership checks run before source-message or prior-history
  reads. Cross-owner/workspace failures do not reveal existence.
- Correction is a new pending proposal bound to an expected note ID and
  revision. Approval conflicts if the note changed.
- Archive removes a note from continuity while preserving it for inspection;
  restore makes the same approved revision eligible again.
- Hard deletion removes note, proposal, and content-bearing lifecycle history
  from ordinary reads and retrieval immediately. It does not delete the source
  chat.
- Notes and transcript content, titles, profile values, prompts, Google
  subjects, tokens, and secrets never enter application logs.
- No embeddings, vector database, transcript-wide semantic scan, automatic
  transcript summarization, shared-workspace ACL, background job, or new
  external dependency belongs in Phase 2.
- Exact replay returns the originally stored response and receipts; it does not
  rerun proposal generation or continuity selection against newer state.
- Browser code calls same-origin FastAPI routes only and never Firestore,
  Vertex AI, or Google provider APIs directly except the existing OIDC flow.

---

## Pass 2A - Note Contracts and Persistence Foundation

### Goal and reviewable outcome

Complete the persistence-independent model work and add transactional
Firestore primitives for one pending proposal, one active projection, and
immutable lifecycle events. There is no public route and no Gemini tool in
this pass. Review is based on exact serialized contracts, Firestore path
evidence, ownership/provenance denial tests, and atomic/idempotent behavior.

### Expected file boundary

- Modify `collaborative_note_policy.py`.
- Modify `schemas.py`.
- Create `collaborative_notes.py` for deterministic IDs, proposal leases,
  event vocabulary, and persistence-domain helpers.
- Modify `database.py`.
- Modify `firestore.indexes.json` only if a query introduced in this pass
  requires an explicit index or content-field exemption.
- Modify `tests/test_collaborative_note_policy.py`.
- Modify `tests/test_collaborative_note_schemas.py`.
- Create `tests/test_collaborative_notes.py`.
- Create `tests/test_collaborative_note_database.py`.
- Modify `tests/test_firestore_indexes.py` only when the index file changes.

Do not change `main.py`, supervisor/runtime modules, chat contracts, or
frontend files in 2A.

### Required contracts

- Add required `note_contract_version="1.0"` to persisted/public lifecycle
  models where the approved earlier model pass intentionally deferred it.
- Add strict `CollaborativeNoteEvent` and bounded event types: `approved`,
  `corrected`, `superseded`, `archived`, `restored`, `deleted`.
- Add bounded proposal, mutation, active-note, and event receipt models needed
  by later chat and API passes; receipts expose human content only where the
  user is authorized to inspect it.
- Derive proposal, note, and event IDs from server-owned provenance and
  idempotency inputs. Retry identity must not depend on model-generated IDs.
- Persist beneath
  `users/{user_id}/workspaces/{workspace_id}/note_proposals`,
  `collaborative_notes`, and each note's `events` subcollection.
- Validate that every source message exists in the claimed source session and
  that the session's stored user/workspace match before proposal persistence.
- Enforce current-message inclusion for ordinary one-message proposals.
- Reject prohibited obvious credential/secret patterns conservatively without
  claiming perfect secret detection.
- Enforce proposal and active-note limits transactionally.
- Build atomic, idempotent primitives for proposal creation and lifecycle
  transitions; public exposure remains deferred.

### TDD tasks

1. **RED contract cycles:** Extend schema/policy tests one behavior at a time
   for version fields, event vocabulary, event relationships, normalized
   serialization, deleted-content omission, receipt bounds, and prohibited
   credential examples. Observe each expected failure before implementation.
2. **GREEN contract implementation:** Add only the strict models and helpers
   required by each RED cycle. Preserve the accepted 1A normalization behavior.
3. **RED identity cycles:** Add deterministic-ID tests proving equal retries
   derive equal IDs and changed owner/workspace/session/message/content or
   expected revision derives a different immutable identity.
4. **GREEN identity implementation:** Implement pure deterministic helpers in
   `collaborative_notes.py` without Firestore access.
5. **RED persistence cycles:** Using the existing fake Firestore transaction
   pattern, prove source ownership, source-message existence, pending expiry,
   unresolved/active limits, idempotent retry, changed retry conflict, atomic
   event/projection writes, stale correction conflict, archive/restore state,
   hard deletion, and content-safe failures.
6. **GREEN persistence implementation:** Add minimal `MemoryEngine` note
   methods and typed domain results. Keep all owner/workspace path construction
   inside the persistence boundary.
7. **REFACTOR:** Consolidate only note-specific transaction parsing and update
   helpers while tests remain green. Do not generalize memory, artifacts, and
   notes into one generic persistence engine.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_collaborative_note_policy.py \
  tests/test_collaborative_note_schemas.py \
  tests/test_collaborative_notes.py \
  tests/test_collaborative_note_database.py \
  tests/test_chat_turn_database.py \
  tests/test_firestore_indexes.py
venv/bin/python -m compileall -q \
  collaborative_note_policy.py collaborative_notes.py schemas.py database.py
git diff --check
```

The full suite is unnecessary because 2A has no public route or runtime
consumer. Existing chat-turn database tests are included because source
ownership and Firestore transaction helpers are shared risk surfaces.

### Manual acceptance targets

1. Inspect one serialized pending proposal, active note, and lifecycle event;
   confirm human content, versions, provenance, revision, and timestamps are
   exact and no Firestore path or Google subject is public.
2. Inspect the focused test output for an owned proposal, cross-user denial,
   cross-workspace denial, stale correction, and hard deletion.
3. Confirm no `/workspace` behavior or public API changed.

Stop after the 2A report and wait for acceptance/checkpoint approval.

---

## Pass 2B - Authorized Note Read and Direct Lifecycle API

### Goal and user-visible outcome

Expose deterministic, authenticated backend operations to list and inspect
notes, create a correction proposal from exact user-reviewed content, archive,
restore, and delete. This pass provides API-observable lifecycle behavior but
does not yet add chat approval/rejection, natural proposals, continuity, or UI.

### Expected file boundary

- Create `collaborative_note_service.py`.
- Modify `schemas.py`.
- Modify `database.py` only for gaps exposed by service/API tests.
- Modify `main.py`.
- Create `tests/test_collaborative_note_service.py`.
- Extend `tests/test_collaborative_note_database.py` only for newly exposed
  pagination/read behavior.
- Modify `tests/test_main.py`.

### Public operations

- `GET /api/users/{user_id}/projects/{project_id}/notes`
- `GET /api/users/{user_id}/projects/{project_id}/notes/{note_id}`
- `POST /api/users/{user_id}/projects/{project_id}/notes/{note_id}/corrections`
- `POST /api/users/{user_id}/projects/{project_id}/notes/{note_id}/archive`
- `POST /api/users/{user_id}/projects/{project_id}/notes/{note_id}/restore`
- `DELETE /api/users/{user_id}/projects/{project_id}/notes/{note_id}`

The list defaults to active notes, uses a bounded server cursor, and requires
an explicit archived filter. Detail includes bounded history and source
availability, not source-message text. Correction creates a pending proposal
bound to `expected_note_id` and `expected_revision`; it does not alter the
active note. Archive, restore, and delete require an expected revision so
stale browser state cannot silently win.

### TDD tasks

1. Write RED service tests for identity derivation, list/detail projection,
   cursor bounds, correction proposal validation, lifecycle idempotency,
   revision conflicts, source-unavailable projection, and deleted-content
   absence.
2. Implement the minimum service commands/results over the 2A database
   boundary; services accept effective authenticated identity, never trust
   route IDs as identity.
3. Write RED FastAPI tests for Google/local identity resolution, route/body
   mismatch, active/archived filters, 404/409/422 translation, cross-scope
   unavailable behavior, and content-safe error logging.
4. Implement the six bounded routes using existing `_resolve_effective_*` and
   error translation patterns.
5. Refactor duplicated note HTTP mapping only after GREEN; do not change
   memory or artifact API semantics.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_collaborative_note_policy.py \
  tests/test_collaborative_note_schemas.py \
  tests/test_collaborative_note_database.py \
  tests/test_collaborative_note_service.py \
  tests/test_main.py \
  tests/test_auth.py
venv/bin/python -m compileall -q \
  collaborative_note_service.py database.py schemas.py main.py
git diff --check
```

### Manual acceptance targets

Use Google OIDC and an API client against localhost:

1. List active and archived notes and inspect one detail record.
2. Create a correction proposal and confirm the active note is unchanged.
3. Archive and restore with the expected revision; repeat an identical action
   and inspect idempotent behavior.
4. Delete a note and confirm list/detail no longer reveal content.
5. Attempt the same IDs under another workspace and confirm unavailable-style
   responses reveal no content or existence.

Stop after the 2B report and wait for acceptance/checkpoint approval.

---

## Pass 2C - Structured Note Decisions and Retry-Safe Chat Effects

### Goal and user-visible outcome

Allow explicit approval or rejection of a pending note proposal through
`POST /api/chat`. A completed decision is persisted before Agent Col responds,
appears in success or partial-failure output, and replays exactly once.

### Expected file boundary

- Modify `schemas.py`.
- Modify `chat_turns.py`.
- Modify `database.py`.
- Modify `collaborative_note_service.py`.
- Modify `agent_col_turn_service.py`.
- Modify `agent_col_responder.py` and `supervisor.py` only for truthful
  precompleted decision instructions.
- Modify `main.py`.
- Create `tests/test_collaborative_note_chat_turns.py` if keeping note ledger
  scenarios separate is clearer than expanding existing large files.
- Modify `tests/test_chat_turns.py`.
- Modify `tests/test_chat_turn_database.py`.
- Modify `tests/test_agent_col_turn_service.py`.
- Modify `tests/test_agent_col_responder.py`.
- Modify `tests/test_main.py`.

### Required behavior

- Add one `collaborative_note_decision` request field containing a server-issued
  proposal ID and `approve` or `reject`.
- Include it in structured-decision mutual exclusion with memory,
  clarification selection, and artifact feedback.
- Approval verifies proposal owner/workspace, pending/unexpired state,
  provenance, expected revision, and turn lease before atomically writing the
  note/event and chat-turn receipt.
- Rejection resolves the proposal without creating an active note or retaining
  rejected content in a lifecycle event.
- Chat-turn claim/reclaim/replay and response completion preserve at most one
  note proposal/mutation receipt.
- Responder timeout/failure after the effect returns the authoritative partial
  receipt. Retry cannot duplicate a note, event, or revision.
- Structured note decisions bypass speculative routing and cannot create a
  second effect.

### TDD tasks

1. RED schema/request tests for four-way structured-decision exclusivity and
   strict note decision serialization.
2. GREEN minimal request contracts.
3. RED database ledger tests for approval, rejection, lease loss, reclaim,
   completed replay, changed-key conflict, responder failure, timeout, and
   note/memory/artifact effect coexistence denial.
4. GREEN atomic decision/ledger persistence and recovery.
5. RED service/turn/API tests for deterministic decision execution,
   precompleted receipt propagation, truthful responder context, success and
   partial-failure projection.
6. GREEN orchestration and FastAPI integration.
7. REFACTOR stable receipt merging only after all focused tests pass.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_collaborative_note_schemas.py \
  tests/test_collaborative_note_database.py \
  tests/test_collaborative_note_service.py \
  tests/test_collaborative_note_chat_turns.py \
  tests/test_chat_turns.py \
  tests/test_chat_turn_database.py \
  tests/test_agent_col_responder.py \
  tests/test_agent_col_turn_service.py \
  tests/test_main.py
venv/bin/python -m compileall -q \
  schemas.py chat_turns.py database.py collaborative_note_service.py \
  agent_col_turn_service.py agent_col_responder.py supervisor.py main.py
git diff --check
```

If the separate `tests/test_collaborative_note_chat_turns.py` is not needed,
omit it from the command rather than creating an empty organizational file.

### Manual acceptance targets

1. Submit one structured approval and inspect one active revision and one
   approval event.
2. Retry the exact request and confirm the same receipt with no duplicate.
3. Reject another proposal and confirm no active note exists.
4. Force responder failure after a completed decision and confirm the partial
   response tells the truth and retry reuses the completed effect.

Stop after the 2C report and wait for acceptance/checkpoint approval.

---

## Pass 2D - Natural Workspace-Note Proposal Cutover

### Goal and user-visible outcome

An ordinary current user message such as “Remember that this workspace must
use API version 2” can create one exact pending collaborative-note proposal.
Agent Col states that review is required and never claims the note is active.

### Expected file boundary

- Create `collaborative_note_candidates.py` for a strict provider-facing
  proposal/no-effect decision contract.
- Create `collaborative_note_tool.py`.
- Modify `collaborative_note_service.py`.
- Modify `supervisor.py`.
- Modify `supervisor_runtime.py`.
- Modify `agent_col_turn_service.py`.
- Modify `chat_turns.py` and `database.py` for proposal effect recovery.
- Modify `schemas.py` and `main.py` for public proposal receipts.
- Create `tests/test_collaborative_note_candidates.py`.
- Create `tests/test_collaborative_note_tool.py`.
- Modify directly affected supervisor, runtime, turn, database, schema, and
  FastAPI tests.

### Required behavior

- The provider supplies only note kind, bounded title/body, and exact evidence
  text from the current user message. Application state supplies every ID,
  owner, workspace, source message, timestamp, revision, and receipt.
- The proposal tool is separate from profile-memory persistence. Supervisor
  instructions distinguish global preference, session-only instruction, and
  workspace note before calling either governed tool.
- The existing memory `workspace_note` no-effect classification remains a safe
  fallback; it must not itself claim or create a note.
- The note tool rejects candidates not grounded in the current message,
  credentials/secrets, retrieved context, expert output, artifact content, or
  structured-decision turns.
- Atomic chat-turn guards enforce zero-or-one durable proposal across memory,
  memory clarification, note, artifact, feedback, and expert boundaries even
  if a provider attempts conflicting calls.
- Proposal receipts propagate through supervisor runtime, turn result,
  partial failure, lease reclaim, completed replay, and `ChatResponse`.
- Agent Col can proactively offer a consequential note, but version 1 creates
  it only when the current user message explicitly adopts the content or asks
  to note/record/retain it. Broader autonomous inference is excluded from this
  contest build because it cannot satisfy the current-message provenance rule
  reliably.

### TDD tasks

1. RED provider-schema tests for every note kind, exact evidence, title/body
   bounds, no-effect outcomes, malformed output, secret examples, and strict
   unknown-field rejection.
2. GREEN the smallest discriminated provider contract and canonical parser.
3. RED tool/service tests proving server-owned provenance, current-message
   grounding, proposal limit, correction separation, structured-turn denial,
   and no activation.
4. GREEN the application-governed proposal tool and service path.
5. RED runtime/ledger/API tests for one proposal, conflicting tool calls,
   retries, reclaim, replay, timeout, responder failure, and truthful public
   receipts.
6. GREEN supervisor/runtime/turn/API propagation and instructions.
7. REFACTOR receipt parsing/merging only while the zero-or-one invariant stays
   green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_collaborative_note_policy.py \
  tests/test_collaborative_note_candidates.py \
  tests/test_collaborative_note_tool.py \
  tests/test_collaborative_note_service.py \
  tests/test_collaborative_note_database.py \
  tests/test_supervisor.py \
  tests/test_supervisor_runtime.py \
  tests/test_agent_col_turn_service.py \
  tests/test_chat_turns.py \
  tests/test_chat_turn_database.py \
  tests/test_main.py \
  tests/test_memory_proposal_tool.py
venv/bin/python -m compileall -q \
  collaborative_note_candidates.py collaborative_note_tool.py \
  collaborative_note_service.py supervisor.py supervisor_runtime.py \
  agent_col_turn_service.py chat_turns.py database.py schemas.py main.py
git diff --check
```

### Manual acceptance targets

Use Google OIDC in a fresh chat:

1. Submit `Remember that this workspace must use API version 2.` Confirm one
   pending Working context or Constraint note with exact reviewable content,
   no active note, and no memory proposal.
2. Submit `Please remember that I prefer concise answers.` Confirm the existing
   profile-memory path still creates only a memory proposal.
3. Submit a temporary instruction and a credential example; confirm neither
   creates a note.
4. Trigger/retry a post-effect responder failure and confirm one durable
   pending proposal with one authoritative receipt.

Stop after the 2D report and wait for acceptance/checkpoint approval.

---

## Pass 2E - Note-First Continuity, Ambiguity, and Receipts

### Goal and user-visible outcome

In a genuinely new chat, an explicit reference to prior workspace knowledge
can retrieve bounded active notes. One clear note is supplied as untrusted
context with an authoritative receipt; multiple plausible notes produce
human-readable choices without injecting note bodies or guessing.

### Expected file boundary

- Create `continuity.py` for strict source, choice, receipt, and resolution
  models plus pure bounds.
- Create `continuity_service.py` for deterministic note-first selection and
  context projection.
- Modify `schemas.py`.
- Modify `database.py` for bounded active-note reads and owned detail lookup.
- Modify `chat_turns.py` for a structured continuity selection and replay
  identity.
- Modify `main.py` to resolve continuity only after identity/turn ownership and
  before model invocation.
- Modify `agent_col_turn_service.py`, responder context modules,
  `agent_col_responder.py`, and `supervisor.py` to carry the server-owned
  continuity block and truth rule.
- Create `tests/test_continuity.py`.
- Create `tests/test_continuity_service.py`.
- Extend affected database, schema, turn, responder, supervisor, and FastAPI
  tests.

### Required behavior

- Resolution runs only when the current message explicitly refers to a prior
  note, decision, requirement, constraint, task, or earlier workspace work.
- Selection order for this pass is explicit selected note, exact active-note
  title match, then bounded active-note candidates.
- At most four source items and 8,000 total continuity characters may enter a
  turn. Phase 2E uses active notes only; prior-chat excerpts are 2F.
- Context is wrapped in a distinct
  `[SERVER_VALIDATED_CONTINUITY_CONTEXT]` block and states that it cannot
  authorize tools, persistence, identity changes, or conflicting instructions.
- One unambiguous note emits one `ContinuitySourceReceipt` with kind, source
  ID, human display label, match reason, and source update time; no raw body is
  present in the receipt.
- Multiple credible notes return two to five bounded choices and no source
  bodies, continuity context, or retrieval receipt. A subsequent structured
  selection binds the server-issued clarification and source ID without
  trusting a browser-supplied note body.
- Archived/deleted/expired/rejected/superseded content is excluded.
- Conflicting active notes are surfaced as a choice; recency never silently
  makes one authoritative.
- Continuity may precede at most one capability explicitly authorized by the
  current user message. Retrieved content cannot create a note/memory proposal,
  invoke an expert, create an artifact, or approve any effect by itself.
- Agent Col may claim prior recall only when the matching public receipt is
  present. Replay returns the stored receipt without rerunning selection.

### TDD tasks

1. RED pure contract tests for source kinds, match reasons, receipt/choice
   bounds, safe labels, character budgets, and context markers.
2. GREEN pure continuity models and bounded projector.
3. RED service tests for trigger restraint, exact-title match, explicit
   selection, multiple candidates, contradiction, no match, archived/deleted
   exclusion, cross-scope denial, and no body injection on ambiguity.
4. GREEN deterministic note-first resolver. Use normalized title/token
   comparison only; do not add model ranking or semantic transcript search.
5. RED orchestration tests for current-message authority, one allowed routed
   capability after retrieval, forbidden retrieved authorization, truth rule,
   success/partial/replay receipts, and structured selection identity.
6. GREEN context and receipt propagation across FastAPI, turn service,
   routing, and responder.
7. REFACTOR only after the bounded-source and authority tests stay green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_continuity.py \
  tests/test_continuity_service.py \
  tests/test_collaborative_note_database.py \
  tests/test_schemas.py \
  tests/test_chat_turns.py \
  tests/test_chat_turn_database.py \
  tests/test_agent_col_responder_context.py \
  tests/test_agent_col_responder_context_v2.py \
  tests/test_agent_col_responder_context_v3.py \
  tests/test_agent_col_responder.py \
  tests/test_supervisor.py \
  tests/test_supervisor_runtime.py \
  tests/test_agent_col_turn_service.py \
  tests/test_main.py
venv/bin/python -m compileall -q \
  continuity.py continuity_service.py schemas.py database.py chat_turns.py \
  main.py agent_col_turn_service.py agent_col_responder.py supervisor.py
git diff --check
```

The broad responder-context set is required because continuity is a new
cross-cutting model-input authority consumed by direct and routed responses.

### Manual acceptance targets

1. Approve `Password generator requirements` in chat A, start chat B, and ask
   what constraints were agreed. Confirm one note receipt and a correct answer.
2. Create two similarly named active notes and ask an ambiguous question.
   Confirm two bounded human choices, no guessed answer, and no receipt yet.
3. Select one choice and confirm one receipt and only that note's content.
4. Archive the selected note and confirm it is excluded; restore it and confirm
   it is eligible again.
5. Repeat in another workspace and confirm no note or existence disclosure.

Stop after the 2E report and wait for acceptance/checkpoint approval.

---

## Pass 2F - Immediately Previous Chat Retrieval

### Goal and user-visible outcome

When the current message explicitly says “the last conversation” or an
equivalent bounded recency reference, Agent Col can use one small excerpt from
the immediately previous owned chat in the same workspace and display one
authoritative prior-chat receipt.

### Expected file boundary

- Modify `continuity.py`.
- Modify `continuity_service.py`.
- Modify `database.py`.
- Modify `firestore.indexes.json` and `tests/test_firestore_indexes.py` if the
  production query needs a composite owner/workspace/update index.
- Modify `schemas.py` only if the accepted 2E receipt contract needs the
  already planned `chat_session` source variant enabled.
- Modify directly affected continuity, database, orchestration, and FastAPI
  tests.

### Required behavior

- Run only for explicit recency language in the current message.
- Resolve the most recently updated prior session for the effective user and
  workspace, excluding the current session.
- Validate owner/workspace before reading messages.
- Supply at most one prior-session excerpt in this Winning Core path, with at
  most eight chronological messages and 3,000 characters, preserving whole
  message boundaries. The approved overall two-excerpt/four-source/8,000
  character ceilings remain hard upper bounds for later extension.
- Exclude system/hidden content and mark user/model transcript text as
  untrusted data.
- Emit `source_kind="chat_session"` and
  `match_reason="previous_chat"` only when an excerpt was actually supplied.
- Missing previous chat produces a bounded not-found/clarifying response and
  no receipt.
- A retrieved old instruction cannot authorize an action in the current turn.
- Exact replay does not switch to a newer “previous” chat.

### TDD tasks

1. RED database query tests for current-session exclusion, deterministic
   newest ordering, owner/workspace isolation, missing timestamps, bounded
   scan/query behavior, and history ownership validation before content read.
2. GREEN the minimum bounded previous-session read and required index.
3. RED excerpt tests for eight-message, 3,000-character, whole-message,
   chronological, role, and global-context bounds.
4. GREEN previous-chat projection in `continuity_service.py`.
5. RED orchestration/API tests for explicit trigger, no incidental retrieval,
   missing source, receipt truth, authority restraint, and replay stability.
6. GREEN integration through the already accepted 2E context/receipt path.
7. REFACTOR shared note/chat source budgeting only after all source-specific
   bounds stay green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_continuity.py \
  tests/test_continuity_service.py \
  tests/test_collaborative_note_database.py \
  tests/test_chat_turn_database.py \
  tests/test_firestore_indexes.py \
  tests/test_agent_col_turn_service.py \
  tests/test_supervisor.py \
  tests/test_agent_col_responder.py \
  tests/test_main.py
venv/bin/python -m compileall -q \
  continuity.py continuity_service.py database.py schemas.py main.py
git diff --check
```

### Manual acceptance targets

1. In chat A, request a bounded script. Start genuinely new chat B and ask,
   `What script did I request in our last conversation?`
2. Confirm Agent Col answers from one bounded excerpt and displays `Used your
   previous conversation` or the owned human chat label.
3. Create chat C, then exact-retry chat B's completed request; confirm replay
   still identifies the original source rather than chat C.
4. Repeat with no prior chat, another workspace, and another user; confirm no
   receipt and no source disclosure.

Stop after the 2F report and wait for acceptance/checkpoint approval.

---

## Pass 2G - Complete Notes and Continuity Browser Experience

### Goal and user-visible outcome

The workspace gains a Notes section distinct from Memory. Users can review
pending notes, inspect active/archived notes, perform every lifecycle action,
answer continuity choices, and open authorized receipt sources from the
conversation.

### Expected file boundary

- Create `frontend/notes-view.mjs`.
- Modify `frontend/api.mjs`.
- Modify `frontend/requests.mjs`.
- Modify `frontend/state.mjs`.
- Modify `frontend/chat-view.mjs`.
- Modify `frontend/app.mjs`.
- Modify `frontend/workspace-layout.mjs`.
- Modify `frontend/index.html`.
- Modify `frontend/styles.css`.
- Create `tests/frontend/notes-view.test.mjs`.
- Modify `tests/frontend/api.test.mjs`.
- Modify `tests/frontend/requests.test.mjs`.
- Modify `tests/frontend/state.test.mjs`.
- Modify `tests/frontend/chat-view.test.mjs`.
- Modify `tests/frontend/workspace-layout.test.mjs`.
- Modify `tests/frontend/workspace-static.test.mjs`.
- Modify `tests/frontend/workspace-view.test.mjs` only if shared workspace
  rendering changes.

Treat Python source as a regression surface. Stop and revise if the browser
requires a backend contract change.

### Required behavior

- Add an independent Notes drawer section; do not place notes inside Memory or
  nest Notes cards inside another card.
- Pending notes show kind, exact title/body, source chat label/availability,
  expiry, Approve, and Reject.
- Active note detail supports correction proposal, archive, and delete.
- Archived listing is explicit and supports restore. Deleted content vanishes.
- Correction inputs enforce title/body bounds before transport but backend
  validation remains authoritative.
- Loading, empty, pending, active, archived, expired, conflict, and error states
  are visible in text and not color alone.
- Continuity ambiguity choices are native buttons, keyboard operable, bounded,
  and show human labels without raw IDs.
- Transcript receipts use separate labels for `Memory proposal`, `Adaptation`,
  `Note proposal`, `Note updated`, `Used note`, and `Used prior chat`.
- Selecting a receipt loads an authorized note or chat detail without changing
  the active conversation.
- Controls disable during the relevant request and prevent duplicate
  submission; exact retry continues through the existing frozen request path.
- Existing independent drawer/chat/artifact scrolling, responsive layout,
  focus visibility, wrapping, and Google OIDC behavior remain unchanged.

### TDD tasks

1. RED API/request tests for every notes route, correction body, structured
   approval/rejection, continuity selection, same-origin paths, IDs, revisions,
   and frozen exact-retry requests.
2. GREEN minimal transport/request builders.
3. RED state tests for notes list/detail, status filters, proposal/lifecycle
   refresh, conflict/error preservation, workspace switch, new conversation,
   receipt source selection, and continuity choices.
4. GREEN immutable state transitions and refresh planning.
5. RED Notes view tests for all lifecycle states, exact content, controls,
   disabled behavior, source availability, archived toggle, and no raw-ID
   primacy.
6. GREEN `notes-view.mjs` and app wiring.
7. RED chat/layout/static tests for separate receipts, ambiguity controls,
   keyboard semantics, section registration, long-text wrapping, desktop and
   mobile containment, and no overlap.
8. GREEN focused DOM/styles/layout changes.
9. REFACTOR only view-local duplication while all frontend tests stay green.

### Focused automated verification

```bash
node --test \
  tests/frontend/api.test.mjs \
  tests/frontend/requests.test.mjs \
  tests/frontend/state.test.mjs \
  tests/frontend/notes-view.test.mjs \
  tests/frontend/chat-view.test.mjs \
  tests/frontend/memory-view.test.mjs \
  tests/frontend/chats-view.test.mjs \
  tests/frontend/workspace-layout.test.mjs \
  tests/frontend/workspace-static.test.mjs \
  tests/frontend/workspace-view.test.mjs
venv/bin/pytest -q \
  tests/test_schemas.py \
  tests/test_main.py \
  tests/test_chat_turns.py
git diff --check
```

Use a focused browser verification at desktop and mobile sizes after the test
runner passes. The backend regression set is required because frontend request
builders directly consume shared FastAPI/chat schemas.

### Manual acceptance targets

Use Google OIDC at `/workspace` on desktop and a narrow mobile viewport:

1. Create one natural pending note and confirm exact title/body before
   approval.
2. Approve it in the Notes surface and inspect source provenance.
3. Propose and approve a correction; confirm only the new revision is active.
4. Archive, list archived, restore, and delete; confirm each visible state.
5. Trigger ambiguity, choose a source with keyboard controls, and inspect the
   resulting receipt without leaving the active chat.
6. Use a prior-chat receipt and open its authorized chat detail without
   changing the active conversation.
7. Confirm long content wraps, controls do not shift layout, drawers scroll
   independently, focus is visible, and no controls overlap at either viewport.
8. Confirm Memory still shows profile preferences only.

Stop after the 2G report and wait for acceptance/checkpoint approval.

---

## Pass 2H - Cross-Chat Live Proof and Phase Closure

### Goal and user-visible outcome

Prove the accepted Phase 2 behavior against live Gemini, Firestore, Google
OIDC, distinct chat sessions, multiple workspaces, and controlled failures.
Reconcile documentation to observed behavior without adding new source
features.

### Expected file boundary

- Modify `docs/aug-25-2026-final-checklist.md`.
- Modify current status/evidence documentation identified during the closure
  audit, likely `AGENT_COL_IDENTITY_AND_ALIGNMENT.md` and
  `BACKEND_FRONTEND_INTEGRATION_CONTRACT_INVENTORY.md`.
- Add bounded screenshot/log evidence under the repository's established
  evidence location only after checking that it contains no tokens, subjects,
  prompts, note bodies not intended for publication, or other private data.
- No source-code change is expected. Any live failure triggers systematic
  debugging and a separately approved correction pass.

### Evidence sequence

1. In session A, establish password-generator requirements and create one
   exact pending note.
2. Approve and inspect the note.
3. In session B, retrieve the active note and inspect one note receipt.
4. In session C, retrieve the immediately previous chat and inspect one chat
   receipt.
5. Create an ambiguous pair and prove source clarification without body
   leakage.
6. Correct the authoritative note and prove only the corrected revision is
   retrieved.
7. Archive, restore, and delete; prove retrieval eligibility changes at each
   state.
8. Reject a separate proposal and prove it never becomes active.
9. Force one post-effect responder failure and prove the completed receipt and
   exact retry remain truthful and nonduplicating.
10. Repeat the lookup under another workspace and test principal; prove
    unavailable behavior without existence disclosure.

### Verification before live evidence

Because Phase 2 changes shared schemas, persistence, ownership, orchestration,
model context, public APIs, and the browser, focused pass tests are no longer
sufficient for phase closure. Run the complete repository suite once:

```bash
venv/bin/pytest -q
node --test tests/frontend/*.test.mjs
venv/bin/python -m compileall -q .
git diff --check
```

Inspect counts, warnings, skips, and exit codes. Do not describe provider-live
behavior as proven by deterministic tests.

### Manual acceptance targets

- Complete all ten evidence steps with genuinely distinct session IDs in
  Google OIDC mode.
- Inspect Firestore state for proposal, active projection, revision, event,
  archive, and deletion behavior without recording private values in logs.
- Confirm Agent Col's language is collaborative and truthful: pending is not
  “remembered,” a receipt supports every recall claim, and ambiguity asks
  rather than guesses.
- Confirm the judged story is visibly “Agent Col leads and takes governed
  notes,” not generic chat history or silent model memory.

Only after user acceptance may Phase 2 be marked complete and checkpointed.
Phase 3 planning remains a separate approval-gated activity.

## Phase-wide risks and trade-offs

- **Provider variability:** Strict candidate schemas, local validation, and
  persisted receipts reduce but do not eliminate live Gemini variation. Live
  acceptance remains decisive.
- **Atomicity complexity:** Note effects cross proposal, projection, event, and
  chat-turn records. The plan deliberately establishes persistence before
  orchestration to prevent partial authority.
- **Firestore query/index behavior:** Emulator/fake tests do not prove hosted
  index readiness. Any production query must be tested against the configured
  Google project before its pass is accepted.
- **Hard deletion:** Firestore multi-document deletion is bounded but cannot be
  treated as a single unlimited transaction. The implementation must fail
  closed and report incomplete deletion without restoring content to
  retrieval.
- **Secret detection:** Obvious credentials can be rejected, but the product
  must not claim perfect sensitive-data classification. User review and
  deletion remain essential controls.
- **Deterministic relevance:** Title/token matching is less flexible than
  embeddings, but it is inspectable, bounded, deletable, and sufficient for
  the contest proof. Arbitrary semantic recall is explicitly excluded.
- **Plan age:** Phase 1 may alter frontend or chat contracts before Phase 2
  starts. The mandatory baseline re-audit prevents this plan from overriding
  accepted newer source.

## Stop and revise conditions

Stop the current pass and return with evidence plus a revised plan if:

- Phase 1 is not fully accepted and checkpointed;
- current source at pass start materially differs from this file map or
  contract baseline;
- source provenance requires reading history before ownership validation;
- a note would need to enter user-global profile memory;
- any path would activate or correct a note without explicit review;
- the model would need to author identity, provenance, revision, or receipt
  IDs;
- retrieved content would need to authorize a tool or durable side effect;
- one turn could persist both memory and note effects;
- correction would overwrite history without an event and expected revision;
- hard deletion cannot immediately exclude content from retrieval;
- implementation requires embeddings, a vector database, automatic transcript
  summaries, shared-workspace ACLs, Cloud Tasks, or a new dependency;
- note/transcript content must enter logs;
- a backend contract must change during frontend-only Pass 2G;
- three approved correction attempts fail for the same root cause.

## Approval and checkpoint sequence

1. Repository owner reviews and approves or revises this Phase 2 plan.
2. After approval, checkpoint this documentation-only plan to `origin/main`.
3. After the Phase 2 plan checkpoint is confirmed, begin the separately gated
   Phase 3 planning workflow requested by the repository owner.
4. Before Phase 2 implementation, complete and checkpoint all remaining Phase
   1 passes.
5. Re-audit Phase 2 against the accepted Phase 1 commit and present Pass 2A for
   explicit implementation approval.
6. For each pass 2A-2H: RED, verify RED, GREEN, verify GREEN, refactor, focused
   verification, report, manual acceptance, then explicit checkpoint approval.
7. Mark Phase 2 complete only after 2H manual evidence is accepted and pushed.
