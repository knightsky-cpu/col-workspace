# Abuse / Acceptance Post-Fix Retest Report

**Retest of checkpoint:** `4ce7e88279edfe0dbd03c2de6555cb632cc6139c`
**Branch:** `main`
**Date:** 2026-09-05
**Prior campaign evidence (preserved, not overwritten):** `docs/abuse-testing-evidence/` at prior checkpoint `b62de150…`
**Auth mode:** `AGENT_COL_AUTH_MODE=local_dev`
**App URL:** `http://127.0.0.1:8000/workspace`
**Scope:** Post-fix manual retest / regression. No application source or test edits. No git state changes. Evidence only under `docs/abuse-testing-retest-evidence/`.

## Preflight

- Branch: `main` — verified
- HEAD: `4ce7e88279edfe0dbd03c2de6555cb632cc6139c` — verified
- Worktree: clean — verified
- Backend start command: `AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000`

## Defects under retest

| ID | Prior class | Prior summary | Retest goal |
| --- | --- | --- | --- |
| D1 | B/D | Missing Firestore index / drain failure | Confirm absent at startup/runtime |
| D2 | C/D | Contradictory “background tools unavailable” vs queued jobs | Consistent messaging with receipts |
| D3 | — | `invalid_memory_candidate` on Memory jobs | Valid Memory completes governed path |
| Draft | C | Notes/Artifact drafts reset unexpectedly | Drafts survive chat/job refresh; clear on submit |

## Test log

### Preflight runtime verification

- Backend started: `Application startup complete` — verified
- Health `GET /` → `{"status":"online"}` — verified
- Workspace `GET /workspace` → 200 — verified
- After ≥8s runtime: **no** `list_expired_running_jobs` / `AgentJob startup drain failed` / `AgentJob runtime drain failed` in backend log — **D1 absent** (resolved in environment)

### Retest identity

- User / project: `abuse-retest-20260905` / `agent-col`

### RETEST D2 — Queued-action messaging consistency

- **TEST:** Rerun artifact scenario that previously claimed background tools unavailable; confirm messaging matches authoritative queued receipt/job.
- **EXPECTED:** Model describes queued work consistently with `Queued action` receipt and AgentJob inventory growth.
- **OBSERVED:**
  - Prompt: create Artifact "Retest D2 Artifact" with two bullets; queue immediately.
  - Assistant: “An artifact creation job … has already been queued for background processing” + lifecycle status Queued; receipt `Queued action: Artifact Builder · Artifact: structured blueprint · Queued`.
  - No contradictory “tools inactive / cannot queue” claims (`claimsInactive=false`).
  - AgentJob `jobref_b2ecd2626f1295af2da3a35cc4ec5130` (`create_artifact`) ran→completed; Artifacts Viewer populated.
- **RESULT:** PASS (product)
- **SCREENSHOT(S):** `d2-artifact-consistent-messaging.png`
- **ISSUE CLASS:** prior D2 product defect appears resolved for this scenario

### RETEST D3 — Memory invalid_memory_candidate scenarios

- **TEST:** Rerun prior failing Memory prompts (communication_style; dark-mode/user_requested; nested/clarify multi-candidate).
- **EXPECTED:** Valid Memory work completes governed path (completed job + pending proposal / successful clarification handling) without `invalid_memory_candidate`.
- **OBSERVED:**
  1. Exact prior communication_style prompt → job `jobref_1b2ca23e8e52b3fd89d4d196d9ef5145` **completed**; report “Memory proposal pending review”; Memory UI pending “Prefers concise bullet answers…”. **PASS for this scenario.**
  2. Prior dark-mode prompt → job `jobref_ed4ccd508bf458bb9f93cabe020274f6` (`Memory request: user_requested_memory`) **failed** `invalid_memory_candidate` / `retryable:false`; report “Memory proposal not created”. **FAIL (product).**
  3. Nested multi-preference prompt (pancakes + concise) → queued `Memory clarification` then job **failed** `invalid_memory_candidate` (`Memory clarification`). Chat correctly identified two candidates; worker still rejected. **FAIL (product).**
