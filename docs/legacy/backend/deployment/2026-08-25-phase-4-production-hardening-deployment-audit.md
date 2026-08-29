# Phase 4 Production Hardening and Deployment Audit

Date: August 25, 2026
Pass: M10-RSCH.2
Status: Approved read-only research audit; no Phase 4 implementation authorized

Status note, August 27, 2026: this audit remains useful production-hardening
provenance, but worker and Cloud Tasks sections describe the older
durable-async path. The current pre-submission path is single-service Cloud Run
hardening without private worker or queue requirements. Use
[`../final-checklist-planning.md`](../final-checklist-planning.md) for the
current roadmap.

## TL;DR

Phase 4 is feasible, but the current repository is not safe to expose as a
public judged deployment yet.

The application already has several valuable production foundations:

- Google ID tokens are verified on the server against the configured OAuth
  client ID;
- the verified Google subject, rather than a browser-supplied alias, derives
  the internal user and default workspace identifiers;
- request-provided user and workspace identifiers cannot override the
  authenticated principal in Google OIDC mode;
- browser API requests are same-origin and send the Google token as a bearer
  credential;
- Pydantic models provide bounded identifiers, messages, source text,
  feedback, and artifact content;
- chat turns already provide idempotency, exact replay, changed-request
  conflict handling, and preservation of completed side effects;
- Firestore stores ownership metadata for the main collaboration domains;
- the repository has canonical artifact and memory read boundaries rather
  than giving the browser direct Firestore access.

The principal production blockers are:

1. `AGENT_COL_AUTH_MODE` silently defaults to `local_dev`. A missed
   production environment variable would therefore start the service in a
   fail-open development identity mode.
2. Google-mode workspace ownership is currently inferred from an identifier
   prefix. It is not yet enforced through a durable owner record for every
   workspace and resource.
3. Phase 3 durable jobs and the private worker do not exist yet. Phase 4
   cannot configure or prove the final Cloud Tasks and worker boundary until
   Phase 3 is accepted.
4. There is no Dockerfile, pinned Python runtime, production startup command,
   Cloud Run service definition, or deployment automation in the current
   repository.
5. Pydantic limits parsed values, but the ASGI boundary does not enforce a
   total request-body byte limit and the application has no request-rate
   limiting.
6. Retention and deletion behavior is not defined for the complete set of
   users, workspaces, sessions, messages, turns, memory, notes, artifacts,
   feedback, and future jobs.
7. generic-artifact read projection logs complete Pydantic validation error
   text. That text can contain rejected field values and therefore needs a
   content-safe logging correction before hosted use.
8. `POST /api/synthesize` remains a public synchronous, non-idempotent
   generation boundary outside the chat-turn ledger.
9. The application does not set a production browser security-header policy,
   including Content Security Policy, frame restrictions, MIME sniffing
   protection, or transport security.
10. Chat-session listing reads at most 200 documents from the global
    `sessions` collection and filters ownership in Python. This is bounded,
    but it is not an adequate production query or ownership boundary.

The recommended Phase 4 decomposition is:

1. production configuration validation and fail-closed startup;
2. durable ownership records and a complete denial matrix;
3. request limits, rate controls, security headers, and content-safe logging;
4. retention, deletion, production queries, and Firestore indexes;
5. containerization, service identities, IAM, Cloud Tasks OIDC, and Cloud Run
   configuration after Phase 3 is accepted;
6. hosted authentication, ownership, controlled-failure, smoke, cost, and
   rollback evidence.

## 1. Scope and evidence standard

This audit compares:

- the actual authentication, ownership, API, persistence, logging, browser,
  and configuration boundaries in the current repository;
- the Phase 4 requirements in `docs/aug-25-2026-final-checklist.md`;
- the accepted Phase 3 research boundary;
- current official Google Identity, Cloud Run, Cloud Tasks, Firestore, Cloud
  Logging, and Cloud Billing documentation.

Evidence is classified as follows:

- **Verified source fact:** directly traced in the current repository.
- **Verified Google Cloud fact:** supported by current official Google
  documentation linked in this audit.
- **Recommendation:** a planning input that Machine 1 must reconcile against
  the accepted Phase 3 implementation before changing source.

This document does not authorize production code, schemas, routes, workers,
indexes, IAM changes, deployment, or cloud-resource creation. It is not the
Phase 4 implementation plan.

## 2. Verified current production posture

### 2.1 Application and deployment topology

**Verified source facts:**

- `main.py` creates one FastAPI application.
- The browser workspace is served by that application at `/workspace` and
  static assets are mounted below `/static/agent-col`.
- The same application owns authentication, memory, workspace, chat,
  artifact, feedback, and direct-synthesis APIs.
- The browser calls same-origin API paths through `frontend/api.mjs`.
- The backend uses the Firestore server client and calls Vertex AI through the
  Google GenAI and ADK libraries.
