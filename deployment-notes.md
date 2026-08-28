# Agent Col Deployment Notes

## 2026-08-28 - Pass 1: Cloud Run Fail-Closed Config Guard

Status: accepted by manual verification.

Previous checkpoint: `d5253e7ce0f85f174085f64a612e4180b63d3178`.

### Scope

- Implemented the first Cloud Run production-hardening pass from `docs/superpowers/plans/2026-08-28-cloud-run-production-hardening-deployment.md`.
- Preserved local development behavior when `K_SERVICE` is absent.
- Did not deploy to Cloud Run.
- Did not enable Google Cloud APIs.
- Did not add Dockerfile packaging.
- Did not change `.env`.

### Source Changes

- `auth.py`
  - `load_auth_settings()` now treats a nonblank `K_SERVICE` as the Cloud Run runtime signal.
  - When `K_SERVICE` is present, startup auth settings fail unless `AGENT_COL_AUTH_MODE=google_oidc`.
  - When `K_SERVICE` is present and Google OIDC mode is selected, startup auth settings fail unless `GOOGLE_OAUTH_CLIENT_ID` or `GOOGLE_CLIENT_ID` is configured with a nonblank value.

- `tests/test_auth.py`
  - Added coverage proving local default auth mode is preserved outside Cloud Run.
  - Added coverage proving Cloud Run rejects missing auth mode, `local_dev`, missing OAuth client ID, and blank OAuth client ID.
  - Added coverage proving Cloud Run accepts `google_oidc` with a trimmed OAuth client ID.

### TDD Evidence

- RED command:

```bash
venv/bin/pytest tests/test_auth.py -k "load_auth_settings" -q
```

Observed result before implementation: `4 failed, 2 passed, 7 deselected`. The failing cases were the unsafe Cloud Run configurations that did not raise `AuthConfigurationError`.

- GREEN command:

```bash
venv/bin/pytest tests/test_auth.py -k "load_auth_settings" -q
```

Observed result after implementation: `6 passed, 7 deselected`.

### Focused Verification

```bash
venv/bin/pytest tests/test_auth.py -q
```

Observed result: `13 passed`.

```bash
venv/bin/pytest tests/test_main.py -k "auth_session or auth_config or google_mode_rejects_project_artifact_mismatch_before_service or google_workspace_create_uses_subject_owned_workspace_prefix or google_chat_requires_idempotency_key_before_service_access or google_chat_propagates_verified_owner_to_claim_and_history or google_mode_rejects_generic_artifact_project_mismatch_before_generation" -q
```

Observed result: `8 passed, 195 deselected, 1 warning`.

```bash
git diff --check
```

Observed result: passed.

### Manual Acceptance

The user reported: "pass successful".

### Checkpoint State

Not checkpointed yet in this note. The accepted source changes and this deployment note are ready for an explicit GitHub checkpoint request.

## 2026-08-28 - Pass 4: HTTP Body Limits, Scoped Rate Limiting, And Security Headers

Status: accepted by manual verification.

Previous checkpoint: `cba0f7d77eb21b53365deec70cabd3f4060437f9`.

### Scope

- Implemented request perimeter hardening only.
- Did not change deployment configuration.
- Did not change Google auth behavior.
- Did not run or depend on live Google Sign-In or Cloud Run behavior checks; those remain deferred to the hosted integration verification phase.
- Preserved the existing schema-level 10,000-character chat message limit as a separate application validation layer.

### Source Changes

- `main.py`
  - Added a 64 KiB raw HTTP body cap enforced by ASGI middleware before FastAPI JSON parsing and before route/service execution.
  - Covered both `Content-Length` rejection and streamed/no-`Content-Length` request bodies.
  - Added deterministic `429 Too Many Requests` responses with `Retry-After`.
  - Added an in-memory rate limiter scoped to expensive or mutating API routes only:
    - `POST /api/chat`
    - `POST /api/synthesize`
    - `POST`, `PATCH`, and `DELETE` under `/api/users/...`
    - `POST`, `PATCH`, and `DELETE` under `/api/projects/...`
  - Left health, workspace, static assets, and cheap read-only API traffic outside the rate-limit bucket.
  - Added security headers to workspace, static assets, and API responses:
    - `Content-Security-Policy`
    - `X-Content-Type-Options`
    - `X-Frame-Options`
    - `Referrer-Policy`
    - `Permissions-Policy`
  - Preserved `/workspace` and `/static/agent-col/...` `Cache-Control: no-store` behavior.

- `tests/test_main.py`
  - Added coverage for raw oversized request rejection before JSON parsing.
  - Added coverage for streamed oversized request rejection before JSON parsing.
  - Added coverage proving the existing 10,000-character chat schema limit remains distinct from the raw body limit.
  - Added coverage proving scoped rate limiting returns deterministic `429` plus `Retry-After` while health/workspace requests remain unaffected.
  - Added coverage proving security headers apply to workspace, static, and API responses while allowing Google Identity Services script/frame origins and same-origin future streaming/fetch.

### TDD Evidence

- RED command:

