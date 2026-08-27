# Winning Core Phase 4 Production Hardening and Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan one approved pass at a
> time. Steps use checkbox (`- [ ]`) syntax for tracking. Repository
> `AGENTS.md` approval, TDD, manual-verification, and checkpoint gates remain
> controlling.

**Status:** Pending approval. This planning document does not authorize source,
dependency, data-migration, Google Cloud, IAM, billing, container, or deployment
changes.

**August 27, 2026 reconciliation note:** Phase 1 memory lifecycle, Phase 2
workspace notes/continuity, internal working state, and the four specialist
expert surfaces are accepted in current source. Winning Core Phase 3 durable
asynchronous artifact jobs remain pending, so this Phase 4 plan still requires
a fresh source re-audit after Phase 3 acceptance before implementation.

**Goal:** Make the accepted Agent Col Winning Core safe and reproducible as a
public Google OIDC application on Cloud Run, with durable ownership, bounded
resource use, content-safe observability, defined data lifecycle, a private
Cloud Tasks worker, least-privilege identities, and hosted security evidence.

**Architecture:** Keep one same-origin public FastAPI service for the browser
and authenticated APIs, and keep the accepted Phase 3 artifact worker as a
separate private Cloud Run service. Move production configuration, ownership,
request controls, rate limits, security headers, logging, and retention into
focused deterministic modules; keep Firestore as authority and identifiers as
locators. Build one pinned image target for each service, deploy both in
`us-east4` with distinct service accounts, and prove the deployed boundary with
two-user denial tests, log canaries, controlled worker failure, and rollback.

**Tech Stack:** Python 3.14.7, FastAPI 0.141.1, Pydantic 2.13.4, Uvicorn
0.52.4, Google ADK 2.7.0, Google GenAI SDK 2.18.1, Gemini 3.6 Flash through
Vertex AI, Firestore, Google Cloud Tasks, Cloud Run, Artifact Registry, Google
OIDC/IAM, Bash, vanilla JavaScript ES modules, Node test runner, and pytest.

**Spec and research input:**

- `docs/aug-25-2026-final-checklist.md`
- `docs/research/2026-08-25-phase-4-production-hardening-deployment-audit.md`
- `docs/superpowers/plans/2026-08-25-winning-core-phase-2-workspace-notes.md`
- `docs/superpowers/plans/2026-08-25-winning-core-phase-3-async-artifact-work.md`

**Governing repository references:**

- `AGENTS.md`
- `AGENT_COL_IDENTITY_AND_ALIGNMENT.md`
- `DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`

## Planning baseline and prerequisites

The source audit used commit `4e1fd4d` on `main`, with `origin/main` equal and
the worktree clean before this plan was drafted. That original baseline
included the approved Phase 4 research audit and planning documents for Phases
2 and 3; it did not include Phase 2 or Phase 3 implementation. As of the
August 27, 2026 documentation reconciliation, Phase 2 is accepted and Phase 3
durable asynchronous artifact work is still pending.

Phase 4 implementation must not start until:

1. every Phase 1 pass is accepted and checkpointed;
2. every Phase 2 pass is accepted and checkpointed;
3. every Phase 3 pass is accepted and checkpointed;
4. this plan is re-audited against that accepted Phase 3 commit;
5. the re-audit replaces predicted note/job/worker paths and query contracts
   with their accepted names and fields;
6. Pass 4A is separately approved for implementation.

The re-audit is a stop gate, not clerical cleanup. It must verify the final
notes schema, job schema, worker route, queue settings, cancellation behavior,
Firestore paths, indexes, public job APIs, and frontend transport before Phase
4 source changes begin.

## Verified current source state

At the planning baseline:

- `auth.py` verifies Google ID tokens against the configured OAuth audience,
  derives identity from `sub`, and prevents a supplied user ID from replacing
  the verified principal.
- `load_auth_settings()` silently defaults an absent `AGENT_COL_AUTH_MODE` to
  `local_dev`; this is the highest-priority fail-open production defect.
- Google workspace authorization accepts a derived ID or derived prefix. It
  does not read an authoritative workspace owner record.
- `AuthenticatedPrincipal.public_dict()` exposes the raw Google subject and
  email, and the current internal Google user ID embeds the raw subject.
- workspace list records live below `users/{user_id}/workspaces`, but the
  default workspace is synthesized when absent; `projects/{project_id}` stores
  only update metadata and is not a canonical owner record.
- session documents store `user_id` and `project_id`; direct session reads
  compare both, and chat-turn transactions already reject stored-owner drift.
- project artifact and feedback routes authenticate a project locator before
  reading project subcollections, but the route gate is still prefix-based.
- Pydantic bounds identifiers, 10,000-character messages/source text,
  200,000-character generic artifacts, feedback, lists, and detail pages.
- no ASGI middleware rejects a total oversized request before JSON parsing.
- no request-rate limiter exists.
- only `/workspace` and static files receive explicit `Cache-Control: no-store`;
  no complete production CSP/header policy exists.
- `generic_artifact_service.py` logs full Pydantic `ValidationError` strings,
  which can include rejected artifact values.
- `POST /api/synthesize` is not used by the browser and remains synchronous,
  public, and outside the chat idempotency ledger.
- `Database.list_chat_sessions()` scans up to 200 global session documents,
  filters owner/workspace in Python, sorts locally, and can omit valid sessions
  after the global scan ceiling.
- `firestore.indexes.json` has no composite indexes and only excludes the
  large blueprint field from indexing.
- dependencies are pinned, but the interpreter and container base are not;
  no `Dockerfile`, `.dockerignore`, production process command, release script,
  or Cloud Run service configuration exists.
- the local virtual environment is Python 3.14.7.

## Reconciled research conclusions

The Phase 4 research audit is correct against the baseline source. Its ten
principal blockers are all represented in the passes below. The plan adds two
source-grounded clarifications:

1. the existing project root is the cleanest canonical workspace authority
   because all workspace artifacts already live below it; the user workspace
   subcollection should remain a list projection, not become a second authority;
