# Phase 3 Durable Artifact Work and Cloud Tasks Integration Audit

Date: August 25, 2026
Pass: M10-RSCH.1
Status: Approved read-only research audit; no Phase 3 implementation authorized

Status note, August 27, 2026: this audit remains useful future engineering
provenance, but durable asynchronous artifacts, Cloud Tasks, and private worker
execution are deferred until after submission under the current finalization
strategy. Use
[`../final-checklist-planning.md`](../final-checklist-planning.md) for the
current pre-submission roadmap.

## TL;DR

Phase 3 is feasible, but Cloud Tasks cannot simply wrap the existing
synchronous artifact call.

The current system already provides strong reusable foundations:

- authenticated user and workspace ownership;
- deterministic chat-turn idempotency;
- exact replay and changed-request conflict handling;
- atomic artifact persistence;
- precompleted-effect recovery;
- authoritative artifact references;
- canonical artifact read models;
- bounded responder projections;
- frontend artifact rendering and retrieval.

The clean integration seam is after the artifact route and exact source have
been validated, but before the current synchronous artifact executor is
called. The synchronous executor call would be replaced by durable job
submission.

The current chat-turn claim is an HTTP-request lease, not a durable background
job lease. A worker cannot safely reuse it unchanged. Phase 3 requires a
separate job ledger with worker fencing, attempts, cancellation intent,
terminal status, and atomic artifact completion.

The principal findings are:

1. Structured blueprint synthesis should be the first and only asynchronous
   artifact workflow. It already has the strongest judged collaboration,
   feedback, adaptation, and persistence contracts. Generic single-file
   artifacts should remain synchronous initially.
2. Cloud Tasks provides durable, at-least-once delivery rather than
   exactly-once execution. Application-level job claiming and artifact
   idempotency remain mandatory.
3. The worker should be a private Cloud Run service invoked by Cloud Tasks
   using an OIDC token from a dedicated service account with only the required
   Cloud Run invocation authority.
4. Task names, job IDs, workspace IDs, session IDs, and artifact IDs are
   locators, not authorization. Every public job operation must derive
   identity from the verified Google principal and validate the stored owner
   and workspace.
5. Cancellation is cooperative. Deleting a task cannot reliably stop worker
   code already running. The application must not promise immediate
   termination of a running generation.
6. Authoritative completion is the Firestore transaction that stores the
   canonical artifact and completed job state. A Cloud Tasks 2xx response is
   not authoritative completion by itself.
7. The highest collision risks are `main.py`, `database.py`, `schemas.py`,
   `agent_col_turn_service.py`, and frontend application state. Isolated job
   modules and narrow adapters would reduce conflicts.
8. The official development path does not provide a normal Cloud Tasks
   emulator. Phase 3 needs an application-owned queue interface with a
   deterministic fake dispatcher for local tests.
9. Retry exhaustion is an operational risk. Cloud Tasks does not provide a
   separate application callback after every retry is exhausted, so Phase 3
   must explicitly reconcile jobs whose worker is never reached.

## 1. Scope and evidence standard

This audit compares:

- the actual synchronous artifact path in the current repository;
- the Phase 3 requirements in `docs/aug-25-2026-final-checklist.md`;
- current official Google Cloud documentation;
- likely implementation surfaces and collision risks.

Evidence is distinguished as follows:

- **Verified source fact:** directly traced in the current repository.
- **Verified Google Cloud fact:** supported by current official Google
  documentation.
- **Recommendation:** a proposed Phase 3 planning input that Machine 1 must
  reconcile before implementation.

This document is not an implementation plan, schema definition, endpoint
contract, or authorization to change production behavior.

## 2. Verified current artifact architecture

### 2.1 Current request flow

The current production flow is:

```text
Browser
  -> POST /api/chat + Bearer token + Idempotency-Key
FastAPI authentication and effective ownership resolution
  -> Firestore chat-turn claim
  -> History and governed-memory context loading
  -> Agent Col turn service
  -> Model-controlled route selection and local validation
  -> Deterministic artifact executor
  -> Synthesis or generic artifact generation
  -> Atomic artifact + precompleted turn-effect persistence
  -> Responder-only Agent Col projection
  -> Atomic assistant-message + completed-turn persistence
  -> ChatResponse
  -> Frontend transcript, receipts, artifact list, and artifact viewer
```

