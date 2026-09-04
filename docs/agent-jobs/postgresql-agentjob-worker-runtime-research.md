# Agent Col: PostgreSQL-Backed AgentJob Durability & Worker-Runtime Research

This document presents the authoritative, source-grounded research and architectural design for executing **PostgreSQL-backed `AgentJobs`** in **Agent Col**. It defines a recoverable, local-first background worker runtime that survives process crashes, restarts, expired leases, network blips, retries, and worker concurrency without coupling background execution to the interactive chat request lifecycle.

Primary codebase contracts:
- [`agent_job_repository.py`](../../agent_job_repository.py)
- [`agent_col_agent_jobs.py`](../../agent_col_agent_jobs.py)
- [`memory_proposal_job_worker.py`](../../memory_proposal_job_worker.py)
- [`agent_col_artifact_executor.py`](../../agent_col_artifact_executor.py)
- [`collaborative_note_job_worker.py`](../../collaborative_note_job_worker.py)
- [`collaborative_notes.py`](../../collaborative_notes.py)
- [`memory_proposals.py`](../../memory_proposals.py)
- [`main.py`](../../main.py)
- [`docs/postgresql-migration/postgresql-migration-mapping.md`](../postgresql-migration/postgresql-migration-mapping.md)
- [`docs/migration/provider-and-persistence-decoupling-plan.md`](../migration/provider-and-persistence-decoupling-plan.md)

---

## A. Executive Recommendation

The recommended architecture is a **Decoupled Local Worker System** backed by PostgreSQL's atomic row-claiming semantics (`UPDATE ... RETURNING` via `FOR UPDATE SKIP LOCKED`).

```text
                                TARGET ARCHITECTURE OVERVIEW

   ┌──────────────────────────────────────────────┐
   │             AGENT COL API SERVER             │
   │               (FastAPI App)                  │
   │                                              │
   │  1. Receives chat/tool request               │
   │  2. Validates user & workspace ownership     │
   │  3. Transactionally writes AgentJob row      │
   │     (status='queued') & Private Payload       │
   │  4. Returns HTTP 202 / Queued Receipt        │
   └──────────────────────┬───────────────────────┘
                          │
                          │  SQL Transaction Commit (agent_jobs table)
                          ▼
   ┌──────────────────────────────────────────────┐
   │             POSTGRESQL DATABASE              │
   │                                              │
   │  • Authoritative AgentJob Queue State        │
   │  • Atomic Claim via FOR UPDATE SKIP LOCKED   │
   │  • Fenced Domain Side-Effect Transactions    │
   │  • Terminal Job Reports & Audit Events       │
   └──────────────────────▲───────────────────────┘
                          │
                          │  Atomic Claim & Fenced Side-Effect Commit
                          ▼
   ┌──────────────────────────────────────────────┐
   │            AGENT COL WORKER RUNTIME          │
   │            (agent-col-worker process)        │
   │                                              │
   │  • Standalone async worker daemon            │
   │  • Claims queued & expired-lease jobs        │
   │  • Heartbeat lease renewal task              │
   │  • Executes provider/model inference         │
   │  • Fenced domain side-effect & report write  │
   └──────────────────────────────────────────────┘
```

### Core Design Rules
1. **Interactive Chat Integrity:** Chat request handlers must only enqueue `AgentJobs` in PostgreSQL and return immediately. Request handlers must **never** spawn background worker `asyncio.create_task` tasks.
2. **Durable Authority & Domain Side-Effect Fencing:** PostgreSQL is the single source of truth for job queueing, state transitions, lease locks, private payloads, domain side effects (artifacts, note proposals, memory proposals), events, and reports. Stale workers whose leases expired are fenced from persisting **both** domain side effects and job status updates.
3. **Stale-Worker Fencing:** Every lease claim increments a `lease_generation` counter. Completion writes must match `status='running'`, `lease_owner`, and `lease_generation`. If the fence check fails, the transaction rolls back, preventing stale domain side-effect commits.
4. **Crash Recovery:** Worker restarts automatically discover orphaned `queued` jobs and expired `running` jobs, reclaiming them safely without manual operator intervention.

---

