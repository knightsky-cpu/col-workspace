# Artifact Lifecycle Audit

This document records the current artifact lifecycle in Agent Col, with source
evidence for each boundary. It is intended to keep the async-work goal concrete
while artifact creation, review, feedback, and viewer refresh move toward true
independent background work.

## Target Lifecycle

Artifacts should be project-scoped durable work products that can be created,
viewed, revised, archived, restored, deleted, and reviewed without being coupled
to a chat response lifecycle.

The desired async model is:

- Agent Col can accept explicit artifact work and enqueue it as an Artifact
  Builder job.
- Artifact Builder jobs run independently from chat response generation.
- Artifact jobs can run beside Note Curator and Memory Analyst jobs.
- Direct Work UI actions remain available while chat is streaming.
- The artifact viewer refreshes from canonical backend state and AgentJob
  completion, not from chat response side effects.
- Artifact feedback should be handled as durable artifact work, not as a chat
  turn effect, when it can be performed independently.
- Failures should be visible through AgentJob reports with enough diagnostic
  detail to investigate the worker path without relying on chat output.

## Current Application Wiring

The application startup path wires artifact services, the artifact job worker,
and the artifact executor in `main.py`.

Source evidence:

```text
main.py:1991 synthesis_service = SynthesisApplicationService(...)
main.py:1995 artifact_service = ArtifactReadService(database=database)
main.py:1996 generic_artifact_service = GenericArtifactReadService(...)
main.py:1999 generic_artifact_creation_service = GenericArtifactCreationService(...)
main.py:2002 agent_job_repository = database.agent_jobs()
main.py:2003 artifact_job_worker = AgentColArtifactCreationJobWorker(...)
main.py:2010 artifact_job_background_tasks: set[asyncio.Task[AgentJob | None]] = set()
main.py:2012 def dispatch_artifact_job(job: AgentJob) -> None:
main.py:2013     artifact_job_worker.dispatch(...)
main.py:2018 artifact_executor = AgentColArtifactExecutor(...)
```

This is the correct basic shape for asynchronous artifact creation: the chat turn
service can enqueue an `AgentJob`, and the dispatcher starts worker execution
outside the synchronous chat response path.

## Agent Col Artifact Acceptance

Artifact handling enters through `AgentColTurnService`.

### Explicit Queue-First Path

`_queue_explicit_durable_actions` handles deterministic durable action
prequeueing. It detects explicit artifact creation through
`_explicit_blueprint_artifact_directive` and queues it before model routing.

Source evidence:

```text
agent_col_turn_service.py:925 async def _queue_explicit_durable_actions(...)
agent_col_turn_service.py:929 artifact_directive = _explicit_blueprint_artifact_directive(...)
agent_col_turn_service.py:938 queue_result = await self._artifact_executor.queue(...)
agent_col_turn_service.py:947 accepted_action_index=accepted_action_index
```

The explicit parser is intentionally narrow:

```text
agent_col_turn_service.py:90 _EXPLICIT_BLUEPRINT_ARTIFACT_REQUEST = re.compile(...)
agent_col_turn_service.py:399 def _explicit_blueprint_artifact_directive(...)
agent_col_turn_service.py:405 if _EXPLICIT_BLUEPRINT_ARTIFACT_REQUEST.search(message) is None:
agent_col_turn_service.py:412 artifact_intent={ "operation": "create_blueprint" ... }
```

This path currently recognizes explicit `create artifact` or `create blueprint
artifact` style requests and creates a blueprint artifact directive. It does not
attempt broad deterministic interpretation of arbitrary phrases like "write me a
program"; those still rely on model routing.

### Routed Artifact Path

If routing returns an artifact directive and a `create_artifact` action was
already prequeued, the turn service does not enqueue or execute another artifact
job. It proceeds to the responder with the prequeued receipt.

Source evidence:

```text
agent_col_turn_service.py:1097 _log_turn_pipeline("routing_finish", ...)
agent_col_turn_service.py:1110 if directive.route is AgentColRouteV4.ARTIFACT:
agent_col_turn_service.py:1111     if _has_queued_action_kind(prequeued_actions, "create_artifact"):
agent_col_turn_service.py:1112         return await self._complete_prequeued_turn(...)
```

If routing returns artifact work and it was not prequeued, the route-specific
completion path queues an artifact job and then runs the responder with the
queued receipt.

