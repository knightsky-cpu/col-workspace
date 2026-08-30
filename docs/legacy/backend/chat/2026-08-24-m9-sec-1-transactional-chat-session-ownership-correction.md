# M9-SEC.1 Transactional Chat Session Ownership Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent any caller from reading, claiming, or appending to an existing chat session unless the session's stored user and workspace exactly match the request's resolved user and workspace.

**Architecture:** Keep authenticated identity resolution in FastAPI, but make Firestore session ownership authoritative at every history and write boundary. Introduce a session-specific ownership error, validate existing session metadata inside retry-safe claim and headerless save transactions, validate before every history read, require the retry-safe idempotent path in Google mode, and return a content-safe unavailable response for ownership mismatches. Preserve local-development headerless compatibility only after it gains the same ownership invariant.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, async Google Cloud Firestore, pytest, httpx.

**Spec:** [`../specs/2026-08-24-m9-cont-1-continuity-domain-and-collaborative-notes-design.md`](../continuity/2026-08-24-m9-cont-1-continuity-domain-and-collaborative-notes-design.md)

## Global constraints

- Treat the effective user ID and workspace/project ID derived by `main.py` as request context, not proof that an existing session belongs to that context.
- The stored `sessions/{session_id}.user_id` and `project_id` fields are the ownership authority for an existing session.
- A new session may establish ownership once. An existing session's owner or workspace must never be rewritten by chat traffic.
- Keep security ownership separate from `ChatTurnOwnershipError`, which already means that a worker lost a turn lease.
- Return the same public unavailable response for a wrong user and a wrong workspace; do not reveal which field differed or whether another owner has the requested session.
- Fail closed on malformed existing session metadata. Do not infer ownership from messages, turn documents, request aliases, or workspace naming conventions.
- Preserve exact idempotent replay for the rightful owner, changed-request conflicts, lease behavior, artifact and memory decisions, responder-only orchestration, and current-session history bounds.
- Keep `project_id` as the internal workspace identifier. This pass does not rename or migrate Firestore collections.
- Do not add collaborative notes, cross-chat retrieval, embeddings, UI changes, Firestore indexes, session migration, or account-sharing behavior.
- Do not stage or checkpoint the implementation until the user completes manual verification and explicitly requests a GitHub checkpoint.

## Verified baseline issue

The current source has two independent ownership gaps:

1. `MemoryEngine.claim_chat_turn()` writes caller-supplied `project_id` and `user_id` to the parent session with `merge=True` without reading the existing session document inside the transaction.
2. The headerless compatibility path calls `get_chat_history(session_id)` without owner/workspace arguments, then `save_message()` merges optional caller-supplied ownership fields into the same parent session without validating its stored owner.

There is also one pre-existing focused-test defect at the accepted baseline: `test_claim_chat_turn_atomically_creates_turn_and_user_message` expects only `updated_at` in the session write, while the current committed implementation also writes project, user, preview, and role. The test fails before M9-SEC.1 begins. It must be reconciled as a test-only baseline repair before creating the security RED tests; it must not be presented as M9-SEC.1 RED evidence.

## Expected file boundary

- Modify: `chat_turns.py`
  - Define a session-specific ownership exception without changing worker lease semantics.
- Modify: `database.py`
  - Add one strict stored-session ownership validator.
  - Validate the parent session inside turn-claim and headerless-save transactions.
  - Validate the parent session before history queries.
- Modify: `synthesis_service.py`
  - Supply command user/workspace identity to bounded history reads.
- Modify: `main.py`
  - Require idempotency keys for Google-authenticated chat.
  - Supply resolved identity to history reads.
  - Translate session ownership failures to a content-safe unavailable response.
- Modify: `tests/test_chat_turn_database.py`
  - Repair the stale baseline assertion and cover transactional claim ownership.
- Modify: `tests/test_database.py`
  - Cover ownership-aware history and transactional headerless message persistence.
- Modify: `tests/test_synthesis_service.py`
  - Cover propagation of command identity to synthesis history reads.
- Modify: `tests/test_main.py`
  - Cover Google idempotency enforcement, unavailable response mapping, and no downstream access after denial.

---

## Task 0: Reconcile the pre-existing focused-test baseline

**Files:**
- Modify: `tests/test_chat_turn_database.py`

- [ ] Update `test_claim_chat_turn_atomically_creates_turn_and_user_message` so its first expected session write matches the currently committed behavior: project ID, user ID, timestamp, user-message preview, and user role.
- [ ] Run the single test and confirm it becomes green without any production-source change:

```bash
venv/bin/pytest -q tests/test_chat_turn_database.py::test_claim_chat_turn_atomically_creates_turn_and_user_message
```

- [ ] Record this as baseline reconciliation, not TDD RED or proof of the security correction.

