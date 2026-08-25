# Agent Col Frontend Plan Revision

## Status and authority

This document is a source-grounded revision of the Agent Col frontend plan as
implemented at commit `609e99342d3a6d79089eb137a4cb4f17d4070074` on
August 24, 2026. It is a planning and review artifact; it changes no production
behavior.

The current executable source is authoritative when an older plan or status
document disagrees with it. The following unaccepted local changes existed
during this review and are not treated as accepted baseline behavior:

- `frontend/state.mjs`;
- `tests/frontend/state.test.mjs`;
- `scrnshot-evidence/memory.png`.

This revision remains subordinate to `AGENTS.md`,
`AGENT_COL_IDENTITY_AND_ALIGNMENT.md`, and
`DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`.

It is also revised against the hackathon requirements supplied by the
repository owner on August 24, 2026. Those requirements make three outcomes
judge-facing rather than optional future work:

- a collaborative partner that takes useful notes and can carry relevant
  context across conversations;
- at least one durable asynchronous workflow that operates beyond a request-
  bound chat loop;
- a reproducible hosted Cloud Run submission with current architecture,
  setup, demo, and Google Cloud runtime evidence.

## TL;DR

Agent Col now has a real, same-origin browser workspace rather than a mock UI.
Google sign-in, private workspace selection, chat, reopenable chat sessions,
global governed memory inspection, blueprint and generic single-file artifact
creation, artifact viewing, export, archive/restore, rename, and immutable
versioning are all wired to backend contracts.

The frontend is therefore functional, but it is not yet submission-ready or
fully aligned with Agent Col's identity or the supplied hackathon brief. The
largest judged product gap is now continuity, not merely memory presentation.
The browser stores and reopens chats, but Agent Col cannot retrieve relevant
prior-chat content in a fresh conversation. In
`scrnshot-evidence/pending.png`, the user asks what script was requested in the
last conversation and Agent Col states that no prior conversation history is
available. The source confirms that a turn receives only the active session's
history plus approved profile memory. A chat archive that the user can open is
not the same capability as a collaborative partner that takes notes and can
recall relevant prior work.

The governed-memory mismatch remains a separate P0 product gap. The UI can
display and act on records that the backend actually creates, but the memory
policy accepts a much narrower set of collaboration signals than the governing
identity requires. Ordinary requests such as a preferred operating environment
can produce friendly prose without a durable proposal, leaving the user unable
to approve what Agent Col appears to have remembered. That is a backend
contract problem first and a frontend control problem second.

The highest-risk technical gap is session ownership enforcement on the chat
write path. Public deployment must not occur until an authenticated request is
prevented from reading or rebinding a session owned by another user/workspace.
The current repository also has five failing Python tests caused by contract
expectation drift, stale top-level documentation, no production deployment
configuration, and several incomplete lifecycle controls.

The correct next sequence is:

1. define the separate contracts for governed profile memory, collaborative
   workspace notes, chat archives, and cross-chat retrieval;
2. correct chat-session ownership before any cross-chat retrieval is exposed;
3. reconcile and expand governed memory and natural proposal behavior;
4. implement bounded, provenance-bearing collaborative notes and cross-chat
   recall, then prove them in a genuinely new chat;
5. add one durable asynchronous workflow and its status UI;
6. establish and verify the hosted Cloud Run path early enough to expose
   deployment defects;
7. finish remaining lifecycle mechanics and submission assets;
8. perform interaction polish only after the judged mechanics are stable.

## Product boundary the frontend must preserve

The browser is a consumer of Agent Col's application contracts. It is not a
second agent, a persistence authority, or a direct model client.

The intended boundary is:

```text
User
  -> same-origin browser workspace
  -> FastAPI application
  -> authenticated identity and workspace resolution
  -> chat-turn claim / deterministic structured decision
  -> Agent Col routing and at most one major capability
  -> deterministic effect persistence
  -> responder-only final response
  -> authoritative receipts and canonical read APIs
  -> browser presentation
```

