# Agent Col Winning Core Final Checklist

## Status and authority

This checklist records the approved Winning Core direction as of August 25,
2026. It is a roadmap and alignment document. It does not authorize any source
change described by a pending phase plan.

Implementation remains governed by:

- [`AGENTS.md`](../AGENTS.md);
- [`AGENT_COL_IDENTITY_AND_ALIGNMENT.md`](../AGENT_COL_IDENTITY_AND_ALIGNMENT.md);
- [`DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`](../DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md).

Every phase below requires its own investigation, bounded implementation plan,
explicit user approval, test-driven implementation, focused automated
verification, manual acceptance, and GitHub checkpoint. Phases execute
sequentially. No parallel implementation is authorized.

## Product north star

> Agent Col is a persistent collaborative partner that grows with the user,
> takes governed notes, and carries authorized work to completion while
> remaining inspectable and user-controlled.

The judged experience must prove adaptation, continuity, collaboration,
authorized action, and production discipline without describing explicit
feedback-driven adaptation as secret learning or background work as hidden
autonomy.

## Approved path

The approved Winning Core path is:

1. finish clarification UI and judge-grade cross-session memory proof;
2. complete governed workspace notes using the existing continuity design;
3. add one durable asynchronous artifact workflow with inspectable states;
4. harden ownership and limits, containerize, and deploy to Cloud Run;
5. reconcile documentation and produce reproducibility and submission evidence;
6. rehearse the four-minute demo, prove controlled failure behavior, complete
   submission materials, and freeze the judged build.

PDF upload is optional. Pasted messy text is the required ingestion boundary.
PDF work may begin only after every Winning Core phase is accepted and stable
with sufficient schedule margin.

## Locked architectural decisions

- [x] Category: Collaborative Partner.
- [x] Gemini 3.6 Flash through Vertex AI.
- [x] Google ADK and Google GenAI SDK.
- [x] Firestore is the durable source of truth.
- [x] Google OIDC is the hosted identity boundary.
- [x] Profile memory and workspace notes remain separate domains.
- [x] Memory, notes, jobs, and artifacts remain application-governed side
  effects; the model cannot write arbitrary Firestore fields.
- [x] Agent Col remains the sole user-facing responder.
- [x] Build one bounded asynchronous artifact workflow, not a general-purpose
  task engine or unrestricted planner.
- [x] Work proceeds sequentially through Phases 1-6.
- [x] Versioned public memory lifecycle checkpoint:
  `0c3a16d Complete versioned memory lifecycle`.

## Phase plan index

Each planned document below must begin with **Status: Pending approval**. A plan
reference does not authorize implementation. Plans will be created and
approved one phase at a time so they can be reconciled against the accepted
source baseline produced by the preceding phase.

1. **Phase 1 - Memory Continuity Closure**
   - Planned file:
     `docs/superpowers/plans/2026-08-25-winning-core-phase-1-memory-continuity.md`
   - Status: not created; pending planning approval.
2. **Phase 2 - Governed Workspace Notes**
   - Planned file:
     `docs/superpowers/plans/2026-08-25-winning-core-phase-2-workspace-notes.md`
   - Status: not created; pending Phase 1 acceptance and planning approval.
3. **Phase 3 - Durable Asynchronous Artifact Work**
   - Planned file:
     `docs/superpowers/plans/2026-08-25-winning-core-phase-3-async-artifact-work.md`
   - Status: not created; pending Phase 2 acceptance and planning approval.
4. **Phase 4 - Production Hardening and Deployment**
   - Planned file:
     `docs/superpowers/plans/2026-08-25-winning-core-phase-4-production-deployment.md`
   - Status: not created; pending Phase 3 acceptance and planning approval.
5. **Phase 5 - Reproducibility and Submission Evidence**
   - Planned file:
     `docs/superpowers/plans/2026-08-25-winning-core-phase-5-reproducibility-evidence.md`
   - Status: not created; pending Phase 4 acceptance and planning approval.
6. **Phase 6 - Demo and Build Freeze**
   - Planned file:
     `docs/superpowers/plans/2026-08-25-winning-core-phase-6-demo-freeze.md`
   - Status: not created; pending Phase 5 acceptance and planning approval.

Every phase plan must define its verified baseline commit, dependencies,
user-visible outcome, architecture and data flow, exact expected file boundary,
preserved invariants, RED-GREEN-REFACTOR tasks, focused verification, manual
acceptance targets, exclusions, risks, stop conditions, and handoff evidence.