2. privacy hardening must address the raw subject embedded in the current
   `google--{subject}` user ID, not only remove the separate `subject` and
   `email` response fields.

The audit's Phase 3 dependency remains controlling. Phase 4 must configure and
prove the accepted worker; it must not redesign job fencing, retry, cancellation,
or artifact completion.

## Resolved architecture and operating decisions

These decisions close the audit's owner choices for this plan. Approval of the
plan approves these as implementation targets, not their implementation.

### Hosted edge

- Use the default HTTPS Cloud Run URL for the judged build.
- Do not add an external load balancer or Cloud Armor in the Winning Core.
- Keep the browser and API same-origin and do not add wildcard CORS.
- Allow unauthenticated platform invocation of the public service only so the
  sign-in page and public auth configuration can load. Every private API keeps
  application-level Google OIDC and durable ownership enforcement.
- Keep the worker private at Cloud Run IAM and application job authority.

This is the bounded schedule choice. A load balancer remains a post-contest
option if measured abuse or a custom-domain requirement justifies it.

### Production environment and startup

Add `AGENT_COL_ENVIRONMENT=local|production`. Absence is valid only when tests
inject settings directly; executable launch commands must set it explicitly.
Production startup rejects:

- any auth mode other than `google_oidc`;
- a missing OAuth client ID;
- a non-HTTPS or non-exact `AGENT_COL_PUBLIC_ORIGIN`;
- a missing project ID, Firestore database ID, or deployment region;
- a region other than `us-east4` for Cloud Run/Tasks/Firestore integration;
- a Vertex model location other than the accepted `global` setting;
- missing accepted Phase 3 queue, worker URL, OIDC audience, or service-account
  configuration;
- debug/reload markers, credential-file settings, placeholders, or test failure
  injection.

Local development remains available only through explicit
`AGENT_COL_ENVIRONMENT=local AGENT_COL_AUTH_MODE=local_dev` or explicit local
Google OIDC settings.

### Principal and workspace authority

- Replace the raw-subject Google user ID with
  `google--{sha256(subject)[:32]}`.
- Public auth session data contains authenticated state, auth mode, local-dev
  flag, opaque user ID, opaque workspace ID, and display name. It omits raw
  subject and email.
- `projects/{workspace_id}` is the canonical workspace record and stores
  contract version, workspace ID, owner user ID, lifecycle status, display
  name, and timestamps.
- `users/{user_id}/workspaces/{workspace_id}` is a bounded list projection. A
  mismatch between projection and canonical owner fails closed.
- Workspace IDs, session IDs, artifact IDs, memory/note IDs, job IDs, and task
  names remain locators only.
- Missing and foreign resources use the same authenticated public unavailable
  result, normally HTTP 404. Missing authentication remains HTTP 401.

A one-time, dry-run-first migration preserves the existing Google user's
memory, sessions, workspace projection, project metadata, and owned child
resources while changing the principal ID and backfilling canonical owner
records. The operator supplies the legacy Google subject only through the
`AGENT_COL_MIGRATION_GOOGLE_SUBJECT` process environment; the tool never prints
or persists that value. It aborts on any owner conflict and separates target
creation (`--apply`) from source removal (`--finalize`). Finalize is refused
until a later run verifies target counts, owner fields, and a completed
migration marker.

### Public generation boundaries

- Disable `POST /api/synthesize` in production with a deterministic 404 while
  retaining it in explicit local development for diagnostic compatibility.
- The accepted Phase 3 chat-routed blueprint job is the only production
  blueprint-generation entry point.
- Generic single-file generation remains synchronous and public but receives
  ownership, body-size, per-user rate, timeout, and Cloud Run scaling controls.

### Request and rate limits

- Reject any API request body above 256 KiB before JSON parsing with HTTP 413.
- Retain stricter Pydantic field and list limits; no upload/multipart boundary
  is introduced.
- Apply durable Firestore fixed-window limits to authenticated provider-cost
  operations using opaque SHA-256 counter IDs and TTL expiry.
- Apply a bounded process-local limiter to unauthenticated auth/config traffic
  as coarse abuse restraint; it is not an identity or cost authority.
- Initial authenticated limits per verified principal are:
  - chat: 12 requests per 60 seconds;
  - generic artifact generation/version generation: 4 per 60 seconds;
  - blueprint job submission: 4 per 60 seconds;
  - explicit failed-job retry: 3 per 10 minutes;
  - deterministic reads/mutations: 120 per 60 seconds.
- Return HTTP 429 with an integer `Retry-After` header.
- Rate documents expire 24 hours after their window and never contain raw
  identity, route parameters, prompts, or content.

### Browser security policy

Production responses use:

```text
Content-Security-Policy: default-src 'self'; script-src 'self' https://accounts.google.com/gsi/client; style-src 'self' https://accounts.google.com/gsi/style; frame-src https://accounts.google.com/gsi/; connect-src 'self' https://accounts.google.com/gsi/; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
Strict-Transport-Security: max-age=31536000; includeSubDomains
Cache-Control: no-store
```

HSTS is emitted only in production. The exact CSP is not accepted until live
Google sign-in succeeds under it.

### Safe observability

- Generate a server-owned request ID for every request and return it in
  `X-Request-ID`.
- Structured application logs allow only event code, operation, result/status,
  latency bucket, attempt/job state, exception class, and opaque hashed resource
  reference when needed.
- Logs never include prompts, messages, source text, memory/note values,
  artifact/feedback content, provider output, email, raw subject, bearer token,
  authorization header, or full Pydantic error text.
- Cloud Logging retention is 30 days for the judged project.

### Retention and deletion

- Active user-owned memory, notes, workspaces, sessions, messages, artifacts,
  and feedback remain until explicit deletion; no silent content TTL is added.
- Terminal artifact jobs and immutable bounded job input snapshots retain for
  30 days, then use Firestore TTL.
- rate-limit counters retain for at most 24 hours through TTL.
- content-free deletion operation receipts retain for 30 days.
- Workspace deletion is authenticated, idempotent, resumable, and bounded to
  100 document deletions per continuation. It marks the workspace `deleting`
  before removing descendants and denies new work while deletion is active.