The browser must never:

- call Gemini or Vertex AI directly;
- hold service-account or application credentials;
- invent completion, citation, memory, feedback, or artifact receipts;
- treat model prose as proof that a durable effect occurred;
- trust a user-entered identifier as authenticated identity;
- mutate Firestore directly;
- expose internal IDs as the primary human label;
- merge the chat, navigation drawer, and artifact viewer into one scrolling or
  state-ownership surface.

## Verified implemented frontend surface

| Surface | Current implementation | Review status |
| --- | --- | --- |
| Application shell | Static HTML, CSS, and ES modules served by FastAPI at `/workspace` | Implemented |
| Authentication gate | Local-development mode or Google Identity Services sign-in using a server-advertised OAuth client ID | Implemented locally; production configuration pending |
| Authenticated identity | Google token is verified server-side and mapped to an internal subject; raw subject is not used as the visible workspace alias | Implemented, with response-minimization work remaining |
| Workspace containers | Create, list, select, and isolate workspace-specific chats and artifacts | Implemented foundation |
| Chat | Submit, retry exact idempotent request, render transcript, errors, actions, citations, artifact and memory receipts | Implemented |
| Chat sessions | List and reopen sessions within the active workspace | Implemented foundation |
| Cross-chat recall | No bounded retrieval of unopened prior chats or collaborative notes into a new turn | Not implemented |
| Collaborative notes | No distinct inspectable workspace-note entity or note lifecycle | Not implemented |
| Left drawer | Independently scrollable Workspace, Artifacts, Memory, and Chats sections; collapsed by default | Implemented |
| Center panel | Independently scrollable transcript with composer retained across drawer states | Implemented |
| Artifact viewer | Independently scrollable, hideable, and expandable viewer | Implemented |
| Blueprint artifacts | List, canonical detail, feedback targets, feedback history, and export | Implemented |
| Generic artifacts | Code/document/data creation, canonical detail, original export, constrained alternative export, PDF printing | Implemented |
| Artifact lifecycle | Archive/restore, metadata rename, immutable new versions, lineage | Implemented |
| Memory inspection | Pending proposals, identity context, active preferences, recent events | Implemented for records the backend recognizes |
| Memory decisions | Approve/reject pending proposals; revoke/delete active signals | Implemented |
| Human labels | Code-style categories and long identifiers are generally hidden from primary UI labels | Substantially implemented |

## What is working well and should be preserved

### One coherent collaboration surface

Chat, memory, artifacts, and receipts live in one workspace. The user no longer
has to call a separate synthesis endpoint or inspect Firestore to prove an
artifact exists. Agent Col remains the conversational owner while the browser
loads canonical records from deterministic APIs.

### Independent surfaces

The left drawer, transcript/composer, and artifact viewer have separate
scrolling and expansion behavior. The artifact viewer can occupy most of the
application width without becoming the chat transcript. This matches the
accepted interaction model and should not be regressed during later styling.

### Authoritative receipts

The UI distinguishes response prose from action, artifact, feedback, memory
proposal, citation, and adaptation receipts. This is essential: a friendly
claim such as "I remembered that" is not durable evidence unless the response
also contains the relevant authoritative receipt and the memory read model
shows the proposal or active signal.

### Artifact-aware export

The primary export preserves the canonical artifact format and filename.
Alternative exports are constrained by the stored artifact family/format, and
PDF printing isolates the artifact rather than printing the entire workspace.
This is a sound user-facing contract and should remain artifact-aware.

### Authenticated workspace isolation

Google mode derives identity from a verified token instead of a typed user ID.
The current UI shows a human authentication state rather than the raw Google
subject. Workspace-specific chat and artifact lists are separated while memory
remains user-global, which matches the accepted product decision.

## Frontend gaps and misalignments

### P0: stored chat history is not usable collaborative continuity

