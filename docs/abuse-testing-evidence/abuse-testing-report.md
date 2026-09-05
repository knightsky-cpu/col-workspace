# Abuse / Acceptance Testing Report

**Checkpoint:** `b62de150d5b30c11c24dc5b2f0546a8eeed281ee`
**Branch:** `main`
**Date:** 2026-09-05
**Auth mode:** `AGENT_COL_AUTH_MODE=local_dev` (source-confirmed: `auth.py`, `docs/development/local-setup.md`, `README.md`)
**App URL:** `http://127.0.0.1:8000/workspace`
**Scope:** Runtime acceptance / evidence collection only. No source edits. No commits/pushes. Evidence files only under `docs/abuse-testing-evidence/`.

## Preflight

- Branch: `main` — verified
- HEAD: `b62de150d5b30c11c24dc5b2f0546a8eeed281ee` — verified
- Worktree: clean at start — verified
- Supported local development auth value: `local_dev` — verified from `auth.py` (`AuthMode = Literal["local_dev", "google_oidc"]`; default and documented local launch) and `docs/development/local-setup.md`
- Backend start command: `AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000`

---

## Environment notes (observed at startup / preflight)

- Backend started successfully (`Application startup complete`, health `{"status":"online"}`).
- Recurring backend ERROR during AgentJob runtime drain: `Firestore list_expired_running_jobs operation failed` — Missing Firestore composite index on `agent_jobs` (`action_kind`, `status`, `lease_expires_at`). Classified under defects as **B/D** (recovery/durability + observability). Does not block ordinary chat or session-scoped job listing.
- Session ID for primary conversation: `session--f0c41a04-8f51-46f7-9e8f-7fd5eef7a809`
- User / workspace: `abuse-test-user-20260905` / `agent-col`

## Defects (running list)

| ID | Class | Summary |
| --- | --- | --- |
| D1 | B/D | Startup/runtime drain fails: missing Firestore index for `list_expired_running_jobs` |
| D2 | C/D | Model claimed background tools inactive despite successful artifact AgentJob |
| D3 | — | Explicit Memory job `jobref_3d75906c...` failed terminal with `invalid_memory_candidate` (retryable=false); async ownership still held |

---

## Test log

### TEST 1 — Control chat

- **TEST:** Send ordinary conversational message with no resource action; verify chat completes and no AgentJob is created for that turn.
- **EXPECTED:** Chat response completes normally; Agents remains `0 active · 0 queued` for the session; chat pipeline reports zero resource actions; no session-scoped AgentJob.
- **OBSERVED:**
  - User message sent; assistant replied: “Message received; confirming receipt of your control message.”
  - UI Agents badge: `0 active · 0 queued` before and after.
  - Backend chat pipeline for the control turn: `completed_actions=0 artifacts=0 memory_proposals=0 collaborative_note_proposals=0`.
  - Caveat: during the same window, an automatic Preference learning capture job completed (`jobref_e1255404156b44cd70ac3616c99ebc22`, `propose_memory_signal`). It appears in `GET .../agent/jobs?session_id=...` despite the control turn reporting zero memory proposals. Agents badge stayed `0 active · 0 queued` because the job had already completed. Classified as observation / possible C (badge timing) rather than control-chat failure; control turn itself did not queue an explicit resource action.
