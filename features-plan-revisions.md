# Agent Col Feature Plan Revisions

## Status and review basis

This is a comprehensive source and feature review of the repository at commit
`609e99342d3a6d79089eb137a4cb4f17d4070074` on August 24, 2026. It records the
implemented product, evaluates it against the authoritative identity and
accepted design direction, and revises the remaining feature plan. It changes
no runtime behavior.

The review used the executable FastAPI, service, routing, persistence, schema,
frontend, and test code as the current truth. Older architecture, inventory,
README, and submission documents were treated as historical when they
contradicted source. Unaccepted local changes to `frontend/state.mjs`, its test,
and one screenshot were excluded from the accepted baseline.

This revision also treats the hackathon requirements supplied by the
repository owner on August 24, 2026 as delivery acceptance criteria. In
particular, the product must demonstrate a collaborative partner that takes
notes and adapts across conversations, at least one durable asynchronous
workflow beyond a standard request-bound chat loop, a hosted project, current
spin-up instructions, a current architecture diagram, and a short demo that
shows the backend running on Google Cloud.

## TL;DR

Agent Col is no longer an early synthesis demo. It is a substantial local
application with:

- model-controlled routing across direct response, clarification, source,
  research, computation, requirements verification, and artifact work;
- a responder-only conversational owner;
- deterministic expert and artifact execution boundaries;
- retry-safe chat-turn effects and authoritative receipts;
- Google-authenticated single-owner workspaces;
- reopenable chat sessions;
- governed cross-session memory with approval and lifecycle events;
- blueprint plus generic code/document/data artifacts;
- canonical artifact reads, feedback for blueprints, export, archive/restore,
  rename, and immutable versions;
- a functional browser workspace over real backend contracts.

That is real progress and a credible product core. It is not yet aligned enough
or hardened enough to call finished. The largest judged identity failure is
that stored chat sessions are not usable cross-chat continuity. In
`scrnshot-evidence/pending.png`, a fresh chat asks what script the user
requested in the prior conversation and Agent Col answers that no previous
conversation history is available. That answer is consistent with the source:
the turn context loads the active session history and approved profile memory,
not relevant prior sessions or collaborative notes. The application stores
chats, but Agent Col does not currently remember prior work unless the user
manually reopens the same session or the information fits the narrow governed
profile schema.

The second identity failure is the narrow memory vocabulary. The largest
security failure is incomplete session ownership validation in the chat path.
The product also remains a synchronous chat application with structured tools;
it has no durable background-job boundary. The largest delivery failures are
the absence of Cloud Run deployment configuration and hosted verification,
stale documentation, missing submission assets, and a currently red Python
test baseline.

The project should not expand into more experts or image artifacts now. It
should separate profile memory from workspace notes and chat archives, repair
the ownership boundary, close governed memory, add bounded cross-chat recall,
prove one durable asynchronous workflow, establish the hosted Cloud Run path,
and produce the required submission evidence. Lifecycle polish that does not
serve that proof comes afterward.

## Hackathon alignment verdict

The following assessment is against the requirement text supplied by the
repository owner, not an inferred product wish list.

| Supplied requirement | Current evidence | Verdict |
| --- | --- | --- |
| Operate beyond standard chat loops | Structured experts and artifact workflows exist, but all execute inside the HTTP request | Partial |
| Run asynchronously in the background | No job entity, queue, authenticated worker, status, cancel, or resume boundary | Not met |
| Handle complex workflows or data representations | Routing, research, computation, requirements verification, blueprints, and generic artifacts are real | Substantially implemented, still synchronous |
| Collaborative partner that leads and takes notes | Agent Col clarifies and guides, but has no distinct workspace-note model and cannot retrieve relevant unopened prior chats | Not met as an end-to-end continuity promise |
| Clear feedback and adaptation | Governed memory approval/lifecycle and blueprint feedback exist; generic artifact feedback and memory scope remain incomplete | Partial |
| Hosted URL for judging | No verified Cloud Run deployment is represented in repository-owned configuration/evidence | Not met |
| Reproducible spin-up instructions | Current README and status documentation drift from source | Not met |
| Current architecture diagram | Existing architecture documentation is stale relative to auth, workspaces, generic artifacts, and the browser | Not met |
| Four-minute demo including Google Cloud proof | No current, verified demo script/evidence bundle exists | Not met |