Source evidence:

```text
agent_col_turn_service.py:1154 async def _complete_artifact_turn(...)
agent_col_turn_service.py:1170 queue_result = await artifact_executor.queue(...)
agent_col_turn_service.py:1213 _log_turn_pipeline("artifact_queued", ...)
agent_col_turn_service.py:1229 result = await self._run_responder(...)
agent_col_turn_service.py:1248 prequeued_actions=queue_result.queued_actions
agent_col_turn_service.py:1370 return AgentColTurnResult(...)
agent_col_turn_service.py:1373 artifacts=()
agent_col_turn_service.py:1383 queued_actions=_stable_merge_queued_actions(...)
```

The important behavior is that `AgentColTurnResult.artifacts` remains empty for
queued artifact work. Chat returns a queued-action receipt, while canonical
artifact visibility comes later from the worker and Work view refresh.

Focused tests already assert the queue-only behavior:

```text
tests/test_agent_col_turn_service_artifacts.py:330 test_turn_service_queues_artifact_before_responder_without_generation
tests/test_agent_col_turn_service_artifacts.py:366 assert len(artifact_executor.queue_commands) == 1
tests/test_agent_col_turn_service_artifacts.py:367 assert artifact_executor.execute_commands == []
tests/test_agent_col_turn_service_artifacts.py:370 assert result.queued_actions == (queued_action,)
tests/test_agent_col_turn_service_artifacts.py:380 test_explicit_artifact_and_note_request_queues_before_router_timeout
tests/test_agent_col_turn_service_artifacts.py:443 assert len(artifact_executor.queue_commands) == 1
tests/test_agent_col_turn_service_artifacts.py:446 assert exc_info.value.queued_actions == (artifact_action, note_action)
```

## Artifact Job Identity and Payload

Artifact jobs are idempotent and scoped by source turn details. The digest
includes project, session, user, turn id, source message id, accepted action
index, operation, artifact family, format, filename, and source text.

Source evidence:

```text
agent_col_artifact_executor.py:191 def _artifact_job_digest(...)
agent_col_artifact_executor.py:195 payload = {
agent_col_artifact_executor.py:199     "turn_id": claim.ids.turn_id,
agent_col_artifact_executor.py:200     "source_message_id": claim.ids.user_message_id,
agent_col_artifact_executor.py:201     "accepted_action_index": accepted_action_index,
agent_col_artifact_executor.py:202     "operation": intent.get("operation"),
agent_col_artifact_executor.py:203     "artifact_family": intent.get("artifact_family"),
agent_col_artifact_executor.py:204     "format": intent.get("format"),
agent_col_artifact_executor.py:205     "filename": intent.get("filename"),
agent_col_artifact_executor.py:206     "source_text": source_text,
```

The job uses `action_kind="create_artifact"` and the agent label
`"Artifact Builder"`.

Source evidence:

```text
agent_col_artifact_executor.py:225 def _artifact_job(...)
agent_col_artifact_executor.py:233 action_kind="create_artifact"
agent_col_artifact_executor.py:235 agent_label="Artifact Builder"
agent_col_artifact_executor.py:237 idempotency_key=f"artifact-create-{digest}"
```

The private payload stores the artifact intent and source text:

```text
agent_col_artifact_executor.py:245 def _artifact_job_payload(...)
agent_col_artifact_executor.py:257 payload={
agent_col_artifact_executor.py:258     "artifact_intent": dict(intent),
agent_col_artifact_executor.py:259     "source_text": source_text,
```

This preserves the worker boundary: the chat response exposes a receipt, while
the worker receives the private execution payload through `AgentJobRepository`.

## Artifact Worker Execution

`AgentColArtifactCreationJobWorker` executes queued artifact creation jobs
outside the chat response path.

Source evidence:

```text
agent_col_artifact_executor.py:489 class AgentColArtifactCreationJobWorker:
agent_col_artifact_executor.py:490     """Execute queued artifact creation jobs outside the chat response path."""
agent_col_artifact_executor.py:511 def dispatch(...)
agent_col_artifact_executor.py:517 task = asyncio.create_task(self.run_job(...))
agent_col_artifact_executor.py:523 task_set.add(task)
agent_col_artifact_executor.py:526 task.add_done_callback(self._log_background_failure)
```