The frontend proves that sessions exist and can be reopened, but it does not
give Agent Col a safe way to find relevant prior work from a new chat. The
failure shown in `scrnshot-evidence/pending.png` is decisive: a prior script is
visible in the user's chat archive, yet Agent Col says it has no record of the
prior request.

Four durable domains must remain distinct:

1. **profile memory** — user-global, approved collaboration preferences and
   low-sensitivity identity context;
2. **collaborative workspace notes** — workspace-scoped decisions, task state,
   constraints, and user-approved takeaways that help continue work;
3. **chat archives** — canonical source transcripts organized by session;
4. **cross-chat retrieval receipts** — bounded proof of which prior session or
   note was supplied to the current turn.

The fix must not inject every transcript into every prompt or silently convert
all conversation into permanent memory. A new chat that refers to prior work
needs ownership-checked, bounded retrieval with provenance. If more than one
prior item plausibly matches, Agent Col should ask the user to choose rather
than fabricate recall. The frontend must show retrieved-note/session receipts
and offer inspection, correction, archive, and deletion controls for notes.

### P0: chat-session ownership is not enforced at the mutation boundary

The session list and detail APIs filter by user and workspace. However,
`POST /api/chat` resolves the authenticated user/workspace and then calls
`get_chat_history(session_id)` without first proving that an existing session
belongs to that identity and workspace. The turn-claim and message-save paths
also merge session ownership fields.

This is a source-level authorization gap. A random session ID is not an access
control. Before public deployment, an existing session must be transactionally
validated as owned by the effective authenticated user and workspace before
history is read or ownership metadata is written. Unknown sessions may be
created only for the current principal. Ownership conflicts must fail closed.

### P0: memory presentation cannot compensate for the narrow memory contract

The frontend correctly refreshes and presents persistent memory state, but it
cannot display a proposal the backend refused to create. The current policy
accepts eight enum-based preferences plus preferred name and broad roles. It
does not accept several signals explicitly contemplated by the governing
identity, including development/operating environment, accessibility needs,
learning approach, explanation pace, and approved domain experience.

This produces the most damaging interaction mismatch currently visible:

1. the user asks naturally to remember a useful collaboration preference;
2. Agent Col may acknowledge it conversationally;
3. no pending proposal is created because the category or value is outside the
   strict allowlist;
4. the UI has nothing to approve;
5. a later session correctly lacks that memory.

The frontend should not add a workaround that stores arbitrary text. The
memory policy, normalizer, proposal tool, responder language, and UI controls
must be reconciled as one governed feature sequence.

### P1: memory creation and correction controls are incomplete

The UI supports approve, reject, revoke, and delete. It does not yet provide a
bounded form for adding a supported memory signal or correcting an existing
value through the governed proposal flow. Users should not have to discover an
exact phrase that causes the model to construct a valid proposal.

Required behavior:

- a UI add action produces a pending proposal, never an immediately active
  signal;
- edit/correct creates a replacement proposal with provenance;
- the old value remains active until the replacement is approved;
- approve/reject/revoke/delete remain explicit;
- human labels are used throughout;
- raw category keys and signal/event IDs stay out of primary labels.

### P1: artifact family and format controls can represent invalid pairs

The manual Create Artifact form exposes family and format as independent
static selects. The backend correctly rejects invalid family/format pairs, but
the UI can present combinations such as Data + Python. The format choices must
be derived from the selected family using the same accepted contract as the
backend. This is a core contract-wiring defect, not aesthetic polish.

### P1: chat-session lifecycle controls are incomplete

Sessions can be listed and reopened, but cannot be renamed, archived, restored,
or deleted. Current titles are derived from message previews and can be too
long. The remaining mechanics require durable human-readable titles and
explicit lifecycle APIs; client-only renaming would be misleading.

### P1: workspace lifecycle controls are incomplete

