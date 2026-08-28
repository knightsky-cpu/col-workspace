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

Not checkpointed yet in this note. This accepted audit note is ready for an explicit GitHub checkpoint request.