- **RESULT:** PASS (with automatic preference-learning side job noted)
- **JOB ID(s):** none created by explicit control-chat resource action. Adjacent auto job: `jobref_e1255404156b44cd70ac3616c99ebc22`
- **SESSION / WORKSPACE:** `session--f0c41a04-8f51-46f7-9e8f-7fd5eef7a809` / `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** none (chat only)
- **REQUEST PATH(S):** `POST /api/chat/stream`; `GET .../agent/jobs?session_id=...`; `GET .../agent/jobs/stream?session_id=...`
- **SCREENSHOT(S):** `01-control-chat.png`
- **BACKEND LOG EVIDENCE:** `Agent_Col chat pipeline stage=turn_service_finish route=chat_stream ... completed_actions=0 artifacts=0 ... memory_proposals=0 ... collaborative_note_proposals=0`; `POST /api/chat/stream` → 200
- **BROWSER CONSOLE / NETWORK EVIDENCE:** Chat stream 200; session job polls 200 with empty list; composer re-enabled after reply
- **DEFECT CLASSIFICATION:** none for this test (D1 pre-existing drain error continues in logs)

### TEST 2 — Artifact while chatting

- **TEST:** Request an artifact; continue ordinary conversation before artifact completion; verify chat usable and artifact job independent.
- **EXPECTED:** Chat turn queues artifact work without owning completion; follow-up chat works; artifact AgentJob progresses independently to completion.
- **OBSERVED:**
  - Artifact request routed `route=artifact` with `queued_actions=1`; chat turn finished in ~10s (`turn_service_finish` elapsed_ms=10025) while job `jobref_f0b1d2eb213f81eef98aa436086dd73b` (`create_artifact`) ran and completed (~16s wall: 09:27:02→09:27:18).
  - Chat showed queued-action receipt: `Queued action: Artifact Builder · Artifact: structured blueprint · Queued`.
  - Follow-up chat after/near completion: composer accepted new message; reply “Chat remains fully responsive and does not feel blocked.”
  - Artifacts Viewer populated with completed blueprint content (“Asynchronous Agent Jobs Framework”).
  - Agents drawer later showed completed Artifact Builder job; active/queued badge was already `0` by the time UI was inspected after the fast completion window.
  - Model prose incorrectly claimed “direct background job execution tools are not active,” while an authoritative AgentJob did complete — observability/UX mismatch (class D/C), not an ownership failure.
- **RESULT:** PASS
- **JOB ID(s):** `jobref_f0b1d2eb213f81eef98aa436086dd73b` (create_artifact, completed)
- **SESSION / WORKSPACE:** `session--f0c41a04-8f51-46f7-9e8f-7fd5eef7a809` / `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** Artifact (`create_artifact`)
- **REQUEST PATH(S):** `POST /api/chat/stream`; `GET .../agent/jobs`; artifact resource GETs
- **SCREENSHOT(S):** `02-artifact-while-chatting.png`
- **BACKEND LOG EVIDENCE:** `responder_finish route=artifact ... queued_actions=1`; follow-up `route=direct queued_actions=0`
- **BROWSER CONSOLE / NETWORK EVIDENCE:** Chat stream 200; job list includes completed create_artifact; composer re-enabled for follow-up
- **DEFECT CLASSIFICATION:** D2 = C/D — model text claimed background tools inactive despite successful AgentJob; badge active window not observed due to fast completion (timing, not proven defect)

### TEST 3 — Memory while chatting

- **TEST:** Trigger explicit Memory proposal; continue chatting before Memory work finishes; verify Memory asynchronous and chat does not own completion.
- **EXPECTED:** Chat queues Memory work and remains usable; Memory AgentJob lifecycle independent of chat completion.
- **OBSERVED:**
  - Chat turn finished with `queued_actions=1` (~13.4s) and message: “Memory work has been queued for background processing…” plus receipt `Queued action: Memory Analyst · Memory request: communication_style · Queued`.
  - Follow-up chat while/after Memory work: composer accepted message; reply `OK`.
  - AgentJob `jobref_3d75906c165cb2d5f5d4c3f5e23c3fc1` (`propose_memory_signal`, Memory request: communication_style) reached terminal `failed` with `invalid_memory_candidate` / `retryable: false` (~2s after create). Matching report #003: “Memory proposal not created”.
  - Agents drawer shows Failed Memory Analyst entry; chat remained independent of that terminal outcome.
  - No pending memory proposals appeared in Memory surface (consistent with failed create).