Bluntly: Agent Col is a strong local synchronous agent application, but it does
not yet satisfy the most differentiating parts of the supplied brief. Calling
chat storage “memory,” or calling request-bound synthesis “background work,”
would be misleading.

## Authoritative product identity

Agent Col is a general collaborative partner. It is not primarily a blueprint
generator, code generator, research agent, or project manager. Those are
capabilities used in service of an ongoing relationship.

The defining product promise is:

1. understand the user's current intent;
2. ask only consequential clarifying questions;
3. choose the smallest appropriate capability;
4. preserve trustworthy continuity across sessions;
5. learn only through explicit governed feedback and approval;
6. explain what action, evidence, artifact, or adaptation actually occurred;
7. keep the user in control of persistent memory and generated work;
8. remain useful across technical, academic, creative, planning, and learning
   domains.

This identity makes memory quality and conversational continuity more central
than adding another specialist or artifact type.

## Current architecture and feature inventory

### Application boundary

`main.py` creates a single FastAPI application and wires authentication,
Firestore persistence, trusted memory, routing, cognitive experts, synthesis,
generic artifact generation, feedback, response generation, and the static
browser workspace. The application is currently synchronous at the HTTP
boundary.

The main conversational flow is:

```text
request
  -> authenticated effective user/workspace
  -> optional idempotent turn claim
  -> bounded history + governed profile projection
  -> structured Agent Col routing
  -> zero or one expert/artifact operation
  -> deterministic effect persistence
  -> responder-only Agent Col output
  -> atomic completion and receipts
```

This architecture correctly separates model judgment from deterministic write
authority. It should be preserved.

### Implemented capability routes

| Route | Purpose | Current state |
| --- | --- | --- |
| `direct` | Stable explanation or conversation without tools | Implemented |
| `clarify` | Ask one useful question when required information is missing | Implemented |
| `source` | Analyze explicitly supplied public URL evidence | Implemented |
| `research` | Use current public evidence and return grounded citations | Implemented |
| `computation` | Execute bounded numerical computation with provenance | Implemented |
| `requirements_verification` | Compare supplied subject evidence against explicit requirements | Implemented |
| `artifact` | Create a blueprint or generic single-file artifact | Implemented |

The zero-or-one-major-capability constraint remains appropriate. It prevents
retrieved or generated content from escalating into unbounded nested actions.
Natural conversation should become less brittle without removing this safety
boundary.

### Implemented API groups

- health and browser workspace;
- authentication configuration/session inspection;
- workspace list and creation;
- chat session list and detail;
- memory inspection, approval/rejection through chat, revoke, and delete;
- direct structured synthesis;
- blueprint list/detail/feedback;
- generic artifact create/list/detail;
- artifact archive/restore, metadata update, and version creation;
- idempotent conversational chat.

### Firestore entities

| Entity | Current role | Ownership model |
| --- | --- | --- |
| `sessions/{session_id}` | Chat metadata, messages, and turn/effect ledger | User/workspace fields stored; mutation validation incomplete |
| `users/{user_id}` | Collaboration profile and memory revision | Auth-derived user in Google mode |
| `users/{user_id}/workspaces/{workspace_id}` | User workspace catalog | Single authenticated owner |
| user memory proposals/events/origins | Governed memory lifecycle and provenance | User-global |
| `projects/{project_id}/blueprints/{id}` | Immutable synthesis blueprints | Workspace-scoped by project ID |
| blueprint feedback subcollections | Immutable target feedback and supersession | Workspace artifact-scoped |
| `projects/{project_id}/artifacts/{id}` | Generic single-file artifacts and version lineage | Workspace-scoped by project ID |

