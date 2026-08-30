# Firestore Memory Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a production-ready asynchronous Firestore persistence module
for ordered chat messages and merge-updated user profiles.

**Architecture:** `database.py` owns one `MemoryEngine` wrapper around
`AsyncClient`. Messages are written atomically to a session parent and a
`messages` subcollection; profiles are stored directly at `users/{user_id}`.
Firestore failures are translated into `MemoryEngineError` without logging
message or profile contents.

**Tech Stack:** Python 3.14, `google-cloud-firestore` 2.28.1, standard-library
`unittest`

**Spec:**
`docs/superpowers/specs/2026-08-19-firestore-memory-engine-design.md`

## Global Constraints

- Create only the production module `database.py`; do not modify `main.py`.
- Keep verification tests temporary under `/private/tmp` because the requested
  deliverable is a single production file.
- Use `from google.cloud.firestore import AsyncClient`.
- Use server timestamps only as top-level document fields.
- Use async Firestore writes, reads, batch commits, and query streams.
- Validate all caller input before constructing Firestore references.
- Catch `GoogleAPIError`, preserve it as `MemoryEngineError.__cause__`, and do
  not log message text, profile contents, session IDs, or user IDs.
- The workspace is not a Git repository, so no commit step is available.

---

### Task 1: Public interface, client ownership, and validation

**Files:**
- Create: `database.py`
- Test: `/private/tmp/test_database.py`

**Interfaces:**
- Consumes: `google.cloud.firestore.AsyncClient`
- Produces: `MemoryEngineError`, `MemoryEngine.__init__`, input-validation
  behavior, and `MemoryEngine.close`

- [ ] **Step 1: Write failing interface and validation tests**

```python
import unittest
from pathlib import Path
from unittest.mock import MagicMock


DATABASE_PATH = Path("<repo-root>/database.py")


class InterfaceTests(unittest.IsolatedAsyncioTestCase):
    def test_database_module_exists(self):
        self.assertTrue(DATABASE_PATH.is_file())

    async def test_invalid_inputs_do_not_call_firestore(self):
        from database import MemoryEngine

        client = MagicMock()
        engine = MemoryEngine(client=client)
        invalid_calls = (
            (engine.save_message, ("", "user", "text")),
            (engine.save_message, ("session", " ", "text")),
            (engine.save_message, ("session", "user", " ")),
            (engine.get_chat_history, (" ",)),
            (engine.update_user_profile, ("", {"tone": "direct"})),
            (engine.update_user_profile, ("user", {})),
            (engine.get_user_profile, ("",)),
        )
        for operation, arguments in invalid_calls:
            with self.assertRaises(ValueError):
                await operation(*arguments)
        client.collection.assert_not_called()

    def test_close_delegates_to_client(self):
        from database import MemoryEngine

        client = MagicMock()
        MemoryEngine(client=client).close()
        client.close.assert_called_once_with()
```

Each invalid async call must raise `ValueError` before the fake client is used.

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```bash
venv/bin/python -B /private/tmp/test_database.py -v
```

Expected: failure because `database.py` and `MemoryEngine` do not exist.

- [ ] **Step 3: Implement the public foundation**