- Account deletion first blocks new work, then uses the same bounded resumable
  mechanism across every owned workspace and the user's profile-memory domain.
- Profile memory is global to the account and is not deleted by deleting one
  workspace.
- Historical responses are not rewritten when one memory/note value is deleted;
  future reads stop projecting the deleted value.
- Parent deletion never assumes Firestore subcollection cascade.

The deletion operation is deterministic application maintenance, not a second
agent workflow. It does not call Gemini, ADK, Cloud Tasks, or the artifact
worker.

### Runtime and Cloud Run controls

- Runtime: Python 3.14.7.
- Region: `us-east4`; Vertex model location remains `global`.
- Artifact Registry repository: `agent-col`.
- Public service: `agent-col-web`; service account:
  `agent-col-web-runtime`.
- Worker service: accepted Phase 3 `agent-col-artifact-worker`; runtime service
  account: `agent-col-worker-runtime`.
- Task OIDC service account: `agent-col-task-caller`.
- Public service: 1 CPU, 1 GiB memory, concurrency 8, 180-second timeout,
  minimum instances 0, maximum instances 2.
- Worker: accepted Phase 3 values initially remain 1 CPU, 1 GiB, concurrency 1,
  180-second timeout, minimum instances 0, maximum instances 1.
- Cloud Tasks queue remains 1 dispatch/second, 1 concurrent dispatch, and 3
  attempts unless accepted Phase 3 evidence requires a lower value.
- Use Cloud Run service identity/ADC; never mount a service-account key.
- Configure a USD 100 billing budget with 50%, 80%, and 100% alerts. Budgets
  notify rather than cap; rate limits, task limits, and maximum instances are
  the actual cost controls.

## Phase pass outline

Implement, verify, manually accept, and checkpoint each pass before requesting
approval for the next.

| Pass | Outcome | Primary boundary |
| --- | --- | --- |
| 4A | Production settings fail closed, public identity is minimized, and existing data has a dry-run-first principal/workspace migration path. | Configuration and identity. |
| 4B | Canonical workspace ownership protects every accepted domain and a two-principal denial matrix proves IDs are only locators. | Authorization and persistence. |
| 4C | Body limits, durable rate controls, security headers, auth-expiry UX, request IDs, and content-safe logs are enforced. | Abuse, browser, and observability controls. |
| 4D | Production queries/indexes are owner-constrained and retention plus resumable workspace/account deletion are deterministic. | Data lifecycle. |
| 4E | Pinned non-root public/worker images build and run locally with production commands and health contracts. | Container release artifact. |
| 4F | Least-privilege identities, queue OIDC, indexes, budget alerts, and both Cloud Run services are deployed in `us-east4`. | Google Cloud deployment. |
| 4G | Hosted auth, denial, limits, logging, worker failure/retry, cost controls, and rollback produce judge-grade closure evidence. | Production acceptance. |

## Global constraints and preserved invariants

- Each pass requires separate explicit approval before source, data, cloud, or
  behavior changes.
- Every source-changing pass uses RED, verified RED, minimal GREEN, verified
  GREEN, then refactor.
- Stop at **implemented, pending manual verification** until user acceptance.
- Checkpoint only accepted work with explicit path staging to `origin/main`.
- Re-audit this plan after accepted Phase 3; do not overwrite newer note/job
  files based on predicted names in this plan.
- Agent Col remains the sole user-facing responder and retains its general
  Collaborative Partner identity.
- Google OIDC identity and canonical stored ownership authorize operations;
  browser identifiers never do.
- Firestore remains the durable source of truth for memory, notes, chat,
  artifacts, jobs, ownership, and deletion state.
- Profile memory and workspace notes remain separate domains.
- Phase 4 configures the accepted durable artifact worker but does not redesign
  Phase 3 state transitions, fencing, cancellation, or completion.
- No public route may run under implicit local-development trust.
- No prompt, note, memory value, feedback, artifact content, token, email, or
  raw subject may enter logs, task payloads, migration reports, or screenshots.
- Same-origin browser transport remains; no wildcard CORS is added.
- No load balancer, Cloud Armor, GKE, Pub/Sub, generalized task engine,
  unrestricted planner, vector database, PDF upload, or unrelated UI redesign.
- Phase 5 owns comprehensive README/architecture/submission reconciliation;
  Phase 4 adds only the runbooks and evidence necessary to deploy and rollback.

## Required pass handoff evidence

Every accepted pass must record:

- accepted checkpoint hash and implementation baseline;
- exact created/modified files and responsibilities;
- RED failure, minimal GREEN, refactor summary, and focused commands/results;
- public/internal contract versions, Firestore paths, indexes, and migration
  state changed by the pass;
- manual inputs and observed outputs without private content;
- cloud resources, regions, revisions, IAM bindings, limits, and cleanup state;
- limitations, source drift, and next-pass stop conditions.

---

## Pass 4A - Fail-Closed Configuration and Principal Migration

### Goal and reviewable outcome

Make production startup impossible under local-development trust, minimize the
public Google identity projection, and provide a tested dry-run-first migration
from raw-subject user IDs and prefix-only projects to opaque principal IDs and
canonical workspace owner records.

### Expected file boundary

- Create `production_config.py` for strict local/production settings and
  startup validation.
- Create `workspace_ownership.py` for canonical workspace records and owner
  status contracts.
- Create `principal_migration.py` for deterministic migration planning and
  conflict validation.
- Create `scripts/migrate-principal-ownership.py` as the explicit operator
  entry point.
- Modify `auth.py` for opaque Google user IDs and minimal public projection.
- Modify `main.py` only for settings/lifespan wiring and production gating of
  `/api/synthesize`.
- Modify accepted repository composition only as required to share the
  Firestore client with the ownership repository.
- Create `tests/test_production_config.py`.
- Create `tests/test_workspace_ownership.py`.
- Create `tests/test_principal_migration.py`.
- Modify `tests/test_auth.py` and focused auth/lifespan tests in
  `tests/test_main.py`.