The use of internal `project_id` as the durable workspace key is sound. The
frontend should continue calling it Workspace without removing or migrating
the backend field.

## Feature alignment assessment

### General conversational ownership — substantially aligned

Agent Col is the only user-facing conversational owner. Experts do not speak
directly to the user, and completed operations are projected through bounded
responder contexts and verified receipts. Direct conversation remains
available without forced tool use.

Remaining problem: routing and memory prompts sometimes require unusually
precise wording. That makes a capable collaborator feel like a command parser.
The fix is not to remove structured contracts; it is to normalize natural
intent before those contracts and make unsupported/ambiguous outcomes honest.

### Expert/tool restraint — aligned

The implemented router supports the accepted cognitive capabilities and the
artifact workflow while maintaining a single major capability per turn.
Source, research, computation, and requirements verification have deterministic
execution and responder projections. This is a strong part of the system.

Remaining limitations:

- long synchronous calls can still time out;
- there is no durable job/status/cancel boundary;
- no file upload or document ingestion exists;
- multi-source or multi-capability workflows require separate turns.

These were acceptable for an early local MVP. They are not acceptable as the
final judged boundary under the supplied requirement for autonomous background
work beyond standard chat loops.

### Governed memory — lifecycle implemented, product scope misaligned

The repository has meaningful governed-memory infrastructure:

- explicit pending proposals;
- approve/reject decisions;
- active profile projection;
- provenance and policy versions;
- correction/supersession event semantics;
- revoke and delete;
- cross-session adaptation receipts;
- user-global memory across workspaces.

The weakness is policy coverage and conversational mapping. The current
allowlist contains:

- response length;
- explanation structure;
- example usage;
- question style;
- planning granularity;
- progress check-ins;
- tool-use style;
- formatting style;
- preferred name;
- broad roles.

The authoritative identity describes a broader safe memory scope, including
accessibility needs, explanation pace, learning approach, and explicitly
approved domain experience. The observed request for macOS/Linux development
environment falls outside the current schema. Agent Col therefore cannot
create the proposal even when the user clearly asks it to remember the
preference.

This is not merely phrasing friction. It is a contract mismatch between the
product identity and `memory_policy.py`. The revised memory work must remain
bounded and normalized; allowing arbitrary durable strings would damage
safety, auditability, and adaptation determinism.

### Cross-session continuity — archive implemented, collaborative recall absent

Chat sessions can be listed and reopened, and active profile memory can adapt a
later session. This proves archive persistence and narrow preference
adaptation. It does not prove that Agent Col can remember prior work.

The screenshot evidence in `scrnshot-evidence/pending.png` demonstrates the
gap: the user asks what script was requested in the last conversation and Agent
Col reports that the current session has no previous history. The source path
matches the observed result because only the current `session_id` history is
loaded into the response context. Session list/detail APIs serve the browser,
but no retrieval service supplies relevant prior sessions to the model.

The target architecture needs four separate durable domains:

- **profile memory:** approved, user-global collaboration preferences and
  low-sensitivity identity signals;
- **workspace notes:** owner-bound project decisions, constraints, task state,
  and agreed takeaways;
- **chat archives:** canonical transcripts and session metadata;
- **continuity retrieval:** bounded, ownership-checked projections with
  application-derived provenance receipts.

These domains must not be collapsed into arbitrary permanent transcript memory.
Agent Col should retrieve only relevant prior sources when the current message
refers to earlier work, and should clarify when multiple matches are plausible.

Remaining gaps:

- chats lack rename/archive/delete;
- titles are previews rather than durable concise labels;
- ordinary references to another unopened chat are not retrieved into current
  model context, as the screenshot proves;
