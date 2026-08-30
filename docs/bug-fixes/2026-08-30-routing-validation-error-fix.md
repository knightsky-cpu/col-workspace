# Routing ValidationError Bug Fix - August 30, 2026

## Summary

This document records the investigation and accepted fix for a repeated
`ValidationError` crash in ordinary streamed chat turns when a user asked Agent
Col to revise generated markdown into a more natural conversation.

The accepted fix is commit `56bfcf7`:

```text
fix: bound routing recent user context
```

The fix was developed on branch `validate-error-fix`, merged into `main`, and
pushed to `origin/main`.

## User-visible symptom

In the Testing workspace, retrying prompts such as the following repeatedly
failed:

```text
can you revise the markdown contents to be a natural flowing conversation instead of the rigid singular questions they are now
```

The browser showed:

```text
Agent_Col response failed.
```

The local server logged:

```text
POST /api/chat/stream HTTP/1.1 200 OK
Agent_Col response failed unexpectedly (ValidationError).
```

The same style of artifact revision worked reliably in a fresher workspace or
chat context, which pointed away from a simple artifact-family/versioning
failure and toward a context-sensitive routing validation failure.

## Important correction from the investigation

The initial assumption that artifact revision/versioning was missing was too
broad.

The existing source already supports generic single-file artifact versions:

- `schemas.py` defines artifact families: `code`, `document`, and `data`.
- `schemas.py` allows `markdown`, `text`, and `html` for the `document`
  family.
- `schemas.py` validates that artifact family and format match.
- `generic_artifact_service.py` supports `create_artifact_version(...)`.
- `main.py` exposes `POST /api/projects/{project_id}/artifacts/{artifact_id}/versions`.
- `frontend/work-view.mjs` renders the "Edit artifact content" / "Save new
  version" form for single-file artifacts.
- `frontend/app.mjs` calls the artifact-version API from that form.

Focused verification confirmed the existing version path:

```bash
venv/bin/pytest -q tests/test_generic_artifact_service.py -k version
```

Result:

```text
2 passed, 14 deselected
```

```bash
venv/bin/pytest -q tests/test_main.py -k create_generic_artifact_version
```

Result:

```text
2 passed, 237 deselected
```

```bash
venv/bin/pytest -q tests/test_agent_col_artifact_executor.py -k single_file_artifact
```

Result:

```text
1 passed, 15 deselected
```

## Root cause

The live bug was not caused by markdown artifact-family validation. It was
caused by unbounded recent chat history being fed into a smaller routing
contract.

The relevant contracts were mismatched:

- `schemas.py` allows ordinary chat messages up to 10,000 characters.
- `agent_col_routing.py` defines `RoutingTaskText` with a 1,000-character max.
- `agent_col_routing_v4.py` uses `RoutingTaskText` for each
  `recent_user_messages` item in `AgentColRoutingInput`.
- `main.py` collected prior user messages from validated chat history and
  passed them through to `AgentColTurnCommand`.
- `agent_col_turn_service.py` previously sliced recent user messages by count
  only, using `MAX_ROUTING_RECENT_USER_MESSAGES = 20`, without stripping,
  dropping blank entries, or truncating each message to the routing contract.

That meant a long previous user prompt in the same chat could trigger a raw
Pydantic `ValidationError` while constructing `AgentColRoutingInput`, before
the routing provider, expert, artifact executor, or responder ran.

The failure was reproduced with a short current revision prompt plus one long
prior user message. The diagnostic output showed:

```text
ValidationError
False
True
1 validation error for AgentColRoutingInput
```

That established that the exception was a raw Pydantic `ValidationError`, not a
governed `AgentColTurnServiceError`.

## Fixes made

### 1. Artifact execution ValidationError wrapping

The first pass fixed a real but separate raw-validation leak at the artifact
executor boundary.

`agent_col_turn_service.py` now imports Pydantic `ValidationError` and wraps
`ValidationError` raised during artifact execution into
`AgentColTurnServiceError`.

Why:

- `main.py` already has a governed path for `AgentColTurnServiceError`.
- Raw exceptions hit the generic unexpected-failure path and produce the
  terminal log `Agent_Col response failed unexpectedly (...)`.
- Validation details can contain schema field names or content-derived data, so
  wrapping keeps the public/API path sanitized.

Regression coverage:

- `tests/test_agent_col_turn_service_artifacts.py::test_streamed_artifact_validation_failure_is_wrapped_safely`

### 2. Routing recent-user context projection

The accepted live fix added a routing-only projection helper:

```python
MAX_ROUTING_RECENT_USER_MESSAGES = 10
MAX_ROUTING_RECENT_USER_MESSAGE_CHARS = 1_000


def _project_recent_user_messages_for_routing(
    recent_user_messages: tuple[str, ...],
) -> tuple[str, ...]:
    projected = tuple(
        message.strip()[:MAX_ROUTING_RECENT_USER_MESSAGE_CHARS]
        for message in recent_user_messages
        if message.strip()
    )
    return projected[-MAX_ROUTING_RECENT_USER_MESSAGES:]
```