The worker can also lease the next queued artifact job by `action_kind`:

```text
agent_col_artifact_executor.py:529 async def run_one(...)
agent_col_artifact_executor.py:537 job = await self._agent_job_repository.lease_next_queued_job(...)
agent_col_artifact_executor.py:544 action_kind="create_artifact"
```

For a specific dispatched job, it leases by job id and executes the private
payload:

```text
agent_col_artifact_executor.py:554 async def run_job(...)
agent_col_artifact_executor.py:561 leased = await self._agent_job_repository.lease_queued_job(...)
agent_col_artifact_executor.py:576 async def _execute_leased_job(...)
agent_col_artifact_executor.py:590 payload = await self._agent_job_repository.get_job_payload(...)
agent_col_artifact_executor.py:595 artifact_id, label = await self._execute_payload(payload)
```

The worker currently supports two operations:

```text
agent_col_artifact_executor.py:608 async def _execute_payload(...)
agent_col_artifact_executor.py:620 if operation == "create_single_file_artifact":
agent_col_artifact_executor.py:626 if operation == "create_blueprint":
agent_col_artifact_executor.py:628 raise ValueError("Artifact job operation is invalid.")
```

### Blueprint Artifact Worker Path

Blueprint jobs call `SynthesisApplicationService.synthesize`.

Source evidence:

```text
agent_col_artifact_executor.py:630 async def _execute_blueprint_payload(...)
agent_col_artifact_executor.py:635 result = await self._synthesis_service.synthesize(...)
agent_col_artifact_executor.py:643 blueprint = result.blueprint
agent_col_artifact_executor.py:645 return result.blueprint_id, label
```

`synthesize` generates a governed blueprint and persists it with
`database.save_blueprint`.

Source evidence:

```text
synthesis_service.py:96 async def synthesize(...)
synthesis_service.py:100 generated = await self.generate_governed_blueprint(command)
synthesis_service.py:102 blueprint_id = await self._database.save_blueprint(...)
synthesis_service.py:111 return SynthesisResult(...)
```

`save_blueprint` writes the canonical document under the project blueprints
collection and stores `originating_turn_id` as `None`.

Source evidence:

```text
database.py:4326 async def save_blueprint(...)
database.py:4352 blueprint_ref = project_ref.collection("blueprints").document()
database.py:4362 "artifact_contract_version": ARTIFACT_CONTRACT_VERSION
database.py:4363 "artifact_type": "synthesis_blueprint"
database.py:4365 "originating_session_id": session_id
database.py:4366 "originating_turn_id": None
database.py:4378 "blueprint": blueprint
```

This means background blueprint artifacts are not persisted as chat-turn durable
effects. They are project-owned artifacts with session provenance.

### Single-File Artifact Worker Path

Single-file jobs run generic generation and then persist through the generic
artifact creation service.

Source evidence:

```text
agent_col_artifact_executor.py:647 async def _execute_single_file_payload(...)
agent_col_artifact_executor.py:670 generated = await self._generic_artifact_generator(...)
agent_col_artifact_executor.py:680 created = await self._generic_artifact_creator.create_artifact(...)
agent_col_artifact_executor.py:687 originating_turn_id=payload.source_turn_id
agent_col_artifact_executor.py:690 return created.reference.artifact_id, created.reference.display_label
```

Generic artifact generation is bounded to structured JSON output and avoids tool
use:

```text
generic_artifact_generation.py:25 _GENERIC_ARTIFACT_SYSTEM_INSTRUCTION = """
generic_artifact_generation.py:32 Return only JSON that satisfies the requested schema. Do not call tools,
generic_artifact_generation.py:33 browse, persist data, or answer conversationally.
```

Generic artifact creation validates and persists the generated file artifact:

```text
generic_artifact_creation_service.py:47 class GenericArtifactCreationService:
generic_artifact_creation_service.py:53 async def create_artifact(...)
generic_artifact_creation_service.py:58 artifact = SingleFileArtifact.model_validate(command.artifact)
generic_artifact_creation_service.py:68 artifact_id = await self._artifact_writer.save_single_file_artifact(...)
```

The database document stores project/session/user ownership, lifecycle status,
filename, family, format, content, and summary.

Source evidence:

```text
database.py:4386 async def save_single_file_artifact(...)
database.py:4420 artifact_ref = project_ref.collection("artifacts").document()
database.py:4430 "artifact_contract_version": ARTIFACT_CONTRACT_VERSION
database.py:4431 "artifact_type": "single_file_artifact"
database.py:4433 "originating_session_id": session_id
database.py:4434 "originating_turn_id": originating_turn_id
database.py:4440 "lifecycle_status": "active"
database.py:4441 "filename": validated_artifact.filename
database.py:4447 "content": validated_artifact.content
database.py:4448 "summary": validated_artifact.summary
```

## Worker Completion, Reports, and Failure Handling

On success, the worker completes the job, writes a completed event, and creates
a job report.

Source evidence:

```text
agent_col_artifact_executor.py:692 async def _complete_job(...)
agent_col_artifact_executor.py:701 completed = await self._agent_job_repository.complete_job(...)
agent_col_artifact_executor.py:707 result_refs={"artifact_id": artifact_id}
agent_col_artifact_executor.py:709 await self._append_event(...)
agent_col_artifact_executor.py:712 message="Artifact created."
agent_col_artifact_executor.py:715 await self._create_report(...)
agent_col_artifact_executor.py:718 title="Artifact created"
agent_col_artifact_executor.py:719 summary="The requested artifact was created."
```

On failure, the worker currently catches all exceptions and writes a generic
failure.

Source evidence:

```text
agent_col_artifact_executor.py:589 try:
agent_col_artifact_executor.py:590     payload = await self._agent_job_repository.get_job_payload(...)
agent_col_artifact_executor.py:595     artifact_id, label = await self._execute_payload(payload)
agent_col_artifact_executor.py:596 except Exception:
agent_col_artifact_executor.py:597     return await self._fail_job(...)
```

```text
agent_col_artifact_executor.py:725 async def _fail_job(...)
agent_col_artifact_executor.py:732 failed = await self._agent_job_repository.fail_job(...)
agent_col_artifact_executor.py:739 code="artifact_creation_failed"
agent_col_artifact_executor.py:740 summary="Artifact could not be created."
agent_col_artifact_executor.py:747 message="Artifact creation failed."
agent_col_artifact_executor.py:753 title="Artifact not created"
agent_col_artifact_executor.py:754 summary="Artifact could not be created."
```

This is insufficient for diagnosis. The report and persisted failure summary do
not distinguish provider validation errors, generation timeouts, persistence
errors, payload schema failures, missing worker dependencies, or lease/state
errors.

## Direct Artifact API Lifecycle

The Work UI talks to direct artifact APIs in `frontend/api.mjs`.

Source evidence:

```text
frontend/api.mjs:577 export function listArtifacts(...)
frontend/api.mjs:591 export function getArtifact(...)
frontend/api.mjs:607 export function createArtifact(...)
frontend/api.mjs:626 export function archiveArtifact(...)
frontend/api.mjs:642 export function restoreArtifact(...)
frontend/api.mjs:658 export function deleteArtifact(...)
frontend/api.mjs:674 export function updateArtifactMetadata(...)
frontend/api.mjs:695 export function createArtifactVersion(...)
```

The direct create endpoint is outside `/api/chat`, but it is synchronous with
provider generation.

Source evidence:

```text
main.py:3875 @app.post("/api/projects/{project_id}/artifacts")
main.py:3899 artifact = await request.app.state.generic_artifact_generator(...)
main.py:3910 await request.app.state.generic_artifact_creation_service.create_artifact(...)
main.py:3922 except GenericArtifactGenerationTimeoutError ...
main.py:3927 except GenericArtifactGenerationError ...
```

This is decoupled from chat, but it is not yet true background work. The HTTP
request waits for generation and persistence before returning.

Direct artifact mutations are also direct request/response handlers in
`frontend/app.mjs`.

Source evidence:

```text
frontend/app.mjs:1712 async function archiveGenericArtifact(...)
frontend/app.mjs:1718 await archiveArtifact(...)
frontend/app.mjs:1725 await loadWorkList()
frontend/app.mjs:1731 async function restoreGenericArtifact(...)
frontend/app.mjs:1750 async function deleteGenericArtifact(...)
frontend/app.mjs:1775 async function updateGenericArtifactMetadata(...)
frontend/app.mjs:1798 async function createGenericArtifactVersion(...)
```