- no collaborative workspace-note entity or note lifecycle exists;
- no receipt tells the user which prior session or note informed the response;
- artifacts can use a small window of prior user messages, but not the prior
  Agent Col answer itself;
- durable memory rejects several valuable collaboration signals.

Agent Col should not claim awareness of an unopened prior session unless the
retrieval contract actually supplies it.

### Artifact system — strong generic foundation, incomplete collaboration loop

The artifact system now supports two distinct families of product behavior:

1. strict structured blueprints with feedback targets;
2. generic single-file code, document, and data artifacts.

Generic artifacts support broad text-based formats, including Python, C, C++,
Rust, Swift, shell languages, web languages, Markdown, text, JSON, YAML, TOML,
and SQL. The canonical artifact stores content, media type, filename, family,
format, display metadata, provenance, lifecycle state, and lineage. The browser
can export the original file, constrained alternatives, or artifact-only PDF.

This corrects the earlier identity drift where every deliverable became a
blueprint.

Remaining gaps:

- context conversion includes recent user messages but not Agent Col's prior
  generated response, so "turn your last answer into a file" is not fully
  implemented;
- the manual UI can select invalid family/format pairs;
- generic artifacts do not have target feedback;
- deletion is absent;
- multi-file bundles are absent;
- uploads and binary artifacts are absent;
- image artifacts are deliberately deferred.

### Authentication and ownership — useful foundation, not production-hardened

Google mode verifies the Google ID token on the server and derives internal
user/workspace identifiers. The frontend no longer exposes the raw Google
subject as the human alias. Local-development mode remains intentionally
insecure and must never be used for public deployment.

Critical gap: session mutation/history access is keyed by supplied session ID
without first validating the existing session's stored user/workspace owner.
List/detail filtering does not protect the chat mutation path. This must be
fixed before public deployment.

Other missing production controls:

- logout;
- minimal auth-session response data;
- production OAuth client/origin configuration;
- rate and payload limits;
- security headers;
- account deletion and retention behavior;
- durable workspace memberships if collaboration ever expands beyond one
  owner.

### Browser workspace — implemented and appropriate for the hackathon

A same-origin browser application is the right current delivery surface for a
Cloud Run submission. A native application would add packaging, signing,
updating, cross-platform, and OAuth callback complexity without improving the
core judged workflow. A PWA or native wrapper can be considered later without
changing the backend contracts.

### Durable asynchronous collaboration — not implemented

Synthesis and expert work still occur inside the request. There is no job
entity, queue, authenticated worker, retry-safe background execution, status
polling, cancellation, or notification. The current turn-effect ledger reduces
duplicate side effects but does not make work survive process termination.

This is a planned capability, not current behavior. The supplied hackathon
brief explicitly values background autonomous work beyond standard chat loops,
so it is no longer a conditional “only if timeouts require it” item. The
smallest credible proof is to promote one existing heavy bounded workflow,
preferably synthesis or generic artifact generation, to a durable job with
queued/running/completed/failed/cancelled states, authenticated worker
execution, idempotent effects, and user-visible status. Ordinary conversational
turns should remain synchronous.

### Deployment and submission — materially incomplete

No repository-owned Cloud Run container/build configuration was found. Hosted
OAuth, ownership, security, and smoke verification have not been completed.
The submission checklist remains largely stale and unchecked.

The product is locally demonstrable but not yet a reproducible hosted
submission. Hosted deployment, spin-up documentation, current architecture,
submission copy, and the demo evidence path are release gates, not end-of-
schedule documentation cleanup.

## Verified defects and quality risks

### Security defect: session owner validation

`POST /api/chat` reads messages by session ID before checking the stored session
owner. The save and turn-claim paths can merge user/workspace metadata. This
must be corrected at the persistence transaction boundary and covered by
cross-owner regression tests.

### Contract defect: memory scope mismatch