The HTTP boundary begins in `main.py` at `POST /api/chat`.
`agent_col_turn_service.py` performs routing, exact-source construction,
execution, and responder orchestration. Artifact execution is centralized in
`agent_col_artifact_executor.py`.

### 2.2 Authentication and ownership

In Google OIDC mode:

- the bearer token is verified against the configured Google OAuth client;
- the Google subject becomes a server-derived internal user identifier;
- the default workspace is derived from that subject;
- additional owned workspace identifiers must remain within the authenticated
  user's namespace;
- request-provided user and workspace IDs cannot override the authenticated
  principal.

These boundaries are implemented in `auth.py` and provide a sound foundation
for job ownership. Phase 3 should extend this boundary instead of creating a
separate identity mechanism.

Local-development identity remains locator-based and is not production
authorization.

### 2.3 Existing chat-turn idempotency

The current turn ledger already provides:

- validated idempotency keys;
- deterministic turn and message IDs;
- exact replay for completed requests;
- HTTP 409 for a changed request using an existing key;
- an in-progress lease;
- lease expiry and reclamation;
- preservation of precompleted effects;
- atomic assistant-message and turn completion.

The contracts are defined in `chat_turns.py` and persisted in `database.py`.
The current 120-second lease is appropriate for retry-safe synchronous HTTP
work but is not sufficient as a background-job ownership contract.

### 2.4 Existing partial-completion guarantee

Artifact effects are persisted before the final responder runs.

For blueprint creation, the persistence transaction writes:

- the immutable blueprint document;
- its project timestamp;
- the completed action receipt;
- the artifact reference;
- the corresponding precompleted chat-turn effect.

Generic single-file artifacts follow the same overall pattern. If the final
responder fails after artifact persistence:

- the artifact remains durable;
- the completed effect remains attached to the turn;
- an exact retry can reuse it;
- the system must not regenerate the artifact.

This is one of the strongest contracts Phase 3 should preserve.

### 2.5 Existing frontend behavior

The browser currently supports:

- authenticated chat submission;
- idempotency-key generation;
- request-level waiting and failure presentation;
- action and artifact receipts;
- artifact listing and selection;
- canonical artifact detail retrieval;
- artifact export;
- archive and restore operations.

Frontend orchestration is concentrated in `frontend/app.mjs`, while
transient request state is stored in `frontend/state.mjs`. The frontend does
not yet contain a durable job model. "Waiting for Agent Col" currently means
that an HTTP request remains open.

## 3. Durable-work integration seam

### 3.1 Recommended replacement boundary

The best seam is after:

- authenticated ownership resolution;
- chat-turn claim;
- model-controlled artifact routing;
- local directive validation;
- exact source and bounded prior-context construction.

It is before:

- calling the synchronous artifact executor;
- invoking synthesis generation;
- persisting an artifact;
- running the artifact-result responder.

```text
Current:

validated artifact command
  -> artifact executor
  -> provider generation
  -> artifact persistence
  -> responder

Phase 3:

validated artifact command
  -> durable job submission
  -> Cloud Task
  -> private worker
  -> provider generation
  -> atomic artifact/job completion
  -> browser observes completion
```

### 3.2 Contracts that can be reused

The following contracts should be reusable with little or no semantic change:

- authenticated user and workspace derivation;
- artifact route decision and local validation;
- server ownership of exact source text;
- synthesis application service;
- blueprint validation;
- governed synthesis-memory projection;
- deterministic adaptation receipts;
- canonical artifact reference;
- canonical blueprint detail and list APIs;
- artifact feedback targets and feedback lifecycle;
- existing artifact viewer and export behavior;
- content-safe responder-projection principles.

### 3.3 Contracts that cannot be reused unchanged

#### Chat-turn claim

