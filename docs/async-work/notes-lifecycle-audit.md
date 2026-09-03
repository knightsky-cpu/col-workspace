# Notes Lifecycle Audit

This document records the current collaborative notes lifecycle in Agent Col,
with source evidence for each boundary. It is intended to keep the async-work
goal concrete while the system moves toward true independent background work.

## Target Lifecycle

Notes should be workspace-scoped durable collaboration context. Creating,
reviewing, approving, rejecting, correcting, archiving, restoring, and deleting
notes should not depend on Agent Col chat response generation.

The desired async model is:

- Agent Col can accept an explicit workspace-note request and queue a Note
  Curator job before or alongside model routing.
- The Note Curator job creates a pending note proposal independently.
- The user reviews note proposals through the Notes UI.
- Note approval or rejection is a direct Notes lifecycle action, not a chat
  turn side effect.
- Notes UI operations remain available while chat is streaming or while other
  background agents are working.
- Note jobs can run beside memory jobs and artifact jobs without one durable
  surface blocking the others.

## Current Direct Notes UI Lifecycle

The direct UI lifecycle is mostly decoupled from chat today.

### Frontend Entry Points

`frontend/app.mjs` handles note decisions, corrections, proposal creation, and
lifecycle mutations with direct Notes API calls:

- `submitCollaborativeNoteDecision` starts at
  `frontend/app.mjs:2024`.
- `createCollaborativeNoteCorrection` starts at
  `frontend/app.mjs:2050`.
- `createCollaborativeNoteProposal` starts at
  `frontend/app.mjs:2077`.
- `changeCollaborativeNoteLifecycle` starts at
  `frontend/app.mjs:2106`.

Example evidence:

```text
frontend/app.mjs:2024 async function submitCollaborativeNoteDecision(decision) {
frontend/app.mjs:2032   await decideNoteProposal(...)
frontend/app.mjs:2040   await loadNotes(state.notes.statusFilter);
frontend/app.mjs:2041   loadAgentJobReports();
frontend/app.mjs:2042   loadAgentJobs();
```

```text
frontend/app.mjs:2077 async function createCollaborativeNoteProposal(request) {
frontend/app.mjs:2085   const response = await createNoteProposal(...)
frontend/app.mjs:2097   state = completeNoteRequest(storePendingNoteProposal(state, response.proposal));
frontend/app.mjs:2098   await loadNotes();
```

These paths call direct API helpers from `frontend/api.mjs`:

- `decideNoteProposal` at `frontend/api.mjs:750`.
- `listNotes` at `frontend/api.mjs:891`.
- `getNote` at `frontend/api.mjs:911`.
- `createNoteCorrection` at `frontend/api.mjs:929`.
- `createNoteProposal` at `frontend/api.mjs:953`.
- `archiveNote` at `frontend/api.mjs:975`.
- `restoreNote` at `frontend/api.mjs:994`.
- `deleteNote` at `frontend/api.mjs:1013`.

### UI Pending State

The Notes panel is guarded by the Notes subsystem's own pending flag, not the
chat turn pending flag.

Source evidence:

```text
frontend/state.mjs:1624 export function beginNoteRequest(state, requestId) {
frontend/state.mjs:1629       pendingRequest: requestId,
```

```text
frontend/state.mjs:1635 export function completeNoteRequest(state) {
frontend/state.mjs:1640       pendingRequest: null,
```

```text
frontend/notes-view.mjs:352 export function renderNotesPanel(...)
frontend/notes-view.mjs:366   const disabled = state.pendingRequest !== null;
frontend/notes-view.mjs:383   renderNoteProposalForm(container, disabled, handlers);
```

This is an important positive async property: direct Notes UI actions are not
disabled by `state.pendingTurn`.

## Current Direct Notes Backend Lifecycle

`main.py` exposes direct Notes routes outside `/api/chat`.

Source evidence:

```text
main.py:2604 @app.get("/api/users/{user_id}/projects/{project_id}/notes")
main.py:2661 @app.get("/api/users/{user_id}/projects/{project_id}/notes/{note_id}")
main.py:2712 @app.post("/api/users/{user_id}/projects/{project_id}/notes/proposals")
main.py:2775 @app.post("/api/users/{user_id}/projects/{project_id}/notes/proposals/{proposal_id}/{decision}")
main.py:2830 @app.post("/api/users/{user_id}/projects/{project_id}/notes/{note_id}/corrections")
main.py:2949 @app.post("/api/users/{user_id}/projects/{project_id}/notes/{note_id}/archive")
main.py:2975 @app.post("/api/users/{user_id}/projects/{project_id}/notes/{note_id}/restore")
main.py:3001 @app.delete("/api/users/{user_id}/projects/{project_id}/notes/{note_id}")
```

