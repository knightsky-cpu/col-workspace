# Agent Col: Migration Sequencing & Coexistence Architecture Plan

This document establishes the authoritative, source-grounded migration sequencing, provider decoupling, and coexistence architecture for **Agent Col**. It defines the step-by-step procedure to transition Agent Col from **Firestore + Google (Gemini / Vertex AI / Google ADK / Google Speech)** to **PostgreSQL + OpenAI (Responses API / GPT-5.6 / Whisper / OpenAI Speech)** while preserving application invariants, changing only one authoritative subsystem at a time, and maintaining clear rollback and recovery capability.

Primary migration contracts:
- [`docs/postgresql-migration/postgresql-migration-mapping.md`](../postgresql-migration/postgresql-migration-mapping.md)
- [`docs/openai-migration/openai-integration-research.md`](../openai-migration/openai-integration-research.md)

---

## A. Executive Recommendation

The recommended strategy is **Strategy C: Provider & Persistence Interfaces First**.

```text
                             LINEAR PRODUCTION MIGRATION PATHWAY
                                  
  ┌───────────────────────────┐      Phase 1: Interface Decoupling
  │ Current Architecture      │ ─────────────────────────────────────────┐
  │ (Firestore + Google/ADK)  │                                          │
  └───────────────────────────┘                                          ▼
                                                     ┌──────────────────────────────────────┐
                                                     │ Interface-Gated Architecture          │
                                                     │ (AbstractMemoryEngine & Providers)   │
                                                     └──────────────────┬───────────────────┘
                                                                        │
                                                                        ▼ Phase 2: Persistence Cutover
                                                     ┌──────────────────────────────────────┐
                                                     │ PostgreSQL + Google (Gemini/ADK)     │
                                                     │ (PostgreSQL Becomes Authoritative)   │
                                                     └──────────────────┬───────────────────┘
                                                                        │
                                                                        ▼ Phase 3: Staged Subsystem Inference Migration
                                                     ┌──────────────────────────────────────┐
                                                     │ PostgreSQL + Hybrid Google/OpenAI    │
                                                     │ (Subsystem-by-Subsystem Migration)   │
                                                     └──────────────────┬───────────────────┘
                                                                        │
                                                                        ▼ Phase 4: Final Unified Target
                                                     ┌──────────────────────────────────────┐
                                                     │ PostgreSQL + OpenAI (Responses API)  │
                                                     │ (Final Production State)             │
                                                     └──────────────────┬───────────────────┘
                                                                        │
                                                                        ▼ Phase 5: Google Retirement
                                                     ┌──────────────────────────────────────┐
                                                     │ Independent Agent Col Architecture   │
                                                     │ (Google SDKs Purged)                 │
                                                     └──────────────────────────────────────┘

  Optional Test-Only Configuration (Non-Production Branch):
  ┌──────────────────────────────────────┐
  │ Firestore + OpenAI (Responses API)   │ (Isolated integration testing only)
  └──────────────────────────────────────┘
```

### Strategy Comparison & Selection Rationale

- **Strategy A (PostgreSQL First without Interfaces):** Replaces Firestore directly while application code is heavily coupled to `MemoryEngine` methods and Google GenAI types. High risk of persistence regressions affecting live model calls.
- **Strategy B (OpenAI First without Interfaces):** Replaces Gemini/Vertex/ADK while persistence is tied to Firestore transaction objects. High risk of inference failures corrupting Firestore turn claims.
- **Strategy C (Interfaces First - RECOMMENDED):** Wraps existing persistence (`MemoryEngine`) and inference (`genai.Client`, ADK `Runner`) behind explicit application interfaces (`AbstractMemoryEngine`, `InferenceProvider`, `StructuredOutputProvider`, `SpeechProvider`). Enables switching **one subsystem at a time** via feature flags with zero dual-write persistence hazards and clean recovery boundaries.

---

## B. Current Coupling Map