The helper is applied before constructing:

- v4 artifact-capable routing input; and
- v3 routing URL-candidate projection input.

Why:

- Routing only needs a small capability-selection context.
- Old or oversized chat history should not be allowed to violate the routing
  schema.
- Dropping blank messages and truncating long messages is safer than expanding
  the routing contract globally.
- Reducing the count from 20 to 10 lowers stale-context influence while keeping
  recent referential prompts useful.

Regression coverage:

- `tests/test_agent_col_turn_service_artifacts.py::test_streamed_artifact_routing_projects_long_recent_user_messages`
- `tests/test_agent_col_turn_service.py::test_stream_turn_limits_recent_user_messages_for_url_projection`
- updated `tests/test_agent_col_turn_service.py::test_turn_service_bounds_recent_user_messages_for_v4_routing`
  from the previous last-20 expectation to last-10.

## Verification evidence for the accepted pass

Focused verification on the feature branch and again after fast-forward merging
into `main`:

```bash
venv/bin/pytest -q tests/test_agent_col_turn_service_artifacts.py -k "artifact or long_recent"
```

Result:

```text
8 passed
```

```bash
venv/bin/pytest -q tests/test_agent_col_turn_service.py -k "stream or recent"
```

Result:

```text
9 passed, 37 deselected
```

```bash
venv/bin/pytest -q tests/test_main.py -k chat_stream
```

Result:

```text
17 passed, 222 deselected
```

```bash
git diff --check
```

Result: passed with no output.

Manual verification also passed in the previously failing Testing chat after
server restart/reload. The same prompt no longer produced the repeated raw
`ValidationError` stream failure.

## Full-suite status at checkpoint time

The full suite was run before integration:

```bash
venv/bin/pytest -q
```

Result:

```text
2500 passed, 9 failed
```

The failures were outside this bug-fix pass:

- smoke/live-test fixture path failures in computation pipeline tests;
- routing v3 smoke runner import path failure;
- orchestration-check fixture drift around `working_state_service`;
- stale workspace static assertions.

Those failures were not fixed or hidden in this pass.

## Recurrence risk

The exact accepted bug is now low risk:

- recent routing context is projected before validation;
- blank recent messages are dropped;
- each recent routing message is capped at 1,000 chars;
- only the last 10 projected recent messages are used;
- regression tests cover the failure pattern.

The broader bug class remains medium risk:

- Agent Col uses many Pydantic models as internal contracts.
- Some boundaries already convert `ValidationError` into domain-specific,
  content-safe errors.
- Other boundaries may still allow raw validation exceptions to escape into
  generic API failure handling.

The recurring pattern to watch for is:

```text
untrusted or persistence-derived input
-> Pydantic model construction
-> raw ValidationError
-> main.py generic "unexpected" exception path
```

## Recommendation: standard raw-validation exception convention

Create and enforce a project-wide backend convention for Pydantic validation
boundaries.

Recommended rule:

> Any Pydantic `ValidationError` raised from untrusted input, stored state,
> provider output, or cross-service contract adaptation must be caught at the
> nearest ownership boundary and converted into a domain-specific, content-safe
> exception.

Recommended implementation pattern:

1. Identify ownership boundary:
   - API request validation belongs to FastAPI/Pydantic request models.
   - Provider output validation belongs to provider adapter modules.
   - Stored document validation belongs to read/repository services.
   - Cross-service command/context validation belongs to the service adapter
     constructing the downstream model.

2. Wrap into a domain error:
   - routing errors -> routing provider/service error;
   - artifact errors -> artifact executor/read state error;
   - memory errors -> memory engine/proposal state error;
   - responder/tool errors -> supervisor runtime error;
   - chat turn orchestration errors -> `AgentColTurnServiceError`.

3. Preserve the original exception as `__cause__` for debugging.

4. Do not stringify raw `ValidationError` into user-visible responses or normal
   logs, because field names and input-derived values can leak content.

5. Add regression tests for each boundary:
   - RED proves raw `ValidationError` currently escapes;
   - GREEN proves the boundary emits the domain error instead;
   - assertions check private/content-derived details are not exposed in
     `str(error)` or normal logs.

Recommended follow-up pass:

- Audit backend `model_validate(...)`, `model_validate_json(...)`, and
  `TypeAdapter.validate_*` calls.
- Classify each as one of:
  - safe API model validation;
  - already wrapped;
  - needs wrapping;
  - intentionally fatal internal invariant.
- Add the smallest missing wrappers and tests per subsystem rather than one
  broad refactor.

## Current Git checkpoint

At the time this bug-fix record was written:

- accepted fix commit: `56bfcf7`
- branch merged: `validate-error-fix`
- destination branch: `main`
- remote: `origin/main`