- **RESULT:** PASS (async ownership). Terminal Memory failure is a separate validation outcome, not chat ownership failure.
- **JOB ID(s):** `jobref_3d75906c165cb2d5f5d4c3f5e23c3fc1` (failed)
- **SESSION / WORKSPACE:** `session--f0c41a04-8f51-46f7-9e8f-7fd5eef7a809` / `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** Memory (`propose_memory_signal`)
- **REQUEST PATH(S):** `POST /api/chat/stream`; `GET .../agent/jobs`; `GET .../agent/reports`; `GET .../memory`
- **SCREENSHOT(S):** `03-memory-while-chatting.png`
- **BACKEND LOG EVIDENCE:** `responder_finish route=direct ... queued_actions=1`; follow-up chat completed; job+report terminal failed
- **BROWSER CONSOLE / NETWORK EVIDENCE:** Chat streams 200; Agents completed list shows Failed Memory job; follow-up composer usable
- **DEFECT CLASSIFICATION:** none for ownership. D3 notes failed Memory candidate validation (not A/B architecture). Failed job reserved as candidate for Test 8 retry (retryable=false may block).

### TEST 4 — Collaborative Note while chatting

- **TEST:** Trigger Note proposal; continue chatting while Note work runs; verify Notes surface/job lifecycle independent of chat.
- **EXPECTED:** Chat queues Note work asynchronously; follow-up chat works; Notes surface reflects proposal independently.
- **OBSERVED:**
  - Chat turn `queued_actions=1` (~11.3s) with message that workspace note proposal was queued; receipt `Queued action: Note Curator · Workspace note: Abuse Test Note 04 · Queued`.
  - AgentJob `jobref_e4ca891facb8aeee766fed745673cc7e` (`propose_collaborative_note`) completed ~2s after create.
  - Notes drawer showed `Pending note proposal` / Task state independently of chat completion.
  - Follow-up chat replied `READY` with composer usable.
  - Agents completed list includes Note Curator Completed.
- **RESULT:** PASS
- **JOB ID(s):** `jobref_e4ca891facb8aeee766fed745673cc7e` (completed)
- **SESSION / WORKSPACE:** `session--f0c41a04-8f51-46f7-9e8f-7fd5eef7a809` / `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** Collaborative Note (`propose_collaborative_note`)
- **REQUEST PATH(S):** `POST /api/chat/stream`; `GET .../notes`; `GET .../agent/jobs`
- **SCREENSHOT(S):** `04-note-while-chatting.png`
- **BACKEND LOG EVIDENCE:** `responder_finish ... queued_actions=1`; notes GET 200 after queue
- **BROWSER CONSOLE / NETWORK EVIDENCE:** Chat 200; Notes pending proposal visible; follow-up READY
- **DEFECT CLASSIFICATION:** none

### TEST 5 — Cross-surface concurrency

- **TEST:** Queue Memory, Note, and Artifact work as close together as practical; continue chatting; verify no identity cross and chat responsive.
- **EXPECTED:** Distinct job/resource identities; chat remains usable while jobs run.
- **OBSERVED:**
  - Combined single-turn request was routed to `clarify` (`queued_actions=0`) asking for individual actions — not a concurrency failure; sequential individual requests used instead (as close as chat turn serialization allows).
  - Note: `jobref_bf85437e2531f90e5aa12ddbc99b05a8` (`propose_collaborative_note`, Abuse Cross Note 05) completed.
  - Artifact: `jobref_9ed131952495ddedc2d69b558ab050c3` (`create_artifact`, abuse_cross_artifact.md) completed; chat showed queued receipt `Artifact Builder · Artifact: abuse_cross_artifact.md`.
  - Memory: `Memory request: user_requested_memory` completed (`job_number` 014); Memory surface showed pending proposal; chat receipt `Memory Analyst · Memory request: user_requested_memory · Queued`.
  - Follow-up chat replied `PONG` with composer usable; no evidence of job_ref/action_kind identity mixing across families.
  - Jobs complete very quickly; 0.5s poller did not capture a simultaneous multi-family nonterminal snapshot, but distinct terminal jobs for all three families exist with separate refs/labels.