- The current repository has no Dockerfile, Cloud Build file, pinned Python
  runtime file, production process definition, Cloud Run service descriptor,
  or infrastructure-as-code deployment boundary.

**Implication:** the current program is a local application source tree, not a
reproducible Cloud Run release artifact. Phase 4 must define both the public
API/UI service and, after Phase 3, the private worker service.

### 2.2 Authentication

**Verified source facts from `auth.py`:**

- Supported modes are `local_dev` and `google_oidc`.
- `load_auth_settings()` defaults an absent `AGENT_COL_AUTH_MODE` to
  `local_dev`.
- Google mode requires a configured OAuth client ID.
- bearer tokens are verified using Google's ID-token verifier and the
  configured audience;
- the verified `sub` claim is converted into a server-owned internal user ID;
- the default workspace ID is a SHA-256-derived server identifier;
- request user IDs must match the authenticated principal;
- request workspace IDs must be the default derived workspace or share its
  accepted derived prefix.

Google's official backend-authentication guidance requires validation of the
ID token's signature, `aud`, `iss`, and expiry and identifies `sub` as the
stable account identifier. The library used here performs those validation
steps when supplied the intended OAuth client ID. See [Verify the Google ID
token on your server side](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).

**Critical gap:** the default-to-development behavior is unsafe for public
deployment. If Cloud Run starts without one environment variable, every
protected resolver trusts request-provided local identifiers. Production
startup must fail closed rather than silently becoming local development.

**Privacy gap:** `AuthenticatedPrincipal.public_dict()` includes the Google
subject and email even though the normal browser only needs authenticated
state, a human display value, and opaque application identifiers. Phase 4
should define the minimal public session projection and avoid unnecessary
identity disclosure.

### 2.3 Browser sign-in boundary

**Verified source facts:**

- the browser obtains a Google credential through Google Identity Services;
- the token is held in application state and sent in the `Authorization`
  header;
- API paths must be same-origin absolute paths;
- no production frontend use of `localStorage`, `sessionStorage`, or direct
  Firestore/provider calls was found in the audited transport boundary;
- workspace and static responses use `Cache-Control: no-store`.

Google requires the OAuth client and exact JavaScript origins to be configured
for the deployed origin. Google also documents Content Security Policy
requirements for Google Identity Services. See [Get your Google API client
ID](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid).

**Gap:** the repository does not currently define the final hosted origin,
OAuth-client configuration procedure, CSP, sign-out/session-expiry behavior,
or deployed unauthorized-state verification.

### 2.4 Ownership model

**Verified source facts:**

- Google-mode user identity is server-derived.
- Workspace access is currently accepted by a derived identifier equality or
  prefix rule.
- Firestore documents store user, workspace/project, session, turn, and
  artifact relationships across relevant domains.
- public routes resolve an effective user or workspace before invoking the
  domain service.
- the Firestore server SDK is used by the backend; the browser does not access
  Firestore directly.