```bash
venv/bin/pytest tests/test_main.py -k "oversized_raw_body or schema_chat_limit_remains_distinct or scoped_rate_limiter or security_headers"
```

Observed result before implementation: `3 failed, 1 passed, 206 deselected`. Failures proved the raw body limit constant, in-memory limiter, and security headers did not exist. The schema-limit test already passed, proving the existing application/schema limit was separate and should remain unchanged.

- Additional RED command after the first body-limit implementation:

```bash
venv/bin/pytest tests/test_main.py -k "streamed_oversized_raw_body"
```

Observed result before the ASGI receive-path fix: failed with `422` instead of `413`, proving streamed oversized bodies could still reach FastAPI JSON/validation handling.

- GREEN command:

```bash
venv/bin/pytest tests/test_main.py -k "streamed_oversized_raw_body"
```

Observed result after the ASGI middleware fix: `1 passed, 210 deselected`.

- GREEN command:

```bash
venv/bin/pytest tests/test_main.py -k "oversized_raw_body or schema_chat_limit_remains_distinct or scoped_rate_limiter or security_headers"
```

Observed result after implementation: `5 passed, 206 deselected`.

### Focused Verification

```bash
venv/bin/pytest tests/test_main.py
```

Observed result: `211 passed, 1 warning`.

```bash
git diff --check
```

Observed result: passed.

The one warning is the existing dependency/runtime `BaseAgentConfig` deprecation warning and was not introduced by this pass.

### Limitations

- The rate limiter is explicitly best-effort, in-memory, per-process, and per Cloud Run instance. It is not distributed, durable, or globally authoritative across scaled Cloud Run instances.
- Google Sign-In/CSP behavior and real Cloud Run behavior remain deferred to hosted integration verification, where they provide meaningful evidence.

### Manual Acceptance

The user reported: "Pass 4: accepted."

### Checkpoint State

Not checkpointed yet in this note. The accepted source changes and this deployment note are ready for an explicit GitHub checkpoint request.

## 2026-08-28 - Pass 2: Ownership Audit And Gap Closure

Status: accepted by manual verification.

Previous checkpoint: `71b8d5b69246d99be76183afe0e70fd537cb01c4`.

### Scope

- Audited public ownership-sensitive FastAPI routes against `auth.py`, `main.py`, `database.py`, and focused tests.
- Produced a route-by-route ownership matrix for user, workspace, memory, note, chat, blueprint, artifact, feedback, synthesis, and chat-turn surfaces.
- Made no Pass 2 source-code changes because no source-backed cross-user ownership gap was proven.

### Source-Backed Findings

- `main.py` routes that accept `user_id` use `_resolve_effective_user_id(...)`.
- `main.py` routes that accept `project_id` use `_resolve_effective_project_id(...)`.
- Mixed `user_id` and `project_id` routes use both guards before downstream service/database access.
- `auth.py` rejects Google user mismatches through `Authenticator.resolve_user_id(...)`.
- `auth.py` rejects Google workspace/project mismatches through `Authenticator.resolve_project_id(...)`.
- Chat session operations validate stored `user_id` and `project_id` through `MemoryEngine._validate_chat_session_owner(...)`.
- Collaborative notes are stored under `users/{user_id}/workspaces/{workspace_id}` and validate stored note/event ownership on read and mutation.
- Project artifact routes are guarded by the Google-owned `project_id` invariant before artifact service/database access.

### Caveat

Project-only artifact routes currently rely on the invariant that Google-owned `project_id` values are hash-derived workspace IDs enforced by `Authenticator.resolve_project_id(...)`. That is acceptable under the current architecture. If project IDs later become user-chosen or human-readable, those routes will need an additional persisted project-owner check.

### Focused Verification

```bash
venv/bin/pytest tests/test_auth.py -q
```

Observed result: `13 passed`.

```bash
venv/bin/pytest tests/test_main.py -k "google_mode_rejects_project_artifact_mismatch_before_service or google_workspace_create_uses_subject_owned_workspace_prefix or google_mode_rejects_generic_artifact_project_mismatch_before_generation or google_chat_requires_idempotency_key_before_service_access or google_chat_propagates_verified_owner_to_claim_and_history or chat_translates_session_ownership_errors_to_uniform_not_found or chat_clarification_selection_hides_ownership_mismatch" -q
```

Observed result: `10 passed, 193 deselected, 1 warning`.

```bash
venv/bin/pytest tests/test_database.py -k "ownership_mismatch or malformed_session_ownership" -q
```

Observed result: `6 passed, 38 deselected`.

```bash
venv/bin/pytest tests/test_chat_turn_database.py -k "ownership_mismatch or request_mismatch or rejects_reclaimed_owner or rejects_expired_owner or mismatched_stored_owner or mismatched_stored_metadata" -q
```

Observed result: `9 passed, 72 deselected`.

```bash
git diff --check
```

Observed result: passed.

### Manual Acceptance

The user accepted Pass 2 after reviewing the explicit route-by-route ownership matrix.

### Checkpoint State