- **RESULT:** PASS
- **JOB ID(s):** Note `jobref_bf85437e2531f90e5aa12ddbc99b05a8`; Artifact `jobref_9ed131952495ddedc2d69b558ab050c3`; Memory user_requested (job 014) — see jobs list for full ref
- **SESSION / WORKSPACE:** `session--f0c41a04-8f51-46f7-9e8f-7fd5eef7a809` / `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** Memory + Note + Artifact
- **REQUEST PATH(S):** `POST /api/chat/stream` (multiple); `GET .../agent/jobs`
- **SCREENSHOT(S):** `05-cross-surface-concurrency.png`
- **BACKEND LOG EVIDENCE:** clarify route for combined request; subsequent `queued_actions=1` for note/artifact/memory turns; artifact_queued stage logged
- **BROWSER CONSOLE / NETWORK EVIDENCE:** Distinct queued-action receipts; PONG follow-up; Memory pending proposal visible
- **DEFECT CLASSIFICATION:** none for identity cross. Observation: multi-resource single turn clarifies rather than multi-queue (product behavior).

### TEST 6 — Resource-surface independence

- **TEST:** Inspect Memory/Notes/Artifacts/Agents; refresh/navigate away and return; verify authoritative refresh without chat completion.
- **EXPECTED:** Surfaces reload from authoritative state after refresh/navigation.
- **OBSERVED:**
  - Before nav: Memory pending dark-mode proposal; Notes pending Abuse Cross Note 05 / Abuse Test Note 04; Artifacts API count=2; Agents completed list populated.
  - Refresh triggered Loading… states then reloaded.
  - Navigated away to `/` then back to `/workspace`; re-entered same local identity `abuse-test-user-20260905` / `agent-col`.
  - After return (no chat turn): Notes showed Cross/Test note proposals; Memory showed dark-mode pending; Agents history present — without requiring chat completion.
  - Authoritative APIs independently: artifacts=2 active; memory unresolved_proposals=1; notes active list 0 with pending proposals in UI.
- **RESULT:** PASS
- **JOB ID(s):** n/a (surface inspection)
- **SESSION / WORKSPACE:** `abuse-test-user-20260905` / `agent-col` (new browser session after re-entry; prior chat session not auto-restored into composer)
- **RESOURCE TYPE:** Memory, Notes, Artifacts, Agents
- **REQUEST PATH(S):** `GET .../memory`; `GET .../notes`; `GET .../artifacts`; `GET .../agent/jobs`; workspace reload
- **SCREENSHOT(S):** `06-resource-surfaces-after-refresh.png`
- **BACKEND LOG EVIDENCE:** resource GETs 200 after refresh/re-entry
- **BROWSER CONSOLE / NETWORK EVIDENCE:** surfaces populated post-refresh without chat
- **DEFECT CLASSIFICATION:** none

### TEST 7 — Terminal job/event/report/resource consistency

- **TEST:** Follow at least one job per resource family to terminal; verify job/report/resource agree; no duplicate terminals.
- **EXPECTED:** Matching terminal status across job and report; resources/labels agree; no duplicate terminals.
- **OBSERVED:**
  - Families checked: Artifact `002`/`011`, Note `004`/`008`, Memory completed `014` and failed `003`/`007`.
  - 16 jobs / 16 reports; zero duplicate job_refs; zero job/report status mismatches.
  - Artifact 011 report: completed “Artifact created” with public label for Abuse Cross Artifact 05.
  - Note 008 report: completed “Workspace note proposal pending review” / Abuse Cross Note 05.
  - Memory 014 report: completed “Memory proposal pending review” / Prefers dark-mode UI…
  - Failed Memory 003/007 reports: failed “Memory proposal not created” matching job failure_summary.
  - Event streams require raw `job_id` (not exposed in public list); event ordinals not fetched via public job_ref — limitation noted, not a contradiction of job/report/resource agreement.
- **RESULT:** PASS (with event-stream raw-id limitation noted)
- **JOB ID(s):** `jobref_...086dd73b` (artifact), `jobref_...5673cc7e`/`...c99b05a8` (notes), `jobref_...786a90a7` (memory completed), failed `...e23c3fc1`/`...75dce115`
- **SESSION / WORKSPACE:** `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** Artifact, Note, Memory
- **REQUEST PATH(S):** `GET .../agent/jobs`; `GET .../agent/reports`
- **SCREENSHOT(S):** `07-terminal-job-report-consistency.png` (Agents/reports view after re-entry)
- **BACKEND LOG EVIDENCE:** job and report projections agree
- **BROWSER CONSOLE / NETWORK EVIDENCE:** 16/16 paired terminal outcomes
- **DEFECT CLASSIFICATION:** none