## Task 1: Define session ownership semantics and secure retry-safe claims

**Files:**
- Modify: `tests/test_chat_turn_database.py`
- Modify: `chat_turns.py`
- Modify: `database.py`

### Contract

Add a distinct error:

```python
class ChatSessionOwnershipError(RuntimeError):
    """Raised when request identity does not own an existing session."""
```

Add a private database validator with the conceptual contract:

```python
@classmethod
def _validate_chat_session_owner(
    cls,
    document: object,
    *,
    user_id: str,
    project_id: str,
) -> None:
    ...
```

It must:

- require a mapping for every existing session document;
- require non-empty string `user_id` and `project_id` fields;
- raise `ChatSessionOwnershipError` for a valid but different owner or workspace;
- raise `ChatTurnStateError` for malformed stored session state;
- include no stored identifiers or user content in exception messages.

- [ ] **RED:** Extend the `ChatTurnStore` fixture with an async `session_ref.get` result and add tests proving:
  - a stored different user is rejected before any transaction write;
  - a stored different project/workspace is rejected before any transaction write;
  - malformed stored ownership is rejected as state corruption;
  - an exact existing owner/workspace may claim a new turn;
  - a missing parent session establishes owner/workspace metadata once.

- [ ] Run the narrow RED command and confirm the new ownership tests fail because `claim_chat_turn()` never reads the parent session:

```bash
venv/bin/pytest -q tests/test_chat_turn_database.py -k 'claim_chat_turn and session'
```

- [ ] **GREEN:** In `MemoryEngine.claim_chat_turn()`:
  - read `session_ref` inside the same Firestore transaction before all writes;
  - validate an existing session against `request.user_id` and `request.project_id`;
  - for a new session, write immutable owner/workspace fields plus current preview metadata;
  - for an existing matching session, update timestamp and preview metadata without rewriting owner/workspace;
  - retain the existing turn request identity, replay, conflict, lease, and deterministic message behavior.

- [ ] Re-run the Task 1 tests and confirm GREEN.

## Task 2: Secure history reads and headerless message writes

**Files:**
- Modify: `tests/test_database.py`
- Modify: `database.py`

### History interface

Change the history read contract to require identity:

```python
async def get_chat_history(
    self,
    session_id: str,
    limit: int | None = None,
    *,
    user_id: str,
    project_id: str,
    exclude_message_id: str | None = None,
) -> list[dict[str, object]]:
    ...
```

Behavior:

- nonexistent session: return an empty history without querying messages;
- exact owner/workspace: preserve current ascending/unbounded and newest-bounded ordering behavior;
- wrong owner/workspace: raise `ChatSessionOwnershipError` before querying messages;
- malformed existing metadata: raise `ChatTurnStateError` before querying messages.

### Headerless write interface

Make `project_id` and `user_id` required keyword arguments to `save_message()`. Replace the unchecked batch merge with one Firestore transaction that:

- reads the parent session before writing;
- establishes owner/workspace only when the parent does not exist;
- validates and preserves owner/workspace when it exists;
- writes message and session preview atomically;
- never rewrites existing owner/workspace metadata.

- [ ] **RED:** Add focused history tests for nonexistent, matching, wrong-user, wrong-workspace, and malformed sessions. Confirm wrong-identity cases fail because the current method does not read the parent.
- [ ] **RED:** Replace the current batch-oriented save test with transactional tests for new, matching, wrong-user, wrong-workspace, and malformed sessions. Confirm the denial tests fail because the current method performs an unchecked merge.
- [ ] Run the narrow RED command:

```bash
venv/bin/pytest -q tests/test_database.py -k 'chat_history or save_message'
```

- [ ] **GREEN:** Implement the required parent read, validator calls, immutable ownership writes, and current ordering/preview behavior.
- [ ] Re-run the Task 2 tests and confirm GREEN.

## Task 3: Propagate identity through synthesis history reads

**Files:**
- Modify: `tests/test_synthesis_service.py`
- Modify: `synthesis_service.py`

- [ ] **RED:** Update the synthesis database fakes to require `user_id` and `project_id`, then assert both `generate_blueprint()` and `generate_governed_blueprint()` read history with the `SynthesisCommand` identity.
- [ ] Run the focused RED command and confirm it fails because the service currently supplies only session ID and limit:

```bash
venv/bin/pytest -q tests/test_synthesis_service.py -k 'history or generate_blueprint or generate_governed_blueprint'
```

- [ ] **GREEN:** Pass `command.user_id` and `command.project_id` to both history reads. Do not change source text, history bounds, governed-memory projection, generation, validation, or persistence behavior.
- [ ] Re-run the Task 3 tests and confirm GREEN.

## Task 4: Enforce the authenticated API boundary and safe failures

**Files:**
- Modify: `tests/test_main.py`
- Modify: `main.py`