Workspaces can be created and selected. Rename, archive, restore, and delete
are not implemented. There is also no shared membership or role model. The
current single-owner model is acceptable for the judged single-user MVP, but
the UI must not imply multi-user workspace collaboration.

### P1: generic artifacts lack the blueprint feedback lifecycle

Blueprints have target-scoped accepted/rejected/edited feedback and
supersession. Generic code/document/data artifacts do not. Archive, rename, and
versioning provide useful lifecycle mechanics, but they are not a substitute
for explicit review feedback if generic artifacts are meant to participate in
the same collaborative learning loop.

### P1: authentication lifecycle is incomplete

The sign-in gate works locally with a configured Google web client. Remaining
core behavior includes logout/session reset, production OAuth client
configuration, hosted origin verification, and account/data-retention
behavior. The auth session API should also return only the minimum public
identity data the frontend needs; the UI hiding a field is weaker than the
server not transmitting it.

### P2: product copy still overemphasizes blueprints

The central introduction still tells users to create a "structured blueprint"
even though the product supports general conversation and generic code,
document, and data artifacts. That copy reinforces the exact identity drift the
governing document warns against. It should describe Agent Col as a general
collaborative partner and present artifacts as one optional outcome.

### P2: chat rendering remains mechanically correct but conversationally raw

The transcript preserves text safely, but model Markdown is displayed as raw
syntax in several cases. A constrained renderer could improve readability
later, but it must not precede the memory and ownership work or introduce an
unsafe HTML boundary.

### P2: stale labels and modules remain

Some internal and historical names still reflect earlier concepts, including
the obsolete Activity view module and older project-oriented wording. These
should be consolidated only after the mechanics stabilize; a broad cleanup
now would add risk without improving the judged workflow.

## Revised frontend development sequence

### Phase F1 — Continuity and governed-memory contract reconciliation

#### F1.0: continuity-domain design

- define profile memory, workspace notes, chat archives, and retrieval receipts
  as separate authorities;
- define what Agent Col may propose as a note, what requires explicit approval,
  and what remains session-only;
- define bounded cross-chat retrieval, ambiguity behavior, provenance, and
  content limits;
- prohibit unbounded transcript injection and unverified claims of recall;
- define the UI read, review, correction, archive, and deletion contracts for
  collaborative notes.

#### F1.1: memory scope and natural-request contract design

- reconcile the governing identity's safe memory categories with the current
  strict policy;
- define bounded normalized values for new categories rather than accepting
  arbitrary durable profile text;
- specify how natural phrases map to one candidate without requiring magic
  words;
- define truthful responder behavior for supported, ambiguous, and unsupported
  requests;
- preserve explicit proposal and approval gates.

#### F1.2: memory policy and persistence evolution

- introduce a versioned policy/schema migration path;
- add approved bounded categories and normalization aliases;
- preserve existing active signals and event provenance;
- test correction, supersession, revocation, deletion, and cross-version reads.

#### F1.3: proposal routing and responder truthfulness

- accept ordinary requests such as "save", "remember", "keep", "use this
  preference", and equivalent natural phrasing;
- distinguish a durable request from a session-only statement;
- propose at most one bounded signal per turn;
- ask a useful clarification only when the candidate is genuinely ambiguous;
- never claim durable memory without a completed proposal receipt.

#### F1.4: memory add/edit/correct UI

- add a bounded Add memory control;
- add Edit/Correct to active identity and preference cards;
- route every change through pending proposal review;
- retain approve/reject/revoke/delete controls;
- refresh canonical memory state after completed effects.

#### F1.5: cross-session proof and closure

- create, approve, and apply each new representative memory class;
- verify it in a genuinely new session and, where relevant, a different
  workspace;
- prove revoked/deleted values stop adapting later responses;
- verify receipts and UI state agree.

### Phase F2 — Session ownership correction

- enforce authenticated user/workspace ownership before chat history reads;
- atomically create or validate session ownership during turn claim;
- reject cross-owner reuse without exposing existence;
- preserve idempotent replay for the rightful owner;
- add local and Google-mode integration tests.