### Interfaces and contracts

`ProductionSettings` must expose validated environment, auth, public origin,
project, database, region, Vertex, queue, worker, and service-account values.
`WorkspaceOwnerRecord` uses contract version `1.0`, owner user ID, workspace
ID, lifecycle status `active|deleting`, display name, and timestamps.
`PrincipalMigrationPlan` keeps the source locator private in process and exposes
only source/target SHA-256 fingerprints, document counts, conflicts, and
dry-run/apply/finalize state; it contains no profile values or content.

### TDD implementation cycles

- [ ] RED configuration tests proving production rejects absent environment,
      local auth, HTTP origin, missing OAuth/project/database/region/worker
      settings, credential-file variables, debug/reload, placeholders, and
      failure-injection flags.
- [ ] Verify RED with
      `venv/bin/pytest -q tests/test_production_config.py` and confirm failures
      are missing configuration behavior, not fixture errors.
- [ ] GREEN the smallest strict settings loader; keep explicit local launch
      behavior valid.
- [ ] RED auth tests proving user ID is SHA-256-derived and public session omits
      subject/email while preserving display name and opaque locators.
- [ ] GREEN `auth.py` without weakening token audience/signature/expiry checks.
- [ ] RED route tests proving production `/api/synthesize` is unavailable and
      local development retains the existing route.
- [ ] GREEN the environment gate without changing chat-routed blueprint jobs.
- [ ] RED migration tests for dry-run, idempotent target reuse, canonical owner
      backfill, raw-subject-free report output, source/target conflict refusal,
      no source deletion during apply, and finalize refusal before verified
      target counts/owner fields/completion marker.
- [ ] GREEN the migration planner/repository and CLI with `--dry-run` required
      by default and explicit `--apply` for a separately approved live run.
- [ ] REFACTOR settings/identity wiring after all focused tests remain green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_production_config.py \
  tests/test_workspace_ownership.py \
  tests/test_principal_migration.py \
  tests/test_auth.py \
  tests/test_main.py -k 'auth or lifespan or synthesize'
venv/bin/python -m py_compile \
  production_config.py workspace_ownership.py principal_migration.py \
  auth.py main.py scripts/migrate-principal-ownership.py
git diff --check
```

The full suite is not required because this pass changes startup and auth
contracts but not domain behavior; Pass 4B broadens verification across every
owned route.

### Manual/runtime acceptance targets

1. Start explicit local development and verify `/workspace` still loads.
2. Attempt production startup with each required variable missing and observe
   process refusal before serving requests.
3. Start local Google OIDC and verify sign-in shows the same display name but
   `/api/auth/session` contains no subject or email.
4. Run migration dry-run and inspect only counts/opaque IDs; do not apply live
   migration until its report is separately approved.

### Stop conditions and exclusions

- Stop if Phase 1-3 accepted data contains an ownership relation the migration
  cannot map without reading user content.
- Stop if a target owner record conflicts with an existing owner.
- No live data migration, IAM, deployment, deletion, or browser redesign.

---

## Pass 4B - Durable Ownership and Complete Denial Matrix

### Goal and reviewable outcome

Replace prefix authority with canonical stored workspace ownership and prove
owner success plus uniform foreign denial across workspaces, sessions, memory,
notes, blueprints, generic artifacts, feedback, jobs, and worker execution.

### Expected file boundary

- Modify `workspace_ownership.py` for owner resolution and lifecycle denial.
- Create `authorization_service.py` for authenticated domain authorization.
- Modify `main.py` to use async durable workspace authorization on every
  workspace route.
- Modify accepted Phase 2 note repository/service files for canonical owner
  checks only where their stored checks are insufficient.
- Modify accepted Phase 3 job repository/API/worker files for canonical owner
  and worker-job checks only where insufficient.
- Modify `database.py` or accepted split repositories for canonical project
  owner writes, session owner queries, and stored child-owner validation.
- Create `tests/test_authorization_service.py`.
- Create `tests/test_production_ownership_matrix.py`.
- Modify focused database, note, artifact, feedback, job, worker, and main tests.

### Ownership matrix

| Domain | Required authority |
| --- | --- |
| Workspace | canonical `projects/{workspace_id}.owner_user_id` |
| Session | canonical workspace owner plus stored session user/workspace |
| Profile memory | authenticated opaque user ID |
| Workspace note | canonical workspace owner plus stored note user/workspace |
| Blueprint/generic artifact | canonical workspace owner plus stored artifact user where present |
| Feedback | owner of canonical parent artifact/workspace |
| Durable job | canonical workspace owner plus stored job user/workspace/session/operation |
| Worker execution | Cloud Run IAM caller plus valid canonical stored job and allowed state transition |

### TDD implementation cycles

- [ ] RED repository tests proving canonical workspace creation writes project
      authority and user-list projection atomically and rejects owner drift.
- [ ] GREEN canonical owner creation/read without relying on ID shape.
- [ ] RED authorization tests with principal A/B, workspace A/B, a forged
      owner-looking prefix, valid foreign IDs, missing resources, and a
      `deleting` workspace.
- [ ] GREEN the deterministic authorization service and uniform unavailable
      classification.
- [ ] RED one owner/foreign/missing matrix row for every accepted public
      operation, including note lifecycle/retrieval and job list/detail/cancel/
      retry/result operations.
- [ ] GREEN route/repository integration. Authentication failures remain 401;
      authenticated missing and foreign resource results become indistinguishable.
- [ ] RED worker tests proving browser tokens, unauthenticated calls, wrong task
      caller, foreign job ownership, wrong operation, and invalid transitions
      cannot execute; valid task identity alone is insufficient without job
      authority.
- [ ] GREEN the accepted private worker checks without changing Phase 3 fencing.
- [ ] RED regression tests proving direct Firestore locators cannot bypass
      parent workspace ownership and profile memory remains account-scoped.
- [ ] REFACTOR repeated route authorization into narrow dependencies/helpers
      only after the matrix is green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_workspace_ownership.py \
  tests/test_authorization_service.py \
  tests/test_production_ownership_matrix.py \
  tests/test_auth.py \
  tests/test_database.py \
  tests/test_chat_turn_database.py \
  tests/test_artifact_read_service.py \
  tests/test_artifact_feedback_service.py \
  tests/test_generic_artifact_service.py \
  tests/test_main.py \
  tests/test_worker_main.py
git diff --check
```