These operations are independent from chat response generation, but they are not
AgentJob-backed. The UI updates state and reloads the Work list after each
operation returns.

## Artifact Read Lifecycle

Blueprint artifact reads are projected through `ArtifactReadService`.

Source evidence:

```text
artifact_read_service.py:55 class ArtifactReadService:
artifact_read_service.py:61 async def list_blueprints(...)
artifact_read_service.py:65 page = await self._database.list_blueprint_documents(...)
artifact_read_service.py:72 if self._uses_legacy_schema(record) ...
artifact_read_service.py:85 async def get_blueprint(...)
artifact_read_service.py:89 record = await self._database.get_blueprint_document(...)
artifact_read_service.py:97 projected = self._project_record(...)
```

The service filters unsupported or legacy schemas from list results and fails
closed for invalid stored detail records.

Source evidence:

```text
artifact_read_service.py:110 def _uses_legacy_schema(...)
artifact_read_service.py:118 def _uses_current_artifact_contract(...)
artifact_read_service.py:136 try:
artifact_read_service.py:147 blueprint = SynthesisBlueprint.model_validate(...)
artifact_read_service.py:188 except (TypeError, ValueError, ValidationError) as exc:
artifact_read_service.py:193 raise ArtifactReadStateError(...)
```

This read boundary is good for async reconciliation: the viewer should trust
canonical project artifact state rather than chat response artifacts.

## Frontend Artifact Refresh Lifecycle

The frontend already refreshes Work state from completed AgentJobs.

Source evidence:

```text
frontend/app.mjs:1199 function refreshAuthoritativeResourcesForCompletedJobs(jobs)
frontend/app.mjs:1205 for (const job of jobs) {
frontend/app.mjs:1221 if (actionKind === "create_artifact") {
frontend/app.mjs:1222     shouldRefreshWork = true;
frontend/app.mjs:1227 if (shouldRefreshWork) {
frontend/app.mjs:1228     loadWorkList({ selectSingleNewArtifact: true });
```

This is the correct direction: artifact visibility is reconciled from AgentJob
completion, not from the chat result.

The Work list loads blueprint and single-file artifacts separately, then merges
the canonical result set.

Source evidence:

```text
frontend/app.mjs:996 async function loadWorkList(...)
frontend/app.mjs:1012 const [blueprintResponse, artifactResponse] = await Promise.all(...)
frontend/app.mjs:1031 const items = [...blueprints, ...artifacts].sort(...)
```

The Work detail path uses canonical read APIs:

```text
frontend/app.mjs:1060 async function loadWorkDetail(item)
frontend/app.mjs:1070 if (item.artifact_type === "single_file_artifact") {
frontend/app.mjs:1071     const artifactResponse = await getArtifact(...)
frontend/app.mjs:1079 const [blueprintResponse, feedbackResponse] = await Promise.all(...)
```

## Artifact Feedback Lifecycle

Artifact feedback has two separate paths today.

### Direct Work UI Feedback

The Work UI submits blueprint feedback directly through `recordBlueprintFeedback`.

Source evidence:

```text
frontend/work-view.mjs:706 renderFeedbackComposer(...)
frontend/app.mjs:1988 await recordBlueprintFeedback(...)
main.py:4298 validated_idempotency_key = validate_idempotency_key(...)
main.py:4320 result = await request.app.state.artifact_feedback_service.record_feedback(...)
```

The service resolves the canonical artifact target and persists feedback:

```text
artifact_feedback_service.py:133 async def record_feedback(...)
artifact_feedback_service.py:137 resolved = await self.resolve_feedback_target(command)
artifact_feedback_service.py:151 await self._feedback_repository.record_blueprint_feedback(...)
artifact_feedback_service.py:192 async def resolve_feedback_target(...)
artifact_feedback_service.py:199 detail = await self._artifact_reader.get_blueprint(...)
artifact_feedback_service.py:227 feedback_id = derive_feedback_id(command.turn_id)
```

This path is outside chat. It is not AgentJob-backed, but it is directly scoped
to artifact state and canonical feedback targets.

### Agent Col Chat-Owned Feedback

Agent Col artifact feedback is still explicitly chat-owned.

Source evidence:

```text
agent_col_artifact_feedback_executor.py:1 """Deterministic chat-owned artifact feedback execution boundary."""
agent_col_artifact_feedback_executor.py:96 async def execute(...)
agent_col_artifact_feedback_executor.py:107 resolved = await self._feedback_resolver.resolve_feedback_target(...)
agent_col_artifact_feedback_executor.py:119 await self._feedback_ledger.record_chat_turn_artifact_feedback_effect(...)
```

The executor rejects commands that already include memory decisions or
precompleted artifact work:

```text
agent_col_artifact_feedback_executor.py:167 if (
agent_col_artifact_feedback_executor.py:170     or claim.request.memory_decision is not None
agent_col_artifact_feedback_executor.py:171     or claim.precompleted_memory_proposals
agent_col_artifact_feedback_executor.py:172     or claim.precompleted_artifacts
```

This is legacy coupling. It keeps Agent Col artifact feedback as a chat-turn
effect instead of a background artifact job.

The database path confirms chat-turn ownership:

```text
database.py:2907 async def record_chat_turn_artifact_feedback_effect(...)
```

## Legacy Chat-Turn Artifact Effect Paths

The database still contains chat-turn artifact effect persistence for blueprint
and single-file artifact creation.

Source evidence:

```text
database.py:2547 async def record_chat_turn_blueprint_effect(...)
database.py:2729 async def record_chat_turn_single_file_artifact_effect(...)
```

These methods reject mixing several durable effects in the same chat turn:

```text
database.py:2559 if (
database.py:2562     claim.request.memory_decision is not None
database.py:2563     or claim.request.artifact_feedback_decision is not None
database.py:2564     or claim.precompleted_memory_proposals
database.py:2566     or claim.precompleted_artifact_feedback
database.py:2568     raise ValueError("Claim is not eligible for artifact effect recording.")
```

The modern Agent Col turn path queues artifact jobs and does not return
completed artifacts inline, but these legacy persistence paths remain in source
and tests. They are architectural residue that can confuse future lifecycle work
because they encode older one-durable-effect chat-turn assumptions.

## Frontend Coupling to Chat Pending State

Work/artifact operations inspected in `frontend/app.mjs` do not directly check
`state.pendingTurn` before archive, restore, delete, metadata update, version
creation, or feedback submission.

However, the workspace drawer still blocks workspace selection, creation, and
deletion while chat is pending.

Source evidence:

```text
frontend/app.mjs:1593 if (!state.context || state.pendingTurn !== null) {
frontend/app.mjs:1607 if (!state.context || state.pendingTurn !== null) {
frontend/app.mjs:1631 if (!state.context || state.pendingTurn !== null) {
```

This is broader UI coupling. It is not artifact-specific, but it prevents the
left drawer from being fully independent while chat is streaming.

## Current State Summary

Artifact creation requested through Agent Col is close to the desired async
model:

- Agent Col queues `create_artifact` work before or after routing.
- Chat returns queued-action receipts rather than generated artifact content.
- `AgentColArtifactCreationJobWorker` performs generation and persistence
  outside the chat response path.
- Completed artifact jobs refresh the Work list and can select the newly created
  artifact.

Several parts are not yet truly asynchronous:

- Direct generic artifact creation waits on provider generation in the HTTP
  request.
- Direct artifact lifecycle actions are direct HTTP operations, not AgentJobs.
- Agent Col artifact feedback is still chat-owned.
- Legacy chat-turn artifact effect paths remain in `database.py`.
- Worker failure reporting loses diagnostic detail.
- The workspace drawer still depends on chat pending state.

## Recommended Future Work

These are not implemented in this audit; they are the next architectural
directions suggested by the evidence.

1. Convert direct generic artifact creation into an optional AgentJob-backed
   path for slow/provider-generated artifacts.
2. Move Agent Col artifact feedback to an artifact feedback job path instead of
   `record_chat_turn_artifact_feedback_effect`.
3. Keep lightweight direct artifact metadata/archive/restore/delete operations
   direct unless they become slow or multi-step.
4. Preserve canonical Work list/detail refresh from backend artifact state.
5. Improve artifact worker failure reports to preserve diagnostic failure class
   and a safe summary.
6. Remove or quarantine legacy chat-turn artifact effect paths after all callers
   move to AgentJob-backed creation.
7. Decouple workspace drawer actions from chat pending state, while preserving
   explicit safeguards for workspace switching during destructive local edits.
