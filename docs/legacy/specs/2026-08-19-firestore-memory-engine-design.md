# Firestore Memory Engine Design

## Goal

Add an asynchronous `MemoryEngine` in `database.py` that stores ordered chat
messages and merge-updates user profiles through Google Cloud Firestore.

## Scope

This pass owns only Firestore access. It does not modify `main.py`, connect
memory to `/api/chat`, create Firestore security rules, provision a Google
Cloud project, or deploy the application.

## Evaluated Storage Approaches

### 1. Session message subcollections — selected

Store each message as its own document beneath its session:

```text
sessions/{session_id}
sessions/{session_id}/messages/{auto_message_id}
```

This layout supports a top-level server timestamp on every message, ordered
queries, concurrent writers, and chat histories that grow without expanding a
single session document toward Firestore's document-size limit.

### 2. Message arrays on session documents — rejected

The original proposal placed message maps in a `messages` array. The Python
SDK cannot encode `SERVER_TIMESTAMP` inside an array element, arrays cannot be
queried with `order_by`, and concurrent append/read-modify-write operations
would create contention. A growing history would also be bounded by the
maximum Firestore document size.

### 3. Top-level message collection — rejected

A top-level `messages` collection with a `session_id` field could support the
required query, but it weakens ownership boundaries and requires additional
filtering and index planning. The session subcollection expresses the access
pattern directly and is simpler for this phase.

## Data Model

### Session document

Path:

```text
sessions/{session_id}
```

Fields written by this pass:

```text
updated_at: server timestamp
```

The document is created automatically on the first message. Subsequent
messages merge-update `updated_at` without replacing future session metadata.

### Message document

Path:

```text
sessions/{session_id}/messages/{auto_message_id}
```

Fields:

```text
role: string
text: string
timestamp: server timestamp
```

The parent session update and message creation are committed in one async
batch. `get_chat_history` queries the message subcollection by `timestamp` in
ascending order and returns the stored message dictionaries.

### User profile document

Path:

```text
users/{user_id}
```

The user document is the profile document for this phase. Profile updates use
`set(updates, merge=True)`, so the first update creates the document and later
updates preserve unspecified fields. Reads return the stored dictionary or an
empty dictionary when the document does not exist.

## Public Interface

`database.py` will expose:

```python
class MemoryEngineError(RuntimeError):
    """Raised when a Firestore memory operation fails."""


class MemoryEngine:
    def __init__(self, client: AsyncClient | None = None) -> None: ...
    async def save_message(
        self, session_id: str, role: str, text: str
    ) -> None: ...
    async def get_chat_history(
        self, session_id: str
    ) -> list[dict[str, object]]: ...
    async def update_user_profile(
        self, user_id: str, updates: dict[str, object]
    ) -> None: ...
    async def get_user_profile(
        self, user_id: str
    ) -> dict[str, object]: ...
    def close(self) -> None: ...
```

When no client is supplied, `MemoryEngine` creates `AsyncClient()` and relies
on Application Default Credentials. Optional client injection keeps unit tests
offline and does not change production behavior. `close()` releases the
Firestore client's gRPC transport and prepares the class for later FastAPI
lifespan integration.

## Validation and Error Handling

- Session IDs, user IDs, roles, and message text must be non-empty strings.
- Profile updates must be a non-empty dictionary.
- Invalid caller input raises `ValueError` before a Firestore operation.
- Firestore API failures are logged without message text or profile contents.
- Firestore API failures are re-raised as `MemoryEngineError` with the original
  exception preserved as the cause.
- Programming errors are not swallowed by a broad `except Exception` block.

## Async Behavior

- All Firestore reads, writes, batch commits, and query iteration use the async
  SDK.
- `save_message` awaits one atomic batch commit.
- `get_chat_history` consumes the asynchronous query stream.
- Profile reads and writes await `AsyncDocumentReference` operations.
- Client construction and `close()` are synchronous because that is the API
  exposed by `google-cloud-firestore` 2.28.1.

## Testing Strategy

Tests will inject an async fake client and verify observable database-boundary
behavior:

- `save_message` creates an auto-ID message reference, batches the parent
  merge and message write, uses both server timestamps, and awaits commit.
- `get_chat_history` orders by `timestamp` ascending and returns documents in
  query order.
- `update_user_profile` performs `set(updates, merge=True)`.
- `get_user_profile` returns stored data or `{}` for a missing document.
- Invalid inputs fail before any Firestore call.
- Firestore API failures become `MemoryEngineError` and retain their causes.

The tests will not write to a live Firestore database. Live acceptance requires
a selected Google Cloud project, an enabled Firestore database, and either
Application Default Credentials or the Firestore emulator.

## Acceptance Criteria

- `database.py` imports and uses `google.cloud.firestore.AsyncClient`.
- All four requested operations are asynchronous.
- Messages use a subcollection and remain queryable in chronological order.
- The first message creates its parent session document atomically.
- Profile writes merge and profile reads return `{}` when missing.
- Unit tests pass without network access or Google Cloud credentials.
- Source passes syntax and clean-style checks.