- **RESULT:** PARTIAL — communication_style fixed; remaining invalid_memory_candidate failures on user_requested_memory + clarification/nested path
- **SCREENSHOT(S):** `d3-communication-style-memory-completed.png`, `d3-dark-mode-memory-failed.png`, `d3-nested-memory-clarification-failed.png`
- **ISSUE CLASS:** product behavior (do not fix in this campaign)

### RETEST DRAFT — Notes/Artifact draft survival

- **TEST:** Unsent Notes + Artifact drafts survive prompt send, response start/complete, unrelated AgentJob/resource refresh; successful submit clears own draft.
- **EXPECTED:** Draft markers persist across chat/job refresh; note submit clears note title/body only.
- **OBSERVED:**
  - Markers set: Notes title `DRAFT-NOTE-TITLE-RETEST-KEEP`, body `DRAFT-NOTE-BODY-RETEST-KEEP…`, Artifact feedback `DRAFT-ARTIFACT-FEEDBACK-RETEST-KEEP`.
  - Survived control chat send (response start), completion (`DRAFT-OK`), Agents open, and workspace Refresh/resource reload — all three markers remained.
  - Successful Create note proposal created pending `note_proposal--741d3730…` with those title/body values.
  - After successful submit, Notes create form **still retained** title/body draft markers (not cleared). Artifact feedback draft correctly remained (other form).
  - Root observation: `submitAndClearDraft` awaits submit before `drafts.delete`, so notes-state re-render during submit redraws the form from the still-present draft Map entry.
- **RESULT:** PARTIAL — survival PASS; clear-on-submit FAIL (product)
- **SCREENSHOT(S):** `draft-after-successful-note-submit-not-cleared.png`
- **ISSUE CLASS:** product (draft clear ordering); survival fix verified

### HARNESS — 4-message submission-proof

- **TEST:** Prove short harness for ordinary chat, Memory, Note, Artifact before full soak.
- **EXPECTED:** Each send proves textarea value, `/api/chat/stream`, transcript message, stream completion, and resource receipt/no-action.
- **OBSERVED:**
  - Harness fix: chat composer selected via `textarea[maxlength=10000]` (first textarea was Notes body maxlength 2000 — prior soak false-negative root cause / harness bug).
  - PROOF-1 ordinary chat → `send_ok` stream#1 status 200; transcript hit; reply `PROOF-CHAT-OK`.
  - PROOF-2 Memory → `send_ok` stream#2; receipt Memory Analyst; job later `memory_proposal_conflict` (pending already exists) — product outcome after successful queue, not harness fail.
  - PROOF-3 Note → `send_ok` stream#3; receipt `Note Curator · Workspace note: Retest Harness Note 03`; job completed.
  - PROOF-4 Artifact → `send_ok` stream#4; receipt `Artifact Builder · Artifact: retest_harness_artifact_04.md`; job completed.
- **RESULT:** PASS (all four `send_ok`)
- **EVIDENCE:** `harness-4msg-proof.jsonl`, `soak13-submission-proof-harness.js`
- **ISSUE CLASS:** prior soak job-count stagnation attributed partly to harness/test-environment (wrong textarea), not solely product

### RETEST matrix (updated after recovery tests 8/10/11/12)

| Area | Result | Notes |
| --- | --- | --- |
| D1 drain index | RESOLVED (env) | Absent after startup/runtime and post-SIGINT restart |
| D2 messaging | PASS | Consistent with receipts |
| D3 Memory | PARTIAL | communication_style PASS; dark-mode + nested clarify still `invalid_memory_candidate` |
| Draft survival | PASS | Survives send/response/refresh |
| Draft clear-on-submit | FAIL | Form retains values after successful note proposal |
| Harness 4-msg proof | PASS | All send_ok |
| TEST 8 retry | NOT EXECUTED | No `retryable:true` failed job |
| TEST 10 queued restart | NOT EXECUTED | Cannot keep durable `queued` through restart (in-process lease race) |
| TEST 11 expired-running | FAIL | Recovery re-leases same job; re-exec hits `AgentJobEvent` event_id conflict loop |
| TEST 12 shutdown hygiene | PASS | Clean SIGINT + restart; D1 absent |