## B. Current AgentJob Architecture Audit

### **CURRENT SOURCE** Codebase Map

| Subsystem / Operation | Source File Location | Source Function / Line Evidence | Current Behavior & Persistence Scope |
| :--- | :--- | :--- | :--- |
| **Job Enqueue** | `agent_job_repository.py` | `enqueue_job()` (l. 54) | Writes `AgentJob` document (`status="queued"`, `attempt_count=0`) to Firestore. |
| **Private Payload** | `agent_job_repository.py` | `save_private_payload()` (l. 150) | Writes `AgentJobPayload` to subcollection `.../agent_jobs/{job_id}/private_payloads/payload`. |
| **Worker Dispatch** | `memory_proposal_job_worker.py`<br>`agent_col_artifact_executor.py`<br>`collaborative_note_job_worker.py` | `dispatch()` (l. 164)<br>`dispatch()` (l. 510)<br>`dispatch()` (l. 120) | Spawns process-local `asyncio.create_task(self.run_job(...))` inside FastAPI HTTP handler loops. |
| **Lease Acquisition** | `agent_job_repository.py` | `claim_job_lease()` (l. 200) | Sets `status="running"`, `lease_owner`, `lease_expires_at`, increments `attempt_count`. |
| **Lease Renewal** | `agent_job_repository.py` | `renew_job_lease()` (l. 260) | Updates `lease_expires_at` if `lease_owner` matches. |
| **Job Completion** | `agent_job_repository.py` | `complete_job()` (l. 310) | Sets `status="completed"`, clears lease fields, writes `result_refs`. |
| **Job Failure** | `agent_job_repository.py` | `fail_job()` (l. 370) | Sets `status="failed"`, clears lease fields, writes `failure_summary`. |
| **Job Cancellation** | `agent_job_repository.py` | `cancel_job()` (l. 430) | Sets `status="cancelled"`, clears lease fields. |
| **Event Logging** | `agent_job_repository.py` | `record_event()` (l. 480) | Writes `AgentJobEvent` to subcollection `.../agent_jobs/{job_id}/events/{event_id}`. |
| **Report Generation**| `agent_job_repository.py` | `save_report()` (l. 520) | Writes `AgentJobReport` to subcollection `.../agent_job_reports/{report_id}`. |

---

## C. Current Durability Gaps & Failure Modes