### TEST 8 — Retry flow

- **TEST:** If a safe reproducible failed job can be produced without source edits, retry it; verify lineage, dispatch, preserved input, no duplicate mutation.
- **EXPECTED:** Retry of a retryable failed AgentJob creates correct lineage without duplicate resource mutation. If no safe failure is available, record NOT EXECUTED.
- **OBSERVED:**
  - Natural failed AgentJobs present: `jobref_3d75906c165cb2d5f5d4c3f5e23c3fc1` (#003) and `jobref_2879635fc17892d5af32a46b75dce115` (#007), both `propose_memory_signal` / `invalid_memory_candidate` with `failure_summary.retryable: false`.
  - Workspace job list: 16 jobs, `any_retryable=False` — no retryable terminal failure exists.
  - Public list projections expose `job_ref` only; AgentJob retry API requires raw `job_id` + `Idempotency-Key` (`POST .../agent/jobs/{job_id}/retry`). UI normal paths do not surface that raw ID.
  - Visible “Retry exact request” control is chat-turn exact retry (`data-retry-turn`), not AgentJob retry — and is not applicable without a failed chat turn.
  - Manufacturing a retryable failure would require source changes, which are out of scope for this evidence pass.
- **RESULT:** NOT EXECUTED — no safe failure available
- **JOB ID(s):** candidate failed (non-retryable): `jobref_3d75906c165cb2d5f5d4c3f5e23c3fc1`, `jobref_2879635fc17892d5af32a46b75dce115`
- **SESSION / WORKSPACE:** `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** Memory (failed, non-retryable)
- **REQUEST PATH(S):** `GET .../agent/jobs` (inspected failure_summary.retryable)
- **SCREENSHOT(S):** `08-retry-flow.png`
- **BACKEND LOG EVIDENCE:** n/a for AgentJob retry (not invoked)
- **BROWSER CONSOLE / NETWORK EVIDENCE:** Job reports empty for new session after re-entry; Agents completed list session-scoped empty; no AgentJob retry request issued
- **DEFECT CLASSIFICATION:** none for this test path (natural failures non-retryable + raw job_id not in public list)

### TEST 9 — Session switching with active jobs

- **TEST:** Start background resource work; switch to another chat/session; return to the original session; verify jobs/reports/resources remain associated with the correct session/workspace.
- **EXPECTED:** Jobs and resulting resources stay bound to the originating session/workspace across New conversation and Chats switches.
- **OBSERVED:**
  - Origin session: `session--cede757d-3991-4b3a-8c5c-e918036b0544` (“Create artifact now short markdown”).
  - Queued/completed on origin: `jobref_...8b6ea005` create_artifact (ran ~17s; poll captured `running` then `completed`); `jobref_...9f059eb8` create_artifact (`abuse_session_switch_note.md`); `jobref_...af76f9e7` propose_collaborative_note (`Abuse Session Switch Note 09`).
  - Jobs complete very quickly; mid-flight UI switch during nonterminal status was only partially captured for the first artifact (API poll showed `running`). Note job was already terminal before New conversation click.
  - Switched via New conversation → Control chat (`session--f0c41a04-...`) → back to origin. Workspace Artifacts/Notes/Memory remained populated independently of the empty new conversation.
  - Session-filtered API: origin has exactly those 3 jobs; Control chat retains prior 16 jobs — no cross-session job list mixing.
  - On return to origin, Agents “Completed (this session)” showed Artifact Builder ×2 + Note Curator for the origin labels; chat preview reflected Session Switch Note 09.
  - Visibility note: automation briefly drove a hidden MCP tab; testing continued on the visible Glass browser at `/workspace` after re-entry.
- **RESULT:** PASS (association). Active-window switch timing limited by fast job completion.
- **JOB ID(s):** `jobref_72700d1b706c088529c16d7f8b6ea005`, `jobref_...9f059eb8`, `jobref_...af76f9e7`
- **SESSION / WORKSPACE:** origin `session--cede757d-3991-4b3a-8c5c-e918036b0544`; other `session--f0c41a04-8f51-46f7-9e8f-7fd5eef7a809`; user `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** Artifact + Collaborative Note
- **REQUEST PATH(S):** `POST /api/chat/stream`; `GET .../agent/jobs?session_id=...`; Chats session select / New conversation
- **SCREENSHOT(S):** `09-session-switch-active-jobs.png`
- **BACKEND LOG EVIDENCE:** session-scoped job lists diverge correctly (3 vs 16)
- **BROWSER CONSOLE / NETWORK EVIDENCE:** Glass tab at `http://127.0.0.1:8000/workspace`; Agents completed list matches origin session jobs after return
- **DEFECT CLASSIFICATION:** none for association. Observation: model text again claimed inability to queue background artifact tools while AgentJobs completed (related to D2). Extra create_artifact labeled `abuse_session_switch_note.md` appeared alongside the note proposal.

### TEST 10 — Queued-job restart recovery

- **TEST:** Safely obtain a durable queued AgentJob; stop backend before worker executes; restart; verify drain discovers it, executes once, reaches terminal.
- **EXPECTED:** Queued job recovered by startup/runtime drain after restart.
- **OBSERVED:**
  - Cannot safely obtain a durable `queued` AgentJob without source edits: chat-created jobs are dispatched in-process immediately and leave nonterminal within ~3s (artifact poll: running→completed in ~3s).
  - Runtime/startup drain is currently failing on every cycle due to D1: `list_expired_running_jobs` missing Firestore composite index → `ERROR:main:AgentJob runtime drain failed.` The drain helper runs expired-running recovery first inside one try/except, so when that query fails the subsequent `list_queued_jobs` dispatch path is not reached either.
  - Manufacturing a stuck queued job or delaying dispatch would require source/runtime changes — out of scope.
- **RESULT:** NOT EXECUTED — cannot produce durable queued job safely; drain also blocked by D1
- **JOB ID(s):** n/a
- **SESSION / WORKSPACE:** `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** n/a
- **REQUEST PATH(S):** observed via backend logs + job polls
- **SCREENSHOT(S):** none (no executable scenario); see D1 log evidence
- **BACKEND LOG EVIDENCE:** recurring `AgentJob runtime drain failed` / `Firestore list_expired_running_jobs operation failed`
- **BROWSER CONSOLE / NETWORK EVIDENCE:** n/a
- **DEFECT CLASSIFICATION:** D1 (B/D) blocks drain path needed for this recovery test

### TEST 11 — Running-job / expired-lease recovery

- **TEST:** Terminate backend while a job is visibly running; after lease expiry, verify single recovery/execution without duplicate mutation. Do not modify lease constants.
- **EXPECTED:** No steal before lease expiry; post-expiry recovery executes once.
- **OBSERVED:**
  - AgentJob leases are 120s (`_ARTIFACT_JOB_LEASE_SECONDS` / note / memory = 120). Ordinary jobs complete in seconds, far before lease expiry.
  - Stopping the backend mid-run is possible in principle, but expired-running recovery uses the same `list_expired_running_jobs` query that is failing (D1), so post-restart recovery of an expired running job cannot be validated with the current runtime.
  - Waiting ≥120s with a manufactured stuck running job would require source changes or unsafe interference — out of scope.
- **RESULT:** NOT EXECUTED — not practical without source changes; recovery query blocked by D1
- **JOB ID(s):** n/a
- **SESSION / WORKSPACE:** `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** n/a
- **REQUEST PATH(S):** code/lease constants + drain logs
- **SCREENSHOT(S):** none
- **BACKEND LOG EVIDENCE:** same D1 drain failures; lease constants 120s vs observed ~3–17s job lifetimes
- **BROWSER CONSOLE / NETWORK EVIDENCE:** n/a
- **DEFECT CLASSIFICATION:** D1 (B/D) prevents validating expired-running recovery

### TEST 12 — Shutdown hygiene

- **TEST:** Shut down while jobs/drainer activity exists; verify clean shutdown; restart and verify durable unfinished work recovers normally.
- **EXPECTED:** Shutdown completes without leaked worker / pending-task warnings; restart recovers durable unfinished work.
- **OBSERVED:**
  - Drain loop was actively erroring (D1) at shutdown time — proves drainer activity present.
  - Graceful SIGINT to uvicorn: logs show `Shutting down` → `Waiting for application shutdown.` → `Application shutdown complete.` → `Finished server process` → `Stopping reloader process`. No pending-task / leaked-worker warnings observed in the shutdown sequence.
  - Restart with `AGENT_COL_AUTH_MODE=local_dev`: `Application startup complete` after `AgentJob startup drain failed` (D1 again). Workspace HTTP 200.
  - Re-entered local identity on visible Glass tab; workspace UI loaded post-restart.
  - No durable unfinished AgentJobs were present to recover (all prior jobs already terminal); therefore recovery of unfinished work could not be positively demonstrated — limited by job speed + D1 drain failure.
- **RESULT:** PASS for clean shutdown sequence. Recovery of unfinished work NOT demonstrated (none pending; D1 blocks drain).
- **JOB ID(s):** n/a (no unfinished jobs at stop)
- **SESSION / WORKSPACE:** `abuse-test-user-20260905` / `agent-col`
- **RESOURCE TYPE:** n/a
- **REQUEST PATH(S):** process SIGINT; restart uvicorn; `GET /workspace`
- **SCREENSHOT(S):** `12-shutdown-hygiene.png`
- **BACKEND LOG EVIDENCE:** clean shutdown lines; startup drain failed (D1); Application startup complete
- **BROWSER CONSOLE / NETWORK EVIDENCE:** Glass `/workspace` identity re-entry after restart succeeded
- **DEFECT CLASSIFICATION:** D1 continues to block startup/runtime drain recovery path


### TEST 13 — Frontend abuse / soak (authoritative expanded mixed-use)

- **TEST:** For at least 10 minutes, aggressively mix ordinary chat; Memory/Note/Artifact creation requests; drawer/Agents open-close; job/resource status checks; session switching; soft refresh; navigate away/back; revisit completed/failed states. Look for stale/duplicate/stuck UI, incorrect association, disabled composer, console errors, non-authoritative surface refresh.
- **EXPECTED:** UI remains usable across overlapping transitions; no stuck pending composer; no duplicate terminal identities; surfaces refresh authoritatively; defects recorded if observed.
- **OBSERVED:**
  - Authoritative expanded soak (not the earlier drawer-toggle-only attempt) ran via Chrome-for-Testing CDP against `http://127.0.0.1:8000/workspace` for **635s** (≥600s). Driver note: Glass MCP tab could not be held by the soak subagent; same app URL used.
  - Activity mix (from `soak13-mixed-log.jsonl` / `soak13-result.json`): 103 cycles; chats control=39, memory=13, note=13, artifact=13; drawer thrash ×77; session switches ×34; soft refresh ×13; nav away/back ×4; Agents/report inspect ×25; identity re-entry events ×112 (post-nav/reload).
  - Final UI snap: Send not disabled; Agents `0 active · 0 queued`; pending notes visible; URL `/workspace`; `consoleErrors: []`; soak `findings: []`.
  - Workspace job list stayed at 19 jobs (17 completed / 2 failed) throughout job polling (`soak13-job-poll.jsonl`) — no new AgentJobs appeared despite Memory/Note/Artifact chat requests completing turns. Overlapping nonterminal AgentJob windows were therefore not observed during this soak; UI soak hygiene still exercised. Related to earlier D2-style model/tool-queue mismatch observations.
  - Soft refresh and nav away/back returned to usable workspace after identity re-entry; composer remained usable for follow-up control chats.
  - Session stopped on user request after soak evidence landed; no further testing.
- **RESULT:** PASS (UI soak hygiene / no stuck composer / no console errors). Limitation: little/no new AgentJob overlap during soak (job count unchanged).
- **JOB ID(s):** no new jobrefs created during soak window; prior workspace jobs remained 19 total
- **SESSION / WORKSPACE:** `abuse-test-user-20260905` / `agent-col` (multiple chat sessions switched during soak)
- **RESOURCE TYPE:** Memory + Note + Artifact requests attempted; chat + Agents/Notes/Artifacts/Memory surfaces exercised
- **REQUEST PATH(S):** `POST /api/chat/stream`; `GET .../agent/jobs`; workspace refresh/navigation; Chats/Agents UI
- **SCREENSHOT(S):** `13-final-soak-state.png`
- **BACKEND LOG EVIDENCE:** D1 drain errors continue independently; soak job poll shows stable 19-job terminal inventory
- **BROWSER CONSOLE / NETWORK EVIDENCE:** `soak13-mixed-log.jsonl`, `soak13-result.json`, `soak13-job-poll.jsonl`; no console errors captured by driver
- **DEFECT CLASSIFICATION:** none new from soak findings list. Observation continues D2-like: resource-creation chats can finish without increasing AgentJob inventory. D1 remains active in backend logs.

---

## End-of-pass summary

**Checkpoint under test:** `b62de150d5b30c11c24dc5b2f0546a8eeed281ee` (`main`)
**Auth:** `AGENT_COL_AUTH_MODE=local_dev`
**Scope:** Runtime acceptance / evidence only. No application source/test changes.

### Counts

| Result | Count |
| --- | ---: |
| PASS | 10 |
| FAIL | 0 |
| NOT EXECUTED | 3 |
| **Total tests** | **13** |

PASS: Tests 1–7, 9, 12, 13
NOT EXECUTED: Tests 8 (no safe retryable failure), 10 (no durable queued job + D1 blocks drain), 11 (lease/recovery not practical + D1)

### Defects

| ID | Class | Summary |
| --- | --- | --- |
| D1 | B/D | Missing Firestore composite index for `list_expired_running_jobs` → startup/runtime drain fails; blocks queued/expired-running recovery validation |
| D2 | C/D | Model text claimed background tools inactive / resource chats completed without new AgentJob inventory growth despite successful AgentJobs in earlier tests |
| D3 | — | Explicit Memory jobs failed terminal `invalid_memory_candidate` / `retryable: false` (validation outcome; async ownership still held) |

### Evidence files under `docs/abuse-testing-evidence/`

Screenshots: `01`–`09`, `12`, `13-final-soak-state.png`
Report: `abuse-testing-report.md`
Poll/logs: `job-poll-samples.jsonl`, `cross-surface-poll.jsonl`, `session-switch-poll.jsonl`, `soak13-job-poll.jsonl`, `soak13-mixed-log.jsonl`, `soak13-result.json`, `soak13-meta.json`, `soak13-start.txt`, `soak13-start-epoch.txt`
Soak helpers (evidence support only): `soak13-runner.js`, `soak13-mixed-driver.mjs`, `soak13-cdp-expr.txt`, `soak13-chunks.json`, `soak13-chunks/`, `soak13-chunks-wrapped/`

**Session stopped by user request. No further testing. No source fixes.**