This phase is mandatory before any hosted/public test.

It is also mandatory before cross-chat retrieval. Expanding retrieval before
fixing ownership would amplify the current authorization gap across sessions.

### Phase F3 — Collaborative notes and cross-chat recall

#### F3.1: durable collaborative-note boundary

- add workspace-scoped, owner-bound note records with source-session/message
  provenance;
- support pending/active/corrected/archived/deleted lifecycle states;
- keep project facts and decisions out of user-global profile memory;
- expose bounded list/detail and lifecycle APIs.

#### F3.2: bounded continuity retrieval

- retrieve only ownership-validated relevant notes or prior sessions when the
  user refers to prior work;
- supply compact server-owned context rather than raw unbounded transcripts;
- return application-derived retrieval receipts;
- ask a useful clarification on ambiguous matches;
- never claim recall without a matching retrieved source.

#### F3.3: continuity UI and live proof

- add a human-readable Notes surface without exposing storage identifiers;
- show which prior chat or note informed a response;
- allow users to inspect, correct, archive, and delete notes;
- prove in a fresh chat that Agent Col can identify the prior script, decision,
  or task from the same workspace and cannot retrieve another workspace or
  user's content.

### Phase F4 — Durable asynchronous workflow

- promote one heavy, already-bounded workflow such as synthesis/artifact
  generation to a durable job boundary;
- persist queued, running, completed, failed, and cancelled states;
- use an authenticated Cloud Tasks worker or an equivalently durable Google
  Cloud execution boundary;
- preserve idempotency so retries cannot duplicate effects;
- add status/resume/cancel UI without making every ordinary chat turn async;
- prove that work survives client disconnect or request termination.

### Phase F5 — Early hosted deployment and security proof

- configure the production Google OAuth client and hosted origin;
- add Cloud Run container/runtime configuration;
- deploy an authenticated baseline before final UI polish;
- verify ownership, idempotency, artifacts, memory, notes, and job status on the
  hosted URL;
- capture Cloud Run and Vertex AI runtime evidence for the demo.

### Phase F6 — Core lifecycle completion

#### F6.1: chat lifecycle

- short durable titles;
- rename;
- archive/restore;
- delete with explicit confirmation and documented retention behavior.

#### F6.2: workspace lifecycle

- rename;
- archive/restore;
- delete only with an explicit, documented child-data policy;
- preserve global user memory unless separately deleted.

#### F6.3: artifact contract completion

- filter manual format options by family;
- decide and implement generic-artifact feedback parity;
- add deletion only after retention and lineage behavior is defined;
- preserve original-format and PDF export behavior.

### Phase F7 — Submission closure and interaction polish

- replace blueprint-centric introductory copy;
- render a safe subset of Markdown;
- improve empty/loading/error states;
- refine chat, artifact, workspace, and memory titles;
- keyboard, responsive, and accessibility review;
- remove obsolete UI modules only with regression coverage;
- update the README with exact local and Cloud Run spin-up instructions;
- update the architecture diagram to the deployed system;
- prepare submission descriptions for features, technologies, data sources,
  findings, and learnings;
- prepare a four-minute demo path covering the problem, value, continuity,
  adaptation, async work, and live Google Cloud evidence.

## Remaining frontend checklist

### Must complete before public deployment

- [ ] Define separate governed contracts for profile memory, workspace notes,
  chat archives, and cross-chat retrieval.
- [ ] Prove bounded prior-chat recall with source/receipt evidence in a fresh
  chat.
- [ ] Reconcile governed-memory categories with the authoritative product
  identity.