### **CURRENT SOURCE** Failure Inventory

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CURRENT DURABILITY GAP MATRIX                         │
│                                                                                 │
│  Failure Scenario            Current Source Outcome        Orphaned State Risk  │
│  ──────────────────────────  ────────────────────────────  ───────────────────  │
│  Process Crash after Enqueue  Task dies; job remains queued Job stuck indefinitely.│
│  Process Crash while Running  Task dies; lease expires      Job stuck running.  │
│  Provider Call Crash/Timeout Task dies; no auto-retry      No execution completion.│
│  Crash during Report Creation Result written; report missing Job report missing. │
│  Server Restart              Tasks discarded on shutdown   In-flight work lost. │
└─────────────────────────────────────────────────────────────────────────────────┘
```

1. **Orphaned Queued Jobs:** If the FastAPI process crashes after `enqueue_job()` but before `asyncio.create_task()` executes, the job remains in `status="queued"` indefinitely because no background polling loop exists to discover un-dispatched jobs.
2. **Orphaned Running Jobs:** If the process crashes while a job is `status="running"`, the task dies immediately. The job remains in `status="running"` with `lease_expires_at` set in the past. Current source contains no startup or background drainer to reclaim expired jobs.
3. **Unbounded HTTP Request Lifetime:** In-process dispatch forces long-running background work to share CPU and memory with the Uvicorn HTTP event loop.
4. **Ungraceful Shutdown:** On FastAPI application shutdown (`main.py` lifespan shutdown), in-flight `asyncio.create_task` instances are abruptly cancelled without releasing lease locks or logging terminal failure events.

---

## D. Target Worker Architecture

### **TARGET DESIGN** Decoupled Local Worker System

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      FASTAPI SERVER (HTTP API BOUNDARY)                         │
│                                                                                 │
│  POST /api/workspaces/{w_id}/agent_jobs                                         │
│    ├── 1. Validate user identity & workspace ownership                          │
│    ├── 2. BEGIN SQL TRANSACTION                                                 │
│    │     ├── INSERT INTO agent_jobs (...) VALUES (..., status='queued');        │
│    │     └── INSERT INTO agent_job_private_payloads (...) VALUES (...);         │
│    ├── 3. COMMIT SQL TRANSACTION                                                │
│    └── 4. RETURN HTTP 202 Accepted (Queued Receipt)                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         │ (PostgreSQL agent_jobs Table)
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      STANDALONE WORKER PROCESS (agent-col-worker)               │
│                                                                                 │
│  Loop:                                                                          │
│    ├── 1. Atomic Queue Claim & Reclaim Event CTE                                │
│    ├── 2. Spawn Lease Heartbeat Task                                            │
│    ├── 3. Execute External Provider / Model Inference                           │
│    ├── 4. Fenced Domain Side-Effect & Completion Transaction:                   │
│    │     BEGIN TRANSACTION;                                                     │
│    │       UPDATE agent_jobs SET status='completed', result_refs=...            │
│    │         WHERE job_id=$1 AND lease_owner=$2 AND lease_generation=$3         │
│    │           AND status='running';                                            │
│    │       IF updated_rows == 0 THEN ROLLBACK & DISCARD SIDE EFFECTS;           │
│    │       INSERT INTO domain_table (artifacts/note_proposals/memory_proposals);│
│    │       INSERT INTO agent_job_reports (...);                                 │
│    │       INSERT INTO agent_job_events (...);                                  │
│    │     COMMIT TRANSACTION;                                                    │
│    └── 5. Cancel Heartbeat Task                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## E. PostgreSQL Queue-Claim & Atomic Reclaim Algorithm

### **RECOMMENDATION** Atomic CTE Claim & Event Logging

Using `FOR UPDATE SKIP LOCKED` avoids worker threads blocking on already-locked claim candidates (note: `SKIP LOCKED` prevents worker lock waiting on queue claim candidates; it does not eliminate all PostgreSQL lock contention elsewhere).

To make reclaim event creation atomic with successful claims, the claim query evaluates whether the claimed candidate was previously `queued` or `running` (expired), recording an attempt/generation-specific event (`started` or `reclaimed`) in the **same atomic SQL transaction**. Candidate selection explicitly enforces `attempt_count < max_attempts`:

```sql
WITH candidate AS (
    SELECT job_id, status AS previous_status
    FROM agent_jobs
    WHERE (status = 'queued' AND attempt_count < max_attempts)
       OR (status = 'running' AND lease_expires_at < CURRENT_TIMESTAMP AND attempt_count < max_attempts)
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
),
claimed AS (
    UPDATE agent_jobs j
    SET status = 'running',
        lease_owner = $1,
        lease_expires_at = CURRENT_TIMESTAMP + ($2 || ' seconds')::INTERVAL,
        lease_generation = j.lease_generation + 1,
        attempt_count = j.attempt_count + 1,
        updated_at = CURRENT_TIMESTAMP
    FROM candidate c
    WHERE j.job_id = c.job_id
    RETURNING j.job_id, j.job_ref, j.user_id, j.workspace_id, j.project_id,
              j.session_id, j.source_turn_id, j.source_message_id, j.action_kind,
              j.idempotency_key, j.attempt_count, j.lease_owner, j.lease_expires_at,
              j.lease_generation, j.retry_of_job_id, c.previous_status
),
event_insert AS (
    INSERT INTO agent_job_events (event_id, job_id, event_type, message, status, public_visibility, created_at)
    SELECT 
        c.job_id || '-' || CASE WHEN c.previous_status = 'running' THEN 'reclaimed' ELSE 'started' END || '-' || c.attempt_count,
        c.job_id,
        CASE WHEN c.previous_status = 'running' THEN 'reclaimed' ELSE 'started' END,
        CASE WHEN c.previous_status = 'running' THEN 'Job execution reclaimed by worker after lease expiry' ELSE 'Job execution started by worker' END,
        'running',
        TRUE,
        CURRENT_TIMESTAMP
    FROM claimed c
)
SELECT * FROM claimed;
```

*Note: Filtering candidate rows with `attempt_count < max_attempts` ensures max-attempt exhaustion is enforced directly in SQL claim/reclaim candidate selection. Expired lease jobs that have reached or exceeded `max_attempts` are transitioned to `status = 'failed'` by a separate cleanup query:*

```sql
UPDATE agent_jobs
SET status = 'failed',
    lease_owner = NULL,
    lease_expires_at = NULL,
    failure_summary = 'Job attempt limit exceeded after worker crash or lease expiry',
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'running'
  AND lease_expires_at < CURRENT_TIMESTAMP
  AND attempt_count >= max_attempts;