Firestore server libraries authenticate with Google Application Default
Credentials and use IAM rather than browser Firestore Security Rules. Server
clients bypass client Security Rules, so application authorization and the
runtime service account are decisive. See [Firestore IAM
roles](https://cloud.google.com/firestore/docs/security/iam) and [Security
Rules conditions and server-client behavior](https://cloud.google.com/firestore/docs/security/rules-fields).

**Critical gap:** an identifier naming convention is not durable ownership.
A route must never authorize access merely because a workspace, session, job,
task, or artifact ID resembles the authenticated user's namespace. Phase 4
needs explicit owner checks against authoritative stored relationships.

### 2.5 Input and serialization bounds

**Verified source facts:**

- Pydantic models reject extra fields in core contracts;
- identifiers are bounded;
- chat messages and synthesis source text are bounded;
- feedback and correction text are bounded;
- generic single-file artifacts have a bounded content size;
- list and detail APIs impose bounded page sizes;
- chat detail retrieval is bounded.

**Gap:** model validation occurs after the request body has been accepted and
parsed. There is no middleware or proxy configuration in the repository that
rejects an oversized body before JSON parsing. A production request-size
policy therefore remains missing even though individual fields are bounded.

Firestore has a 1 MiB maximum document size. Application limits must preserve
headroom for metadata, encoding, arrays, and future schema growth rather than
allowing user content to approach that limit. See [Firestore quotas and
limits](https://cloud.google.com/firestore/quotas).

### 2.6 Idempotency and partial completion

**Verified source facts:**

- Google-authenticated chat requires an idempotency key;
- feedback and memory-clarification effects require idempotency where their
  contracts demand it;
- completed chat requests replay exactly;
- reuse of a key with a changed request conflicts;
- completed artifact effects can survive a responder failure;
- direct `POST /api/synthesize` does not use the chat-turn ledger and has no
  equivalent public idempotency contract.

**Implication:** Phase 4 should preserve chat as the public judge-facing
artifact entry point. The direct synthesis route must be explicitly retained
as a restricted developer boundary, made idempotent, or removed from the
public deployed surface. Leaving it publicly accessible would bypass part of
the accepted durability and retry story.

### 2.7 Logging

**Verified source facts:**

- many application errors log exception class names rather than user content;
- public errors generally return bounded descriptions;
- `generic_artifact_service.py` logs the full string form of Pydantic
  `ValidationError` when stored generic artifact content or metadata is
  invalid.

Pydantic validation errors can include rejected input values. That makes the
generic-artifact warnings a potential content-bearing logging path. Phase 4
must replace them with content-free event data such as operation, contract
version, exception class, and correlation identifier.

Cloud Logging automatically collects Cloud Run container output. Log routing,
storage, exclusions, and retention must therefore be deliberately configured.
See [Cloud Logging routing and storage](https://cloud.google.com/logging/docs/routing/overview)
and [Cloud Logging quotas and limits](https://cloud.google.com/logging/quotas).

### 2.8 Queries and indexes

**Verified source facts:**

- `Database.list_chat_sessions()` reads at most 200 documents from the global
  `sessions` collection, filters by user and workspace in Python, sorts the
  result, and then applies the requested limit;
- workspace listing reads from a user-owned workspace subcollection;
- artifact and blueprint reads use project-owned collection boundaries;
- `firestore.indexes.json` declares no composite indexes and only disables
  indexing for the large blueprint field.

The session scan is technically bounded, but it is incomplete after a user or
deployment has more than 200 globally encountered sessions and makes the
application examine documents it should not need. Phase 4 needs ownership-
constrained queries and the required indexes. Similar review is necessary for
future jobs and notes after their accepted schemas exist.

### 2.9 Retention and deletion

**Verified source facts:**

- memory supports governed lifecycle operations;
- generic artifacts support archive and restore;
- several domains have deletion operations;
- there is no repository-wide retention schedule or complete account/workspace
  deletion workflow covering all nested data;
- Phase 3 jobs are not implemented yet.

Firestore TTL deletion does not cascade into subcollections. Deleting a parent
document also does not automatically delete its descendants. See [Firestore
TTL policies](https://cloud.google.com/firestore/docs/ttl).

**Implication:** account and workspace deletion require an explicit recursive,
retry-safe application workflow. TTL may be useful for selected terminal
records but cannot serve as the whole deletion design.

## 3. Phase 4 checklist gap analysis

### 3.1 Ownership audit

**Current status:** partially present, not production-complete.

The source derives authenticated identity and validates route locators, but
the complete domain matrix has not been proven and workspace authorization is
still namespace-based.

### 3.2 Cross-user and cross-workspace denial

**Current status:** partially covered by resolvers and tests, not hosted-
verified.

Every read and write must be tested with two real principals, two workspaces,
swapped locators, valid-but-foreign identifiers, and nonexistent identifiers.

### 3.3 Request and artifact-size limits

**Current status:** field limits exist; total request-byte and deployment-edge
limits are missing.

### 3.4 Rate limiting and security headers

**Current status:** missing.

Cloud Armor rate limiting requires an external Application Load Balancer and
is not automatically present on a direct `run.app` URL. See [Cloud Armor rate
limiting](https://cloud.google.com/armor/docs/rate-limiting-overview).
Machine 1 must decide between application-level limits on the direct Cloud Run
URL or a load-balancer/Cloud Armor boundary.

### 3.5 Content-safe logs

**Current status:** mostly disciplined but not proven and with one verified
generic-artifact validation leak risk.

### 3.6 Retention and deletion

**Current status:** domain-specific lifecycle controls exist; complete policy
and recursive cleanup do not.

### 3.7 Runtime pin and container

**Current status:** Python dependencies are pinned; the Python interpreter,
container base, and production process are not.

Cloud Run containers must listen on the injected `PORT` and on `0.0.0.0`, not
only loopback. See the [Cloud Run container runtime
contract](https://cloud.google.com/run/docs/container-contract).

### 3.8 Service accounts, IAM, indexes, and task OIDC

**Current status:** not implemented as deployable configuration. Phase 3 must
land first so the worker and job collections are authoritative.

### 3.9 Cloud Run controls and hosted proof

**Current status:** missing. No deployed evidence is present in the audited
source tree.

## 4. Required target security and ownership boundary

### 4.1 Identity is authority; identifiers are locators

The production invariant should be:

```text
verified Google subject
  -> application principal
  -> authoritative stored ownership relationship
  -> permitted domain operation
```

The following values must never become authorization by themselves:

- user aliases;
- workspace/project IDs;
- session IDs;
- message or turn IDs;
- artifact or feedback IDs;
- memory or note IDs;
- job IDs;
- Cloud Tasks names;
- filenames or display names.

### 4.2 Ownership matrix

| Domain | Authoritative owner requirement | Public operations requiring proof |
| --- | --- | --- |
| Workspace | Stored owner subject/internal user | List, create, select, update, delete |
| Session | Stored user and workspace relationship | List, detail, continue, archive/delete |
| Memory | Authenticated user | Inspect, propose, decide, correct, revoke, delete |
| Workspace note | Authenticated user plus workspace | List, inspect, propose, decide, correct, archive, restore, delete, retrieve |
| Blueprint | Authenticated user plus workspace | List, detail, feedback, export, archive/delete if added |
| Generic artifact | Authenticated user plus workspace | Create, list, detail, export, archive, restore, delete |
| Feedback | Owner of parent artifact and workspace | List, create, supersede |
| Durable job | Stored user, workspace, session, and operation | Submit, status, cancel, retry, result retrieval |
| Worker invocation | IAM-authenticated Cloud Tasks principal | Execute one stored job only |

### 4.3 Public not-found behavior

For foreign resources, public behavior should avoid confirming existence.
After authenticating the caller, a missing or foreign resource should normally
produce the same unavailable response. Operational logs may record a
content-free denial category and correlation ID without including user input.

## 5. Production configuration and fail-closed startup

### 5.1 Required startup validation

**Recommendation:** introduce an explicit deployment environment and validate
all required production settings before the application begins serving.

A production startup gate should reject at least:

- absent or `local_dev` authentication mode;
- absent Google OAuth client ID;
- invalid or unapproved public origin;
- missing Google Cloud project or region configuration;
- missing Firestore database configuration;
- absent public-service or worker service-account expectations;
- missing queue/worker settings after Phase 3;
- unsafe debug, reload, or development flags;
- placeholder secrets or local credential paths.

Local development can retain its explicit launch mode, but production must not
reach it through a default.

### 5.2 Secrets and public configuration

The OAuth client ID is public browser configuration and is not a client
secret. Runtime service credentials must use Cloud Run service identity and
Application Default Credentials rather than a mounted service-account key.
Actual secrets should use Secret Manager. See [Configure secrets for Cloud
Run](https://cloud.google.com/run/docs/configuring/services/secrets) and
[Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity).

## 6. Request, abuse, and browser controls

### 6.1 Request-size enforcement

**Recommendation:** enforce a small total request-byte ceiling before JSON
parsing and retain stricter per-contract Pydantic limits. Return HTTP 413 for
an oversized body. Do not read unbounded bodies merely to formulate a nicer
error.

Different routes may need different ceilings, but the initial Phase 4 design
should remain simple and explainable:

- small control/read requests;
- bounded chat and pasted-source requests;
- bounded generic-artifact content;
- no file upload in the Winning Core.

### 6.2 Rate limiting

**Recommendation:** define limits by verified user and operation, with a
coarser unauthenticated/IP limit for sign-in and health-adjacent abuse. High-
cost provider operations should have lower limits than deterministic reads.

Required behavior includes:

- HTTP 429 and a useful `Retry-After` value;
- no reliance on client-supplied user IDs;
- bounded counters and expiry;
- separate limits for normal reads, chat, synthesis/job submission, retry,
  and export where relevant;
- controlled maximum Cloud Run instances as the final cost backstop.

If the judged deployment uses a direct Cloud Run URL, application-level rate
controls are still required. If a load balancer is added, Cloud Armor can
provide an additional edge layer, not a replacement for application ownership
and per-user cost governance.

### 6.3 Security headers

The public UI/API should define and test at least:

- `Content-Security-Policy`, including only the Google Identity Services
  sources actually required;
- `X-Content-Type-Options: nosniff`;
- a frame policy through CSP `frame-ancestors` or an equivalent compatible
  header;
- `Referrer-Policy`;
- `Permissions-Policy` for unused browser capabilities;
- `Strict-Transport-Security` on the hosted HTTPS origin;
- explicit content types for generated downloads;
- `Cache-Control: no-store` for identity-bearing and private responses.

The exact CSP must be tested with Google sign-in rather than copied blindly,
because an incorrect policy can disable the authentication UI.

### 6.4 CORS and same-origin policy

The current same-origin application is the lower-complexity boundary and
should be preserved unless deployment evidence requires separation. Do not
add broad wildcard CORS merely because the service is public.

## 7. Content-safe observability

### 7.1 Logging contract

Production application logs should contain only operational metadata needed
to diagnose behavior, such as:

- correlation/request ID;
- route or operation name;
- result class and HTTP status;
- latency bucket;
- provider/tool/action category;
- job state and attempt number;
- exception class or bounded internal error code;
- opaque hashed or redacted resource references when necessary.

They should not contain:

- prompts or chat messages;
- source text;
- memory or note values;
- artifact content;
- feedback text;
- Google ID tokens, access tokens, authorization headers, or cookies;
- email addresses or raw Google subjects;
- model internal reasoning;
- full Pydantic validation errors containing input values.

### 7.2 Audit events versus content logs

Security-relevant events should be structured separately from user content:

- authentication required/denied;
- ownership denied;
- rate limit applied;
- invalid worker identity;
- job transition conflict;
- retention/deletion start and completion;
- production configuration refusal.

These events still need a redaction test. Calling a log an audit log does not
make content exposure safe.

## 8. Retention and deletion constraints

### 8.1 Required policy decisions

Before hosted use, the owner must decide and document retention for:

- identity metadata;
- workspaces;
- sessions, messages, and turns;
- memory proposals, active signals, and lifecycle events;
- workspace notes and provenance;
- blueprints and generic artifacts;
- artifact feedback;
- durable jobs, attempts, and failure receipts;
- application and Cloud Logging entries.

### 8.2 Deletion semantics

Required distinctions include:

- archive/hide versus soft delete versus irreversible deletion;
- account deletion versus one-workspace deletion;
- deleting a profile memory without deleting historical artifact evidence;
- deleting a workspace note without rewriting an old response;
- deleting an artifact and handling its feedback and job provenance;
- retaining minimum operational evidence without retaining user content;
- cancellation of active work before or during deletion.

### 8.3 Implementation constraint

Because Firestore parent deletion and TTL do not cascade, deletion must use a
bounded, retry-safe application workflow that enumerates authorized child
collections. Phase 3 may provide a useful durable-work foundation, but account
deletion should not be quietly folded into the first asynchronous artifact
worker without a separately approved contract.

## 9. Cloud Run container and runtime requirements

### 9.1 Container contract

The production image should:

- pin a supported Python runtime explicitly;
- install the locked runtime dependencies;
- copy only required application and static files;
- run as a non-root user where practical;
- exclude `.env`, ADC files, test evidence, downloads, caches, and development
  virtual environments;
- bind Uvicorn to `0.0.0.0:$PORT`;
- use a production startup command without `--reload`;
- emit content-safe stdout/stderr logs;
- expose one deterministic health boundary.

Cloud Run's container contract requires ingress containers to listen on the
injected port and all interfaces. See [Cloud Run container runtime
contract](https://cloud.google.com/run/docs/container-contract). Google also
recommends avoiding root where the container does not require it. See [Deploy
containers to Cloud Run](https://cloud.google.com/run/docs/deploying).

### 9.2 Health checks

The current root endpoint proves only that the process can answer. A startup
or readiness check must not call Gemini or Firestore on every probe, but the
deployment needs separate evidence that required configuration was validated
at startup. See [Configure Cloud Run health
checks](https://cloud.google.com/run/docs/configuring/healthchecks).

### 9.3 Timeouts and concurrency

Cloud Run request timeouts do not guarantee application cancellation; a timed-
out container may continue work. This reinforces the Phase 3 conclusion that
durable provider work cannot depend on one public HTTP request. See [Configure
Cloud Run request timeout](https://cloud.google.com/run/docs/configuring/request-timeout).

Concurrency must be measured against:

- async Python behavior;
- Firestore and Vertex client behavior;
- memory use of prompts and generated artifacts;
- provider-call latency;
- job-worker claim and fencing logic;
- database transaction contention.

See [Configure maximum concurrent requests for Cloud
Run](https://cloud.google.com/run/docs/configuring/concurrency).

## 10. Public service, private worker, and IAM

### 10.1 Public API/UI service

The browser must be able to load the workspace, so the simplest judged
deployment may allow unauthenticated Cloud Run invocation at the service IAM
layer while application routes enforce Google OIDC user authentication and
ownership. This is safe only if every sensitive route is covered by the
application gate and local development cannot start in production.

Ingress should be selected deliberately. If using the default `run.app` URL,
restricting ingress to internal traffic would break the public browser. If an
external load balancer is introduced, ingress can be limited to the load
balancer path. See [Restrict network ingress for Cloud
Run](https://cloud.google.com/run/docs/securing/ingress).

### 10.2 Private worker service

After Phase 3, the worker should not allow public unauthenticated invocation.
Cloud Tasks should send an OIDC token from a dedicated task-delivery service
account, and only the required identity should have Cloud Run invocation
authority. See [Authenticate service-to-service requests to Cloud
Run](https://cloud.google.com/run/docs/authenticating/service-to-service).

The worker must still validate the stored job and state transition. IAM proves
the caller may invoke the service; it does not prove that a supplied job ID is
valid or authorize a transition by itself.

### 10.3 Recommended service-account separation

Use distinct service identities for:

1. the public API/UI service;
2. Cloud Tasks OIDC delivery;
3. the private worker.

Each should receive only the permissions needed for its role. Avoid Editor,
Owner, or broad project-wide roles. The API service should be able to submit
tasks but not impersonate unrelated identities. The task-delivery account
should invoke only the worker. The worker should access only the Firestore,
Vertex AI, logging, and other resources required by accepted Phase 3 behavior.

## 11. Cloud Tasks and Phase 3 dependency

Phase 4 must not invent deployment settings before the Phase 3 contracts are
accepted. It needs the final:

- queue and worker regions;
- public submission and private worker endpoints;
- task OIDC audience;
- task-delivery service account;
- job state and retry policy;
- worker timeout and concurrency assumptions;
- cancellation and retry semantics;
- stale-job reconciliation behavior;
- Firestore job queries and indexes.

The accepted M10-RSCH.1 conclusion remains controlling: Cloud Tasks delivery
is at least once; job claiming, fencing, and artifact idempotency remain
application responsibilities. Phase 4 configures and proves this boundary but
must not weaken it.

## 12. Cost and abuse controls

### 12.1 Cloud Run controls

Set and document:

- maximum instances for the public service and worker;
- measured concurrency;
- request timeout;
- minimum instances only if judge reliability justifies the cost;
- CPU and memory sized from evidence;
- worker task dispatch rate aligned with Vertex AI and Firestore capacity.

Maximum instances limit scaling but can be exceeded briefly in some traffic
conditions and should not be treated as an exact billing cap. See [Configure
maximum instances for Cloud Run](https://cloud.google.com/run/docs/configuring/max-instances).

### 12.2 Budget controls

Google Cloud budgets and alerts notify; they do not hard-cap spend. See [Create
and manage budgets](https://cloud.google.com/billing/docs/how-to/budgets).
The actual cost boundary must combine:

- application per-user/provider-operation limits;
- Cloud Tasks dispatch and retry limits;
- Cloud Run maximum instances;
- bounded provider retries and timeouts;
- Artifact/source size limits;
- budget alerts and operational monitoring;
- an explicit shutdown/rollback procedure.

## 13. Firestore production constraints

### 13.1 Index planning

Phase 4 should define indexes only from accepted query contracts. Likely
queries include:

- sessions by owner, workspace, lifecycle status, and update time;
- artifacts by workspace, lifecycle status, and creation time;
- notes by owner, workspace, status, and update/creation time;
- jobs by owner, workspace, state, and update time;
- terminal jobs for reconciliation or retention;
- feedback by parent artifact and creation time.

The exact fields cannot be locked until Phase 2 and Phase 3 schemas are
accepted. Index deployment and query verification belong in the final Phase 4
plan, not this audit.

### 13.2 Document-size and hot-document risk

Do not accumulate unbounded arrays, histories, attempts, or full transcripts
in one document. Use bounded documents/subcollections and transactional state
summaries. Job heartbeat frequency and rate-limit counters must avoid turning
one document into a write hotspot.

### 13.3 Database location

The Firestore database, Cloud Run services, Cloud Tasks queue, and Vertex AI
region choices should minimize latency and satisfy supported-region
constraints. Region selection must be explicit and consistent in deployment
instructions.

## 14. File and surface collision map

This is a research-only prediction. Machine 1 must reconcile it with the
accepted Phase 2 and Phase 3 source baseline.

| Surface | Expected Phase 4 risk | Isolation recommendation |
| --- | --- | --- |
| `main.py` | Startup validation, middleware, protected routes, health | Keep configuration and middleware logic in focused modules; wire narrowly |
| `auth.py` | Fail-closed mode, public projection, stored ownership | Preserve token verification; add repository/service-owned authorization separately |
| `schemas.py` | Error, limit, retention, deployment-facing models | Prefer domain-specific model modules over more global growth |
| `database.py` | Ownership queries, deletion, indexes, future jobs/notes | Move domain repositories into isolated modules before adding broad production logic if approved |
| `agent_col_turn_service.py` | Phase 3 async behavior and public response | Phase 4 should configure and protect, not redesign orchestration |
| Artifact services | size, logging, lifecycle, deletion | Correct content-safe logging without changing artifact semantics |
| Memory/note services | ownership, deletion, retention | Keep profile memory and workspace notes separate |
| `frontend/api.mjs` | auth expiry, 413/429, hosted errors | Centralize transport handling and retain same-origin paths |
| frontend state/views | login expiry, job state, denial/error UX | Do not mix security authority into browser state |
| `firestore.indexes.json` | production queries | Generate only from accepted, tested queries |
| deployment files | image, service accounts, service configs | Add a dedicated deployment boundary rather than shell fragments scattered through docs |
| `README.md` and setup docs | hosted and local truth | Reconcile comprehensively in Phase 5 after deployment is accepted |

## 15. Verification strategy for Phase 4 planning

### 15.1 Deterministic configuration tests

Propose tests that prove:

- production refuses absent auth mode;
- production refuses `local_dev`;
- production refuses missing OAuth client configuration;
- local development remains explicitly launchable;
- public auth projection omits unnecessary Google identifiers;
- unsafe placeholder or missing worker settings fail startup after Phase 3.

### 15.2 Ownership and authorization tests

Use two principals and at least two workspaces to verify every operation in the
ownership matrix:

- owner succeeds;
- other user is denied;
- same user, other workspace is correctly allowed or denied according to
  stored ownership;
- forged prefix and valid-format foreign identifier fail;
- missing and foreign resources do not leak existence;
- worker route rejects browser ID tokens and unauthenticated requests;
- valid Cloud Tasks OIDC identity still cannot execute a foreign or invalid
  job.

### 15.3 Limit and abuse tests

- body immediately below the limit succeeds;
- body above the limit returns 413 before domain execution;
- excessive request rate returns 429 and `Retry-After`;
- rate limits use the verified principal, not browser identifiers;
- high-cost operation limits are independent from cheap reads;
- generic artifact and blueprint limits preserve Firestore headroom;
- rate-control storage remains bounded.

### 15.4 Header and browser tests

- hosted workspace and API responses contain the expected security headers;
- Google sign-in works under the deployed CSP;
- forbidden framing is rejected;
- downloads use safe content types and filenames;
- private responses are not cached;
- authentication expiry returns to a clear sign-in state without exposing old
  private content.

### 15.5 Content-safe logging tests

Inject unique canary strings into:

- prompts;
- memory and note values;
- artifact content;
- feedback;
- validation failures.

Trigger success and failure paths, then query Cloud Logging and prove none of
the canaries, tokens, emails, or raw subjects appear. This evidence is more
credible than a source-only claim.

### 15.6 Retention and deletion tests

- delete one memory without deleting unrelated workspace evidence;
- delete one workspace and enumerate all required child domains;
- retry an interrupted deletion without duplication or resurrection;
- prevent new work during account/workspace deletion;
- verify TTL-selected records expire without assuming cascade;
- verify logs follow their independent retention policy;
- verify foreign users cannot start, inspect, or retry deletion.

### 15.7 Container and hosted tests

- build the image from a clean checkout;
- inspect image contents for `.env`, credentials, virtual environments, and
  user data;
- run the image locally with the production command and injected `PORT`;
- prove non-root execution if selected;
- deploy public and private services with the intended service accounts;
- verify unauthenticated worker denial;
- verify authorized Cloud Tasks delivery;
- run Google sign-in and same-user ownership smoke tests;
- run cross-user and cross-workspace denial tests;
- demonstrate one controlled worker failure and retry after Phase 3;
- verify Cloud Run, Cloud Tasks, Firestore, Vertex AI, and Cloud Logging
  evidence for judging;
- execute and document rollback to a previous revision.

## 16. Risks and unresolved owner decisions

Machine 1 must obtain explicit decisions for:

1. Whether the public service uses the direct Cloud Run URL or a load balancer
   and Cloud Armor.
2. The final hosted origin and production Google OAuth client.
3. Whether `POST /api/synthesize` is disabled, restricted, or made idempotent
   in the public deployment.
4. The durable workspace ownership-record design that replaces prefix-only
   authority.
5. Account, workspace, session, artifact, note, memory, feedback, and job
   retention periods.
6. Archive versus delete semantics for each domain.
7. Public API and worker regions and the existing Firestore/Vertex locations.
8. Cloud Run CPU, memory, timeout, concurrency, minimum instances, and maximum
   instances based on measured behavior.
9. Rate-limit storage and whether an edge load balancer is justified for the
   schedule and judged scope.
10. The worker identity, queue identity, and least-privilege IAM bindings after
    Phase 3 is accepted.
11. Whether raw Google subject and email are ever needed in a public session
    response.
12. The final notes and job queries/indexes after Phase 2 and Phase 3.
13. The exact hosted failure, rollback, and budget-response procedure.

## 17. Recommended Phase 4 planning inputs

### Pass 4.1 - Production configuration and fail-closed startup

- introduce explicit environment classification;
- reject production local-development auth;
- validate required hosted configuration;
- minimize public auth-session identity fields;
- define a production-safe health/startup contract.

### Pass 4.2 - Durable ownership and denial matrix

- introduce authoritative workspace owner records;
- audit every domain route and repository;
- add cross-user and cross-workspace denial tests;
- ensure resource identifiers remain locators only.

### Pass 4.3 - Limits, headers, and content-safe observability

- enforce request-byte limits;
- add bounded per-principal/operation rate controls;
- add the tested browser security policy;
- remove content-bearing validation logs;
- add canary-based logging verification.

### Pass 4.4 - Retention, deletion, queries, and indexes

- approve the retention matrix;
- implement bounded recursive deletion where authorized;
- replace global/filter-in-Python queries;
- add only required Firestore indexes;
- verify interrupted and foreign deletion behavior.

### Pass 4.5 - Container, IAM, Cloud Tasks, and Cloud Run deployment

- pin the Python runtime and add the production container;
- define the public API/UI and private worker services;
- assign distinct least-privilege service accounts;
- configure Cloud Tasks OIDC from the accepted Phase 3 contracts;
- configure regions, timeouts, concurrency, maximum instances, and secrets;
- deploy indexes and services.

### Pass 4.6 - Hosted security, smoke, cost, failure, and rollback proof

- run the hosted identity and ownership matrix;
- verify worker authentication;
- inspect logs for content canaries;
- verify request/rate limits and browser headers;
- demonstrate controlled failure and successful retry;
- capture Cloud Run, Cloud Tasks, Firestore, Vertex AI, and budget evidence;
- prove rollback.

## 18. Explicit reconciliation checklist for Machine 1

Before writing the Phase 4 implementation plan, Machine 1 should:

- [ ] confirm the accepted Phase 2 notes schema and routes;
- [ ] confirm the accepted Phase 3 job schema, worker, queue, and frontend
  contracts;
- [ ] re-run the ownership inventory against the then-current source;
- [ ] replace any prefix-only authorization assumption with a stored-owner
  decision;
- [ ] decide the direct-Cloud-Run versus load-balancer boundary;
- [ ] decide the fate of the direct synthesis endpoint;
- [ ] approve retention and deletion semantics for every durable domain;
- [ ] measure provider latency, memory, and safe concurrency;
- [ ] select explicit Cloud Run/Tasks/Firestore/Vertex regions;
- [ ] define service accounts and minimum IAM permissions;
- [ ] define the production environment and startup-refusal tests;
- [ ] define request-byte and operation-rate limits;
- [ ] define and test the Google-compatible CSP;
- [ ] inventory every logging call and add canary verification;
- [ ] derive Firestore indexes from accepted queries;
- [ ] define budget alerts, maximum instances, and an operational shutdown
  response;
- [ ] define hosted smoke, cross-owner denial, controlled failure, and
  rollback evidence;
- [ ] keep Phase 5 documentation reconciliation outside Phase 4 except where
  deployment operation requires a minimal runbook.

## 19. Official Google documentation consulted

- [Verify the Google ID token on your server side](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
- [Get your Google API client ID and configure Google Identity Services](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
- [Cloud Run container runtime contract](https://cloud.google.com/run/docs/container-contract)
- [Deploy containers to Cloud Run](https://cloud.google.com/run/docs/deploying)
- [Configure Cloud Run health checks](https://cloud.google.com/run/docs/configuring/healthchecks)
- [Configure Cloud Run request timeout](https://cloud.google.com/run/docs/configuring/request-timeout)
- [Configure Cloud Run concurrency](https://cloud.google.com/run/docs/configuring/concurrency)
- [Configure Cloud Run maximum instances](https://cloud.google.com/run/docs/configuring/max-instances)
- [Restrict network ingress for Cloud Run](https://cloud.google.com/run/docs/securing/ingress)
- [Authenticate service-to-service requests to Cloud Run](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity)
- [Configure secrets for Cloud Run](https://cloud.google.com/run/docs/configuring/services/secrets)
- [Firestore IAM roles](https://cloud.google.com/firestore/docs/security/iam)
- [Firestore Security Rules conditions and server-client behavior](https://cloud.google.com/firestore/docs/security/rules-fields)
- [Firestore quotas and limits](https://cloud.google.com/firestore/quotas)
- [Firestore TTL policies](https://cloud.google.com/firestore/docs/ttl)
- [Cloud Logging routing and storage](https://cloud.google.com/logging/docs/routing/overview)
- [Cloud Logging quotas and limits](https://cloud.google.com/logging/quotas)
- [Create and manage Cloud Billing budgets](https://cloud.google.com/billing/docs/how-to/budgets)
- [Cloud Armor rate limiting](https://cloud.google.com/armor/docs/rate-limiting-overview)

## 20. Final assessment

The current repository has a credible application-level foundation for a
production judged build, especially in server-verified Google identity,
same-origin browser transport, bounded contracts, authoritative Firestore
state, and idempotent chat effects. It does not yet have a production
deployment boundary.

The most dangerous current defect is configuration fail-open: an omitted auth
mode starts local-development trust behavior. The most important architectural
gap is durable resource ownership beyond identifier naming. The most important
operational gaps are request/rate limits, content-safe observability,
retention/deletion, a pinned container, least-privilege service identities,
and hosted denial/failure proof.

Phase 4 should begin only after Phase 2 and Phase 3 are accepted, because the
notes, jobs, private worker, and final Firestore query surfaces must be part of
the production audit and deployment. Machine 1 should treat this report as
planning input, re-verify every source fact against that accepted baseline,
and obtain separate approval for each implementation pass.