### TEST 8 — Retry flow (retest)

- **TEST:** Retry a safe genuine retryable failed AgentJob without unsupported datastore mutation.
- **EXPECTED:** Retry lineage/dispatch correct; or NOT EXECUTED if no safe failure.
- **OBSERVED:**
  - Workspace jobs scanned for identity `abuse-retest-20260905` / `agent-col` (and prior abuse-test user for completeness).
  - Failed jobs present include `invalid_memory_candidate` and `memory_proposal_conflict`; all expose `failure_summary.retryable: false`.
  - `any_retryable=False` — no genuine retryable terminal failure available.
  - Public list projections expose `job_ref` only; AgentJob retry API requires raw `job_id` + `Idempotency-Key`.
  - Manufacturing a retryable failure would require unsupported source/datastore mutation (out of scope).
- **RESULT:** NOT EXECUTED — no safe retryable failure available
- **EVIDENCE:** `test8-jobs-scan.json`, `t8-t10-t11-t12-summary.json`
- **ISSUE CLASS:** none for this test path; product Memory failures remain non-retryable

### TEST 10 — Queued-job restart recovery (retest)

- **TEST:** Obtain durable `queued` AgentJob; stop backend before worker executes; restart; verify drain discovers and executes once.
- **EXPECTED:** Startup/runtime drain discovers queued job, executes once, reaches terminal.
- **OBSERVED:**
  - D1 drain-index failure **absent** before and after restart (`d1-absence-pre-recovery.json`, `d1-absence-post-restart.json`; 0× `list_expired_running_jobs operation failed` / `AgentJob startup|runtime drain failed` / index errors). Startup log shows `list_expired_running_jobs` + `list_queued_jobs` queries succeeding into `Application startup complete`.
  - Attempted live capture: chat-queued artifact `jobref_d20bcc1ad72cf7fc4f30eee80a8d6e10` briefly observed as `queued` (~12:20:06Z), then SIGINT backend.
  - Race: in-process dispatcher leased the job before process death completed. After restart (~12:20:15Z) the durable persisted state was already `running` (lease `…T12:22:06.598218Z`), not `queued`.
  - Therefore a durable **queued** restart-recovery scenario was not achieved without source/runtime delay or datastore mutation.
  - (Same kill/restart experiment continued as TEST 11 for expired-running path.)
- **RESULT:** NOT EXECUTED — cannot safely produce durable queued job that survives restart still queued (D1 no longer the blocker)
- **EVIDENCE:** `t10-t11-timeline.json`, `t10-t11-prekill-poll.jsonl`, `t10-post-restart-poll.json`, `t10-t11-stop-backend.json`, `t10-t11-start-backend.json`, `t10-t11-restart-uvicorn.log`, `t10-t11-recovery-orchestrator.py`
- **ISSUE CLASS:** setup limitation (in-process immediate dispatch), not D1

### TEST 11 — Expired-running / lease recovery (retest)

- **TEST:** Terminate backend while job running; wait real 120s lease lifecycle (constants unmodified); restart; verify same-job single recovery/execution.
- **EXPECTED:** No steal before lease expiry; post-expiry recovery executes once to terminal without duplicate mutation.
- **OBSERVED:**
  - Lease constants remain `_ARTIFACT_JOB_LEASE_SECONDS = 120` (unchanged).
  - From TEST 10 kill race: job `jobref_d20bcc1ad72cf7fc4f30eee80a8d6e10` (`create_artifact`) survived restart as `running` with real lease.
  - Quick restart (~2.6s to healthy) then waited full lease cycles while backend up (runtime drain interval 60s).
  - Lease renewal / recovery cycles observed on the **same** `job_ref` / `attempt_count=1`:
    - leased `updated_at=12:20:06Z` → `lease_expires_at=12:22:06Z`
    - recovered/re-leased `updated_at=12:22:16Z` → `lease_expires_at=12:24:16Z`
    - recovered/re-leased `updated_at=12:24:17Z` → `lease_expires_at=12:26:17Z`
  - Drain/recovery path is active and D1 remains absent; however each re-execution attempt fails with `AgentJobEvent conflicts with existing event_id` (8 occurrences in restart log) because partial events from the interrupted first run collide on re-append.
  - Job remained nonterminal (`running`) through observed cycles; blueprints list stayed empty for this work; single successful completion **not** achieved.
  - Product defect on recovery re-execution (event idempotency / conflict) — not fixed in this campaign.