The direct proposal route requires an `Idempotency-Key` header before calling
the note service:

```text
main.py:2725 idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")]
main.py:2730 if idempotency_key is None:
main.py:2753 result = await request.app.state.collaborative_note_service.create_proposal(...)
```

The direct decision route calls `CollaborativeNoteService.decide_proposal`,
then returns the resulting action, note, and event:

```text
main.py:2801 result = await request.app.state.collaborative_note_service.decide_proposal(...)
main.py:2819 return _public_collaborative_note_decision_response(...)
```

## Note Service Lifecycle

The service layer is `collaborative_note_service.py`.

### Direct UI Proposal Creation

`CollaborativeNoteService.create_proposal` creates a synthetic source message,
then creates a pending note proposal.

Source evidence:

```text
collaborative_note_service.py:198 async def create_proposal(...)
collaborative_note_service.py:202   source_text = f"Create note proposal: {command.title}\n\n{command.body}"
collaborative_note_service.py:205   source_message_id = await self._database.save_message(...)
collaborative_note_service.py:212   proposal = await self._database.create_collaborative_note_proposal(...)
```

This is a storage/provenance coupling to chat session messages. It is not chat
response coupling, but the source message still lives in the chat message store.

### Natural Agent Proposal Creation

`CollaborativeNoteService.create_natural_proposal` handles model/tool and
background worker proposal creation.

Source evidence:

```text
collaborative_note_service.py:227 async def create_natural_proposal(...)
collaborative_note_service.py:231   if command.memory_decision_present ...
collaborative_note_service.py:239   if not isinstance(command.decision, NoteCandidateDecision):
collaborative_note_service.py:241   validate_note_candidate_evidence(...)
collaborative_note_service.py:245   idempotency_key = command.turn_lease.turn_id if command.turn_lease is not None else command.source_message_id
collaborative_note_service.py:250   proposal = await self._database.create_collaborative_note_proposal(...)
```

If the command has a turn lease, the note proposal can be recorded as a chat
turn durable effect. If it does not have a turn lease, it creates only the
pending note proposal.

### Approval, Rejection, and Lifecycle

Approval and rejection are service calls over the note proposal state:

```text
collaborative_note_service.py:272 async def decide_proposal(...)
collaborative_note_service.py:280   if command.decision == "approve":
collaborative_note_service.py:281       note, event = await self._database.approve_collaborative_note_proposal(...)
collaborative_note_service.py:292   event = await self._database.reject_collaborative_note_proposal(...)
```

Archive, restore, and delete are direct note lifecycle commands:

```text
collaborative_note_service.py:304 async def archive_note(...)
collaborative_note_service.py:317 async def restore_note(...)
collaborative_note_service.py:330 async def delete_note(...)
```

## Database Persistence Lifecycle

The persistence boundary is `database.py`.

### Pending Proposal Creation

`create_collaborative_note_proposal` validates identifiers, source messages,
idempotency, proposal state, pending proposal limits, and optional chat turn
ownership.

Source evidence:

```text
database.py:810 async def create_collaborative_note_proposal(...)
database.py:830 if not 1 <= len(source_message_ids) <= 5:
database.py:834 normalized_title = validate_note_storage_text(title)
database.py:835 normalized_body = validate_note_storage_text(body)
database.py:836 ids = derive_note_proposal_ids(...)
database.py:848 proposal = CollaborativeNoteProposal(...)
database.py:947 pending_count = await self._count_query_results(...)
database.py:952 if pending_count >= 10:
database.py:970 transaction.set(proposal_ref, proposal.model_dump(mode="python"))
```

If a turn lease is provided, the same transaction may also update the chat turn:

```text
database.py:956 effect = self._collaborative_note_proposal_turn_effect_update(...)
database.py:971 if turn_ref is not None and effect is not None:
database.py:972     transaction.set(turn_ref, effect, merge=True)
```

### Approval

Approval materializes a pending proposal as an active collaborative note. It
handles both new-note approval and correction approval.

Source evidence:

