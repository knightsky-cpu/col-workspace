# Chat Turn Idempotency

## Purpose

`POST /api/chat` accepts an optional `Idempotency-Key` header so a client can
retry one logical collaborative turn without creating another completed turn
or another pair of chat messages. Firestore is the durable authority for the
turn state; an ADK invocation session remains temporary execution state.

This contract protects only the current chat-turn workflow. It is not a claim
that every future tool, external API, synthesis request, or background job is
automatically idempotent.

## HTTP contract

The header is optional to preserve the original local-development chat path.
When supplied, its value must contain 1 through 128 ASCII letters, digits,
underscores, or hyphens.

| Request state | Result |
| --- | --- |
| New valid key and request | The server claims and executes the turn. |
| Completed key with the identical request | HTTP 200 with the stored `ChatResponse`; Gemini is not called again. |
| Same key with a different request identity | HTTP 409 with `Idempotency key conflicts with a different chat request.` |
| Matching turn with an unexpired lease | HTTP 409 with `Chat turn is already in progress.` and a `Retry-After` header. |
| Invalid header value | HTTP 422 with `Idempotency key is invalid.` |
| Expired matching lease | A new owner may resume the incomplete turn. |

Request identity includes `project_id`, `session_id`, `user_id`, `message`, and
the complete optional `memory_decision`. Changing any of these while reusing a
key is a conflict.

## Persistence and execution order

The server hashes the header value with SHA-256. The raw idempotency key is not
stored in the turn document.

```text
sessions/{session_id}/turns/{sha256_key}
sessions/{session_id}/messages/turn--{sha256_key}--user
sessions/{session_id}/messages/turn--{sha256_key}--model
```

The operation order is:

1. Transactionally validate or create the turn and deterministic user message.
2. Return the stored response immediately if the turn is already completed.
3. Load bounded history and approved collaboration memory.
4. Apply a deterministic memory decision, if the request includes one.
5. Renew the lease before invoking the supervisor.
6. Invoke the bounded ADK supervisor.
7. Transactionally write the deterministic model message, response receipts,
   and `completed` turn state.
8. On a supervisor provider failure or timeout, expire the owned lease so the
   client can retry with the same key.

The completed turn stores response receipts while the deterministic model
message stores response text. Replay reconstructs and locally validates the
public `ChatResponse` from both records.

## Guarantees

- A completed turn is replayed without another supervisor invocation.
- The identical successful replay returns semantically identical JSON.
- A changed request cannot silently reuse a completed or in-progress turn.
- Turn completion and the model message are one Firestore transaction.
- A deterministic user-message identifier prevents duplicate user messages
  for the same key.
- Stored turn metadata is validated before it is trusted.

This is an effectively-once durable completion boundary for a single chat
turn. It is stronger than best-effort deduplication, but it is not universal
exactly-once execution.

## Limitations

- The server does not automatically retry an HTTP request. The client must
  resend the same body and header after a timeout or transient failure.
- A process can fail after Gemini performs work but before Firestore records
  completion. A later retry can repeat provider computation and cost, although
  it still converges on one durable completed turn and one deterministic
  message pair.
- Headerless requests retain the older behavior and do not receive durable
  replay or conflict protection.
- Tools are not connected to the supervisor yet. Every future side-effecting
  tool needs its own idempotency and receipt contract.
- `/api/synthesize` has a separate reliability boundary and is not protected by
  this chat header.
- Request-provided user, project, and session identifiers are not an
  authorization boundary. Public deployment remains blocked on verified
  identity and ownership checks.

## Logging and privacy boundary

Application errors log operation categories and exception classes, not raw
keys, messages, model responses, memory values, or Firestore documents. The
live smoke runner follows the same boundary: it prints generated inspection
locators, derived document IDs, status codes, and the replay comparison only.

The public HTTP response necessarily contains the requested model response.
That is distinct from application logs and smoke-runner summaries.

## Verification

Offline contract tests:

```bash
pytest -q tests/test_smoke_test_chat_idempotency.py
pytest -q tests/test_main.py -k "idempotent or idempotency or claimed_turn"
pytest -q tests/test_chat_turns.py tests/test_chat_turn_database.py
```

With the local server running:

```bash
python3 smoke_test_chat_idempotency.py
```

Success requires `first=200 replay=200 conflict=409 replay_equal=true`. Use the
printed session and derived IDs to inspect the completed turn and its two
messages in Firestore.