- **RESULT:** FAIL (product) — expired-running discovery/re-lease works; same-job recovery does not complete cleanly (event_id conflict loop)
- **JOB ID(s):** `jobref_d20bcc1ad72cf7fc4f30eee80a8d6e10`
- **EVIDENCE:** `t11-lease-expiry-poll.json`, `t11-final-jobs.json`, `t11-event-conflict-excerpts.txt`, `t11-reports.json`, `t11-blueprints.json`, `t10-t11-restart-uvicorn.log`, `t8-t10-t11-t12-summary.json`
- **ISSUE CLASS:** product (recovery re-execution / event_id conflict); D1 not implicated

### TEST 12 — Shutdown hygiene (optional retest)

- **TEST:** Clean SIGINT restart without long disruption; confirm shutdown/startup hygiene and D1 absence.
- **EXPECTED:** Clean stop; restart reaches `Application startup complete`; health online; drain queries do not fail on missing index.
- **OBSERVED:**
  - SIGINT to uvicorn PIDs (98655/98661) → process tree cleared; health false.
  - Restart `AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000` → ready in ~2.6s; `GET /` online.
  - Startup performed `list_expired_running_jobs` + `list_queued_jobs` without index/drain ERROR; `Application startup complete`.
  - Unfinished running job remained for TEST 11 observation (see above); recovery of unfinished work partially demonstrated (re-lease) but not clean terminal completion.
- **RESULT:** PASS for clean shutdown/restart hygiene + D1-absent startup drain. Full unfinished-work terminal recovery FAIL per TEST 11.
- **EVIDENCE:** `t10-t11-stop-backend.json`, `t10-t11-start-backend.json`, `t12-restart-log-head.txt`, `d1-absence-post-restart.json`
- **ISSUE CLASS:** none for shutdown path; unfinished recovery limited by TEST 11 product defect

### D1 status (recovery retest)

- **RESULT:** D1 remains **absent** (resolved in environment) across pre-recovery runtime log and post-SIGINT restart log.
- **EVIDENCE:** `d1-absence-pre-recovery.json`, `d1-absence-post-restart.json`

### REGRESSION RERUN — Tests 1–7, 9, 12 (API-primary)

**When:** 2026-09-05 (~12:25–12:28Z)
**Identity:** `abuse-retest-20260905` / `agent-col`
**Regression session:** `session--a1b2c3d4-e5f6-7890-abcd-ef1234567890`
**Session B (Test 9):** `session--b2c3d4e5-f6a7-8901-bcde-f12345678901`
**Constraint adherence:** No git changes; no app source/test edits; evidence only under `docs/abuse-testing-retest-evidence/`. Concurrent ≥10min Glass soak continued polling `session--3f7d5db0-da58-4003-a7d4-94a41ab1c823` — regression chats used a **separate session**; backend **not** killed for this wave. Screenshots via separate Chrome-for-Testing CDP on `:9335`/`:9334` (Glass `:9333` left alone).
**Helpers:** `retest-1-7-9-api-runner.py`, `retest-1-7-9-results.json`, `retest-1-7-9-matrix.json`, `retest-1-7-9-api-runner.log`, `retest-1-7-9-screenshots.mjs`

#### TEST 1 — Control chat (retest)