```

---

## F. Worker Identity & Lease Protocol

### **RECOMMENDATION** Worker Instance Identifier
Format: `<hostname>/<pid>/<instance_uuid>` (e.g. `col-node-01/18492/f47ac10b`).

### Lease Lifecycle & Heartbeat Protocol

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│              LEASE TIMING PROTOCOL (OPERATIONAL RECOMMENDATION)                 │
│                                                                                 │
│  Baseline Lease Duration: 60s (Illustrative operational recommendation)         │
│  Heartbeat Frequency: Every 20s (1/3 of baseline lease duration)                │
│                                                                                 │
│  Time 0s         Time 20s        Time 40s        Time 60s (Target Completion)   │
│  ├───────────────┼───────────────┼───────────────┼───────────────┤              │
│  Claim Job       Heartbeat 1     Heartbeat 2     Fenced Commit   │              │
│  (Gen = 1)       (Expires=80s)   (Expires=100s)  (Gen = 1)       │              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

*Note: 60-second lease durations and 20-second heartbeat intervals are illustrative operational recommendations requiring workload benchmark validation prior to production selection.*

1. **Lease Renewal Query:**
   ```sql
   UPDATE agent_jobs
   SET lease_expires_at = CURRENT_TIMESTAMP + ($1 || ' seconds')::INTERVAL,
       updated_at = CURRENT_TIMESTAMP
   WHERE job_id = $2 AND lease_owner = $3 AND lease_generation = $4 AND status = 'running';
   ```
2. **Heartbeat Failure:** If the renewal query returns 0 rows (lease lost or job cancelled), the heartbeat task triggers best-effort local task cancellation.

---

## G. Fencing Domain Side Effects & Stale-Worker Prevention

### **TARGET DESIGN** Domain Side-Effect Fencing

It is insufficient to fence only the `agent_jobs` row status update. If a stale worker whose lease expired persists a domain side effect (such as writing an artifact, note proposal, or memory proposal) while its `complete_job()` call fails, the application database becomes corrupted.

Distinguish:
- **External Provider Execution:** May run **at-least-once** across retries/reclaims.
- **Authoritative Database Side Effects:** Must be **idempotent and fenced** in a single atomic SQL transaction.

```text
                           FENCED DOMAIN SIDE-EFFECT TRANSACTION

   Worker Process A (Stale)                              PostgreSQL Database Engine
   ────────────────────────                              ──────────────────────────
   1. Model computation completed.
   2. BEGIN TRANSACTION;
   3. UPDATE agent_jobs SET status='completed'... ────> Fails: 0 rows updated
                                                        (lease_generation mismatch)
   4. ROLLBACK TRANSACTION; ───────────────────────────> Rolls back all pending writes!
                                                        (No artifact, note, or memory
                                                         proposal is persisted)
```

### Fenced Side-Effect Transaction Pattern

```sql
BEGIN;

-- 1. Fence the AgentJob row
UPDATE agent_jobs
SET status = 'completed',
    result_refs = $1,
    lease_owner = NULL,
    lease_expires_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = $2
  AND lease_owner = $3
  AND lease_generation = $4
  AND status = 'running';

-- 2. Check affected rows inside application code.
-- IF affected_rows == 0: ROLLBACK and exit!

-- 3. Persist Authoritative Domain Side Effect (Atomic with Job Completion)
INSERT INTO artifacts (artifact_id, project_id, user_id, ...) VALUES (...);