```text
database.py:990 async def approve_collaborative_note_proposal(...)
database.py:1026 if proposal.status != "pending":
database.py:1030 if proposal.expires_at <= observed_at:
database.py:1042 note_collection = workspace_ref.collection("collaborative_notes")
database.py:1098 note = CollaborativeNote(...)
database.py:1113 event = CollaborativeNoteEvent(...)
database.py:1132 transaction.set(proposal_ref, proposal_document, merge=False)
database.py:1133 transaction.set(note_ref, note.model_dump(mode="python"), merge=False)
```

The active note limit is enforced for new active notes:

```text
database.py:1088 active_count = await self._count_query_results(...)
database.py:1093 if active_count >= 50:
database.py:1095     "Collaborative note active limit reached."
```

### Old Chat-Turn Durable Effect Restriction

The optional chat turn effect update still contains an old one-durable-effect
restriction.

Source evidence:

```text
database.py:4162 def _collaborative_note_proposal_turn_effect_update(...)
database.py:4224 if (
database.py:4225     turn_data.get("memory_proposals")
database.py:4226     or turn_data.get("memory_clarifications")
database.py:4227     or turn_data.get("artifacts")
database.py:4228     or turn_data.get("artifact_feedback")
database.py:4229     or turn_data.get("collaborative_note_events")
database.py:4231     raise ChatTurnStateError("Stored chat turn has another durable effect.")
```

This matters only for chat-turn-owned note effects. Queue-first Note Curator
jobs restore without a turn lease, so they avoid this old invariant.

## Queue-First Agent Note Lifecycle

Explicit note requests in Agent Col now have a durable prequeue path.

### Explicit Note Extraction

`AgentColTurnService._explicit_workspace_note_command` detects explicit
workspace-note syntax and turns it into a note candidate.

Source evidence:

```text
agent_col_turn_service.py:416 def _explicit_workspace_note_command(...)
agent_col_turn_service.py:422   match = _EXPLICIT_WORKSPACE_NOTE_STATING.search(command.message)
agent_col_turn_service.py:425   body = match.group("body").strip()
agent_col_turn_service.py:426   boundary = _EXPLICIT_WORKSPACE_NOTE_BOUNDARY.search(body)
agent_col_turn_service.py:431   decision = NoteCandidateDecision(...)
agent_col_turn_service.py:443   return NaturalCollaborativeNoteCommand(...)
```

This path sets `accepted_action_index`, which is part of the queued job digest.

### Durable Action Queueing

`AgentColTurnService._queue_explicit_durable_actions` queues artifact, note,
and memory durable work in order.

Source evidence:

```text
agent_col_turn_service.py:925 async def _queue_explicit_durable_actions(...)
agent_col_turn_service.py:953 note_command = _explicit_workspace_note_command(...)
agent_col_turn_service.py:958 if note_command is not None and self._note_queue is not None:
agent_col_turn_service.py:959     queued_actions.append(await self._note_queue.queue(note_command))
```

### App-Level Queue Wiring

`main.py` wires the note job worker and queue adapter.

Source evidence:

```text
main.py:2067 note_job_worker = CollaborativeNoteProposalJobWorker(...)
main.py:2071 note_job_background_tasks: set[asyncio.Task[AgentJob | None]] = set()
main.py:2073 def dispatch_note_job(job: AgentJob) -> None:
main.py:2074     note_job_worker.dispatch(job, task_set=note_job_background_tasks)
main.py:2079 class CollaborativeNoteQueue:
main.py:2081     queued_action = await queue_collaborative_note_agent_job(...)
main.py:2090     if queued_job is not None:
main.py:2091         dispatch_note_job(queued_job)
```

This is good for async: a queued note job is dispatched as a background task
without waiting for the chat response to complete.

### Queued Job Identity

`collaborative_note_tool.py` builds the durable job ID from user, workspace,
session, source message, turn ID, accepted action index, note kind, title, and
body.

Source evidence:

```text
collaborative_note_tool.py:209 def _note_job_digest(...)
collaborative_note_tool.py:213 command.user_id
collaborative_note_tool.py:214 command.workspace_id
collaborative_note_tool.py:215 command.session_id
collaborative_note_tool.py:216 command.source_message_id
collaborative_note_tool.py:217 turn_id
collaborative_note_tool.py:218 str(command.accepted_action_index) ...
collaborative_note_tool.py:221 command.decision.note_kind
collaborative_note_tool.py:222 command.decision.title
collaborative_note_tool.py:223 command.decision.body
```

The public queue helper returns the queued action receipt:

```text
collaborative_note_tool.py:338 async def queue_collaborative_note_agent_job(...)
collaborative_note_tool.py:343 queued = await _queue_note_agent_job(...)
collaborative_note_tool.py:347 return queued.to_queued_action_receipt()
```