The table below catalogs every intersection where Firestore, Gemini/Vertex, Google ADK, Google Search, Google Speech, Google Auth, and `AgentJob` orchestration collide in current application code:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                             CURRENT APPLICATION SURFACE                                         │
│                                                                                                                 │
│  main.py (FastAPI Lifespan)                                                                                     │
│    ├── database.MemoryEngine (Firestore AsyncClient) ──────────────────────────┐                               │
│    ├── vertex_config (GOOGLE_CLOUD_PROJECT, GOOGLE_GENAI_USE_ENTERPRISE)        │                               │
│    ├── genai.Client (Google GenAI SDK) ──────────────────────────────────┐      │                               │
│    ├── speech_service (Google STT / TTS SDKs)                           │      │                               │
│    └── auth.py (Google OIDC Token Verification)                         │      │                               │
│                                                                         │      │                               │
│  AgentColTurnService (Turn Orchestrator)                                │      │                               │
│    ├── MemoryEngine ────────────────────────────────────────────────────┼──────┼────────────────────────────┐  │
│    ├── AgentColRoutingProviderV4 ─── (genai.Client) ────────────────────┤      │                            │  │
│    ├── SupervisorRuntime ──────────── (google.adk App & Runner) ─────────┼──────┼─────────────────────────┐  │  │
│    └── Specialist Services                                              │      │                         │  │  │
│          ├── ResearchExpertService ── (types.GoogleSearch Grounding) ────┤      │                         │  │  │
│          ├── ComputationalExpertService (genai.Client) ─────────────────┤      │                         │  │  │
│          ├── SourceExpertService ──── (genai.Client) ───────────────────┤      │                         │  │  │
│          └── WorkingStateService ──── (genai.Client) ───────────────────┘      │                         │  │  │
│                                                                                │                         │  │  │
│  AgentJobRepository (Background Job Persistence)                               │                         │  │  │
│    └── Firestore AsyncClient ──────────────────────────────────────────────────┴─────────────────────────┼──┼──┤
│                                                                                                          │  │  │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┼──┼──┘
                                                                                                           │  │  │
                                                DECOUPLED BOUNDARIES NEEDED                                │  │  │
                                                                                                           ▼  ▼  ▼
                                          1. AbstractMemoryEngine / AbstractAgentJobRepository (PostgreSQL)
                                          2. InferenceProvider / StructuredOutputProvider (OpenAI Responses)
                                          3. OpenAIResponderAdapter / OpenAIRunnerAdapter (ADK Removal)
```

---

## C. Required Compatibility Interfaces

To decouple application logic from vendor drivers, the following thin interfaces will be established prior to swapping implementations:

| Proposed Interface / Abstraction | Current Implementation | Source File Location | Primary Application Callers | Firestore/Google Implementation | PostgreSQL/OpenAI Implementation | Exists Today? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `AbstractMemoryEngine` | `MemoryEngine` | `database.py` | `main.py`, `AgentColTurnService`, `TrustedMemoryService`, `CollaborativeNoteService`, `ContinuityService`, `WorkingStateService` | `MemoryEngine` (Firestore SDK) | `PostgresMemoryEngine` (asyncpg / SQLAlchemy) | No (Direct class) |
| `AbstractAgentJobRepository` | `AgentJobRepository` | `agent_job_repository.py` | `main.py`, `AgentColTurnService`, Background Queue Workers | `AgentJobRepository` (Firestore) | `PostgresAgentJobRepository` (PostgreSQL) | No (Direct class) |
| `InferenceProvider` | Direct `genai.Client` calls | `vertex_config.py`, `agent_col_turn_service.py` | Specialist services, `AgentColTurnService` | `GoogleGenAIProvider` | `OpenAIProviderAdapter` (Responses API) | No (Direct SDK) |
| `StructuredOutputProvider` | `agent_col_routing_provider_v4.py` | `agent_col_routing_provider_v4.py` | `AgentColTurnService`, `synthesis_service.py`, `generic_artifact_generation.py` | `GenAIStructuredOutputProvider` | `OpenAIStructuredOutputProvider` (`text.format`) | Partial (v4 provider class) |
| `WebSearchProvider` | Direct `types.GoogleSearch` | `research_expert_service.py` | `ResearchExpertService` | `GoogleSearchGroundingProvider` | `OpenAIWebSearchProvider` (`web_search_preview`) | No (Direct SDK tool) |
| `SpeechProvider` | Direct Google STT/TTS | `speech_service.py` | `main.py` speech API routes | `GoogleSpeechProvider` | `OpenAISpeechProvider` (`gpt-transcribe`, `gpt-4o-mini-tts`) | Partial (Service wrapper) |

---

## D. Migration Dependency Graph

The acyclic dependency graph below illustrates the precise order in which components must be decoupled, cut over, and verified:

```text
Phase 1: Interface Decoupling & Config Setup
  ├── 1.1 Create AbstractMemoryEngine & AbstractAgentJobRepository interfaces.
  ├── 1.2 Create InferenceProvider & StructuredOutputProvider interfaces.
  └── 1.3 Implement granular configuration flags (PERSISTENCE_BACKEND, PROVIDER_*).
        │
        ▼