## Phase 1 - Memory Continuity Closure

- [ ] Render durable clarification choices in the browser workspace.
- [ ] Allow one valid choice to create exactly one pending memory proposal.
- [ ] Prevent clarification and proposal effects from coexisting in one turn.
- [ ] Preserve choices through retry, replay, timeout, and responder failure.
- [ ] Approve a natural version-two proposal through the UI.
- [ ] Begin a genuinely new chat session and demonstrate adapted behavior.
- [ ] Display an authoritative adaptation receipt and provenance.
- [ ] Verify rejection, correction, revocation, and deletion.
- [ ] Capture judge-grade live evidence.

**Exit condition:** A user can teach Agent Col an eligible preference, approve
it, observe a changed response in another session, inspect why Agent Col
adapted, and remove or correct the preference.

## Phase 2 - Governed Workspace Notes

- [ ] Complete note persistence using the approved continuity boundary.
- [ ] Propose one bounded workspace note from the current user message.
- [ ] Require user review before activation.
- [ ] Support approval, rejection, correction, archive, restore, and deletion.
- [ ] Preserve source-session and source-message provenance.
- [ ] Enforce authenticated user and workspace ownership.
- [ ] Project only bounded active notes into Agent Col context.
- [ ] Add bounded note retrieval and application-derived retrieval receipts.
- [ ] Support bounded immediately-previous-chat retrieval.
- [ ] Clarify ambiguous retrieval instead of guessing.
- [ ] Add a complete Notes UI with observable lifecycle states.

**Exit condition:** Agent Col visibly takes useful, user-approved workspace
notes without confusing workspace knowledge with global profile preferences or
silently persisting conversation.

## Phase 3 - Durable Asynchronous Artifact Work

- [ ] Select one artifact-generation workflow as the only asynchronous flow.
- [ ] Create an inspectable Firestore job before execution.
- [ ] Implement `queued`, `running`, `completed`, `failed`, and `cancelled`.
- [ ] Persist user, workspace, session, originating request, and artifact
  relationships.
- [ ] Enforce idempotent submission, execution, completion, and retry.
- [ ] Enqueue work through Google Cloud Tasks.
- [ ] Authenticate Cloud Tasks to a private worker.
- [ ] Provide safe cancellation and retry where the operation permits them.
- [ ] Persist verified completion and failure receipts.
- [ ] Display job progress, result, retry, and cancellation controls.
- [ ] Demonstrate one controlled failure and successful retry.

**Exit condition:** A user can authorize work, leave the request, inspect its
durable progress, and receive one verified result without duplication or
hidden execution.

## Phase 4 - Production Hardening and Deployment

- [ ] Audit ownership for workspaces, sessions, memory, notes, artifacts,
  feedback, and jobs.
- [ ] Fail closed on cross-user and cross-workspace access.
- [ ] Enforce text, request, and artifact-size limits.
- [ ] Add bounded request-rate limiting and security headers.
- [ ] Verify logs exclude prompts, notes, profile values, feedback, and
  artifact content.
- [ ] Define and document retention and deletion behavior.
- [ ] Pin the production Python runtime.
- [ ] Add a Dockerfile and production startup command.
- [ ] Configure service accounts, IAM, Firestore indexes, and Cloud Tasks OIDC.
- [ ] Configure Cloud Run maximum instances, timeouts, and budget controls.
- [ ] Deploy the public API/UI and private worker.
- [ ] Run hosted authentication, ownership, failure, and smoke checks.

**Exit condition:** The judged build runs consistently on Google Cloud and no
public route depends on local-development trust assumptions.

## Phase 5 - Reproducibility and Submission Evidence

- [ ] Reconcile `README.md`, architecture, local setup, testing, integration
  inventory, identity status, and submission checklist.
- [ ] Document every environment variable without publishing credentials.
- [ ] Provide exact local and Cloud Run spin-up instructions.
- [ ] Update the architecture diagram to include Gemini, ADK, Firestore,
  Cloud Tasks, OIDC, the public service, and the private worker.
- [ ] Run the complete relevant suite from a clean clone.
- [ ] Run a hosted end-to-end smoke test.
- [ ] Audit Git history and ignored files for credentials and generated data.
- [ ] Audit dependencies, fonts, icons, libraries, and media licensing.
- [ ] Capture judge-readable Cloud Run, Firestore, and Cloud Tasks evidence.