-- 4. Persist Terminal Job Report & Event
INSERT INTO agent_job_reports (report_id, job_id, ...) VALUES (...);
INSERT INTO agent_job_events (event_id, job_id, event_type, ...) VALUES (...);

COMMIT;
```

---

## H. Startup Drain & Expired-Job Reclaim

### **RECOMMENDATION** Unified Startup Claim

When `agent-col-worker` starts up, it immediately executes the unified claim query (Section E).

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          WORKER STARTUP RECOVERY FLOW                           │
│                                                                                 │
│  1. Process Start (agent-col-worker)                                            │
│  2. Initialize DB Connection Pool                                               │
│  3. Execute Atomic Queue Claim (Section E CTE)                                  │
│     • Claims queued jobs or reclaims expired running jobs                       │
│     • Emits 'reclaimed' event atomically inside claim transaction if expired     │
│  4. Enter Main Worker Execution Loop                                            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Jobs exceeding `max_attempts` during reclaim transition to `status='failed'` with a `failure_summary` reading `"Job attempt limit exceeded after worker crash/lease expiry"`.

---

## I. Worker Topology Options Comparison

| Architectural Criteria | Option A: Embedded in FastAPI Process | Option B: Standalone Worker CLI (RECOMMENDED) | Option C: Shared Multi-Worker Pool |
| :--- | :--- | :--- | :--- |
| **Process Isolation** | Low (Shares event loop with API) | **High (Dedicated process space)** | High (Dedicated process pool) |
| **Crash Safety** | Low (API crash kills workers) | **High (Worker crash isolated from API)** | High |
| **Deployment Complexity**| Minimal (Single process) | **Low (Single extra command / container)** | Medium (Worker pool orchestrator) |
| **Development Setup** | Single command (`uvicorn main:app`) | **Dual command (`uvicorn` + `python -m worker`)** | Multi-process setup |

---

## J. Attempt Count Invariant & Retry Model

### **DEFINITIVE INVARIANT**
> `attempt_count` = *the number of execution leases successfully acquired for this specific `AgentJob` record.*

### Attempt Count Lifecycle

| Lifecycle Event | `attempt_count` Value | `retry_of_job_id` | Explanation |
| :--- | :--- | :--- | :--- |
| **Newly Enqueued Job** | `0` | `NULL` | Job created in `status='queued'`, unclaimed. |
| **First Lease Claim** | `1` | `NULL` | First worker acquires lease (`attempt_count = 1`). |
| **Expired Lease Reclaim** | `2` | `NULL` | Second worker reclaims expired job (`attempt_count = 2`). |
| **Automatic Same-Row Retry** | `2` | `NULL` | Generation-fenced transition returns `running` job to `queued`. Next claim acquires a new lease (`attempt_count = 2`). |
| **Manual User Retry** | `0` (New Job) | Parent `job_id` | User requests retry post-failure. Creates a **new** `AgentJob` row with `attempt_count=0`. |

### Automatic Same-Row Retry Protocol

1. **Generation-Fenced Requeue:**
   When a retryable transient failure occurs (e.g. provider rate limits, transient network timeouts, database lock serialization errors):
   - If `attempt_count < max_attempts`, the worker executes a generation-fenced transaction transitioning the job from `status='running'` back to `status='queued'` while clearing lease ownership:
     ```sql
     UPDATE agent_jobs
     SET status = 'queued',
         lease_owner = NULL,
         lease_expires_at = NULL,
         updated_at = CURRENT_TIMESTAMP
     WHERE job_id = $1
       AND lease_owner = $2
       AND lease_generation = $3
       AND status = 'running';
     ```
   - The normal claim path (Section E) then reclaims the job, increments `lease_generation`, and increments `attempt_count` (e.g., from 1 to 2).
   - This strictly preserves the invariant: `attempt_count = number of execution leases successfully acquired for this AgentJob row`. An automatic retry is **not** executed under the existing lease.
   - If `attempt_count >= max_attempts`, the retry handler transitions the job directly to `status='failed'` with `failure_summary = 'Max execution attempts exceeded'`. Max-attempt exhaustion is also enforced in SQL claim/reclaim candidate selection (`attempt_count < max_attempts`).

2. **Retry Policy Classification:**
   - **Automatic Same-Row Retries:** Transient provider timeouts, HTTP 429 rate limits, and DB lock serialization errors trigger a generation-fenced transition back to `status='queued'` for a new lease claim, up to `max_attempts` (illustrative operational recommendation: 3 attempts).
   - **Non-Retryable Terminal Failures:** Permanent policy rejections and validation errors immediately transition to `status='failed'` without automatic retries.
   - **User Cancellation:** User cancellation transitions the job directly to `status='cancelled'`, matching Section K and the AgentJob state machine.

---

## K. Cancellation Semantics & Interruption Limits

### Best-Effort Local Interruption vs. Fenced Safety

Cancelling a Python `asyncio.Task` is a **best-effort local interruption**. It does **not** guarantee that an HTTP or RPC request already sent to a remote model provider endpoint stops executing on the remote provider server.

The authoritative safety guarantees are:
1. **Queue Prevention:** Setting `status='cancelled'` in PostgreSQL prevents any worker from ever claiming or executing the job.
2. **Side-Effect Fencing:** If an external provider call completes for a cancelled job, the worker's fenced transaction (Section G) checks `status = 'running'`. Because status is `'cancelled'`, the fenced transaction fails (0 rows updated), rolling back and discarding all model output without persisting domain side effects.

---

## L. Crash-Recovery State Machine

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        AGENTJOB CRASH-RECOVERY STATE MACHINE                    │
│                                                                                 │
│  Current State       Condition                    Action on Restart             │
│  ─────────────────── ───────────────────────────  ────────────────────────────  │
│  queued              Any                          Claim & execute (Attempt 1).  │
│  running             lease_expires_at > now()     Do nothing (Worker active).   │
│  running             lease_expires_at <= now() &  Reclaim & execute              │
│                      attempt_count < max_attempts (Attempt = Attempt + 1).    │
│  running             lease_expires_at <= now() &  Transition to 'failed'        │
│                      attempt_count >= max_attempts(Max attempts exceeded).      │
│  completed           Any                          Terminal; no action.          │
│  failed              Any                          Terminal; no action.          │
│  cancelled           Any                          Terminal; no action.          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## M. Action-Kind Idempotency & Provenance Audit

The table below audits canonical repository source logic for each action kind:

| Action Kind | Canonical Deterministic Identity / Provenance Key | Source Function Evidence | Duplicate Model Execution Possible? | Duplicate Database Side Effect Possible? | Exact Uniqueness & Idempotency Guard |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `create_artifact` | `blueprint_id = "blueprint--" + turn_id`<br>`artifact_id = "artifact--" + turn_id` | `database.py:2860`<br>`database.py:4440` | Yes (At-least-once model calls) | **No (Fenced & Unique PK)** | Primary Key `blueprint_id` / `artifact_id` uniqueness + Fenced side-effect transaction. |
| `propose_collaborative_note` | `proposal_id = "note_proposal--" + digest` | `collaborative_notes.py:42`<br>`database.py:2400` | Yes | **No (Fenced & Unique PK)** | Primary Key `proposal_id` uniqueness in `note_proposals` table + Fenced transaction. |
| `propose_memory_signal` | `origin_id = ProposalOriginIds` (SHA256 digest of user_id, session_id, source_message_id, category) | `memory_proposals.py:80`<br>`database.py:6257` | Yes | **No (Fenced & Unique PK)** | Primary Key `origin_id` in `memory_proposal_origins` + Fenced transaction. |
| `retrieve_chat_context` | N/A (Read-only context lookup) | `agent_job_repository.py` | Yes | **No (Read-only)** | Read-only operation; zero domain side-effect persistence. |

---

## N. Event & Report Transaction Semantics

Worker execution uses **three discrete transactional phases**:

1. **Phase 1: Claim Transaction (Short DB Lock):** Executes Section E CTE query. Claims job, increments `lease_generation` and `attempt_count`, and logs a deterministic attempt-specific event (`{job_id}-started-{attempt_count}` or `{job_id}-reclaimed-{attempt_count}`) atomically.
2. **Phase 2: External Provider Execution (Outside DB Lock):** Runs model inference, structured output generation, or code execution outside SQL transactions.
3. **Phase 3: Fenced Side-Effect & Completion Transaction (Short DB Lock):** Executes Section G query. Persists domain side effect, job status, report, and event atomically inside 1 short SQL transaction.

---

## O. PostgreSQL Indexes & Transaction Semantics

```sql
-- 1. Queue Claiming & Expired Lease Reclaim Index (Critical Path)
CREATE INDEX idx_agent_jobs_queue_claim 
ON agent_jobs (created_at ASC) 
WHERE status IN ('queued', 'running');