### API behavior

- In `google_oidc` mode, `POST /api/chat` without `Idempotency-Key` returns HTTP 422 before history, persistence, memory, artifact, routing, or model access.
- In `local_dev` mode, headerless compatibility remains available, but all history and message operations receive the effective local user/workspace and use Task 2's ownership checks.
- A `ChatSessionOwnershipError` from claim, history, or save returns HTTP 404 with exactly:

```json
{"detail": "Chat session is unavailable."}
```

- Do not log the requested/stored session owner, project, message content, token, or mismatching values.
- Preserve the current 409 response for idempotency conflicts and worker lease ownership changes; these are different contracts.

- [ ] **RED:** Add a Google-mode test proving a valid bearer token without an idempotency key returns 422 and touches no database, memory, artifact, router, or model service.
- [ ] **RED:** Add claim, history, user-save, and model-save error translation tests proving session ownership failures return the same 404 body and stop downstream work.
- [ ] **RED:** Update `ServiceState.get_chat_history()` and `save_message()` fakes to require and record resolved user/workspace arguments. Add assertions proving both Google-derived and local effective identities are propagated.
- [ ] Run the focused RED command:

```bash
venv/bin/pytest -q tests/test_main.py -k 'chat and (ownership or idempotency or history or save)'
```

- [ ] **GREEN:** Import and translate `ChatSessionOwnershipError`, enforce the Google-mode idempotency precondition after authentication resolution, and pass effective identity into every chat history call.
- [ ] Re-run the Task 4 tests and confirm GREEN.

## Task 5: Focused security regression verification

**Files:**
- No new files expected.

- [ ] Run the exact affected database, service, and API suites because the signature and ownership contract is shared across all chat and synthesis consumers:

```bash
venv/bin/pytest -q \
  tests/test_chat_turn_database.py \
  tests/test_database.py \
  tests/test_synthesis_service.py \
  tests/test_main.py
```

- [ ] Run static syntax/format integrity checks:

```bash
venv/bin/python -m compileall -q chat_turns.py database.py synthesis_service.py main.py
git diff --check
```

- [ ] Inspect all output, exit codes, warnings, skips, and failure counts. Do not claim a pass if the pre-existing baseline assertion or any ownership regression remains red.
- [ ] Review the final diff for content-bearing logging, accidental identifier disclosure, optional ownership arguments, unrelated refactors, or changes outside the approved file boundary.

## Manual visual/runtime verification targets

After implementation, report the pass as **implemented, pending manual verification** and give the user these exact targets:

1. **Google-owned normal chat:** Sign in through Google, enter an owned workspace, send `Explain in one sentence why session ownership matters.` Expected: one normal response, no visible ownership identifiers, and the chat remains reopenable.
2. **Google replay regression:** Use the browser's `Retry exact request` only after an induced timeout if available. Expected: the same rightful turn is reused; no duplicate user/model messages are created.
3. **Local headerless compatibility:** In local-development mode, submit one ordinary browser turn. Expected: the chat succeeds and appears only under the same local user and workspace.
4. **Cross-workspace denial:** Using a known existing local session ID, submit a direct `POST /api/chat` under a different local workspace with a fresh idempotency key. Expected: HTTP 404 with `Chat session is unavailable.`, no response content from the original session, and the original session remains accessible from its rightful workspace.
5. **Cross-user denial:** Repeat target 4 with a different local user. Expected: the same HTTP 404 body; no indication whether the session exists or which field mismatched.
6. **Regression boundary:** Reopen the rightful chat, create no note, and verify artifacts, memory decisions, chat list/detail, and current-session history still behave as before.

## Stop conditions

Stop implementation and return for revised approval if:

- existing production session documents lack usable `user_id` or `project_id` metadata in a way that would make accepted user data broadly inaccessible;
- Firestore cannot transactionally read the parent session before the existing claim/message writes without changing the persistence architecture;
- securing the headerless path requires removing it rather than preserving local compatibility;
- an ownership-safe history read requires a new index, migration, or collection layout;
- authenticated browser requests do not consistently send idempotency keys;
- the correction would require collaborative notes, cross-chat retrieval, frontend changes, or a generic authorization framework.

## Acceptance boundary

M9-SEC.1 is accepted only when automated evidence and the user's manual verification demonstrate that:

- an existing session owner/workspace cannot be overwritten by a new claim or message;
- unauthorized history is never returned;
- authenticated Google chat always uses the retry-safe claim path;
- rightful owner replay and normal local chat still work;
- public denial copy does not disclose private ownership state;
- no notes or cross-chat continuity behavior has been introduced yet.

The next pass after acceptance is **M9-NOTE.1 — Collaborative Note Models and Deterministic Validation**. It remains unapproved and must not begin automatically.