## Note Worker Lifecycle

`CollaborativeNoteProposalJobWorker` executes queued note proposal jobs outside
chat.

Source evidence:

```text
collaborative_note_job_worker.py:102 class CollaborativeNoteProposalJobWorker:
collaborative_note_job_worker.py:118 def dispatch(...)
collaborative_note_job_worker.py:124 task = asyncio.create_task(self.run_job(...))
collaborative_note_job_worker.py:136 async def run_one(...)
collaborative_note_job_worker.py:144 job = await self._agent_job_repository.lease_next_queued_job(... action_kind="propose_collaborative_note")
collaborative_note_job_worker.py:161 async def run_job(...)
collaborative_note_job_worker.py:168 leased = await self._agent_job_repository.lease_queued_job(...)
```

The worker execution path loads the private payload and calls the service:

```text
collaborative_note_job_worker.py:183 async def _execute_leased_job(...)
collaborative_note_job_worker.py:197 payload = await self._agent_job_repository.get_job_payload(...)
collaborative_note_job_worker.py:202 result = await self._note_service.create_natural_proposal(note_command_from_payload(payload))
```

Completion creates an AgentJob report:

```text
collaborative_note_job_worker.py:223 async def _complete_job(...)
collaborative_note_job_worker.py:232 completed = await self._agent_job_repository.complete_job(...)
collaborative_note_job_worker.py:246 await self._create_report(...)
collaborative_note_job_worker.py:249 title="Workspace note proposal pending review"
collaborative_note_job_worker.py:250 summary="A workspace note proposal was created and is pending your review."
```

Failure also creates an AgentJob report:

```text
collaborative_note_job_worker.py:258 async def _fail_job(...)
collaborative_note_job_worker.py:265 failed = await self._agent_job_repository.fail_job(...)
collaborative_note_job_worker.py:272 code="collaborative_note_proposal_conflict"
collaborative_note_job_worker.py:273 summary="Workspace note proposal could not be created."
collaborative_note_job_worker.py:283 await self._create_report(...)
collaborative_note_job_worker.py:286 title="Workspace note proposal not created"
```

## Remaining Chat Coupling

### Legacy Chat-Based Note Decision Path

The backend still accepts `payload.collaborative_note_decision` inside the chat
execution path.

Source evidence:

```text
main.py:4705 if payload.collaborative_note_decision is not None:
main.py:4714 note_decision_result = await note_service.decide_proposal(...)
main.py:4756 effect_result = await database.record_chat_turn_collaborative_note_decision_effect(...)
```

The current UI appears to use direct note APIs, but the old request builder
still exists:

```text
frontend/requests.mjs:234 export function buildCollaborativeNoteDecisionChatRequest(...)
frontend/requests.mjs:111 export function selectChatEndpoint(request) {
frontend/requests.mjs:113   const structuredFields = [
frontend/requests.mjs:117     "collaborative_note_decision",
frontend/requests.mjs:120   return structuredFields.some((field) => body[field] != null) ? "/api/chat" : "/api/chat/stream";
```

This is stale coupling. It is not necessarily active in the current UI path,
but it remains a supported path in source.

### Responder/Tool Duplicate Risk

The responder has direct collaborative-note fallback instructions:

```text
agent_col_responder.py:286 For direct collaborative-note fallback, use propose_collaborative_note only to
agent_col_responder.py:298 sensitive data as prohibited. Make at most one note proposal call per turn.
agent_col_responder.py:299 If server-validated precompleted actions show that the current logical turn
agent_col_responder.py:300 already completed an artifact, artifact feedback, memory, or workspace-note
agent_col_responder.py:301 effect, do not call propose_collaborative_note.
```

The tool checks only for precompleted durable effects:

```text
collaborative_note_tool.py:195 def _turn_has_precompleted_durable_effect(...)
collaborative_note_tool.py:201 value = state.get(_PRECOMPLETED_DURABLE_EFFECT_STATE_KEY, False)
```

`SupervisorRuntime` sets `memory_prequeued_for_turn` for memory duplicate
suppression, but there is no equivalent `note_prequeued_for_turn` state:

```text
supervisor_runtime.py:466 "memory_prequeued_for_turn": _has_queued_memory_work(queued_actions)
supervisor_runtime.py:472 "note_user_id": context.user_id
supervisor_runtime.py:478 "note_source_message_text": context.message
```

The helper that marks precompleted durable effects does not include queued note
jobs:

```text
supervisor_runtime.py:888 def _has_precompleted_durable_effect(...)
supervisor_runtime.py:895 return (
supervisor_runtime.py:896     any(action.action_name in _DURABLE_PRECOMPLETED_ACTION_NAMES for action in actions)
supervisor_runtime.py:900     or bool(memory_proposals)
supervisor_runtime.py:902     or bool(collaborative_note_proposals)
```

The precompleted action-name set contains artifact/feedback actions, not queued
note work:

```text
supervisor_runtime.py:209 _DURABLE_PRECOMPLETED_ACTION_NAMES = frozenset(
supervisor_runtime.py:211     "synthesize_project",
supervisor_runtime.py:212     "create_artifact",
supervisor_runtime.py:213     "record_blueprint_feedback",
```

The runtime accepts queued note tool responses by appending the queued action if
it is not exactly already present:

```text
supervisor_runtime.py:580 elif isinstance(parsed_note, QueuedCollaborativeNoteToolResponse):
supervisor_runtime.py:584     if parsed_note.queued_action not in queued_actions:
supervisor_runtime.py:585         queued_actions.append(parsed_note.queued_action)
```

This means the note path has a similar class of duplicate risk to the memory
duplicate bug that was recently fixed, except note-specific suppression has not
been added yet.

### Responder Text Still Narrates Queued Note Work

`SupervisorRuntime` sanitizes some note completion claims when note work is
queued:

```text
supervisor_runtime.py:89 _QUEUED_NOTE_COMPLETION_CLAIM_PATTERN = re.compile(...)
supervisor_runtime.py:149 def _sanitize_queued_work_response_text(...)
supervisor_runtime.py:158 has_note_work = _has_queued_work_kind(queued_actions, "propose_collaborative_note")
supervisor_runtime.py:190 if has_note_work and not collaborative_note_proposals and _contains_queued_note_completion_claim(paragraph):
supervisor_runtime.py:203 retained_paragraphs.append(_QUEUED_NOTE_REPLACEMENT_TEXT)
```

This is useful protection, but it also shows that chat text is still part of
queued note presentation. The longer-term async goal is for AgentJob reports
and the Notes panel to own the lifecycle status.

### Stale Supervisor Instruction

`agent_col_responder.py` no longer contains the stale note+memory prohibition,
but `supervisor.py` still does:

```text
supervisor.py:153 Never create both a note proposal and a memory proposal or clarification in
supervisor.py:154 one ordinary turn.
```

Production app construction uses `agent_col_responder.py`:

```text
main.py:47 from agent_col_responder import create_responder_app
main.py:2124 create_responder_app(...)
```

However, `supervisor.py` is still imported by `supervisor_runtime.py` for
constants and remains heavily covered by tests. This is stale source-of-truth
residue and can confuse future maintenance.

## What Is Already Good

- Direct Notes UI actions use direct Notes APIs, not chat.
- The Notes UI has its own pending state and is not blocked by `pendingTurn`.
- Explicit Agent Col note requests can be queued as AgentJob work.
- The Note Curator worker executes outside chat response generation.
- Queued note jobs restore without a turn lease, avoiding the old single-turn
  durable-effect invariant.
- Completed note jobs create AgentJob reports and can refresh the Notes panel.

## What Is Not Yet Fully Async

- Legacy `/api/chat` note decision handling still exists.
- Legacy request-building for chat-based note decisions still exists.
- The responder can still call `propose_collaborative_note` after a deterministic
  note prequeue because there is no note-specific prequeue suppression state.
- Runtime still blocks direct memory and note proposal receipts in the same
  model tool pass.
- Chat text still narrates queued note work, with sanitizer cleanup.
- Note worker failure summaries collapse multiple root causes into one generic
  conflict message.
- Direct UI-created note proposals store a synthetic user message in the chat
  message store for provenance.

## Summary

The collaborative note lifecycle is further along the async path than memory in
some important ways: direct UI operations are already independent from chat, and
explicit Agent Col note requests can become background Note Curator jobs.

The main remaining lifecycle problems are not in the core Note worker. They are
in stale compatibility paths and orchestration coupling:

- chat-owned note decisions still exist;
- chat-turn effect recording still carries old single-effect assumptions;
- the responder/tool path lacks note-specific duplicate suppression for already
  prequeued note work;
- note status is still partially narrated through chat.

The next architectural direction should preserve the working direct Notes API
and background Note Curator job path, while removing or quarantining stale
chat-based note lifecycle paths and making the responder treat prequeued note
work the same way memory now does.