-- 2. Idempotency Key Lookup Index
CREATE UNIQUE INDEX idx_agent_jobs_workspace_idempotency 
ON agent_jobs (workspace_id, idempotency_key);

-- 3. Workspace Job Listing Index
CREATE INDEX idx_agent_jobs_workspace_list 
ON agent_jobs (workspace_id, created_at DESC);

-- 4. Expired Lease Monitor Index
CREATE INDEX idx_agent_jobs_lease_expiry 
ON agent_jobs (lease_expires_at ASC) 
WHERE status = 'running';
```

---

## P. Fenced Graceful Shutdown Protocol

When `agent-col-worker` receives `SIGTERM` or `SIGINT`:

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        FENCED GRACEFUL SHUTDOWN SEQUENCE                        │
│                                                                                 │
│  1. Receive SIGTERM / SIGINT signal.                                            │
│  2. Set shutdown_requested = True (Stops claiming new jobs).                    │
│  3. Wait up to SHUTDOWN_TIMEOUT for active jobs to complete.                    │
│  4. For incomplete in-flight jobs, execute Fenced Lease Expiry Acceleration:   │
│     UPDATE agent_jobs                                                           │
│     SET lease_expires_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP    │
│     WHERE job_id = $1 AND lease_owner = $2 AND lease_generation = $3             │
│       AND status = 'running';                                                   │
│     (Preserves lease_generation & attempt_count; makes job immediately          │
│      reclaimable by other workers while fencing stale completions)              │
│  5. Close DB Connection Pool & exit cleanly (0 exit code).                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Q. FastAPI / Worker Separation Boundary

```python
@app.post("/api/workspaces/{workspace_id}/agent_jobs", status_code=202)
async def create_agent_job(
    workspace_id: str,
    request: CreateAgentJobRequest,
    repo: AbstractAgentJobRepository = Depends(get_job_repo),
) -> QueuedJobReceipt:
    job = build_agent_job(workspace_id, request)
    payload = build_private_payload(job, request)
    
    # Transactionally store job & payload in PostgreSQL
    await repo.enqueue_job_with_payload(job, payload)
    
    # Return HTTP 202 receipt (No asyncio.create_task!)
    return QueuedJobReceipt(job_id=job.job_id, status="queued")
