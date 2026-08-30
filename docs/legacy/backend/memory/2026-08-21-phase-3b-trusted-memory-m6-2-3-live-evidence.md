# Trusted Memory M6.2.3 Live Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. The repository
> owner selected inline execution. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a reproducible live HTTP smoke runner for new, replay, and
conflict chat-turn paths and document the exact retry-safety contract,
Firestore layout, local commands, and troubleshooting boundaries.

**Architecture:** A standalone HTTPX CLI drives the public FastAPI boundary;
it never imports or calls `MemoryEngine`, the supervisor, or Gemini directly.
The runner generates pseudonymous locators, validates both successful bodies
as `ChatResponse`, verifies semantic JSON equality, requires the exact conflict
response, derives Firestore locators from the accepted turn-domain helper, and
prints no key, prompt, response text, or provider error body. Offline tests use
HTTPX `MockTransport`, exercising real request construction and response
parsing without network, Firestore, ADK, or Gemini access.

**Tech Stack:** Python 3.14, HTTPX 0.28.1, Pydantic v2, pytest,
pytest-asyncio, Markdown.

**Spec:**
[`docs/superpowers/specs/2026-08-20-phase-3b-trusted-memory-m6-idempotency-design.md`](2026-08-20-phase-3b-trusted-memory-m6-idempotency-design.md)

## Global constraints

- No production behavior changes: do not modify `main.py`, `database.py`,
  `chat_turns.py`, schemas, memory services, or supervisor modules.
- The runner must use `POST /api/chat`, not internal persistence methods.
- The runner uses one fresh key for first, replay, and conflict requests.
- The first and replay bodies must both validate as `ChatResponse` and compare
  equal as parsed JSON objects.
- The conflict must be HTTP `409` with exactly
  `{"detail": "Idempotency key conflicts with a different chat request."}`.
- Success is exactly the status sequence `200`, `200`, `409`.
- Output may contain only generated user/session IDs, derived Firestore
  document IDs, status codes, and `replay_equal=true`.
- Output must not contain the raw key, prompt, changed prompt, model response,
  receipt content, response headers, or raw failure bodies.
- Failure exceptions and CLI messages identify only the failing stage and safe
  status category; they do not echo request or response content.
- The runner default base URL is `http://127.0.0.1:8000` and accepts an
  explicit `--base-url` for future hosted verification.
- No dependency changes and no automatic server startup.
- Documentation distinguishes implemented local behavior from target Cloud
  Tasks, tools, authentication, and deployment behavior.
- No intermediate Git commits. Checkpoint only after manual acceptance.

## File structure

- Create `smoke_test_chat_idempotency.py`: live HTTP smoke runner and safe
  structural result.
- Create `tests/test_smoke_test_chat_idempotency.py`: offline HTTP transport,
  response-validation, status, privacy, and CLI tests.
- Create `docs/design/turn-idempotency.md`: public contract, guarantees,
  limitations, Firestore layout, and security boundary.
- Create `docs/development/local-setup.md`: verified local setup and startup.
- Create `docs/development/testing.md`: focused/full/smoke commands and what
  each proves.
- Create `docs/development/troubleshooting.md`: safe diagnosis for 409, 422,
  429, 500, 502, 504, ADC, and project configuration.
- Modify `README.md`: current implemented capability/status, smoke command,
  and documentation navigation.
- Modify `docs/architecture.md`: current durable turns and governed memory;
  clearly label target asynchronous architecture.

---

### Task 1: Offline-tested HTTP smoke contract

**Files:**

- Create: `tests/test_smoke_test_chat_idempotency.py`
- Create: `smoke_test_chat_idempotency.py`

**Interfaces:**