- **TEST:** Ordinary conversational message; no resource action; chat completes; no explicit AgentJob for that turn.
- **EXPECTED:** Chat completes; `queued_actions=[]`; no create_artifact / propose_* job from the control turn.
- **OBSERVED:** Reply “Receipt of your control message is confirmed.”; `queued_actions=[]`; session jobs before/after unchanged for explicit resource kinds.
- **RESULT:** PASS
- **JOB ID(s):** none (explicit)
- **SCREENSHOT(S):** `retest-01-control-chat.png` (session list + later transcript context; API is authoritative for turn zero-actions)
- **ISSUE CLASS:** none

#### TEST 2 — Artifact while chatting (retest)

- **TEST:** Queue artifact; continue chatting; job independent of chat completion.
- **EXPECTED:** Chat queues artifact; follow-up chat works; AgentJob reaches terminal independently; messaging consistent with receipt (prior D2).
- **OBSERVED:**
  - Chat queued `Artifact Builder · Artifact: structured blueprint`; `claims_inactive=false` (no contradictory inactive-tools claim).
  - Job `jobref_1d39bb053068a07be5dece720ff7ff4a` completed (~10s).
  - Follow-up reply exact `CHAT-STILL-RESPONSIVE`.
- **RESULT:** PASS (also reinforces D2 fixed for this scenario)
- **JOB ID(s):** `jobref_1d39bb053068a07be5dece720ff7ff4a`
- **SCREENSHOT(S):** `retest-02-artifact-while-chatting.png`
- **ISSUE CLASS:** none (D2 remains resolved)

#### TEST 3 — Memory while chatting (retest)

- **TEST:** Explicit Memory proposal; chat remains usable; Memory job lifecycle independent.
- **EXPECTED:** Async ownership held; chat follow-up works regardless of Memory terminal validation outcome.
- **OBSERVED:**
  - Chat described Memory queued for background processing; follow-up `OK`.
  - Job `jobref_bdc36509a31869f17d99d0405328239d` terminal **failed** `memory_proposal_conflict` / `retryable:false` (pending proposal already exists from earlier D3 communication_style success) — not ownership failure.
  - Known remaining D3: some Memory paths still fail validation/conflict; do not fix in this campaign.
- **RESULT:** PASS (async ownership)
- **JOB ID(s):** `jobref_bdc36509a31869f17d99d0405328239d` (failed conflict)
- **SCREENSHOT(S):** `retest-03-memory-while-chatting.png` (Memory pending proposal visible)
- **ISSUE CLASS:** known product D3 partial / pending-proposal conflict (not ownership)

#### TEST 4 — Collaborative Note while chatting (retest)

- **TEST:** Note proposal while chatting; Notes surface/job independent.
- **EXPECTED:** Note AgentJob completes; pending proposal appears; follow-up chat works.
- **OBSERVED:**
  - Queued Note Curator for `Abuse Retest Note 04`.
  - Job `jobref_aa2688211599ec58bfbd30f9556d49a4` completed; Notes API pending includes `Abuse Retest Note 04`.
  - Follow-up `READY`.
  - Side observation: model also created accompanying artifact `jobref_8adc981b8aa5bdd528b9655946bb064a` (`abuse_retest_note.md`) — extra resource, not identity cross.
- **RESULT:** PASS
- **JOB ID(s):** `jobref_aa2688211599ec58bfbd30f9556d49a4` (note); adjacent artifact `jobref_8adc981b8aa5bdd528b9655946bb064a`
- **SCREENSHOT(S):** `retest-04-note-while-chatting.png`
- **ISSUE CLASS:** none

#### TEST 5 — Cross-surface concurrency (retest)

- **TEST:** Queue Note + Artifact + Memory close together; distinct identities; chat responsive.
- **EXPECTED:** Distinct job refs/action_kinds; follow-up usable.
- **OBSERVED:**
  - Note `jobref_04baa4a27f8397622fb696854d6a725a` completed (`Abuse Retest Cross Note 05`).
  - Artifact `jobref_3cdd66db8182926176429b81035beb61` completed.
  - Memory `jobref_15518b15c4369bb76d8460e9db8a3b77` failed `memory_proposal_conflict` (pending already exists) — distinct ref/family retained.
  - Follow-up `PONG`. No job_ref/action_kind mixing across families.