Phase 2: PostgreSQL Persistence Cutover (Inference remains Google)
  ├── 2.1 Deploy PostgreSQL DDL & indices.
  ├── 2.2 Execute bulk/shadow copy from Firestore to PostgreSQL while live.
  ├── 2.3 ENTER DURABLE-WRITE FREEZE WINDOW (503 on mutating routes).
  ├── 2.4 Drain in-progress chat turns and AgentJobs.
  ├── 2.5 Run final delta/catch-up migration & verify Migration Manifest.
  ├── 2.6 Switch PERSISTENCE_BACKEND=postgresql & run smoke checks.
  └── 2.7 REOPEN WRITES (PostgreSQL is now authoritative).
        │
        ▼
Phase 3: Staged Subsystem OpenAI Migration (Persistence is PostgreSQL)
  ├── 3.1 PROVIDER_ROUTING=openai (v4 Intent Routing via gpt-5.6-luna).
  ├── 3.2 PROVIDER_ANALYSTS=openai (working_state, continuity, preferences via gpt-5.6-luna).
  ├── 3.3 PROVIDER_SPECIALISTS=openai (source, computational, requirements via gpt-5.6-sol/terra).
  ├── 3.4 PROVIDER_ARTIFACTS=openai (blueprint synthesis, single-file artifacts via gpt-5.6-sol).
  ├── 3.5 PROVIDER_SEARCH=openai (research web search grounding via gpt-5.6-terra + web_search).
  ├── 3.6 PROVIDER_RESPONDER=openai (OpenAIResponderAdapter replaces Google ADK Runner).
  └── 3.7 PROVIDER_SPEECH=openai (gpt-transcribe & gpt-4o-mini-tts).
        │
        ▼
Phase 4: Collapse Configurations to OpenAI
  └── Set INFERENCE_PROVIDER_DEFAULT=openai; collapse temporary PROVIDER_* flags.
        │
        ▼
Phase 5: Google Runtime Dependency Retirement
  ├── 5.1 Remove Google SDK dependencies from requirements.txt.
  └── 5.2 Delete legacy Firestore and Vertex AI configuration files.