The memory schema cannot represent several safe collaboration preferences the
identity document promises. Model prose can appear to acknowledge a request
that has no durable effect. The responder must explicitly distinguish
session-only accommodation, rejected candidate, pending proposal, and active
memory.

### UI contract defect: invalid generic artifact combinations

The backend family/format mapping is stricter than the frontend's independent
select controls. The UI should consume or mirror one authoritative mapping and
never offer invalid combinations.

### Context defect: prior-answer artifact conversion

The generic artifact context builder uses recent user messages only. It cannot
faithfully convert a previous Agent Col code block or prose answer because that
answer is absent from the generator source. This must remain a declared
limitation until a bounded server-owned transcript projection is designed.

### Red test baseline

The comprehensive Python test run produced:

```text
5 failed, 1935 passed, 1 warning
```

The failures appear to be stale expectations after accepted schema/session/
artifact changes:

- routing-provider artifact schema fields;
- chat-session metadata persisted during turn claim and completion;
- generic artifact lifecycle/version metadata;
- workspace static accessibility label.

Even when production behavior is intentional, a red main-branch suite is a
real quality problem. The expectations must be reconciled through a bounded
test-contract pass, not ignored.

The frontend Node test run produced:

```text
118 passed, 0 failed
```

That run included the current unaccepted local frontend state change and must
not be treated as acceptance of that change.

### Documentation drift

Several high-visibility documents still describe now-implemented features as
missing, including browser workspace, authentication, chat-routed artifacts,
artifact retrieval, feedback, and personalization. In particular:

- `README.md` is no longer a reliable feature-status summary;
- `docs/architecture.md` does not describe the current route and persistence
  model;
- `BACKEND_FRONTEND_INTEGRATION_CONTRACT_INVENTORY.md` predates many current
  APIs;
- `docs/submission-checklist.md` is not reconciled with implementation.

This violates the repository's reproducibility goal and increases development
drift. Documentation reconciliation is required before submission.

### Maintainability risk

Core files are very large (`main.py`, `database.py`, `schemas.py`, turn service,
and several frontend modules), while legacy and versioned routing/executor
modules remain beside current ones. This makes it harder to know which code is
authoritative and raises regression risk.

Do not perform a broad rewrite before submission. After the behavioral
baseline is green, extract cohesive routers/repositories/view modules in small
tested passes and archive or remove proven-dead versions.

### Dependency warning

The Python suite reports a deprecation warning for `BaseAgentConfig`. It is not
the current blocker, but dependency/API migration should be scheduled before a
future library update makes it a failure.

## Revised feature roadmap

### Track 1: M9 continuity and governed-memory closure

1. **M9-CONT.1 — Continuity Domain and Collaborative Notes Design**
   - design-only separation of profile memory, workspace notes, chat archives,
     and cross-chat retrieval receipts;
   - define note proposal/approval, provenance, correction, archive, deletion,
     ambiguity, and retrieval limits.
2. **M9-SEC.1 — Transactional Chat Session Ownership Correction**
   - enforce owner/workspace validation before history reads, turn claims, or
     mutation;
   - this must land before cross-chat retrieval expands the accessible history
     surface.
3. **M9-MEM.1 — Governed Memory Scope and Natural Request Contract
   Reconciliation**
   - align identity, bounded categories, normalized values, proposal semantics,
     migration, responder truthfulness, and UI needs.
4. **M9-MEM.2 — Versioned Memory Policy and Natural Proposal Routing**
   - TDD implementation of approved categories, aliases, schema migration,
     ordinary durable-intent phrasing, one-proposal discipline, and truthful
     unsupported/session-only responses.
5. **M9-NOTE.1 — Governed Collaborative Note Persistence and APIs**
   - workspace-scoped note records with source-session/message provenance and
     inspect/correct/archive/delete lifecycle.