```

---

## R. Local Development & Test Strategy

```python
class AgentJobWorkerRuntime:
    async def claim_next_job(self) -> AgentJobContext | None:
        """Claims the next single eligible job from PostgreSQL."""
        ...
        
    async def execute_job(self, ctx: AgentJobContext) -> AgentJobReport:
        """Executes a claimed job to terminal completion."""
        ...
        
    async def drain_once(self) -> list[AgentJobReport]:
        """Claims and executes all currently queued/expired jobs until queue is empty."""
        ...
```

Unit tests call `await worker_runtime.drain_once()` deterministically in pytest suites without timing races.

---

## S. Migration Sequence from Current Source

```text
Phase 1: Database Schema Deployment
  └── Deploy agent_jobs DDL with lease_generation column & PostgreSQL indexes.

Phase 2: Repository Interface & Postgres Implementation
  └── Create AbstractAgentJobRepository and implement PostgresAgentJobRepository
      with atomic claim CTE and fenced completion transactions.

Phase 3: Worker Runtime Primitive Implementation
  └── Create agent_col_worker/ runtime module containing AgentJobWorkerRuntime primitives.

Phase 4: Standalone Worker CLI Entrypoint
  └── Implement python -m agent_col_worker CLI daemon.

Phase 5: FastAPI Handler Decoupling
  └── Remove asyncio.create_task() calls from main.py and tool handlers; return HTTP 202.