Broader ownership verification is required because one authorization contract
is shared by every durable domain and public route.

### Manual/runtime acceptance targets

1. With two Google accounts, create one workspace each and prove each owner can
   use their own memory, notes, chats, artifacts, feedback, and jobs.
2. Swap every captured locator between accounts and verify the same unavailable
   response as a nonexistent locator, with no private content in the browser.
3. Invoke the worker directly without Cloud Tasks and verify platform denial.
4. Mark a test workspace deleting and verify new chat, note, artifact, and job
   work is refused.

### Stop conditions and exclusions

- Stop if any accepted Phase 2/3 repository cannot establish parent ownership
  without a schema migration; revise the pass before writing around it.
- No rate limits, retention deletion, cloud IAM changes, or deployment yet.

---

## Pass 4C - Limits, Browser Security, and Content-Safe Observability

### Goal and reviewable outcome

Reject oversized and excessive requests before costly work, apply the tested
Google-compatible browser policy, recover cleanly from expired authentication,
and prove application logs cannot contain unique user-content canaries.

### Expected file boundary

- Create `request_controls.py` for body ceilings, request IDs, and route classes.
- Create `rate_limits.py` for fixed-window contracts and Firestore repository.
- Create `security_headers.py` for environment-aware response policy.
- Create `safe_observability.py` for allowlisted structured events.
- Modify `main.py` for middleware/dependency wiring and 413/429 projection.
- Modify `generic_artifact_service.py` to remove full validation errors.
- Audit every current production logging call listed by a static inventory test;
  if a second content-bearing source path is found, stop and revise this file
  boundary before modifying that module.
- Modify `frontend/api.mjs`, `frontend/state.mjs`, `frontend/app.mjs`, and
  `frontend/auth-view.mjs` for 401 expiry and 413/429 handling.
- Create `tests/test_request_controls.py`, `tests/test_rate_limits.py`,
  `tests/test_security_headers.py`, and `tests/test_safe_observability.py`.
- Modify `tests/test_generic_artifact_service.py`, focused `tests/test_main.py`,
  and corresponding frontend tests.

### TDD implementation cycles

- [ ] RED ASGI tests proving 256 KiB succeeds when the domain schema permits,
      256 KiB plus one byte returns 413, lying/missing `Content-Length` cannot
      bypass streaming enforcement, and no route/service executes after denial.
- [ ] GREEN a streaming ASGI body-limit wrapper that never buffers beyond the
      ceiling solely to produce an error.
- [ ] RED rate tests for each exact operation/window limit, verified-principal
      identity, deterministic hashed counter IDs, atomic increments, 429,
      integer `Retry-After`, bounded unauthenticated entries, and 24-hour expiry.
- [ ] GREEN Firestore fixed-window cost controls and bounded local coarse limiter.
- [ ] RED header tests for the exact production policy, HSTS omission in local
      HTTP, no-store on private APIs, safe download content type/filename, no
      wildcard CORS, and server-owned `X-Request-ID`.
- [ ] GREEN response middleware without adding inline-script CSP exceptions.
- [ ] RED canary tests inserting unique values into chat, note, memory,
      artifact, feedback, Pydantic failures, provider failures, auth denial,
      ownership denial, and rate denial; assert neither values nor raw tokens,
      subjects, or emails appear in captured logs.
- [ ] GREEN allowlisted event logging and content-free validation warnings.
- [ ] RED frontend tests proving 401 clears token/private state and returns to
      sign-in, 413 displays a size-specific error, and 429 displays retry timing
      without retry loops.
- [ ] GREEN centralized frontend transport/state handling.
- [ ] REFACTOR only after Python and Node tests remain green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_request_controls.py \
  tests/test_rate_limits.py \
  tests/test_security_headers.py \
  tests/test_safe_observability.py \
  tests/test_generic_artifact_service.py \
  tests/test_main.py -k 'limit or header or auth or log or artifact or chat or job'
node --test \
  tests/frontend/api.test.mjs \
  tests/frontend/state.test.mjs \
  tests/frontend/auth-view.test.mjs