The current claim assumes an active HTTP owner with a short lease. A worker may
begin much later and run longer. Passing the current `ChatTurnClaim` into a
background worker would create fragile coupling and stale-owner failures.

#### Artifact executor ownership

The current executor completes effects against an owned chat-turn claim. A job
worker needs separate job ownership and fencing. A fake chat-turn claim should
not be constructed merely to reuse the executor, because that would disguise
the real durability boundary.

#### Chat response completion

The current response is returned after artifact execution and responder
generation. Phase 3 must explicitly decide what `/api/chat` returns when
artifact work becomes queued. That is a product-contract decision, not an
implementation detail.

### 3.4 Recommended first asynchronous workflow

**Recommendation:** promote only structured blueprint synthesis to durable
execution first.

Reasons:

- it is already the canonical judge-facing artifact loop;
- it supports feedback targets;
- it supports governed synthesis adaptations;
- it has canonical read models;
- it best demonstrates asynchronous heavy work;
- it avoids destabilizing generic code and text artifacts simultaneously.

Generic single-file artifact generation should remain synchronous during the
first Phase 3 implementation.

## 4. Official Cloud Tasks and Cloud Run findings

### 4.1 Delivery and duplicate execution

Cloud Tasks durably stores a successfully created task before the originating
request returns. Explicit task names provide duplicate-creation protection,
but Cloud Tasks uses at-least-once delivery semantics. Google states that
duplicate execution is rare but possible, so handlers must remain idempotent.

Sources:

- [Cloud Tasks overview](https://docs.cloud.google.com/tasks/docs/dual-overview)
- [Cloud Tasks common pitfalls](https://docs.cloud.google.com/tasks/docs/common-pitfalls)

Consequences:

- successful `CreateTask` proves queue acceptance, not artifact completion;
- a task may execute more than once;
- application idempotency remains mandatory;
- task-name deduplication does not replace job or artifact idempotency.

Cloud Tasks remembers task names for a limited period after deletion,
currently documented as up to 24 hours. A long-lived application cannot treat
that tombstone as permanent duplicate prevention.

### 4.2 OIDC-authenticated worker delivery

Cloud Tasks can attach an OIDC token when dispatching to an HTTP target such as
Cloud Run. The task-caller service account must be in the same Google Cloud
project as the queue, and the principal creating the task needs permission to
act as that service account.

Sources:

- [Creating HTTP target tasks](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)
- [Cloud Tasks access control](https://docs.cloud.google.com/tasks/docs/access-control)
- [Cloud Run service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)

Recommended actors:

| Actor | Required authority |
| --- | --- |
| Public API runtime service account | Create tasks on the selected queue |
| Public API runtime service account | `iam.serviceAccounts.actAs` on the task-caller service account |
| Cloud Tasks service agent | Generate the delivery token |
| Dedicated task-caller service account | `roles/run.invoker` on the private worker |
| Private worker runtime service account | Only the Firestore, Vertex AI, logging, and worker-runtime permissions actually required |

Cloud Tasks headers are informational and must not be treated as caller
identity. The worker's authorization must rely on the verified Cloud Run/IAM
identity boundary, not a task name or retry-count header.

### 4.3 Public API versus private worker

Recommended boundary:

```text
Internet
  -> Google-authenticated user
Public Agent Col API/browser service
  -> CreateTask
Cloud Tasks queue
  -> OIDC as dedicated task-caller service account
Private artifact worker
  -> Firestore + Vertex AI
```

The public service authenticates users and enforces resource ownership. The
private worker authenticates the Cloud Tasks service identity and validates
the canonical job record. These are separate security boundaries.

### 4.4 Queue, quota, concurrency, and cost controls

Cloud Tasks queues support maximum dispatch rate, maximum concurrent
dispatches, retry attempts and duration, backoff intervals, and exponential
backoff configuration.

Sources:

- [Configuring Cloud Tasks queues](https://docs.cloud.google.com/tasks/docs/configuring-queues)
- [Cloud Tasks quotas and limits](https://docs.cloud.google.com/tasks/docs/quotas)

Current documented limits include a task size of up to 1 MiB and a queue
dispatch rate of up to 500 tasks per second. Task payloads should therefore
contain only an opaque job locator and contract version. Prompt text,
conversation history, memory values, and artifact content should remain in
Firestore.

Cloud Run provides configurable request concurrency and maximum-instance
controls.

Sources:

- [Cloud Run concurrency](https://docs.cloud.google.com/run/docs/about-concurrency)
- [Cloud Run maximum instances](https://docs.cloud.google.com/run/docs/configuring/max-instances)

Recommended conservative initial settings for a provider-bound worker are:

- Cloud Run container concurrency: 1;
- queue maximum concurrent dispatches: 1-2;
- worker maximum instances: 1-3;
- a conservative dispatch rate.

These values are recommendations, not Google requirements. They must be
adjusted using measured synthesis latency, Vertex quotas, demo load, and cost.

### 4.5 Deadlines and request timeouts

Cloud Tasks HTTP targets currently support a default dispatch deadline of 10
minutes, a minimum of 15 seconds, and a maximum of 30 minutes. A non-2xx
response or a response that misses its deadline is treated as a failed attempt
and retried according to queue policy.

Source:

- [Cloud Tasks task resource](https://docs.cloud.google.com/tasks/docs/reference/rest/v2/projects.locations.queues.tasks)

Cloud Run request timeout defaults to 5 minutes and can be configured up to 60
minutes. When the timeout is exceeded, Cloud Run returns 504, but the container
may continue processing.

Source:

- [Cloud Run request timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout)

Recommended relationship:

```text
application generation deadline
  < Cloud Tasks dispatch deadline
  <= Cloud Run request timeout
```

The worker must use fencing because a timed-out or disconnected worker process
may continue and later try to commit.

### 4.6 Retry behavior

Cloud Tasks treats 2xx responses as successful task completion. Other
responses and deadline failures are retried according to queue configuration.
Google documents stronger throttling for HTTP 429, HTTP 503, and sustained
queue error rates. Cloud Tasks also honors `Retry-After` for applicable error
responses.

Sources:

- [Cloud Tasks task resource](https://docs.cloud.google.com/tasks/docs/reference/rest/v2/projects.locations.queues.tasks)
- [Cloud Tasks common pitfalls](https://docs.cloud.google.com/tasks/docs/common-pitfalls)

Recommended worker behavior:

- persist a terminal application failure and return 2xx so the task is
  removed;
- persist a retryable attempt failure and return a retriable non-2xx;
- do not use HTTP failure responses merely to convey a normal terminal job
  result to the browser.

Examples of retryable failures:

- transient provider 429 or 5xx;
- transient provider timeout;
- transient Firestore availability failure;
- retryable Firestore transaction abort;
- transient Cloud Run resource exhaustion.

Examples of terminal failures:

- unsupported or invalid persisted job contract;
- ownership invariant failure;
- missing required source;
- unsupported artifact schema;
- explicit cancellation observed before execution;
- deterministic local validation failure after the approved bounded
  generation policy is exhausted.

Task-level retry configuration is currently documented as a Preview feature.
A stable first implementation should prefer queue-level retry policy unless
Phase 3 explicitly accepts a Preview dependency.

Source:

- [Configuring task retries](https://docs.cloud.google.com/tasks/docs/configure-retry-task)

### 4.7 Retry-exhaustion limitation

Cloud Tasks does not provide the application a normal separate callback after
all task retries are exhausted.

If the worker receives the final attempt, it can persist terminal failure. If
the worker is never reached because of IAM, routing, deployment, or service
failure, the job may remain queued or running after Cloud Tasks stops retrying.

Phase 3 therefore needs one of:

1. an application-owned job deadline and reconciliation process;
2. explicit operational reconciliation against task state;
3. a controlled maximum-attempt policy the worker can observe when reached;
4. a documented stale-job procedure for the first bounded release.

This remains an unresolved architecture decision.

### 4.8 Cancellation limitations

A scheduled or dispatched Cloud Task can be deleted with the required
permission.

Source:

- [Cloud Tasks delete task API](https://docs.cloud.google.com/tasks/docs/reference/rest/v2/projects.locations.queues.tasks/delete)

Deletion is not a reliable process kill. Google documents that when a request
is cancelled or its deadline expires, Cloud Tasks stops waiting for the
response, but worker code may continue.

Truthful cancellation semantics are:

- queued job: cancellation can normally prevent generation;
- running before provider call: the worker can observe cancellation and stop;
- running during provider call: cancellation is requested, but immediate
  termination cannot be guaranteed;
- artifact already committed: cancellation cannot retroactively deny or erase
  completion;
- browser language should say "Cancellation requested" until authoritative
  state confirms the outcome.

The worker should check cancellation while claiming the job, immediately
before provider invocation, and immediately before final persistence.

### 4.9 Region constraints

Cloud Tasks and Cloud Run both have region-specific availability.

Sources:

- [Cloud Tasks locations](https://docs.cloud.google.com/tasks/docs/locations)
- [Cloud Run locations](https://docs.cloud.google.com/run/docs/locations)

Recommendation:

- place the queue, public API, and private worker in one supported region;
- align the region with Vertex AI availability and existing Firestore
  deployment;
- make the exact region an explicit Phase 3 planning decision.

Cloud Run documents no networking charges for service-to-service traffic in
the same region.

### 4.10 Local development

Google's migration documentation describes a local-development server that
does not emulate Cloud Tasks API endpoints. The documented workflow does not
provide a normal official Cloud Tasks emulator.

Sources:

- [Cloud Tasks migration guidance](https://docs.cloud.google.com/tasks/docs/migrating)
- [Testing Cloud Run services locally](https://docs.cloud.google.com/run/docs/testing/local)

Recommended local boundary:

```text
ArtifactJobDispatcher
  |- CloudTasksDispatcher in deployed environments
  `- DeterministicFakeDispatcher in local tests
```

The fake dispatcher should accept the same application command, record
enqueue attempts deterministically, and permit duplicate-delivery, retry, and
stale-worker simulations. It must never silently become the production
fallback. A controlled deployment test must still use a real Cloud Tasks queue
and private Cloud Run worker.

### 4.11 Logging and observability

Cloud Tasks supports logs for task creation, task deletion, dispatch attempts,
and attempt responses. Queue logging may require an explicit sampling ratio.
Cloud Run produces request, container, and system logs and supports structured
application logging.

Sources:

- [Cloud Tasks monitoring and logging](https://docs.cloud.google.com/tasks/docs/monitor)
- [Cloud Run logging](https://docs.cloud.google.com/run/docs/logging)

Recommended safe structured fields:

- opaque job ID;
- operation;
- state;
- attempt number;
- worker generation;
- duration;
- result category;
- retryable flag;
- exception class.

Do not log task OIDC tokens, Google user subjects, raw prompts, conversation
history, memory values, artifact content, provider responses, raw task bodies,
or feedback content.

## 5. Durable job-state constraints

This section proposes behavioral constraints, not a Firestore schema.

### 5.1 Public states

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

A separate cancellation-request timestamp or flag is required because a
running job may not be immediately cancellable.

### 5.2 Recommended transitions

| Current state | Next state | Owner | Required guard |
| --- | --- | --- | --- |
| none | queued | authenticated submission service | Durable job exists before task dispatch |
| queued | running | private worker | Atomic lease/fence claim |
| queued | cancelled | authenticated cancellation service | Ownership check and no committed artifact |
| queued | failed | submission or reconciliation service | Terminal enqueue or contract failure |
| running | queued | worker | Persisted retryable failure and lease release |
| running | running | replacement worker | Previous lease expired and generation token changes |
| running | completed | worker | Atomic artifact and completion transaction |
| running | failed | worker | Terminal failure persisted |
| running | cancelled | worker | Cancellation observed before completion commit |
| completed | none | nobody | Terminal |
| failed | none | nobody | Terminal for this job |
| cancelled | none | nobody | Terminal for this job |

An explicit user retry should create a new job linked to the failed or
cancelled job rather than erasing terminal history or resetting it in place.
Cloud Tasks automatic redelivery remains another attempt on the same job.

### 5.3 Worker ownership and fencing

A durable worker claim should include:

- unique lease owner;
- lease expiry;
- monotonically changing attempt or generation value;
- attempt timestamp;
- cancellation check.

A completion transaction must reject a stale worker unless the job is still
running, the worker owns the current generation, the lease is valid, no
cancellation outcome has already won, and no conflicting artifact has been
committed.

Without fencing, a timed-out first worker could commit after a second worker
has reclaimed the job.

### 5.4 Stale worker detection

Recommended mechanism:

1. A worker transaction claims a queued or stale running job.
2. The worker receives a unique generation token.
3. Long executions renew the lease.
4. State changes require the generation token.
5. Final completion verifies current ownership.
6. Expired workers cannot commit.

If provider generation may exceed the lease, heartbeat renewal is required.

### 5.5 Duplicate-artifact prevention

Task-name deduplication is insufficient. Recommended application guarantees:

- one deterministic artifact effect key per job;
- canonical artifact ID derived from that job or effect key;
- completion transaction writes the artifact and completed job atomically;
- an existing matching artifact is replayed;
- an existing conflicting artifact is an invariant failure;
- duplicate workers may duplicate provider cost but cannot create multiple
  authoritative artifacts.

### 5.6 Authoritative completion

Authoritative completion is one Firestore transaction that records:

- canonical artifact;
- artifact ownership and lineage;
- completed action receipt;
- artifact reference;
- completed job state;
- completion timestamp;
- winning worker generation and attempt.

The worker should return HTTP 2xx only after this transaction succeeds. A
Cloud Tasks 2xx without an authoritative completed job and artifact is a
worker defect.

### 5.7 Browser-visible job data

The browser may safely receive:

- public job ID;
- display label;
- status;
- created, started, and completed timestamps;
- retryable status;
- bounded user-facing error category;
- cancellation-request state;
- completed action receipt;
- artifact reference when complete.

The browser should not receive:

- Cloud Tasks resource name;
- worker service account;
- lease owner;
- OIDC audience or token data;
- raw stack trace;
- raw provider response;
- queue configuration;
- internal Firestore path.

The browser should poll the application API, never Cloud Tasks directly.

## 6. Ownership and security audit

### 6.1 Job submission

Job submission must authenticate the Google principal, derive the effective
user internally, validate workspace ownership, store the owner and workspace
on the job, and never accept a request-provided owner as authoritative.

### 6.2 Job status reads

A job ID is a locator only. A status read must authenticate the principal,
derive the effective user, validate workspace ownership, load the job inside
that boundary, and return unavailable when ownership does not match.
Possession of a job ID must not grant access.

### 6.3 Cancellation and retry

Cancellation and retry must repeat the full user/workspace ownership check.
They must not authorize based on a job ID, task name, artifact ID, session ID,
or workspace ID supplied by the browser.

### 6.4 Artifact retrieval

The completed artifact reference must still be resolved under the
authenticated workspace. A completed job must not create a shortcut around
canonical artifact authorization.

### 6.5 Worker invocation

The private worker authenticates the dedicated Cloud Tasks caller service
account. It should parse only a bounded job locator and contract version, load
the canonical job, enforce its state and lease, and obtain user, workspace,
and source from the canonical job record. Those values must not be accepted as
authority from task payload fields.

### 6.6 Authorization-confusion risks

| Identifier | Safe use | Unsafe use |
| --- | --- | --- |
| Job ID | Locate job after authentication | Treat possession as access |
| Task name | Cloud Tasks deduplication and operations | Treat as worker identity |
| Workspace ID | Scope query after principal validation | Allow browser to select another owner |
| Artifact ID | Retrieve inside authenticated workspace | Treat as bearer capability |
| Session ID | Locate owned session | Infer user identity |
| Retry-count header | Observability and retry decisions | Authenticate Cloud Tasks |
| OIDC token subject | Authenticate worker service identity | Substitute for end-user ownership |

## 7. Integration collision map

| Surface | Collision risk | Reason | Recommended isolation |
| --- | --- | --- | --- |
| `main.py` | High | Central FastAPI routes, auth, and chat orchestration | Add isolated job router/service wiring; minimize inline route logic |
| `database.py` | Very high | Existing chat, artifact, memory, and workspace persistence | Put job persistence in a dedicated repository module |
| `schemas.py` | High | Shared public and internal models | Define durable-job models separately and re-export only if required |
| `agent_col_turn_service.py` | High | Exact artifact dispatch seam | Inject a narrow artifact-work dispatcher |
| `agent_col_artifact_executor.py` | High | Coupled to `ChatTurnClaim` | Do not fake claims; create a separate job executor using existing application services |
| `synthesis_service.py` | Medium/low | Reusable generation boundary | Prefer no semantic change |
| `auth.py` | Medium | Public owner resolution | Reuse for users; keep worker service identity separate |
| `frontend/api.mjs` | Medium | New status, retry, and cancel transport | Add bounded job API helpers |
| `frontend/state.mjs` | High | Needs durable job state and polling | Isolate job state from request-only `pendingTurn` |
| `frontend/app.mjs` | High | Central UI orchestration | Delegate polling and job actions to a focused controller |
| Artifact views | Medium | Need queued, completed, and result rendering | Reuse viewer after canonical artifact reference appears |
| `firestore.indexes.json` | Medium/high | Job-list and status queries may require composite indexes | Define only after query model is accepted |
| `requirements.txt` | Low | Cloud Tasks client dependency is absent | Add official client only during approved implementation |
| Deployment configuration | New | No checked-in worker, queue, and IAM deployment contract found | Add explicit public API, private worker, queue, and IAM deployment definitions |

## 8. Recommended Phase 3 verification strategy

### 8.1 Deterministic state-transition tests

Prove that only permitted transitions succeed, terminal states cannot
transition, stale worker generations cannot update state, cancellation cannot
overwrite completed artifacts, and completed artifact references match
canonical storage.

### 8.2 Submission idempotency

Prove that exact duplicate submission returns the same job, a changed request
with the same idempotency key conflicts, job-first/task-second recovery does
not create multiple jobs, and enqueue retry uses the same deterministic task
name.

### 8.3 Duplicate delivery

Invoke the worker twice for one job and prove that at most one worker owns the
current generation, at most one canonical artifact exists, a completed job
replays its result, and no second artifact is created.

### 8.4 Stale-worker test

1. Worker A claims a job.
2. Its lease expires.
3. Worker B reclaims it.
4. Worker A attempts completion and is rejected.
5. Worker B completes authoritatively.

### 8.5 Authenticated-worker test

Prove that unauthenticated invocation is denied, an ordinary end-user Google
token cannot invoke the worker, the configured task-caller service account can
invoke it, and the worker still validates the job state and contract.

### 8.6 Cross-user and cross-workspace denial

For status, retry, cancel, and artifact retrieval, prove that the owner
succeeds, another authenticated user receives an unavailable response, another
workspace cannot access the job, and changed request locators do not bypass
derived ownership.

### 8.7 Cancellation

Prove queued cancellation prevents generation, a running worker observes
cancellation before provider invocation, cancellation during provider work
remains requested until resolution, completion and cancellation have
deterministic precedence, and a completed job cannot be cancelled.

### 8.8 Retry

Prove that retryable provider failure receives another attempt on the same
job, a new attempt generation is used, terminal failure returns 2xx only after
state persistence, explicit user retry creates a linked new job, and duplicate
delivery does not duplicate artifacts.

### 8.9 Controlled live failure

Recommended judge-facing evidence:

1. Submit one blueprint job.
2. Fail its first worker attempt through a deployment-gated test injection.
3. Show queued, running, and retry evidence without user content.
4. Show the Cloud Tasks dispatch attempt and retry.
5. Complete the second worker attempt.
6. Show that only one artifact exists.
7. Show the browser progress through queued, running, and completed.
8. Load the canonical artifact.
9. Replay the exact submission and receive the same job/result.
10. Reuse the key with a changed request and receive a conflict.

The failure injection must never be exposed as an unauthenticated public
switch.

### 8.10 Google Cloud evidence for judging

Capture:

- public Cloud Run API service;
- separate private worker service;
- worker authentication requirement;
- dedicated task-caller service account;
- `roles/run.invoker` binding;
- Cloud Tasks queue region and configuration;
- dispatch and retry logs;
- Cloud Run worker request logs;
- Firestore job-state timeline;
- final canonical artifact;
- deployed `.run.app` browser URL;
- content-safe logs without prompts or memory values.

## 9. Risks and unresolved decisions

Machine 1 must resolve these before writing a Phase 3 implementation plan:

1. Which workflow becomes asynchronous? Recommendation: blueprint synthesis
   only.
2. What does `/api/chat` return immediately? It needs a bounded queued-job
   receipt and truthful conversational acknowledgement.
3. When and where is the assistant completion message generated?
4. How is Firestore job creation reconciled with non-transactional Cloud Tasks
   enqueue?
5. How are retry-exhausted or never-delivered tasks reconciled?
6. Is user retry a new job or a reset of a terminal job? Recommendation: a new
   linked job.
7. What wins when cancellation races with artifact completion?
8. What lease duration and heartbeat interval match measured synthesis time?
9. What task-name derivation avoids exposing user, workspace, or artifact
   identity?
10. What region satisfies Cloud Tasks, Cloud Run, Vertex AI, Firestore, and
    cost requirements?
11. What retention and deletion relationships exist among jobs, chat turns,
    and artifacts?
12. What queue concurrency and Cloud Run instance limits fit the demo budget
    and Vertex quotas?

## 10. Recommended Phase 3 planning inputs

Machine 1 should build the future implementation plan around:

- one blueprint workflow only;
- dedicated durable-job models;
- dedicated job repository;
- dedicated queue-dispatch abstraction;
- Cloud Tasks production dispatcher;
- deterministic local fake dispatcher;
- private worker service;
- job-specific worker lease and fencing;
- atomic job/artifact completion;
- application-owned status API;
- application-owned cancel and retry operations;
- end-user ownership checks on every public operation;
- OIDC worker authentication using a dedicated service account;
- frontend job polling isolated from current request state;
- canonical artifact viewer reuse after completion;
- explicit queue concurrency, retry, timeout, region, retention, and cost
  decisions;
- operational handling for retry exhaustion and stalled jobs.

## 11. Reconciliation checklist for Machine 1

- [ ] Confirm Phase 1 changes do not alter the identified artifact-dispatch
      seam.
- [ ] Accept one asynchronous workflow, preferably blueprint synthesis.
- [ ] Define immediate chat-response semantics.
- [ ] Define artifact completion versus responder completion.
- [ ] Define job-first/task-second enqueue recovery.
- [ ] Define retry-exhaustion reconciliation.
- [ ] Define cancellation language and race precedence.
- [ ] Accept job states and transition ownership.
- [ ] Accept worker lease, heartbeat, and fencing semantics.
- [ ] Ensure job and task identifiers contain no user-facing or sensitive
      values.
- [ ] Require authenticated user/workspace ownership on public job APIs.
- [ ] Require Cloud Run IAM and OIDC worker authentication.
- [ ] Limit task payload to an opaque job locator and contract version.
- [ ] Define least-privilege queue and worker service-account permissions.
- [ ] Select the queue, worker, and public API region.
- [ ] Align request, task, provider, lease, and UI polling deadlines.
- [ ] Bound queue concurrency and Cloud Run maximum instances.
- [ ] Ensure the local fake dispatcher cannot activate in production.
- [ ] Explicitly allowlist content-safe logging fields.
- [ ] Determine Firestore queries and indexes before editing indexes.
- [ ] Include controlled live retry evidence in acceptance.
- [ ] Do not bundle generic artifacts, memory work, or frontend polish into
      Phase 3.

## 12. Investigation boundary

M10-RSCH.1 performed research and source review only. It did not implement
production code, schemas, endpoints, workers, queues, frontend state, or
deployment configuration. All architectural recommendations remain subject to
Machine 1 reconciliation and the repository's normal approval-gated
implementation workflow.