Phase 6: Multi-Worker & Crash Verification
  └── Execute end-to-end integration tests verifying worker restarts and multi-process concurrency.
```

---

## T. Observability & Security Requirements

1. **Structured Worker Metrics:** Log queue depth, claim latency, lease renewals, lease expirations, reclaim counts, execution durations, and retry counts.
2. **Data Security & Privacy:** Private payloads in `agent_job_private_payloads` must never be logged in plain text. Public events/reports omit prompt inputs, private reasoning tokens, and internal model context.
3. **Database Role Least Privilege:** Worker user requires `SELECT`, `INSERT`, `UPDATE` permissions on `agent_jobs`, `agent_job_private_payloads`, `agent_job_events`, `agent_job_reports`, and domain tables (`artifacts`, `blueprints`, `note_proposals`, `memory_proposals`, `memory_proposal_origins`).

---

## U. Risks and Operational Recommendations Summary

*Note: All numerical values below are illustrative operational recommendations requiring workload benchmarking prior to production selection.*

| Operational Parameter | Illustrative Recommendation | Benchmarking & Evaluation Requirement |
| :--- | :--- | :--- |
| **Lease Duration** | `60 seconds` | Benchmark against long-running multi-file synthesis workloads. |
| **Heartbeat Interval** | `20 seconds` (1/3 lease) | Verify under CPU-bound serialization loads. |
| **Max Automatic Attempts** | `3 attempts` | Evaluate transient provider rate-limit recovery. |
| **Shutdown Timeout** | `30 seconds` | Test container termination grace periods. |
| **DB Connection Pool** | `5 - 10 connections` per worker | Benchmark under high-concurrency worker polling. |

---

## V. Architecture Diagrams

### Diagram 1: Current Process-Local Flow

```text
User Request ──> FastAPI Route Handler ──> Enqueue Firestore ──> asyncio.create_task()
                                                                       │
                                                                       ▼
                                                             In-Process Worker Task
                                                             (Lost on Server Crash)
```

### Diagram 2: Target PostgreSQL-Backed Worker Flow

```text
User Request ──> FastAPI Route Handler ──> INSERT agent_jobs ──> Return 202
                                                │
                                                ▼ (PostgreSQL Queue)
                                    agent-col-worker Process
                                    (FOR UPDATE SKIP LOCKED)
                                                │
                                                ▼
                                    Fenced Execution & Report
```

### Diagram 3: Job Lifecycle / State Machine

```text
     [Enqueued]
          │
          ▼
      (queued) ───────────────> (cancelled) [User Cancellation]
          │                         ▲
          │ Atomic Claim            │ Heartbeat Check Fails
          ▼                         │
      (running) ────────────────────┘
          │
          ├─────────────────────────> (completed) [Fenced Commit]
          │
          └─────────────────────────> (failed)    [Max Attempts Exceeded]
```

### Diagram 4: Crash / Reclaim Sequence

```text
Worker A Claims Job (Gen 1) ──> Worker A Crashes ──> Lease Expires
                                                          │
                                                          ▼
Worker B Claims Job (Gen 2) <── Scans Expired Leases <────┘
          │
          ▼
Fenced Commit (Gen 2) ──> SUCCESS
```

### Diagram 5: API vs. Worker Ownership Boundary

```text
┌────────────────────────────────────────┐     ┌────────────────────────────────────────┐
│          API OWNERSHIP BOUNDARY        │     │       WORKER OWNERSHIP BOUNDARY        │
│                                        │     │                                        │
│ • User Authentication & Authorization  │     │ • Queue Claiming & Lease Locks         │
│ • Workspace Permission Validation      │     │ • Lease Heartbeat Renewal              │
│ • Idempotency Verification             │     │ • Provider / Model Execution           │
│ • Job & Private Payload Enqueue        │     │ • Fenced Domain Side-Effect Commit     │
│ • HTTP 202 Receipt Formatting          │     │ • Public Report & Audit Event Writes   │
└────────────────────────────────────────┘     └────────────────────────────────────────┘
```