git diff --check
```

### Manual/runtime acceptance targets

1. Sign in with Google under the CSP and verify no blocked required GIS
   script/frame/connect request in browser developer tools.
2. Exceed one low test rate and verify 429 plus countdown, then success after
   the window without duplicate work.
3. Expire/replace the token and verify private workspace content clears before
   the sign-in view returns.
4. Trigger safe canaries, inspect local captured logs, and confirm no canary,
   email, subject, token, prompt, note, feedback, or artifact content appears.

### Stop conditions and exclusions

- Stop if the exact CSP blocks Google sign-in; measure the blocked origin and
  revise only the required directive.
- Stop if durable rate accounting can double-charge an idempotent replay; rate
  policy must distinguish accepted new work from exact replay where required.
- No Cloud Logging claim until Pass 4G queries hosted logs.

---

## Pass 4D - Retention, Resumable Deletion, Production Queries, and Indexes

### Goal and reviewable outcome

Replace global/filter-in-Python reads, codify retention, and let an authenticated
owner delete a workspace or account through a bounded, interruption-safe
operation that cannot resurrect data or accept new work during deletion.

### Expected file boundary

- Create `retention_policy.py` for exact domain retention rules and TTL fields.
- Create `deletion_operations.py` for strict status/progress/receipt contracts.
- Create `deletion_service.py` for bounded workspace/account deletion stages.
- Create `deletion_repository.py` or extend the accepted domain repositories
  only where transaction/batch ownership makes that necessary.
- Modify `workspace_ownership.py` and `authorization_service.py` for deletion
  lifecycle gates.
- Modify `database.py` or accepted split repositories for owner-constrained
  session/note/job/artifact queries.
- Modify `main.py` for authenticated start/status/continue deletion endpoints.
- Modify `firestore.indexes.json` and `tests/test_firestore_indexes.py` from
  accepted query fields only.
- Create `tests/test_retention_policy.py`, `tests/test_deletion_operations.py`,
  `tests/test_deletion_service.py`, and `tests/test_deletion_repository.py`.
- Modify focused database, main, note, job, and ownership tests.

### Deletion stages

Workspace deletion advances in this fixed order: mark canonical workspace
`deleting`; request cancellation of nonterminal accepted Phase 3 jobs; remove
job attempts/snapshots; notes/provenance; feedback; artifacts/blueprints;
session turns/messages/clarifications; sessions; user workspace projection;
canonical workspace record; write a content-free terminal receipt. Account
deletion runs each owned workspace stage first, then profile memory proposals,
origins, events, active profile, user projections, and user root. Each call
deletes at most 100 documents and persists the next stage/cursor before return.

### TDD implementation cycles

- [ ] RED policy tests for exact 30-day terminal-job/deletion-receipt retention,
      24-hour rate retention, explicit-user-delete content behavior, and global
      profile memory exclusion from one-workspace deletion.
- [ ] GREEN immutable retention contracts and TTL field writers.
- [ ] RED session query tests proving Firestore predicates constrain both owner
      and workspace before limit/order and return complete newest results.
- [ ] RED accepted note/job query tests for owner/workspace/status/time fields.
- [ ] GREEN query changes and only the composite indexes those tests require.
- [ ] RED deletion model/repository tests for idempotency-key conflict, owner
      mismatch, active-to-deleting transition, 100-document ceiling, durable
      stage/cursor, interruption/retry, terminal replay, and no parent-first
      orphaning.
- [ ] GREEN bounded repository primitives.
- [ ] RED service tests for every ordered domain, active-job cancellation,
      new-work denial, workspace-only preservation of profile memory, complete
      account deletion, foreign status/continue denial, and no resurrection.
- [ ] GREEN deterministic deletion service without Gemini/ADK/Cloud Tasks.
- [ ] RED FastAPI tests for authenticated start/status/continue, 202 progress,
      terminal 200, same-key replay, changed-request conflict, and uniform
      foreign unavailability.
- [ ] GREEN route projections and bounded public receipts.
- [ ] REFACTOR stage handlers after interruption tests remain green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_retention_policy.py \
  tests/test_deletion_operations.py \
  tests/test_deletion_repository.py \
  tests/test_deletion_service.py \
  tests/test_firestore_indexes.py \
  tests/test_database.py \
  tests/test_workspace_ownership.py \
  tests/test_production_ownership_matrix.py \
  tests/test_main.py -k 'session or deletion or workspace or ownership'
git diff --check
```

Broader persistence verification is required because deletion crosses every
durable domain. The final accepted Phase 2/3 test files must be added during
the mandatory pre-implementation re-audit.

### Manual/runtime acceptance targets

1. Build a disposable workspace containing chat, clarification, note,
   blueprint, generic artifact, feedback, and terminal job data.
2. Interrupt deletion after one batch, restart the app, continue with the same
   key, and verify completion without duplicate/resurrected data.
3. Verify profile memory survives workspace deletion and disappears only after
   a separately confirmed account deletion on a disposable test account.
4. Verify a foreign account cannot start, inspect, or continue either deletion.

### Stop conditions and exclusions

- Stop if accepted Phase 2/3 data has an unenumerated child collection.
- Stop if any query needs an index not represented in source and tests.
- No silent scheduled content deletion, content export, or browser deletion UI
  is included unless separately approved.

---

## Pass 4E - Pinned Production Containers and Local Release Proof

### Goal and reviewable outcome

Produce deterministic, non-root public and worker container targets that exclude
local credentials/data, honor Cloud Run's port contract, validate production
settings, and pass local health and shutdown checks.

### Expected file boundary

- Create one multi-stage `Dockerfile` with named `web` and `worker` runtime
  targets sharing a pinned dependency/runtime base.
- Create `.dockerignore`.
- Create `scripts/start-web.sh` and `scripts/start-worker.sh` with `exec`,
  `0.0.0.0`, injected `PORT`, and no reload.
- Create `scripts/verify-container.sh` for deterministic local inspection.
- Modify `main.py` and accepted `worker_main.py` only for `/health/live` and
  `/health/ready` boundaries that do not call Gemini/Firestore per probe.
- Create `tests/test_container_contract.py` and focused health tests.

### Container contract

- Pin Python 3.14.7 and every Python requirement.
- Install only `requirements.txt` in runtime layers.
- Run as a non-root application user.
- Copy only runtime Python, frontend, and required metadata files.
- Exclude `.git`, `.env`, ADC/credential JSON, `venv`, caches, downloads,
  screenshots, tests, research/evidence, and local Firestore data.
- Web command: Uvicorn `main:app` on `0.0.0.0:${PORT}` without reload.
- Worker command: Uvicorn accepted `worker_main:app` on
  `0.0.0.0:${PORT}` without reload.

### TDD implementation cycles

- [ ] RED static contract tests for pinned runtime, non-root user, no reload,
      injected port/all-interface bind, required files, forbidden image paths,
      and separate web/worker commands.
- [ ] GREEN Docker/start/ignore files.
- [ ] RED health tests proving liveness is process-only, readiness reflects
      validated startup state, and neither probe calls Firestore, Vertex, ADK,
      or Cloud Tasks.
- [ ] GREEN minimal health routes in both apps.
- [ ] Build both targets from the clean worktree.
- [ ] Run containers with explicit production environment and injected ports;
      verify health, workspace/static assets, Google auth config, non-root UID,
      signal shutdown, and absence of forbidden files.
- [ ] REFACTOR image layers only when behavior and inspection remain green.

### Focused automated verification

```bash
venv/bin/pytest -q tests/test_container_contract.py tests/test_main.py -k health tests/test_worker_main.py -k health
docker build --target web -t agent-col-web:phase4 .
docker build --target worker -t agent-col-worker:phase4 .
scripts/verify-container.sh agent-col-web:phase4 agent-col-worker:phase4
git diff --check
```

