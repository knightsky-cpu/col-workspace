# Troubleshooting

## Diagnose from the boundary that failed

Start with the complete Uvicorn log and the HTTP status/body. Do not paste API
keys, credential files, raw private memory, or unrelated Firestore documents
into issues or logs. The application intentionally returns bounded public
errors while keeping provider details server-side.

## Application does not start: project cannot be determined

Typical error:

```text
OSError: Project was not passed and could not be determined from the environment.
```

Set the project in `.env` and in the Google Cloud CLI:

```dotenv
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
```

```bash
gcloud config set project YOUR_PROJECT_ID
```

Restart Uvicorn after changing `.env`.

## Application does not start: unsupported auth mode

Typical error:

```text
auth.AuthConfigurationError: Unsupported auth mode.
```

Check the spelling of `AGENT_COL_AUTH_MODE`. The supported local values are:

```bash
AGENT_COL_AUTH_MODE=local_dev
AGENT_COL_AUTH_MODE=google_oidc
```

`google_iodc` is a typo and will fail startup.

## Google OIDC mode does not sign in

Google OIDC mode requires the public web OAuth client ID in the environment:

```dotenv
GOOGLE_OAUTH_CLIENT_ID=YOUR_PUBLIC_WEB_CLIENT_ID
```

The OAuth client's authorized JavaScript origins must include the exact origin
you open in the browser, for example:

```text
http://127.0.0.1:8000
```

Google OIDC authenticates the browser user to the application. Vertex AI and
Firestore server calls still use Application Default Credentials separately.

## ADC quota-project warning

If startup warns that end-user credentials have no quota project, run:

```bash
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

This requires permission to use services in that project. The warning is not
the same as a Gemini free-tier request limit.

## HTTP 422

- `Idempotency key is invalid.` means the header is empty, longer than 128
  characters, or contains characters outside ASCII letters, digits,
  underscores, and hyphens.
- A Pydantic error under `body` means the JSON is missing required fields or a
  field violates its schema.
- `json_invalid` with `Invalid control character` usually means a literal
  newline was pasted inside a JSON string. Use a single-line `--data` payload
  or construct JSON with a proper serializer.

## HTTP 409

- `Idempotency key conflicts with a different chat request.` means the key was
  reused after changing `project_id`, `session_id`, `user_id`, `message`, or
  `memory_decision`. Use the original request exactly or create a new key.
- `Chat turn is already in progress.` means a matching worker still owns the
  lease. Honor the `Retry-After` header, then resend the identical request and
  key.
- Memory-signal or proposal conflict responses mean the requested lifecycle
  transition no longer matches stored governed state. Inspect memory before
  choosing a new action.

## Gemini 429 appears in Uvicorn and the API returns 502

The ADK/GenAI stack can report `429 RESOURCE_EXHAUSTED` when the configured
model quota is exhausted. The current public chat endpoint translates that
provider failure to:

```json
{"detail":"Agent_Col response failed."}
```

This is not an idempotency defect. Wait for the quota window or change the
project/plan deliberately. If an idempotency key was used, retry the identical
request with that key; the failed turn lease is expired so it can be resumed.
Do not repeatedly hammer the endpoint because each resumed attempt can consume
provider quota.

## HTTP 502

- Chat: ADK/Gemini did not return a valid final Agent_Col response.
- Synthesis: Gemini generation or local structured-output validation failed.

Inspect the exception class in the server log. Public errors intentionally do
not include provider bodies or user content.

## HTTP 504

The configured supervisor or synthesis deadline expired. For an idempotent chat
turn, wait briefly and retry the identical request and key. A provider call may
have performed computation before the timeout, so retry safety guarantees one
durable completion, not one provider computation.

## HTTP 500

`Database operation failed.` indicates a Firestore client, IAM, database, or
network failure. `Chat turn state is invalid.` means the stored turn/message
records violate the application contract. Do not edit those documents to make
the error disappear. Preserve the records, capture only safe document paths
and state fields, and reproduce with the focused persistence tests before
proposing a repair.

## Live smoke runner reports replay mismatch

The runner requires parsed first and replay `ChatResponse` objects to be equal.
A mismatch means the completed response was not replayed faithfully. Keep the
generated session and IDs, inspect the turn plus deterministic model message,
and run:

```bash
pytest -q tests/test_main.py -k "idempotent or idempotency or claimed_turn"
pytest -q tests/test_chat_turns.py tests/test_chat_turn_database.py
```

Do not rerun with a new key until the original evidence has been inspected.

## Firestore inspection

Open the Firestore console for the configured `GOOGLE_CLOUD_PROJECT`.

For the idempotency smoke, use the printed IDs to verify:

```text
sessions/{session_id}/turns/{turn_id}
sessions/{session_id}/messages/{user_message_id}
sessions/{session_id}/messages/{model_message_id}
```

The turn should be `completed`; there should be one user record and one model
record at the deterministic message IDs. Never copy their text into a public
bug report.