Checkpointed to `origin/main` at `50b1951f33b7bdaf916b47dcf279301f93b577c0`.

## 2026-08-28 - Pass 3: Public/Internal User Identity Split

Status: accepted from automated verification. Live Google/OIDC integration confirmation deferred to hosted/browser verification.

Previous checkpoint: `50b1951f33b7bdaf916b47dcf279301f93b577c0`.

### Scope

- Replaced public Google-mode browser/API `user_id` exposure with a deterministic opaque locator.
- Preserved internal persisted user IDs as `google--{subject}`.
- Made no Firestore migration.
- Kept frontend identity behavior simple: the browser stores and sends the backend-provided `user_id` unchanged.
- Patched only source-proven public response leak surfaces.

### Source Changes

- `auth.py`
  - Added deterministic public locator generation as `user--{sha256(subject)[:32]}`.
  - `/api/auth/session` public output now uses the opaque locator and does not include `subject` or `google--{subject}`.
  - Google-mode `resolve_user_id()` now validates the supplied opaque public locator and returns the existing internal `google--{subject}` ID to downstream services and Firestore.
  - Local-dev behavior remains unchanged.

- `main.py`
  - Added public response shapers for chat session list/detail `user_id`.
  - Added public response shapers for collaborative note/detail/lifecycle `owner_user_id`.
  - Added public response shaping for chat `collaborative_note_events`.
  - Kept downstream service/database calls on the internal effective user ID.

- Frontend tests
  - Updated fixtures to use opaque public locators.
  - No frontend identity translation logic was added.

### TDD Evidence

- RED command:

```bash
venv/bin/pytest tests/test_auth.py -k "public_session_uses_opaque_user_locator or resolves_public_user_locator_to_internal_id or rejects_raw_internal_user_locator" -q
```

Observed result before implementation: `3 failed, 13 deselected`. Failures proved the public session still returned `google--109876543210`, opaque locators were rejected, and raw internal locators were still accepted.

- RED command:

```bash
venv/bin/pytest tests/test_main.py -k "auth_session_returns_google_principal or google_workspace_create_uses_subject_owned_workspace_prefix or google_mode_rejects_raw_internal_user_locator or list_chat_sessions_returns_project_user_sessions or get_chat_session_detail_returns_chronological_messages or google_collaborative_note_responses_hide_internal_owner or google_chat_propagates_verified_owner_to_claim_and_history or google_chat_note_event_receipts_hide_internal_owner" -q
```

Observed result before implementation/refinement: route tests failed because the backend rejected opaque locators or returned internal `google--{subject}` IDs in public responses. The chat note-event receipt test failed because `collaborative_note_events[0].owner_user_id` exposed `google--109876543210`.

- GREEN command:

```bash
venv/bin/pytest tests/test_auth.py -k "public_session_uses_opaque_user_locator or resolves_public_user_locator_to_internal_id or rejects_raw_internal_user_locator" -q
```

Observed result after implementation: `3 passed, 13 deselected`.

- GREEN command:

```bash
venv/bin/pytest tests/test_main.py -k "auth_session_returns_google_principal or google_workspace_create_uses_subject_owned_workspace_prefix or google_mode_rejects_raw_internal_user_locator or list_chat_sessions_returns_project_user_sessions or get_chat_session_detail_returns_chronological_messages or google_collaborative_note_responses_hide_internal_owner or google_chat_propagates_verified_owner_to_claim_and_history or google_chat_note_event_receipts_hide_internal_owner" -q
```

Observed result after implementation: `8 passed, 198 deselected, 1 warning`.

### Focused Verification

```bash
venv/bin/python -m py_compile auth.py main.py
```

Observed result: passed.

```bash
venv/bin/pytest tests/test_auth.py -q
```

Observed result: `16 passed`.

```bash
venv/bin/pytest tests/test_main.py -q
```

Observed result: `206 passed, 1 warning`.

```bash
node --test tests/frontend/auth-view.test.mjs tests/frontend/state.test.mjs tests/frontend/api.test.mjs tests/frontend/requests.test.mjs tests/frontend/workspace-static.test.mjs
```

Observed result: `98 passed`.

```bash
git diff --check
```

Observed result: passed.

### Public Leak Audit

- Patched `/api/auth/session` so Google mode returns an opaque public `user_id` and never returns `subject`.
- Patched chat session list/detail responses so persisted internal `user_id` values are replaced by the public route locator.
- Patched collaborative note list/detail/lifecycle responses so persisted `owner_user_id` values are replaced by the public route locator.
- Patched chat responses and partial-failure responses so `collaborative_note_events` do not expose internal `owner_user_id`.
- Left inbound request schema fields unchanged because they now carry the public locator and are translated at the auth boundary.
- Left artifact response models unchanged because the audited artifact metadata responses do not serialize `user_id`.

### Manual Acceptance

The user accepted Pass 3 from automated verification and explicitly deferred live Google/OIDC integration confirmation to the existing hosted/browser verification phase.

### Checkpoint State

Not checkpointed yet in this note. The accepted source changes and this deployment note are ready for an explicit GitHub checkpoint request.