- **RESULT:** PASS
- **JOB ID(s):** note `…4d6a725a`; artifact `…035beb61`; memory `…db8a3b77`
- **SCREENSHOT(S):** `retest-05-cross-surface-concurrency.png`
- **ISSUE CLASS:** none for identity; Memory conflict is known pending-state/D3 residue

#### TEST 6 — Resource-surface independence (retest)

- **TEST:** Authoritative Memory/Notes/Artifacts/Agents reload without requiring chat completion.
- **EXPECTED:** Surfaces reload from authoritative APIs after refresh-equivalent re-fetch.
- **OBSERVED:** Re-fetched without chat turn: memory unresolved_proposals=1; notes pending=4; artifacts active=5; jobs/reports present. UI screenshots show pending Notes/Memory and Active Artifacts populated independently of empty composer.
- **RESULT:** PASS
- **JOB ID(s):** n/a
- **SCREENSHOT(S):** `retest-06-resource-surfaces-after-refresh.png`
- **ISSUE CLASS:** none. Browser nav-away limited (soak on Glass); API + drawer refresh evidence used.

#### TEST 7 — Terminal job/event/report/resource consistency (retest)

- **TEST:** At least one terminal job per family; job/report status agree; no duplicate terminals.
- **EXPECTED:** Matching statuses; no duplicate job_refs.
- **OBSERVED:** Session-scoped 8 jobs / 8 reports; 0 mismatches; 0 duplicate refs. Families present: artifact completed, note completed, memory failed (conflict) with matching report text.
- **RESULT:** PASS
- **JOB ID(s):** see session pairs in `retest-1-7-9-results.json` (includes `…0ff7ff4a`, `…556d49a4`, `…5328239d`, …)
- **SCREENSHOT(S):** `retest-07-terminal-job-report-consistency.png`
- **ISSUE CLASS:** none (event raw-id limitation unchanged)

#### TEST 9 — Session switching with active jobs (retest)

- **TEST:** Resource work on origin session; switch to another session; verify association.
- **EXPECTED:** Jobs stay bound to originating `session_id`; no cross-session job-list mixing.
- **OBSERVED:**
  - Origin queued/completed `jobref_f02ff226e7524857a5f69f2709912c9c` (`Retest Session Switch Artifact 09`).
  - Session B control chat `SESSION-B-OK` (0 AgentJobs).
  - Session-filtered lists: origin 8 jobs; session B 0 jobs; intersection empty; origin artifact ref only in A.
  - UI shows both chat sessions listed; origin transcript includes queued artifact messaging.
- **RESULT:** PASS
- **JOB ID(s):** `jobref_f02ff226e7524857a5f69f2709912c9c`
- **SCREENSHOT(S):** `retest-09-session-switch-active-jobs.png`
- **ISSUE CLASS:** none. UI “New conversation” mid-flight limited by fast completion + soak; API session filter is authoritative.

#### TEST 12 — Shutdown hygiene (this regression wave)

- **TEST:** Shut down/restart while soak may be active.
- **EXPECTED:** Only execute if safe without interrupting soak.
- **OBSERVED:** Glass/soak client continued frequent `agent/jobs` + `jobs/stream` polls on soak session throughout this wave. Killing backend would interrupt soak. Prior recovery-wave TEST 12 already recorded separately above.
- **RESULT:** NOT EXECUTED (this wave) — would interrupt concurrent soak
- **JOB ID(s):** n/a
- **ISSUE CLASS:** test-environment coordination constraint

### Regression matrix (Tests 1–7, 9, 12)