```python
import logging
from typing import Any

from google.api_core.exceptions import GoogleAPIError
from google.cloud import firestore
from google.cloud.firestore import AsyncClient


logger = logging.getLogger(__name__)


class MemoryEngineError(RuntimeError):
    """Raised when a Firestore memory operation fails."""


class MemoryEngine:
    def __init__(self, client: AsyncClient | None = None) -> None:
        self._client = client or AsyncClient()

    @staticmethod
    def _validate_string(value: object, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string.")

    @staticmethod
    def _validate_updates(updates: object) -> None:
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a non-empty dictionary.")

    def close(self) -> None:
        self._client.close()
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run the same `unittest` command. Expected: interface, validation, and client
close checks pass.

### Task 2: Atomic session-message persistence and ordered reads

**Files:**
- Modify: `database.py`
- Test: `/private/tmp/test_database.py`

**Interfaces:**
- Consumes: validation and `self._client`
- Produces: `save_message` and `get_chat_history`

- [ ] **Step 1: Add failing session-operation tests**

Add tests that configure a fake session document, auto-ID message document,
async batch commit, ordered query, and async snapshot stream. Assert these
literal boundary calls:

```python
batch.set.assert_any_call(
    session_ref,
    {"updated_at": firestore.SERVER_TIMESTAMP},
    merge=True,
)
batch.set.assert_any_call(
    message_ref,
    {
        "role": "user",
        "text": "hello",
        "timestamp": firestore.SERVER_TIMESTAMP,
    },
)
messages_ref.order_by.assert_called_once_with(
    "timestamp", direction=firestore.Query.ASCENDING
)
batch.commit.assert_awaited_once_with()
```

The history assertion must compare the literal ordered list returned by two
fake snapshots.

- [ ] **Step 2: Run tests and verify method-missing failures**

Run the full temporary suite. Expected: failures because the session methods
are not defined.

- [ ] **Step 3: Implement atomic save and ordered retrieval**

Implement `save_message` with `client.batch()`, a parent `set` using
`merge=True`, an auto-ID message `set`, and one awaited `commit`. Implement
`get_chat_history` with:

```python
query = messages_ref.order_by(
    "timestamp", direction=firestore.Query.ASCENDING
)
history: list[dict[str, Any]] = []
async for snapshot in query.stream():
    data = snapshot.to_dict()
    if data is not None:
        history.append(data)
return history
```

Catch only `GoogleAPIError`, log a constant operation message, and raise
`MemoryEngineError` from the original error.

- [ ] **Step 4: Run tests and verify session behavior passes**

Run the full temporary suite. Expected: atomic write and ordered-read checks
pass without network access.

### Task 3: User profiles and Firestore error translation

**Files:**
- Modify: `database.py`
- Test: `/private/tmp/test_database.py`

**Interfaces:**
- Consumes: validation and `self._client`
- Produces: `update_user_profile`, `get_user_profile`, and consistent error
  translation across all operations

- [ ] **Step 1: Add failing profile and error tests**

Assert the profile write and read boundaries:

```python
user_ref.set.assert_awaited_once_with(
    {"tone": "direct"}, merge=True
)
self.assertEqual(await engine.get_user_profile("user-1"), {"tone": "direct"})
self.assertEqual(await missing_engine.get_user_profile("missing"), {})
```

Configure one async Firestore operation to raise `ServiceUnavailable`. Assert
that the public method raises `MemoryEngineError`, that
`exception.__cause__` is the same `ServiceUnavailable` instance, and that
captured log output contains neither message text nor profile data.

- [ ] **Step 2: Run tests and verify profile/error failures**

Run the full temporary suite. Expected: failures because the profile methods
and error translation are incomplete.

- [ ] **Step 3: Implement profile operations and shared error translation**

Use `users/{user_id}`, `await user_ref.set(updates, merge=True)`, and
`await user_ref.get()`. Return `{}` when `snapshot.exists` is false or
`snapshot.to_dict()` returns `None`. Each operation catches only
`GoogleAPIError`, logs a constant safe message, and raises
`MemoryEngineError` from the original exception.

- [ ] **Step 4: Run the complete suite**

Run:

```bash
venv/bin/python -B /private/tmp/test_database.py -v
```

Expected: all interface, validation, session, profile, lifecycle, and error
tests pass with no warnings.

### Task 4: Final source verification and cleanup

**Files:**
- Verify: `database.py`
- Remove: `/private/tmp/test_database.py`

**Interfaces:**
- Consumes: completed module and passing tests
- Produces: verified single-file production deliverable

- [ ] **Step 1: Verify syntax and imports without bytecode artifacts**

```bash
venv/bin/python -B -c 'import database; print("database_import=pass")'
```

- [ ] **Step 2: Verify PEP 8 line length**

```bash
awk 'length($0) > 88 { print FNR ":" length($0) ":" $0 }' database.py
```

Expected: no output.

- [ ] **Step 3: Re-read the complete production module against the spec**

Confirm every public signature, collection path, timestamp, merge flag,
ordering clause, validation rule, safe log message, and exception cause.

- [ ] **Step 4: Remove the temporary test harness**

Delete only `/private/tmp/test_database.py` after recording the passing test
output. Do not remove workspace files.