- [ ] Normalize natural durable-memory requests without weakening approval.
- [ ] Add memory add/edit/correct controls through pending proposals.
- [ ] Prove new, corrected, revoked, and deleted memory across sessions.
- [ ] Enforce chat-session ownership before history read or session mutation.
- [ ] Add logout and safe authenticated-session reset.
- [ ] Configure and verify the production Google OAuth client/origin.
- [ ] Prevent invalid artifact family/format selections in the UI.
- [ ] Add Cloud Run build/runtime configuration and hosted security checks.
- [ ] Define retention and deletion behavior for user, workspace, chat, memory,
  and artifact data.
- [ ] Restore a fully green required test baseline.
- [ ] Add one durable background workflow with job status, retry safety, and
  authenticated worker execution.
- [ ] Deploy an authenticated Cloud Run baseline and capture hosted runtime
  evidence.

### Core mechanics for the judged workspace

- [ ] Add collaborative note inspection, correction, archive, and deletion.
- [ ] Surface human-readable prior-chat/note retrieval receipts.
- [ ] Add chat rename/archive/restore/delete contracts and controls.
- [ ] Add workspace rename/archive/restore/delete contracts and controls.
- [ ] Decide and implement generic artifact feedback parity or document its
  deliberate exclusion from the judged loop.
- [ ] Add bounded artifact deletion only if lineage and retention permit it.
- [ ] Ensure all primary labels are human-readable and identifiers are
  secondary/debug-only.
- [ ] Keep memory global per authenticated user and chats/artifacts scoped to
  the selected workspace.

### Polish after mechanics

- [ ] Replace blueprint-centric workspace guidance with general collaboration
  language.
- [ ] Render safe Markdown without allowing generated HTML execution.
- [ ] Refine compact titles and secondary metadata.
- [ ] Complete keyboard, focus, responsive, and accessibility verification.
- [ ] Consolidate obsolete frontend modules and oversized coordinators through
  tested refactors.

### Explicitly deferred

- [ ] PNG/JPEG and generated-image artifacts, pending a separate image
  generation design.
- [ ] Multi-file repositories or archive bundles.
- [ ] Native desktop packaging; the same-origin browser is the correct current
  Cloud Run/hackathon delivery surface.
- [ ] Deep Research or additional experts until the core judged workflow is
  reliable and deployed.
- [ ] Real-time streaming, WebSockets, and notifications. Durable background
  job status is no longer deferred because the supplied hackathon brief makes
  beyond-chat asynchronous operation part of the judged product direction.

## Manual acceptance standard for the revised frontend

The frontend is ready for submission only when a reviewer can:

1. sign in without seeing or entering an internal identity token;
2. create/select a private workspace;
3. converse naturally without a prompt guide;
4. create and reopen a chat;
5. refer naturally to work in a different prior chat and receive an accurate,
   provenance-backed answer or a useful ambiguity clarification;
6. inspect, correct, archive, and delete a collaborative note without changing
   global profile memory;
7. create a generic code/document/data artifact and retrieve its original
   file;
8. inspect, export, rename, archive/restore, and version that artifact;
9. state a supported collaboration preference naturally, receive a pending
   proposal, approve it, and observe the adaptation in a new session;
10. correct, revoke, and delete that memory using visible controls;
11. submit one durable background task, leave or disconnect, and later observe
    its authoritative completed or failed state without a duplicate effect;
12. see no false durable-memory, note, recall, artifact, citation, job, or
    action claim;
13. remain unable to access another authenticated user's session, workspace,
    artifact, or memory;
14. complete the main workflow on the hosted Cloud Run URL with bounded,
    understandable failure behavior.

## Recommended next pass

**M9-CONT.1 — Continuity Domain and Collaborative Notes Design**

This should be a design-only pass that separates governed profile memory,
workspace collaborative notes, canonical chat archives, and bounded cross-chat
retrieval receipts. It must incorporate the planned memory-scope and natural-
request reconciliation, define the security dependency on session ownership,
and specify the smallest UI proof for notes and prior-work recall. It must not
solve continuity by injecting all transcripts or permitting arbitrary
unstructured durable memory. Implementation should remain split into
separately accepted TDD passes after the contract is approved.