Container builds are required because static Dockerfile tests cannot prove
installed dependencies, copied contents, UID, startup, or port behavior.

### Manual/runtime acceptance targets

1. Start each image on a nondefault injected port and verify health.
2. Inspect web image contents and confirm no `.env`, ADC, credential JSON,
   tests, screenshots, `venv`, or user content.
3. Verify the web image reaches the Google sign-in screen and the worker image
   rejects unauthenticated execution.
4. Stop both with `docker stop` and verify clean process shutdown.

### Stop conditions and exclusions

- Stop if Python 3.14.7 base availability or a native dependency prevents a
  reproducible image; do not silently change runtime.
- No push to Artifact Registry or Cloud Run deployment in this pass.

---

## Pass 4F - Least-Privilege Google Cloud Deployment

### Goal and reviewable outcome

Create and deploy the accepted indexes, public service, private worker, queue
OIDC, service identities, runtime limits, logging retention, TTL policies, and
budget alerts through reviewable idempotent scripts.

### Expected file boundary

- Create `deploy/cloud-run.env.example` with names only and no credentials.
- Create `scripts/deploy-production.sh` for APIs, registry, images, services,
  queue integration, and output summary.
- Create `scripts/configure-production-iam.sh` for explicit service accounts
  and narrow bindings.
- Create `scripts/configure-production-data.sh` for indexes, TTL, and logging
  retention/exclusions.
- Create `scripts/configure-budget.sh` for the USD 100 alerting budget.
- Create `scripts/rollback-production.sh` for explicit previous-revision traffic.
- Modify accepted Phase 3 deployment scripts rather than duplicate worker/queue
  creation when they already own a command.
- Modify `firestore.indexes.json` only if deployment validation exposes drift.
- Create `tests/test_production_deployment_contract.py`.
- Create `docs/development/production-operations.md` as the minimal deploy,
  smoke, rollback, and shutdown runbook needed for this phase.

### IAM boundary

- `agent-col-web-runtime`: accepted minimum Firestore data access, Vertex AI
  invocation, Cloud Tasks enqueue, and logging; no service-account key creator,
  project editor, owner, or worker invoker role.
- `agent-col-task-caller`: only `roles/run.invoker` on
  `agent-col-artifact-worker`; no Firestore or Vertex role.
- `agent-col-worker-runtime`: accepted minimum Firestore, Vertex AI, and logging;
  no public service administration or task enqueue unless Phase 3 proves it is
  required.
- the deployer identity may create/update resources but is not a runtime
  identity.

### TDD and deployment cycles

- [ ] RED static tests for exact project/region/service/queue/repository names,
      service-account separation, forbidden broad roles, public/worker ingress,
      OIDC audience, runtime controls, TTL policies, 30-day logs, budget values,
      and rollback command.
- [ ] GREEN idempotent scripts with `set -euo pipefail`, explicit project flags,
      preflight output, and no secret/token printing.
- [ ] Run script syntax/static tests and `gcloud ... --dry-run` or describe-only
      preflights where supported.
- [ ] With separate explicit approval, enable required APIs, create service
      accounts/repository/queue, apply IAM/indexes/TTL/logging/budget settings,
      build and push both images, and deploy both services.
- [ ] Configure the public service for unauthenticated platform invocation and
      application Google OIDC; keep worker unauthenticated invocation disabled.
- [ ] Set Cloud Tasks OIDC audience to the exact deployed worker URL.
- [ ] Read back every resource and compare effective values with the contract.
- [ ] Run the production principal migration dry-run against the live database;
      stop for separate approval before `--apply`, verify the copied target in
      a separate run, then stop for another approval before `--finalize` removes
      legacy source records.
- [ ] REFACTOR scripts only after repeated describe/apply is idempotent.

### Focused automated verification

```bash
venv/bin/pytest -q tests/test_production_deployment_contract.py tests/test_firestore_indexes.py
bash -n scripts/deploy-production.sh
bash -n scripts/configure-production-iam.sh
bash -n scripts/configure-production-data.sh
bash -n scripts/configure-budget.sh
bash -n scripts/rollback-production.sh
git diff --check
```

After separately approved cloud mutation, capture sanitized outputs from
`gcloud run services describe`, `gcloud tasks queues describe`, service-account
IAM policy reads, Firestore index/TTL reads, and budget description.

### Manual/runtime acceptance targets

1. Open the deployed public URL and reach Google sign-in.
2. Verify the worker URL returns platform 401/403 when invoked without the
   task-caller identity.
3. Verify public/worker revisions use their intended runtime service accounts,
   limits, image digests, and regions.
4. Verify no service-account keys were created and no runtime account has
   Editor/Owner.
5. Verify budget alerts, max instances, queue rate/concurrency/retries, TTL,
   and logging retention from Cloud Console or sanitized CLI output.

### Stop conditions and exclusions

- Stop before any cloud mutation unless that exact pass action is explicitly
  approved.
- Stop if an accepted Phase 3 IAM requirement conflicts with least privilege;
  investigate the exact API call before widening a role.
- No custom domain, load balancer, Cloud Armor, minimum instances, or public
  worker invocation.

---

## Pass 4G - Hosted Security, Failure, Cost, and Rollback Proof

### Goal and reviewable outcome

Prove the hosted system behaves as designed with real Google sign-in, two
principals, private worker delivery, bounded requests, content-safe logs,
controlled failure/retry, cost controls, and a successful revision rollback.

### Expected file boundary

- Create `hosted_production_check.py` for content-free deterministic HTTP
  checks that accept tokens only through environment/process input and never
  print them.
- Create `tests/test_hosted_production_check.py` for request construction,
  redaction, and failure classification.
- Modify accepted Phase 3 live-check tools only where real job failure/retry
  evidence needs reusable helpers.
- Create `docs/evidence/phase-4-production/README.md` as the evidence manifest.
- Modify `docs/aug-25-2026-final-checklist.md` and current status records only
  after user manual acceptance.