```

---

## E. Exact Phased Migration Order

### Phase 1: Interface Decoupling & Configuration Setup
- **Goal:** Introduce abstract interfaces around `MemoryEngine`, `AgentJobRepository`, and `genai.Client` without altering runtime execution.
- **Entry Condition:** Current codebase passes unit & integration test suites.
- **Actions:**
  1. Define `AbstractMemoryEngine` protocol in `database_interface.py` matching `MemoryEngine`'s async methods.
  2. Define `AbstractAgentJobRepository` protocol in `agent_job_repository_interface.py`.
  3. Define `InferenceProvider` and `StructuredOutputProvider` protocols in `inference_interface.py`.
  4. Wire `PERSISTENCE_BACKEND` (`"firestore"` | `"postgresql"`) and granular `PROVIDER_*` flags in `main.py` lifespan setup.
- **Verification:** Run `pytest`; all tests pass using existing Firestore + Google implementations under interface wrappers.

### Phase 2: PostgreSQL Persistence Migration
- **Goal:** Transition all durable state from Firestore to PostgreSQL while maintaining Google GenAI/ADK for inference.
- **Entry Condition:** Phase 1 interfaces deployed and verified.
- **Actions:**
  1. Deploy PostgreSQL schema (`docs/postgresql-migration/postgresql-migration-mapping.md`).
  2. Perform shadow bulk migration from Firestore while live writes continue against Firestore.
  3. Enter a short **Durable-Write Freeze Window**: return HTTP 503 / maintenance mode on state-mutating endpoints (`/api/chat`, note proposals, memory mutations, workspace operations).
  4. Drain in-progress chat turns and `AgentJobs`.
  5. Execute final delta/catch-up migration for records updated since the shadow copy timestamp.
  6. Validate the **Migration Manifest** (cardinality, checksums, FK integrity).
  7. Set `PERSISTENCE_BACKEND=postgresql`.
  8. Run PostgreSQL smoke checks and reopen writes.
- **Verification:** Execute live turn claims, transcript retrieval, note approvals, and `AgentJob` leasing against PostgreSQL.

### Phase 3: Staged Subsystem OpenAI Migration
- **Goal:** Migrate inference workloads from Google GenAI/ADK to OpenAI Responses API over authoritative PostgreSQL state.
- **Entry Condition:** Phase 2 PostgreSQL cutover completed and verified stable.
- **Subsystem Cutover Sequence:**
  1. `PROVIDER_ROUTING=openai` (Intent Routing via `gpt-5.6-luna`).
  2. `PROVIDER_ANALYSTS=openai` (working state, continuity, preferences via `gpt-5.6-luna`).
  3. `PROVIDER_SPECIALISTS=openai` (source, computational, requirements via `gpt-5.6-sol`/`terra`).
  4. `PROVIDER_ARTIFACTS=openai` (blueprint synthesis, single-file artifacts via `gpt-5.6-sol`).
  5. `PROVIDER_SEARCH=openai` (research web search grounding via `gpt-5.6-terra` + `web_search_preview`).
  6. `PROVIDER_RESPONDER=openai` (Primary Responder & ADK removal via `OpenAIResponderAdapter`).
  7. `PROVIDER_SPEECH=openai` (speech adapters via `gpt-transcribe` & `gpt-4o-mini-tts`).
- **Verification:** Run test gates after each sub-phase.

### Phase 4: Collapse Configurations & Final Google Retirement
- **Goal:** Collapse temporary `PROVIDER_*` flags to `INFERENCE_PROVIDER_DEFAULT=openai` and purge Google SDK dependencies.
- **Entry Condition:** All sub-phases of Phase 3 verified stable in production.
- **Actions:** Remove `google-genai`, `google-adk`, `google-cloud-firestore` from `requirements.txt`. Delete `vertex_config.py`.

---

## F. PostgreSQL Cutover Procedure & Consistency Freeze Window

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL CUTOVER CONSISTENCY TIMELINE                      │
│                                                                                 │
│  T-60m: Deploy PostgreSQL DDL & Indices to production database instance.        │
│  T-30m: Run initial shadow bulk copy while Firestore remains authoritative.     │
│  T-05m: ENTER DURABLE-WRITE FREEZE WINDOW:                                      │
│         • Return 503 / Maintenance Mode on mutating HTTP routes (/api/chat, etc.)│
│         • Fence & drain in-progress chat-turn leases.                           │
│         • Fence & drain active AgentJobs.                                       │
│  T-02m: Execute final delta catch-up migration for recent Firestore updates.    │
│  T-01m: Verify Migration Manifest (Cardinality, checksums, FK integrity).      │
│  T-00m: SWITCH PERSISTENCE_BACKEND=postgresql.                                  │
│  T+01m: Run PostgreSQL smoke checks (Read/write verification).                  │
│  T+02m: REOPEN WRITES (Lift maintenance mode; PostgreSQL is now authoritative). │
│  T+30m: Firestore becomes read-only reference / diagnostic state.               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## G. Migration Manifest Framework

Because PostgreSQL normalizes array fields (e.g. `source_message_ids` -> junction tables) and Firestore stores memory proposals in category slots (`users/{user_id}/memory_proposals/{category}`), simple 1:1 SQL row count parity does not apply to all domains. Parity is enforced using a per-domain **Migration Manifest**:

| Domain | Firestore Source Path | PostgreSQL Target Table(s) | Cardinality Expectation | Key Field Verification & Parity Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Users** | `users/{id}` | `users` | Exact 1:1 | Verify `user_id` presence, `collaboration_profile` JSON checksum. |
| **Workspaces** | `users/{id}/workspaces/{id}` | `workspaces` | Exact 1:1 | Verify `workspace_id`, `user_id` FK, `display_name`, `is_default`. |
| **Projects** | `projects/{id}` | `projects` | Exact 1:1 | Verify `project_id REFERENCES workspaces(workspace_id)`. |
| **Sessions** | `sessions/{id}` | `sessions` | Exact 1:1 | Verify `session_id`, `user_id` FK, `project_id` FK, `last_completed_turn_id`. |
| **Messages** | `sessions/{id}/messages/{id}` | `messages` | Exact 1:1 | Verify `message_id`, `session_id` FK, `role`, text length checksum. |
| **Note Proposals** | `workspaces/{id}/note_proposals/{id}` | `note_proposals` + `note_proposal_source_messages` | 1:1 Parent, 1:N Junction | Verify `proposal_id`; verify junction table rows equal `len(source_message_ids)`. |
| **Notes** | `workspaces/{id}/collaborative_notes/{id}` | `collaborative_notes` + `note_source_messages` | 1:1 Parent, 1:N Junction | Verify `note_id`, `revision`; verify junction table rows equal `len(source_message_ids)`. |
| **Note Events** | `collaborative_notes/{id}/events/{id}` | `note_events` + `note_event_source_messages` | 1:1 Parent, 1:N Junction | Verify `event_id`, `note_id` FK; verify junction table rows match `len(source_message_ids)`. |
| **Memory Proposals (Category Slots)** | `users/{user_id}/memory_proposals/{category}` | `memory_proposals` | Category-Slot Mapping (At most 1 active/pending proposal per category slot per user) | Verify category-slot document keying (`category`), `user_id` FK, inner `proposal_id`, status, and `proposed_value` JSON checksum. |
| **Memory Proposal Origins** | `users/{user_id}/memory_proposal_origins/{origin_id}` | `memory_proposal_origins` | Independent Source Domain (1 per origin derived) | Verify exact `origin_id` PK, `user_id` FK, `category`, stored inner `proposal_id` (provenance metadata, unconstrained by category slot proposals), source session/message provenance (`source_session_id`, `source_message_id`), evidence message ID / clarification ID where applicable. |
| **Memory Events** | `users/{id}/memory_events/{id}` | `memory_events` | Exact 1:1 | Verify `event_id`, `user_id` FK, `category`, `memory_value` JSON checksum. |
| **Chat Turns** | `sessions/{id}/turns/{id}` | `chat_turns` | Exact 1:1 | Verify `turn_id`, `session_id` FK, `status`, `idempotency_key`. |
| **Working State** | `sessions/{id}/working_state/current` | `session_working_state` | Exact 1:1 per session | Verify `session_id` PK, `current_goal`, `intent_hypothesis`. |
| **Blueprints** | `projects/{id}/blueprints/{id}` | `blueprints` | Exact 1:1 | Verify `blueprint_id`, `project_id` FK, `blueprint` JSON payload checksum. |
| **Artifacts** | `projects/{id}/artifacts/{id}` | `artifacts` | Exact 1:1 | Verify `artifact_id`, `project_id` FK, `filename`, content byte size. |
| **AgentJobs** | `workspaces/{id}/agent_jobs/{id}` | `agent_jobs` + `agent_job_private_payloads` | 1:1 Job, 1:1 Payload | Verify `job_id`, `job_ref` uniqueness, `workspace_id` FK, status. |

---

## H. AgentJob Migration Metadata & Operational Rules

1. **Job Audit & Provenance Metadata:** Payloads may include `accepted_provider` (`"google"` | `"openai"`) and `accepted_persistence` (`"firestore"` | `"postgresql"`) for audit and logging purposes. However, these fields are **non-authoritative for routing**; repository selection and model dispatch remain governed strictly by application-level configuration flags (`PERSISTENCE_BACKEND` and `PROVIDER_*`).
2. **Worker Restarts Across Cutover:** During the Phase 2 freeze window, active `AgentJob` queue workers will be drained or fenced before switching `PERSISTENCE_BACKEND=postgresql`. Active `lease_expires_at` locks guarantee no job is executed twice across the persistence boundary.
3. **Retry Behavior Verification:** Retrying a failed job queued prior to cutover will execute against the currently configured provider/repository backend. Retry payload reconstruction behavior will be verified during implementation against canonical `AgentJob` source logic.

---

## I. Temporary Coexistence Matrix & Rollback Semantics

The matrix below specifies supported, temporary, and prohibited/unsafe runtime state combinations:

| Persistence Backend | Inference Configuration | ADK Runtime Present? | System Status | Operational & Rollback Guidelines |
| :--- | :--- | :--- | :--- | :--- |
| **Firestore** | **Google GenAI (Global)** | Yes | **Supported (Current)** | Baseline production configuration. |
| **PostgreSQL** | **Google GenAI (Global)** | Yes | **Supported & Temporary** | Target state for Phase 2. Tests database layer independently. |
| **PostgreSQL** | **Hybrid Subsystems** | Partial | **Supported & Temporary** | Phase 3 intermediate state (e.g. `PROVIDER_ROUTING=openai`, `PROVIDER_RESPONDER=google`). |
| **PostgreSQL** | **OpenAI Responses** | No | **Supported (Final)** | Final target production state. |
| **Firestore** | **OpenAI Responses** | No | **Test Only (Non-Prod)** | Isolated integration testing setup only; not a production migration branch. |
| **Firestore + PostgreSQL (Dual-Write)** | Any Provider | Any | **UNSAFE & PROHIBITED** | **DO NOT USE.** Dual-writing creates split-brain turn claim conflicts. |

### Two-Stage Rollback & Recovery Semantics

```text
                               PERSISTENCE ROLLBACK WINDOWS
                               
  Phase 2 Cutover Window:
  
  [Shadow Copy] ──> [Freeze Window] ──> [PERSISTENCE_BACKEND=postgresql] ──> [Post-Cutover Writes Accept]
                                                          │                                 │
                                                          ▼                                 ▼
                                            PRE-WRITE CUTOVER ROLLBACK        POST-WRITE CUTOVER RECOVERY
                                            • Switching flag back to          • Toggling flag causes DATA LOSS.
                                              Firestore is SAFE & LOSSLESS.   • Fix forward on PostgreSQL, OR
                                                                              • Freeze & run DB reconciliation
                                                                                before restoring Firestore.