6. **M9-CONT.2 — Bounded Cross-Chat Retrieval and Receipts**
   - ownership-checked relevant retrieval, compact context projection,
     ambiguity clarification, and application-derived source receipts.
7. **M9-UI.1 — Memory and Notes Controls**
   - bounded memory add/correct controls plus note inspection/correction/
     archive/delete and visible retrieval provenance.
8. **M9-EVAL.1 — Genuine New-Chat Continuity Closure**
   - prove profile adaptation and prior-work recall in separate new sessions;
   - prove revoked/deleted state disappears and cross-owner/workspace retrieval
     is denied.

### Track 2: contract and test truth

1. reconcile the five stale Python tests and restore a green main baseline;
2. make artifact family/format selection contract-aware;
3. minimize auth-session response data and add logout;
4. update the integration inventory to the accepted runtime contracts;
5. preserve focused regression coverage for every continuity and ownership
   boundary.

### Track 3: M10 durable background execution

1. **M10-JOB.1 — Durable Job Contract Design**
   - choose one existing heavy workflow and define job states, ownership,
     idempotency, cancellation, retry, result receipts, and retention.
2. **M10-JOB.2 — Job Persistence and Authenticated Worker**
   - persist jobs and execute them through Cloud Tasks or an equivalently
     durable authenticated Google Cloud worker.
3. **M10-JOB.3 — Browser Status and Recovery**
   - show queued/running/completed/failed/cancelled status and allow safe
     resume/cancel without duplicating effects.
4. **M10-JOB.4 — Disconnect and Retry Proof**
   - demonstrate that the workflow survives client disconnect or request
     termination and preserves exactly-once visible effects.

### Track 4: hosted submission path

1. production OAuth client and hosted origin;
2. Cloud Run build/deploy configuration and service-account separation;
3. limits, security headers, content-safe logs, and retention review;
4. hosted auth/ownership/idempotency/artifact/memory/note/job smoke tests;
5. current README local and Cloud Run spin-up instructions;
6. current architecture diagram covering browser, FastAPI, Vertex AI,
   Firestore, Cloud Tasks/worker, and receipt boundaries;
7. submission text for features, technologies, data sources, findings, and
   learnings;
8. a four-minute demo storyboard and evidence capture that visibly proves the
   backend is running on Google Cloud.

### Track 5: remaining mechanics and polish

1. chat rename/archive/restore/delete and concise titles;
2. workspace rename/archive/restore/delete and explicit child-data policy;
3. generic artifact feedback decision;
4. bounded artifact deletion/retention decision;
5. safe prior-Agent-response projection for artifact conversion;
6. safe Markdown rendering, accessibility, and copy polish.

### Later, only if schedule permits

- PWA/native wrapper;
- Deep Research or additional experts;
- image generation and PNG/JPEG artifacts;
- multi-file project bundles;
- multi-user workspace membership and sharing;
- file/document ingestion through a separately designed provenance and
  security boundary.

## Remaining project checklist

### Identity and collaboration

- [ ] Make normal conversation the default interaction rather than requiring
  a prompt guide.
- [ ] Keep one user-facing Agent Col and responder-only expert projection.
- [ ] Ensure clarifications are consequential, not ritual.
- [ ] Let Agent Col take bounded, inspectable workspace notes with explicit
  provenance and user control.
- [ ] Retrieve relevant prior work in a new chat or clarify genuine ambiguity.
- [ ] Never describe stored chat lists as model-usable memory unless retrieval
  actually supplied the prior content.
- [ ] Remove blueprint-centric product copy.
- [ ] Never claim a durable effect without an authoritative receipt.

### Cross-chat continuity and notes

- [ ] Keep profile memory, workspace notes, chat archives, and retrieval
  receipts as separate contracts.