```python
class ChatIdempotencySmokeError(RuntimeError): ...

@dataclass(frozen=True, slots=True)
class ChatIdempotencySmokeResult:
    user_id: str
    session_id: str
    turn_id: str
    user_message_id: str
    model_message_id: str
    first_status: int
    replay_status: int
    conflict_status: int
    replay_equal: bool

    def safe_summary(self) -> str: ...

async def run_chat_idempotency_smoke(
    *,
    client: httpx.AsyncClient,
    id_factory: Callable[[], UUID] = uuid4,
) -> ChatIdempotencySmokeResult: ...

def build_parser() -> argparse.ArgumentParser: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

- [ ] Write `test_run_chat_idempotency_smoke_exercises_new_replay_and_conflict`
  first. Dynamically import the missing module so collection succeeds, use a
  fixed UUID and `httpx.MockTransport`, return literal valid `ChatResponse`
  JSON twice then the exact conflict JSON, and assert request path, identical
  key/header/body for first and replay, changed message only for conflict,
  result statuses, semantic equality, and literal derived document IDs.

- [ ] Run:

```bash
venv/bin/pytest -q tests/test_smoke_test_chat_idempotency.py::test_run_chat_idempotency_smoke_exercises_new_replay_and_conflict
```

Expected RED: ordinary assertion failure that the smoke module is missing.

- [ ] Implement the dataclass, safe domain error, three-request sequence,
  `ChatResponse.model_validate()` checks, exact conflict check, ID derivation,
  and structural result. Normalize `client.base_url` behavior by posting to
  `"/api/chat"`; tests and CLI construct clients with a base URL.

- [ ] Rerun the exact RED node. Expected GREEN: one pass with no network.

- [ ] Add parameterized RED tests for first/replay non-200 status, malformed
  success JSON, unequal replay JSON, conflict non-409, and wrong conflict body.
  Assert `ChatIdempotencySmokeError` contains the safe stage but excludes all
  private request/response markers.

- [ ] Run:

```bash
venv/bin/pytest -q tests/test_smoke_test_chat_idempotency.py -k failure
```

Expected RED: missing or unsafe failure translation.

- [ ] Implement minimal stage-specific safe errors and rerun all failure tests.
  Expected GREEN: all selected cases pass.

- [ ] Add privacy and CLI RED tests. Assert `safe_summary()` contains the three
  statuses, `replay_equal=true`, and generated Firestore locators, while
  excluding raw key, prompts, response text, receipts, and private server body.
  Patch `run_chat_idempotency_smoke()` for `main()` and assert one summary line,
  client closure, default URL, explicit `--base-url`, and exit `0`.

- [ ] Implement `build_parser()` and `main()` using `asyncio.run()`, one
  `httpx.AsyncClient(base_url=..., timeout=100.0)`, and guaranteed async client
  closure. Rerun the complete smoke-test file until GREEN.

---

### Task 2: Current-state architecture and reproducibility documentation

**Files:**

- Create: `docs/design/turn-idempotency.md`
- Create: `docs/development/local-setup.md`
- Create: `docs/development/testing.md`
- Create: `docs/development/troubleshooting.md`
- Modify: `README.md`
- Modify: `docs/architecture.md`

- [ ] Write `docs/design/turn-idempotency.md` with: optional header contract;
  validation; new/replay/conflict/in-progress outcomes; request identity;
  claim/renew/complete/release order; Firestore turn and deterministic message
  paths; safe logging; headerless limitation; effectively-once durable
  completion; and the provider crash window that can duplicate computation.

- [ ] Write `docs/development/local-setup.md` using repository-pinned commands
  for Python environment, dependencies, `.env` names without values, ADC,
  project/quota configuration, server startup, health check, idempotency smoke,
  synthesis smoke, and shutdown.

- [ ] Write `docs/development/testing.md` documenting the full suite, focused
  idempotency route tests, persistence tests, offline smoke tests, live smoke,
  and what each does and does not prove.

- [ ] Write `docs/development/troubleshooting.md` with observable causes and
  bounded actions for: missing project, ADC quota warning, invalid key `422`,
  conflict/active `409`, Gemini quota `429` surfaced as `502`, provider `502`,
  timeout `504`, safe database `500`, replay mismatch, and malformed/copy-paste
  JSON. Include the Firestore console link without secrets.

- [ ] Update `README.md`: move explicit feedback-driven profile learning,
  governed memory inspection/revocation/deletion, cross-session adaptation,
  and retry-safe chat turns into implemented status; retain tools, durable
  background jobs, UI, auth, and deployment as not implemented; label Cloud
  Tasks as target architecture; add the live smoke command and documentation
  links.

- [ ] Update `docs/architecture.md`: add current
  `sessions/{session_id}/turns/{turn_id}`, deterministic messages,
  `users/{user_id}/memory_proposals`, and `memory_events`; separate the current
  synchronous FastAPI/ADK system from the target Cloud Tasks worker diagram;
  preserve the public deployment gate.

- [ ] Review all commands against live filenames and pinned dependencies.
  Search for claims that feedback learning or chat idempotency is missing and
  correct only stale current-state claims, not future synthesis idempotency.

---

### Task 3: Verification and manual gate

**Files:**

- Verify all approved files; do not modify production source.

- [ ] Run the new offline smoke tests:

```bash
venv/bin/pytest -q tests/test_smoke_test_chat_idempotency.py
```

- [ ] Run related route and persistence tests:

```bash
venv/bin/pytest -q tests/test_main.py -k "idempotent or idempotency or claimed_turn"
venv/bin/pytest -q tests/test_chat_turns.py tests/test_chat_turn_database.py tests/test_database.py
```

- [ ] Run CLI/static verification:

```bash
venv/bin/python -m py_compile smoke_test_chat_idempotency.py tests/test_smoke_test_chat_idempotency.py
venv/bin/python smoke_test_chat_idempotency.py --help
git diff --check
```

- [ ] Run the full suite because README/architecture claims must match the
  tested repository state:

```bash
venv/bin/pytest -q
```

- [ ] Stop at **implemented, pending manual verification**. Provide:

```bash
python3 smoke_test_chat_idempotency.py
```

Expected structural output:

```text
trusted-memory-m6-2-3 pass first=200 replay=200 conflict=409 replay_equal=true user_id=<generated> session_id=<generated> turn_id=<digest> user_message_id=<derived> model_message_id=<derived>
```

- [ ] Ask the user to inspect the generated session in Firestore and verify one
  completed turn plus one deterministic user/model message. Do not commit or
  push before explicit acceptance.

Firestore console:
[project-e1e2a890-4566-48a8-a32](https://console.cloud.google.com/firestore/databases/-default-/data/panel/sessions?project=project-e1e2a890-4566-48a8-a32)