| Test | Result | Key job ref(s) |
| --- | --- | --- |
| 1 Control chat | PASS | none (explicit) |
| 2 Artifact while chatting | PASS | `jobref_1d39bb053068a07be5dece720ff7ff4a` |
| 3 Memory while chatting | PASS (ownership) | `jobref_bdc36509a31869f17d99d0405328239d` (failed `memory_proposal_conflict`) |
| 4 Note while chatting | PASS | `jobref_aa2688211599ec58bfbd30f9556d49a4` |
| 5 Cross-surface concurrency | PASS | `jobref_04baa4a27f8397622fb696854d6a725a`, `jobref_3cdd66db8182926176429b81035beb61`, `jobref_15518b15c4369bb76d8460e9db8a3b77` |
| 6 Resource-surface independence | PASS | n/a |
| 7 Terminal job/report consistency | PASS | session pairs (8/8 matched) |
| 9 Session switching | PASS | `jobref_f02ff226e7524857a5f69f2709912c9c` |
| 12 Shutdown hygiene | NOT EXECUTED | n/a (soak active) |

### Known remaining product issues (unchanged; do not fix)

- **D3 partial:** some Memory jobs still fail (`invalid_memory_candidate` earlier; this wave also saw `memory_proposal_conflict` when pending already exists).
- **Draft clear-on-submit:** still fails (earlier retest).
- **D2:** appears fixed (consistent queued messaging; `claims_inactive=false` on artifact retest).

### TEST 13 — Frontend abuse / soak (post-fix retest)

- **TEST:** ≥10-minute mixed frontend soak with submission-proof harness (ordinary chat / Memory / Note / Artifact cycling; drawer thrash; Agents inspect; soft refresh; nav away/back). Operator stopped campaign after target duration.
- **EXPECTED:** Proven submissions (`send_ok`) throughout; UI remains usable; no stuck composer; surfaces refresh authoritatively; product defects recorded separately from harness failures.
- **OBSERVED:**
  - **Actual soak duration:** **655s** (~10.9 min) wall clock (`start_iso` `2026-09-05T12:27:25.417Z` → `end_iso` `2026-09-05T12:38:20.146Z`). Target was 600s; run exceeded target and was then stopped cleanly.
  - Driver: Chrome for Testing + Playwright `fill()` on `textarea[maxlength=10000]` (Glass MCP tabs unavailable to soak subagent).
  - Cycles attempted: 20. **`send_ok=0`, `send_fail=0`**. **15 `cycle_error`** events: Playwright timeout clicking chat composer — element resolved in DOM but **not visible** (final snap showed Local development identity gate / “Enter workspace”; drawer thrash repeatedly left composer obscured).
  - UI thrash still executed: drawer_thrash=6, inspect_agents=4, session_switch=4, soft_refresh=2, nav_roundtrip=2 (counts from soak_end result).
  - Job poll throughout: 16 jobs; statuses completed=10, failed=5, running=1. Nonterminal residual: `jobref_d20bcc1ad72cf7fc4f30eee80a8d6e10` (`create_artifact` / structured blueprint) — **prior TEST 11 product recovery loop**, not created by soak submissions.
  - **No D2/D3 product failures attributed to soak** (zero proven chat submissions). D2/D3 remain separate diagnostics (`d2-d3-unresolved-diagnostics.json`).
  - Pre-soak **4-message harness proof** separately PASS (`harness-4msg-proof.jsonl`) — proves submission-proof helpers work when composer is reachable; soak FAIL is harness/environment visibility, not a regression of that proof.
- **RESULT:** FAIL (harness/test-environment) — duration met; submission-proof soak objectives not met (`send_ok=0`).
- **EVIDENCE:** `soak13-meta.json`, `soak13-mixed-log.jsonl`, `soak13-job-poll.jsonl`, `soak13-result.json`, `soak13-mixed-driver.mjs`, `soak13-submission-proof-harness.js`, `13-final-soak-state.png`, `harness-4msg-proof.jsonl`
- **ISSUE CLASS:** harness/test-environment (composer not visible / identity gate after thrash). Residual running job is product TEST 11, recorded separately.

### Campaign stop / process shutdown

- Soak driver + Chrome-for-Testing (`.chrome-soak-profile`, prior PIDs 1713/1714 tree) stopped; ports 9333–9335 freed; soak poll file mtime stabilized.
- Backend (uvicorn PIDs 216/217/218 on `127.0.0.1:8000`, campaign-owned, logging to `t10-t11-restart-uvicorn.log`) stopped via SIGINT after evidence finalize; port 8000 FREE; health unreachable. Verification: `campaign-process-shutdown.json`.
- Original prior campaign under `docs/abuse-testing-evidence/` was **not** overwritten.