**Exit condition:** A judge can understand, reproduce, run, and verify the
actual submitted system from the repository and hosted evidence.

## Phase 6 - Demo and Build Freeze

- [ ] Demonstrate approved profile learning and new-session adaptation.
- [ ] Demonstrate a governed workspace note.
- [ ] Demonstrate a consequential clarification.
- [ ] Start and inspect asynchronous artifact work.
- [ ] Show feedback producing an improved artifact.
- [ ] Show controlled failure handling or retry.
- [ ] Show Firestore, Cloud Tasks, Cloud Run, and hosted URL proof.
- [ ] Keep the final video four minutes or shorter.
- [ ] Complete the Devpost description, technologies, learnings, links, and
  disclosures.
- [ ] Freeze the judged build by August 30, 2026.
- [ ] Submit before August 31, 2026, at 5:00 PM Pacific.

**Exit condition:** The repository, hosted build, cloud evidence, video, and
submission text tell one truthful and reproducible Collaborative Partner story.

## Existing design and planning references

- [Continuity and collaborative notes design](superpowers/specs/2026-08-24-m9-cont-1-continuity-domain-and-collaborative-notes-design.md)
- [Collaborative note model plan](superpowers/plans/2026-08-24-m9-note-1a-collaborative-note-proposal-active-projection-models.md)
- [Judge-facing collaborative artifact loop](superpowers/specs/2026-08-23-m8-col-1-judge-facing-collaborative-artifact-loop-design.md)
- [Browser workspace design](superpowers/specs/2026-08-23-phase-4a-lightweight-browser-workspace-design.md)
- [Hybrid ADK supervisor contract](superpowers/specs/2026-08-19-hybrid-adk-supervisor-contract-design.md)
- [Submission checklist](submission-checklist.md)
- [Architecture](architecture.md)
- [Local development setup](development/local-setup.md)

Current executable source remains authoritative when an older design or status
document differs from implemented behavior. Every new phase plan must compare
its assumptions with the source and accepted checkpoint before implementation.

## Local environment and authentication modes

The ignored repository `.env` was updated on August 25, 2026, to include the
public Google OAuth web client identifier used by the browser sign-in flow:

```dotenv
GOOGLE_OAUTH_CLIENT_ID=994154906699-jh6jkqprffr941im0mhq09efa3kj2p0a.apps.googleusercontent.com
```

The OAuth client ID is public configuration, not a client secret. The `.env`
file remains ignored by Git and is not included in this checkpoint. Do not add
an OAuth client secret, service-account key, access token, or ADC credential to
the repository.

Vertex AI and Firestore use Google Application Default Credentials separately
from browser OIDC. Before either launch mode, the local machine must have valid
ADC and the correct quota project configured.

### Local development authentication

From the repository root, run:

```bash
AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app \
  --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/workspace
```

This mode intentionally uses local-development identity behavior and must not
be exposed publicly.

### Google OIDC authentication

Ensure the OAuth client's authorized JavaScript origins include the exact
local origin used below. Then run from the repository root:

```bash
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app \
  --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/workspace
```

The browser obtains a Google ID token for the configured OAuth client. The API
verifies that token and derives the effective user and private workspace
identity from verified claims.

## Scope guardrails

- No generalized autonomous planner.
- No arbitrary multi-tool chain or unrestricted Firestore write.
- No silent profile-memory or workspace-note activation.
- No semantic transcript indexing or vector database in the Winning Core.
- No completion notification unless derived from verified persisted state.
- No PDF upload work before all six core phases are accepted and stable.
- No unrelated redesign or speculative capability expansion.
- No checkpoint for source behavior before required manual acceptance.
- No contest claim without observable application and Google Cloud evidence.

## Phase completion record

Update this table only after the corresponding pass has been manually accepted
and checkpointed.

| Phase | Status | Accepted checkpoint | Evidence location |
| --- | --- | --- | --- |
| 1. Memory Continuity Closure | Pending plan | - | - |
| 2. Governed Workspace Notes | Pending plan | - | - |
| 3. Durable Asynchronous Artifact Work | Pending plan | - | - |
| 4. Production Hardening and Deployment | Pending plan | - | - |
| 5. Reproducibility and Submission Evidence | Pending plan | - | - |
| 6. Demo and Build Freeze | Pending plan | - | - |