```

1. **Pre-Write Cutover Rollback Window:** Before PostgreSQL accepts authoritative post-cutover writes, toggling `PERSISTENCE_BACKEND=firestore` is completely safe and lossless because Firestore remains fully up to date.
2. **Post-Write Cutover Recovery Window:** Once PostgreSQL accepts authoritative writes, Firestore becomes stale/read-only diagnostic history. Toggling `PERSISTENCE_BACKEND=firestore` after this point will result in data loss. Recovery must occur via:
   - **Fix Forward (Recommended):** Apply patch directly to PostgreSQL while it remains authoritative.
   - **Reconciliation Recovery:** Freeze writes, execute a reverse PostgreSQL → Firestore reconciliation script, and then restore Firestore authority.

---

## J. Granular Configuration & Subsystem Provider Strategy

Phase 3 uses granular temporary provider flags to support staged subsystem migration:

```bash
# Core Persistence Flag
PERSISTENCE_BACKEND="postgresql"        # Options: "firestore" | "postgresql"

# Default Inference Provider
INFERENCE_PROVIDER_DEFAULT="google"     # Options: "google" | "openai"

# Subsystem Provider Overrides (Temporary Phase 3 Flags)
PROVIDER_ROUTING="openai"              # Options: "google" | "openai" (gpt-5.6-luna)
PROVIDER_ANALYSTS="openai"             # Options: "google" | "openai" (working_state, continuity, preferences)
PROVIDER_SPECIALISTS="openai"          # Options: "google" | "openai" (source, computational, requirements)
PROVIDER_ARTIFACTS="google"            # Options: "google" | "openai" (synthesis, generic artifacts)
PROVIDER_SEARCH="google"               # Options: "google" | "openai" (research web search)
PROVIDER_RESPONDER="google"            # Options: "google" | "openai" (ADK wrapper vs OpenAIResponderAdapter)
PROVIDER_SPEECH="google"               # Options: "google" | "openai" (gpt-transcribe & gpt-4o-mini-tts)
```

After Phase 3 completes and Google dependencies are retired, these temporary override flags will be collapsed into a single unified `INFERENCE_PROVIDER_DEFAULT="openai"` setting.

---

## K. Verification Gates & Benchmarked Operational Recommendations

| Phase | Required Test Suite / Command | Verification Criteria & Parity Gate | Operational Recommendation (Requires Benchmarking) |
| :--- | :--- | :--- | :--- |
| **Phase 1** | `pytest tests/test_agent_col_turn_service.py` | All interface wrappers pass unit tests with existing Firestore/Google logic. | Initial dev soak window before staging |
| **Phase 2** | `pytest tests/test_database.py` + Manifest Validator | Migration Manifest zero-missing parity, FK integrity check passes. | Recommended 48-72h staging soak; PostgreSQL pool max 20 connections |
| **Phase 3a** | `pytest tests/test_agent_col_routing_v4.py` | v4 intent routing returns 100% valid `AgentColRoutingDecisionV4` structures via `gpt-5.6-luna`. | Latency target < 350ms |
| **Phase 3b** | `pytest tests/test_working_state_service.py` | Working state snapshots extract valid `WorkingStateSnapshot` objects. | Snapshot extraction < 700ms |
| **Phase 3c-d**| `pytest tests/test_synthesis.py` | Blueprint synthesis and single-file artifact generation match Pydantic schemas. | Synthesis model timeout recommendation < 15s |
| **Phase 3e** | `pytest tests/test_research_expert.py` | Web search annotations map cleanly into `CitationReceipt` objects. | Optional snippet handling verified |
| **Phase 3f** | `pytest tests/test_chat_turns.py` | `OpenAIResponderAdapter` streams text deltas and final `ChatResponse` SSE payloads. | Full streaming turn pass |
| **Phase 3g** | `pytest tests/test_speech_service.py` | STT transcription and TTS audio synthesis succeed using `gpt-transcribe` / `gpt-4o-mini-tts`. | Audio roundtrip success |

*Note: Soak durations, connection pool limits, and timeout values are initial operational recommendations that must be validated through benchmark evaluations prior to production selection.*

---

## L. Detailed Rollback & Recovery Matrix Per Phase

| Phase | Trigger Condition | Pre-Cutover / Pre-Write Action | Post-Write Recovery Action | Data Loss Impact |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 1** | Interface wrapper regression in unit tests. | Revert code via Git. | N/A | **None** |
| **Phase 2** | DB latency spike or manifest check failure. | Toggle `PERSISTENCE_BACKEND=firestore`. | Freeze writes; execute DB → Firestore reconciliation script before switching. | **None (Pre-write)** / **Reconciliation required (Post-write)** |
| **Phase 3a-e**| Validation failures on specific OpenAI subsystem. | Revert `PROVIDER_<SUBSYSTEM>=google`. | Revert `PROVIDER_<SUBSYSTEM>=google` (Fix forward on provider level). | **None** (DB state preserved). |
| **Phase 3f** | `OpenAIResponderAdapter` streaming stall or turn error. | Revert `PROVIDER_RESPONDER=google`. | Revert `PROVIDER_RESPONDER=google` (Re-engages Google ADK Runner). | **None** (Turn claims handled in PostgreSQL). |
| **Phase 3g** | Audio transcription / synthesis error rate increase. | Revert `PROVIDER_SPEECH=google`. | Revert `PROVIDER_SPEECH=google`. | **None** |

---

## M. Final Google Dependency Removal Checklist

- [ ] `database.py` Firestore `AsyncClient` references replaced by `PostgresMemoryEngine` (or moved to legacy module).
- [ ] `agent_job_repository.py` Firestore queries replaced by `PostgresAgentJobRepository`.
- [ ] `agent_col_responder.py` and `supervisor_runtime.py` Google ADK imports removed.
- [ ] `vertex_config.py` removed; replaced by `openai_config.py`.
- [ ] `research_expert_service.py` `types.GoogleSearch` grounding removed; replaced by OpenAI Web Search tool.
- [ ] `speech_service.py` Google Speech SDKs removed; replaced by OpenAI Speech APIs.
- [ ] `requirements.txt` cleaned of `google-genai`, `google-adk`, `google-cloud-firestore`, `google-cloud-speech`, `google-cloud-texttospeech`.
- [ ] Repository grep check for `google.genai` and `google.adk` returns **0 occurrences** in production application code.

---

## N. Risks and Unresolved Questions

1. **Reasoning Effort Latency Impact:** `gpt-5.6-sol` with high reasoning effort under complex code synthesis workloads must be benchmarked to establish production timeout thresholds.
2. **PostgreSQL Connection Pool Tuning:** Async connection pool parameters (`asyncpg` pool max connections) must be benchmarked under high-concurrency background `AgentJob` worker execution.
3. **Migration Manifest Catch-Up Performance:** The delta migration script duration during the Phase 2 freeze window must be benchmarked on representative dataset sizes to minimize maintenance mode downtime.