## Final campaign matrix

| ID | Area | Result | Class | Notes |
| --- | --- | --- | --- | --- |
| Preflight | git/backend/D1 absent | PASS | env | HEAD `4ce7e882…`, clean worktree, D1 absent |
| D1 | Firestore drain index | RESOLVED | env | Absent startup/runtime + post-restart |
| D2 | Queued messaging consistency | PASS | product resolved | `jobref_b2ecd262…` completed; no inactive-tools contradiction |
| D3a | Memory communication_style | PASS | product | `jobref_1b2ca23e…` completed; pending proposal |
| D3b | Memory dark-mode / user_requested | FAIL | product unresolved | `jobref_ed4ccd50…` `invalid_memory_candidate` |
| D3c | Memory nested clarification | FAIL | product unresolved | `jobref_b8835dd6…` `invalid_memory_candidate` |
| Draft | Survival across send/refresh | PASS | product resolved | markers survived |
| Draft | Clear-on-submit | FAIL | product unresolved | note form retained values after successful proposal |
| Harness | 4-msg submission proof | PASS | harness | chat/Memory/Note/Artifact all `send_ok` |
| TEST 1 | Control chat | PASS | — | |
| TEST 2 | Artifact while chatting | PASS | — | also reinforces D2 |
| TEST 3 | Memory while chatting | PASS | ownership | terminal `memory_proposal_conflict` (pending exists) |
| TEST 4 | Note while chatting | PASS | — | |
| TEST 5 | Cross-surface concurrency | PASS | — | Memory conflict residue |
| TEST 6 | Resource-surface independence | PASS | — | |
| TEST 7 | Terminal job/report consistency | PASS | — | |
| TEST 8 | Retry flow | NOT EXECUTED | setup | no `retryable:true` failure; public list lacks raw job_id |
| TEST 9 | Session switch + jobs | PASS | — | |
| TEST 10 | Queued restart recovery | NOT EXECUTED | setup | cannot hold durable `queued` through restart (in-process lease race); D1 not blocker |
| TEST 11 | Expired-running recovery | FAIL | product | same-job re-lease then `AgentJobEvent` event_id conflict loop |
| TEST 12 | Shutdown hygiene | PASS | — | recovery wave; regression-wave NOT EXECUTED (soak active) |
| TEST 13 | ≥10 min mixed soak | FAIL | harness/env | 655s; `send_ok=0`; composer not visible |

## Acceptance readiness (async-decoupling path)

| Item | Verified resolved? |
| --- | --- |
| D1 | **Yes** (environment) |
| D2 | **Yes** |
| D3 | **No** (partial; D3b/D3c unresolved) |
| Frontend draft survival | **Yes** |
| Frontend draft clear-on-submit | **No** |
| TEST 11 recovery | **No** (new FAIL) |
| TEST 13 soak proof | **No** (harness/env FAIL; not product soak defect) |
| Ready for final acceptance? | **No** — block on D3 remaining failures, draft clear-on-submit, TEST 11 event_id conflict, and a successful submission-proven soak |

## Evidence index (this campaign)

- Report: `docs/abuse-testing-retest-evidence/abuse-testing-retest-report.md`
- D2/D3 diagnostics: `d2-d3-unresolved-diagnostics.json` (+ `d3-*.json/png`, `d2-artifact-consistent-messaging.png`)
- Recovery: `t8-t10-t11-t12-summary.json`, `t11-*`, `t10-*`, `d1-absence-*.json`
- Regression 1–7/9: `retest-1-7-9-*.json`, `retest-0*.png`
- Soak: `soak13-*`, `13-final-soak-state.png`, `harness-4msg-proof.jsonl`
- Final API snapshots: `final-jobs-snapshot.json`, `final-reports-snapshot.json`, `final-memory-snapshot.json`
- Prior campaign preserved: `docs/abuse-testing-evidence/`

**Campaign ended:** 2026-09-05T12:40:27Z
