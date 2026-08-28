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