- [ ] Add owner/workspace-bound collaborative note persistence and lifecycle.
- [ ] Add bounded relevant prior-session/note retrieval.
- [ ] Emit application-derived receipts for retrieved prior context.
- [ ] Prove the prior-script screenshot scenario succeeds in a fresh chat.
- [ ] Prove ambiguous recall asks the user to choose instead of guessing.
- [ ] Prove cross-user and cross-workspace retrieval fails closed.

### Governed memory

- [ ] Approve a revised safe memory-category contract.
- [ ] Add versioned normalization for natural user phrasing.
- [ ] Cover development environment, accessibility, learning approach,
  explanation pace, and approved domain-experience decisions as bounded
  categories where accepted.
- [ ] Preserve one-proposal and explicit-approval rules.
- [ ] Add UI creation and correction.
- [ ] Prove cross-session adaptation and removal.

### Ownership and security

- [ ] Enforce session ownership before history access or mutation.
- [ ] Add cross-user/workspace denial tests.
- [ ] Add logout.
- [ ] Minimize authentication response fields.
- [ ] Define retention and account deletion.
- [ ] Add production rate/payload limits and security headers.

### Artifacts

- [ ] Couple family and format controls.
- [ ] Decide generic artifact feedback parity.
- [ ] Design prior-Agent-response conversion safely.
- [ ] Decide deletion and retention behavior.
- [ ] Preserve canonical original export and artifact-only PDF.
- [ ] Keep image and binary formats deferred.

### Chats and workspaces

- [ ] Add concise durable chat titles.
- [ ] Add chat rename/archive/restore/delete.
- [ ] Add workspace rename/archive/restore/delete.
- [ ] Keep memory user-global and content workspace-scoped.
- [ ] Do not imply sharing until membership/roles exist.

### Reliability and maintainability

- [ ] Restore the Python suite to green.
- [ ] Preserve frontend test coverage as accepted changes land.
- [ ] Resolve the ADK deprecation warning.
- [ ] Split large modules only through bounded regression-tested passes.
- [ ] Remove or archive legacy versions only after proving they are unused.

### Durable background execution

- [ ] Define one bounded heavy workflow as a durable job.
- [ ] Persist queued, running, completed, failed, and cancelled states.
- [ ] Add an authenticated retry-safe worker and exactly-once visible effects.
- [ ] Add browser status, recovery, and cancellation controls.
- [ ] Prove the job survives disconnect or request termination.

### Deployment and submission

- [ ] Add reproducible Cloud Run build/runtime files.
- [ ] Configure production OAuth origin/client.
- [ ] Run hosted security and smoke verification.
- [ ] Update README, architecture, integration inventory, and submission
  checklist.
- [ ] Record a clean-clone setup and demo path.
- [ ] Write the submission feature, technology, data-source, findings, and
  learnings descriptions from verified behavior.
- [ ] Capture judge-facing evidence of conversation, prior-chat continuity,
  collaborative notes, artifact, feedback, governed memory, adaptation,
  background work, and ownership.
- [ ] Record a four-minute demo that shows the problem, value proposition,
  hosted workflow, and Cloud Run/Vertex AI evidence.

## Scope that should not be expanded now

The following are reasonable future capabilities but would distract from the
current product proof:

- arbitrary unstructured persistent memory;
- a generic model-visible Firestore tool;
- multiple experts in one turn;
- autonomous nested delegation;
- PNG/JPEG/image generation;
- multi-file repositories;
- Deep Research;
- collaborative multi-user workspaces;
- native desktop packaging;
- streaming and notifications without a durable job requirement.

## Recommended immediate decision

Approve **M9-CONT.1 — Continuity Domain and Collaborative Notes Design** as the
next pass. It should produce one authoritative design contract separating
profile memory, workspace notes, chat archives, and cross-chat retrieval, with
no production source change. It must incorporate the planned governed-memory
scope reconciliation rather than treating all prior-chat facts as profile
memory. The implementation sequence should then fix session ownership before
adding retrieval, continue through the bounded memory passes, and close with a
genuine new-chat recall proof.