### Evidence scenarios

1. Google account A signs in and completes memory, note, chat, artifact, and
   queued blueprint operations in workspace A.
2. Account B receives the uniform unavailable result for A's workspace,
   session, note, artifact, feedback, and job locators.
3. Oversized body returns 413 before domain execution; rate excess returns 429
   with `Retry-After` and no duplicate side effect.
4. Google sign-in succeeds under CSP; responses have the exact headers and
   private content is not cached after auth expiry.
5. Unique canaries traverse success/failure paths; Cloud Logging query returns
   zero canary/token/email/raw-subject matches.
6. Cloud Tasks invokes the private worker; direct invocation is denied.
7. Environment-gated Phase 3 controlled failure produces one failed/retryable
   history and one later canonical completed artifact without duplication.
8. Traffic moves to a previous healthy public revision and back while worker
   authority and durable job state remain consistent.
9. Cloud Console/CLI proves max instances, queue limits, budget alerts, TTL,
   service identities, Firestore, Vertex AI, and image revisions.

### TDD and verification cycles

- [ ] RED runner tests for token redaction, same-origin URL validation,
      content-free output, account/workspace fixture separation, expected
      status classes, and canary hashing.
- [ ] GREEN the smallest hosted check runner; never persist or print tokens.
- [ ] Run offline production-hardening tests before provider/cloud quota.
- [ ] Run account A owner scenarios and account B denial matrix.
- [ ] Run limits, headers, auth expiry, worker IAM, controlled failure/retry,
      and canary log inspection.
- [ ] Roll public traffic to the previous healthy revision, run health/auth
      smoke, then restore the accepted candidate revision.
- [ ] Inspect billing/resource controls and capture privacy-reviewed evidence.
- [ ] REFACTOR only the runner/evidence manifest after all scenarios are stable.

### Focused and broader verification

```bash
venv/bin/pytest -q tests/test_hosted_production_check.py
node --test tests/frontend/*.test.mjs
venv/bin/pytest -q \
  tests/test_production_config.py \
  tests/test_workspace_ownership.py \
  tests/test_authorization_service.py \
  tests/test_production_ownership_matrix.py \
  tests/test_request_controls.py \
  tests/test_rate_limits.py \
  tests/test_security_headers.py \
  tests/test_safe_observability.py \
  tests/test_retention_policy.py \
  tests/test_deletion_operations.py \
  tests/test_deletion_repository.py \
  tests/test_deletion_service.py \
  tests/test_container_contract.py \
  tests/test_production_deployment_contract.py \
  tests/test_firestore_indexes.py
git diff --check
```

The complete directly affected hardening set is required because Phase 4's
closure claim spans shared auth, persistence, browser, worker, and deployment
contracts. The full historical repository suite remains Phase 5 clean-clone
reproducibility work unless a focused check exposes cross-domain regression.

### Manual/runtime acceptance targets

1. Complete every evidence scenario above at the hosted URL with privacy-safe
   screenshots and sanitized Cloud Console/CLI captures.
2. Confirm the application remains usable after rollback and restoration.
3. Confirm all canary Cloud Logging searches return zero matches.
4. Confirm no private data or credentials appear in evidence files or Git
   status.

### Stop conditions and exclusions

- Any cross-owner data exposure, fail-open auth, public worker invocation,
  content-bearing log, duplicate artifact, unbounded cost path, or failed
  rollback keeps Phase 4 failed.
- Do not weaken tests, ownership, CSP, IAM, or limits to make hosted checks pass;
  use systematic debugging and a separately approved correction pass.
- No Phase 5 documentation reconciliation begins before user acceptance and
  checkpoint of Phase 4.

## Material risks and mitigations

- **Plan drift before execution:** Phase 2 has landed after the original
  baseline, while Phase 3 durable asynchronous artifact jobs are still pending.
  Mandatory re-audit and explicit stop conditions prevent guessed paths from
  overwriting accepted contracts.
- **Identity migration risk:** changing raw-subject IDs touches durable memory
  and ownership. Dry-run, conflict refusal, target verification, no same-run
  source deletion, and separate live-apply approval protect existing data.
- **Dual ownership drift:** project root is canonical; user workspace records
  are projections and mismatch fails closed.
- **Rate-limit contention:** fixed windows are per principal/operation/window,
  expire through TTL, and avoid one global hot document.
- **CSP sign-in breakage:** exact directives are automated, but live GIS sign-in
  is the acceptance gate.
- **Deletion complexity:** fixed stage order, 100-document batches, durable
  cursors, and retry tests avoid parent-first orphaning and timeout dependence.
- **Cloud IAM widening:** scripts forbid broad roles and require read-back proof;
  any missing permission is diagnosed from the exact denied operation.
- **Cold starts:** minimum instances remain zero for cost. The demo rehearsal in
  Phase 6 may warm the service without changing the billed architecture.
- **Budgets are not caps:** application rate limits, task dispatch bounds, and
  Cloud Run maximum instances remain the enforcement boundary.

## Explicit exclusions

- External load balancer, custom domain, Cloud Armor, CDN, or broad CORS.
- General-purpose rate-limit platform or third-party cache.
- Generalized background/deletion task engine.
- Redesign of Agent Col routing, memory, notes, artifacts, or Phase 3 jobs.
- PDF upload, semantic transcript search, vector database, or generalized
  autonomous planner.
- Comprehensive README, architecture diagram, licensing audit, clean-clone
  proof, and submission reconciliation; those remain Phase 5.
- Demo script, Devpost text, and build freeze; those remain Phase 6.

## Phase 4 closure condition

Phase 4 is complete only after every pass is separately approved, implemented
through TDD, manually accepted, and checkpointed; both pinned services are
deployed in `us-east4`; Google OIDC and durable ownership fail closed; limits,
headers, logs, retention, deletion, IAM, queue delivery, cost controls, and
rollback are proven against the hosted build; and the evidence contains no
private content or credentials.

Until then, status remains **planned, pending approval** or **implemented,
pending manual verification** at the applicable pass boundary.
