# Verified Firestore Audit & Target PostgreSQL Migration Architecture

This document records the verified Firestore source contract and a proposed PostgreSQL normalization derived from the application repository source code: [`database.py`](../../database.py), [`agent_job_repository.py`](../../agent_job_repository.py), [`schemas.py`](../../schemas.py), [`chat_turns.py`](../../chat_turns.py), [`collaborative_notes.py`](../../collaborative_notes.py), [`collaborative_note_policy.py`](../../collaborative_note_policy.py), [`memory_policy.py`](../../memory_policy.py), [`memory_proposals.py`](../../memory_proposals.py), [`memory_clarifications.py`](../../memory_clarifications.py), [`preference_learning.py`](../../preference_learning.py), [`working_state.py`](../../working_state.py), [`firestore.indexes.json`](../../firestore.indexes.json), and [`docs/repo-map.md`](../repo-map.md).

The Firestore inventory is **CURRENT SOURCE**. The relational DDL is **TARGET DESIGN** and includes explicitly labeled normalization and worker-runtime extensions. It is not an implementation-state claim. Any stronger SQL constraint must pass a migration preflight against existing Firestore records before deployment.

---

## A. Exact Firestore Persistence Inventory

The table below catalogs every Firestore collection, path structure, document keying strategy, and document payload type strictly as implemented in the codebase:

| Firestore Collection Path | Document Keying Strategy | Source Model / Payload Class | Primary Ownership & Scope | Key Persisted Fields |
| :--- | :--- | :--- | :--- | :--- |
| `users/{user_id}` | `user_id` (str) | `dict` + `VersionedCollaborationProfile` | Global user identity | Top-level profile fields (`identity_context`, `active_preferences`, `schema_version`, etc.) + `memory_updated_at` |
| `users/{user_id}/workspaces/{workspace_id}` | `workspace_id` (str) | `WorkspaceSummary` | User workspace scope | `workspace_contract_version`, `workspace_id`, `display_name`, `created_at`, `updated_at`, `is_default`, `deleted` |
| `.../note_proposals/{proposal_id}` | `proposal_id` (`"note_proposal--" + digest`) | `CollaborativeNoteProposal` | Workspace note proposal | `proposal_id`, `note_kind`, `title`, `body`, `source_session_id`, `source_message_ids`, `expected_note_id`, `expected_revision`, `policy_version`, `status`, `created_at`, `expires_at`, `resolved_at` |
| `.../collaborative_notes/{note_id}` | `note_id` (`"note--" + digest` or `expected_note_id`) | `CollaborativeNote` | Workspace note scope | `note_id`, `owner_user_id`, `workspace_id`, `note_kind`, `title`, `body`, `status`, `revision`, `source_session_id`, `source_message_ids`, `source_event_id`, `created_at`, `updated_at` |
| `.../collaborative_notes/{note_id}/events/{event_id}` | `event_id` (`note_id + "--" + event_type + "--" + seed`) | `CollaborativeNoteEvent` | Note revision event history | `event_id`, `note_id`, `proposal_id` (nullable), `owner_user_id`, `workspace_id`, `event_type`, `note_kind` (nullable), `title` (nullable), `body` (nullable), `source_session_id` (nullable), `source_message_ids`, `revision`, `previous_revision`, `created_at` |
| `.../preference_observations/{obs_id}` | `observation_id` (IdentifierStr) | `PreferenceObservation` | Workspace preference tracking | `observation_id`, `authority`, `user_id`, `project_id`, `session_id`, `source_turn_id`, `source_message_id`, `category`, `canonical_value`, `evidence_kind`, `evidence_summary`, `confidence_delta`, `created_at`, `is_active_memory`, `can_adapt_response` |
| `.../preference_hypotheses/{hyp_id}` | `hypothesis_id` (`"pref-hyp--" + ...`) | `PreferenceHypothesis` | Workspace preference hypothesis | `hypothesis_id`, `authority`, `user_id`, `project_id`, `category`, `canonical_value`, `evidence_count`, `contradiction_count`, `confidence`, `source_observation_ids`, `first_observed_at`, `last_observed_at`, `is_active_memory`, `can_adapt_response` |
| `.../agent_jobs/{job_id}` | `job_id` (IdentifierStr) | `AgentJob` | Background job state | `job_id`, `user_id`, `project_id`, `workspace_id`, `session_id`, `source_turn_id`, `source_message_id`, `action_kind`, `status`, `display_label`, `agent_label`, `created_at`, `updated_at`, `idempotency_key`, `attempt_count`, `lease_owner`, `lease_expires_at`, `result_refs`, `failure_summary`, `retry_of_job_id` |
| `.../agent_jobs/{job_id}/private_payloads/payload` | Static `"payload"` | `AgentJobPayload` | Protected job payload storage | Full `AgentJobPayload` envelope: `schema_version`, `job_id`, owner/scope IDs, source IDs, `action_kind`, `created_at`, and inner `payload` JSON object |
| `.../agent_jobs/{job_id}/events/{event_id}` | `event_id` (IdentifierStr) | `AgentJobEvent` | Background job execution audit | `event_id`, `job_id`, `event_type`, `message`, `created_at`, `status`, `public_visibility`, `metadata` |
| `.../agent_job_reports/{report_id}` | Worker-derived `report_id` distinct from `job_id` | `AgentJobReport` | Completed background job report | `report_id`, `job_id`, `user_id`, `project_id`, `workspace_id`, `session_id`, `action_kind`, `agent_label`, `status`, `title`, `summary`, `public_resource_label`, `public_metadata`, `created_at` |
| `users/{user_id}/memory_proposals/{category}` | `category` (str) | `MemoryProposal` / `MemoryProposalV2` | User governed memory proposal category slot | `proposal_id` (inner), `category`, `proposed_value`, `expected_signal_id`, `policy_version`, `status`, `source_session_id`, `source_message_id`, `evidence_message_id`, `clarification_id`, `created_at`, `expires_at`, `resolved_at` |
| `users/{user_id}/memory_proposal_origins/{origin_id}` | `origin_id` (SHA256 32-char prefix) | `ProposalOriginV1` / `ProposalOriginV2` | Memory proposal deduplication origin | `schema_version`, `proposal_id`, `category`, `source_session_id`, `source_message_id`, `evidence_message_id`, `clarification_id`, `created_at` |
| `users/{user_id}/memory_events/{event_id}` | `event_id` (IdentifierStr) | `MemoryEvent` / `MemoryEventV2` | Memory provenance audit log | `event_id`, `event_type`, `signal_id`, `category`, `value` (memory value), `policy_version`, `source_type`, `source_session_id`, `source_message_id`, `evidence_message_id`, `clarification_id`, `confirmation_channel`, `confirmation_session_id`, `confirmation_message_id`, `related_signal_id`, `memory_revision`, `created_at` |
| `sessions/{session_id}` | `session_id` (IdentifierStr) | `ChatSessionSummary` | Chat session container | `project_id`, `user_id`, `display_title`, `last_message_preview`, `last_message_role`, `last_completed_turn_id`, `active_memory_clarification_id`, `last_consumed_memory_clarification_id`, `last_consuming_memory_turn_id`, `created_at`, `updated_at` |
| `sessions/{session_id}/messages/{message_id}` | `message_id` (Auto or `turn--<id>--user/model`) | `ChatMessage` | Session transcript messages | `role` (`"user"` \| `"model"`), `text`, `timestamp` |
| `sessions/{session_id}/turns/{turn_id}` | `turn_id` (`hashlib.sha256(key)`) | `ChatTurnClaim` / `ChatTurnRecord` | Durable chat turn claims & leases | `schema_version`, `status` (`"in_progress"` \| `"completed"`), `project_id`, `user_id`, `user_message_id`, `model_message_id`, `lease_owner`, `lease_expires_at`, `memory_decision`, `memory_clarification_selection`, `artifact_feedback_decision`, `collaborative_note_decision`, `continuity_selection`, `actions`, `artifacts`, `citations`, `memory_proposals`, `memory_clarifications`, `collaborative_note_proposals`, `collaborative_note_events`, `artifact_feedback`, `adaptation`, `continuity`, `working_state`, `quality`, `created_at`, `updated_at`, `completed_at` |
| `sessions/{session_id}/memory_clarifications/{id}` | `clarification_id` (IdentifierStr) | `MemoryClarificationEnvelope` | Pending memory ambiguity envelope | `clarification_schema_version`, `clarification_id`, `user_id`, `session_id`, `workspace_id`, `evidence_message_id`, `clarification_turn_id`, `candidates`, `status` (`"open"` \| `"consumed"` \| `"expired"`), `created_at`, `expires_at`, `consuming_turn_id`, `consuming_message_id`, `selected_candidate_index` |
| `sessions/{session_id}/working_state/current` | Static `"current"` | `WorkingStateSnapshot` | Hidden session working state | `schema_version`, `status`, `authority`, `user_id`, `project_id`, `session_id`, `source_message_id`, `request_summary`, `current_goal`, `intent_hypothesis`, `active_constraints`, `unresolved_questions`, `clarification_status`, `next_step_hypothesis`, `confidence`, `updated_at` |
| `projects/{project_id}` | `project_id` (str) | Dict | Project anchor container | `updated_at` |
| `projects/{project_id}/blueprints/{blueprint_id}` | `blueprint_id` (Auto str) | `BlueprintDocumentRecord` | Project synthesis blueprint | `artifact_contract_version`, `artifact_type`, `created_at`, `originating_session_id`, `originating_turn_id`, `user_id`, `model_name`, `schema_version`, `parent_artifact_id`, `feedback_counts`, `adaptation_receipts`, `applied_feedback_ids`, `blueprint` (JSONB) |
| `.../blueprints/{blueprint_id}/feedback/{id}` | `feedback_id` (IdentifierStr) | `BlueprintFeedbackDocumentRecord` | Blueprint feedback | `feedback_contract_version`, `feedback_id`, `artifact_id`, `target_id`, `target_kind`, `decision`, `feedback_text`, `correction_text`, `originating_session_id`, `source_message_id`, `originating_turn_id`, `user_id`, `schema_version`, `status` (`"active"`), `supersedes_feedback_id`, `created_at` |
| `.../feedback_supersessions/{supersession_id}` | `supersession_id` (`supersedes_feedback_id`) | Dict | Feedback replacement audit | `supersession_contract_version`, `supersedes_feedback_id`, `superseded_by_feedback_id`, `created_at` |
| `projects/{project_id}/artifacts/{artifact_id}` | `artifact_id` (Auto str) | `ArtifactDocumentRecord` | Generic single-file artifacts | `artifact_contract_version`, `artifact_type`, `created_at`, `originating_session_id`, `originating_turn_id`, `user_id`, `model_name`, `schema_version`, `display_label`, `parent_artifact_id`, `lifecycle_status` (`"active"` \| `"archived"` \| `"deleted"`), `filename`, `artifact_family`, `format`, `byte_size`, `content`, `summary`, `deleted` (bool), `deleted_at`, `updated_at` |

---

## B. Corrected PostgreSQL Entity Relationship Diagram

```mermaid
erDiagram
    USERS ||--o{ WORKSPACES : "owns"
    WORKSPACES ||--o1 PROJECTS : "1:1 mapping"
    USERS ||--o{ MEMORY_PROPOSALS : "owns (category slots)"
    USERS ||--o{ MEMORY_PROPOSAL_ORIGINS : "owns (provenance log)"
    USERS ||--o{ MEMORY_EVENTS : "owns"
    
    WORKSPACES ||--o{ NOTE_PROPOSALS : "contains"
    WORKSPACES ||--o{ COLLABORATIVE_NOTES : "contains"
    WORKSPACES ||--o{ NOTE_EVENTS : "contains note events"
    
    WORKSPACES ||--o{ PREFERENCE_OBSERVATIONS : "tracks"
    WORKSPACES ||--o{ PREFERENCE_HYPOTHESES : "evaluates"
    
    USERS ||--o{ SESSIONS : "owns"
    PROJECTS ||--o{ SESSIONS : "contains"
    SESSIONS ||--o{ MESSAGES : "transcript"
    SESSIONS ||--o{ CHAT_TURNS : "leases & claims"
    SESSIONS ||--o1 SESSION_WORKING_STATE : "hidden state"
    SESSIONS ||--o{ MEMORY_CLARIFICATIONS : "clarifications"
    
    PROJECTS ||--o{ BLUEPRINTS : "synthesis"
    BLUEPRINTS ||--o{ BLUEPRINT_FEEDBACK : "feedback"
    BLUEPRINTS ||--o{ BLUEPRINT_FEEDBACK_SUPERSESSIONS : "supersessions"
    PROJECTS ||--o{ ARTIFACTS : "generates"
    
    WORKSPACES ||--o{ AGENT_JOBS : "queues"
    AGENT_JOBS ||--o1 AGENT_JOB_PRIVATE_PAYLOADS : "private payload"
    AGENT_JOBS ||--o{ AGENT_JOB_EVENTS : "audit events"
    AGENT_JOBS ||--o1 AGENT_JOB_REPORTS : "terminal report"
```

---

## C. Target Relational DDL (Data Definition Language)

The source stores message and turn IDs beneath a session document while `derive_chat_turn_ids()` hashes only the request idempotency key. PostgreSQL therefore uses composite `(session_id, logical_id)` keys. This preserves source identity scope and prevents identical client idempotency keys in different sessions from colliding.

```sql
-- 1. Base Identity & Workspaces
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    -- POSTGRESQL NORMALIZATION — NOT A LITERAL FIRESTORE FIELD
    -- Packs Firestore top-level user fields (identity_context, active_preferences, memory_updated_at)
    collaboration_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- POSTGRESQL NORMALIZATION — NOT A LITERAL FIRESTORE FIELD
    -- Operational SQL timestamps for user entity creation/update tracking; not literal Firestore user fields
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE workspaces (
    workspace_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    workspace_contract_version TEXT NOT NULL DEFAULT '1.0',
    display_name TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    -- TARGET NORMALIZATION: populate only after preflight proves the current
    -- project_id == workspace_id convention for the migrated record.
    workspace_id TEXT UNIQUE REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. Chat Sessions & Messages
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    display_title TEXT NOT NULL,
    last_message_preview TEXT,
    last_message_role TEXT,
    last_completed_turn_id TEXT,
    active_memory_clarification_id TEXT, -- Added lifecycle pointer
    last_consumed_memory_clarification_id TEXT, -- Added lifecycle pointer
    last_consuming_memory_turn_id TEXT, -- Added lifecycle pointer
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE messages (
    message_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'model')),
    text TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, message_id)
);

CREATE TABLE chat_turns (
    turn_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
    user_message_id TEXT NOT NULL,
    model_message_id TEXT,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    -- POSTGRESQL NORMALIZATION — NOT A LITERAL FIRESTORE FIELD
    -- Stored Firestore document derives turn_id from request idempotency key but does not store literal field
    idempotency_key TEXT,
    memory_decision JSONB,
    memory_clarification_selection JSONB,
    artifact_feedback_decision JSONB,
    collaborative_note_decision JSONB,
    continuity_selection JSONB,
    actions JSONB DEFAULT '[]'::jsonb,
    artifacts JSONB DEFAULT '[]'::jsonb,
    citations JSONB DEFAULT '[]'::jsonb,
    memory_proposals JSONB DEFAULT '[]'::jsonb,
    memory_clarifications JSONB DEFAULT '[]'::jsonb,
    collaborative_note_proposals JSONB DEFAULT '[]'::jsonb,
    collaborative_note_events JSONB DEFAULT '[]'::jsonb,
    artifact_feedback JSONB DEFAULT '[]'::jsonb,
    adaptation JSONB,
    continuity JSONB,
    working_state JSONB,
    quality JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (session_id, turn_id),
    UNIQUE (session_id, idempotency_key),
    FOREIGN KEY (session_id, user_message_id) REFERENCES messages(session_id, message_id),
    FOREIGN KEY (session_id, model_message_id) REFERENCES messages(session_id, message_id)
);

-- 3. Collaborative Notes, Proposals, & Events
CREATE TABLE note_proposals (
    proposal_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
    note_kind TEXT NOT NULL CHECK (note_kind IN ('decision', 'requirement', 'constraint', 'task_state', 'working_context')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source_session_id TEXT NOT NULL REFERENCES sessions(session_id),
    expected_note_id TEXT,
    expected_revision INTEGER,
    policy_version TEXT NOT NULL DEFAULT '1.0',
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    CHECK ((expected_note_id IS NULL) = (expected_revision IS NULL))
);

CREATE TABLE note_proposal_source_messages (
    proposal_id TEXT NOT NULL REFERENCES note_proposals(proposal_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    message_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 5),
    PRIMARY KEY (proposal_id, session_id, message_id),
    FOREIGN KEY (session_id, message_id) REFERENCES messages(session_id, message_id) ON DELETE CASCADE
);

CREATE TABLE collaborative_notes (
    note_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
    note_kind TEXT NOT NULL CHECK (note_kind IN ('decision', 'requirement', 'constraint', 'task_state', 'working_context')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    revision INTEGER NOT NULL DEFAULT 1,
    source_session_id TEXT NOT NULL REFERENCES sessions(session_id),
    source_event_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE note_source_messages (
    note_id TEXT NOT NULL REFERENCES collaborative_notes(note_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    message_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 5),
    PRIMARY KEY (note_id, session_id, message_id),
    FOREIGN KEY (session_id, message_id) REFERENCES messages(session_id, message_id) ON DELETE CASCADE
);

CREATE TABLE note_events (
    event_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL, -- Provenance & locator metadata; NOT FK to collaborative_notes(note_id) because events exist even if parent note is not created (e.g. rejected proposals) or deleted
    proposal_id TEXT REFERENCES note_proposals(proposal_id), -- Nullable for lifecycle/direct actions
    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('approved', 'corrected', 'rejected', 'superseded', 'archived', 'restored', 'deleted')),
    note_kind TEXT CHECK (note_kind IN ('decision', 'requirement', 'constraint', 'task_state', 'working_context')), -- Nullable for deleted/rejected events
    title TEXT, -- Nullable for deleted/rejected events
    body TEXT, -- Nullable for deleted/rejected events
    source_session_id TEXT REFERENCES sessions(session_id), -- Nullable for lifecycle events
    revision INTEGER NOT NULL,
    previous_revision INTEGER,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE note_event_source_messages (
    event_id TEXT NOT NULL REFERENCES note_events(event_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    message_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 5),
    PRIMARY KEY (event_id, session_id, message_id),
    FOREIGN KEY (session_id, message_id) REFERENCES messages(session_id, message_id) ON DELETE CASCADE
);

-- 4. Governed Memory Proposals, Origins, & Events
CREATE TABLE memory_proposals (
    proposal_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    proposed_value JSONB NOT NULL,
    expected_signal_id TEXT,
    policy_version TEXT NOT NULL CHECK (policy_version IN ('1.0', '2.0')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    source_session_id TEXT NOT NULL REFERENCES sessions(session_id),
    source_message_id TEXT NOT NULL,
    evidence_message_id TEXT,
    clarification_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    -- Mirrors the single mutable Firestore category-slot document across all statuses.
    UNIQUE (user_id, category),
    FOREIGN KEY (source_session_id, source_message_id) REFERENCES messages(session_id, message_id),
    FOREIGN KEY (source_session_id, evidence_message_id) REFERENCES messages(session_id, message_id)
);

CREATE TABLE memory_proposal_origins (
    origin_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    schema_version TEXT NOT NULL CHECK (schema_version IN ('1.0', '2.0')),
    proposal_id TEXT NOT NULL, -- Provenance metadata; NOT FK to memory_proposals(proposal_id) to preserve historical origin records across category slot replacements
    category TEXT NOT NULL,
    source_session_id TEXT NOT NULL REFERENCES sessions(session_id),
    source_message_id TEXT NOT NULL,
    evidence_message_id TEXT,
    clarification_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (source_session_id, source_message_id) REFERENCES messages(session_id, message_id),
    FOREIGN KEY (source_session_id, evidence_message_id) REFERENCES messages(session_id, message_id)
);

CREATE TABLE memory_events (
    event_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    signal_id TEXT,
    category TEXT NOT NULL,
    value JSONB NOT NULL, -- Exact Firestore source field name ('value')
    policy_version TEXT NOT NULL CHECK (policy_version IN ('1.0', '2.0')),
    source_type TEXT NOT NULL DEFAULT 'explicit_user_feedback',
    source_session_id TEXT REFERENCES sessions(session_id),
    source_message_id TEXT,
    evidence_message_id TEXT, -- V2 field
    clarification_id TEXT, -- V2 field
    confirmation_channel TEXT,
    confirmation_session_id TEXT REFERENCES sessions(session_id),
    confirmation_message_id TEXT,
    related_signal_id TEXT,
    memory_revision INTEGER NOT NULL DEFAULT 1, -- Exact Firestore source field name ('memory_revision')
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (source_session_id, source_message_id) REFERENCES messages(session_id, message_id),
    FOREIGN KEY (source_session_id, evidence_message_id) REFERENCES messages(session_id, message_id),
    FOREIGN KEY (confirmation_session_id, confirmation_message_id) REFERENCES messages(session_id, message_id)
);

-- 5. Memory Ambiguity Clarification Envelope
CREATE TABLE memory_clarifications (
    clarification_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    evidence_message_id TEXT NOT NULL,
    clarification_turn_id TEXT NOT NULL,
    clarification_schema_version TEXT NOT NULL DEFAULT '1.0',
    candidates JSONB NOT NULL, -- Array of MemoryClarificationCandidate JSON objects
    status TEXT NOT NULL CHECK (status IN ('open', 'consumed', 'expired')),
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consuming_turn_id TEXT,
    consuming_message_id TEXT,
    selected_candidate_index INTEGER CHECK (selected_candidate_index BETWEEN 0 AND 4),
    FOREIGN KEY (session_id, evidence_message_id) REFERENCES messages(session_id, message_id),
    FOREIGN KEY (session_id, clarification_turn_id) REFERENCES chat_turns(session_id, turn_id),
    FOREIGN KEY (session_id, consuming_turn_id) REFERENCES chat_turns(session_id, turn_id),
    FOREIGN KEY (session_id, consuming_message_id) REFERENCES messages(session_id, message_id)
);

-- Add foreign key constraints for session clarification pointers after memory_clarifications table creation
ALTER TABLE sessions ADD CONSTRAINT fk_sessions_active_clarification FOREIGN KEY (active_memory_clarification_id) REFERENCES memory_clarifications(clarification_id) ON DELETE SET NULL;
ALTER TABLE sessions ADD CONSTRAINT fk_sessions_last_consumed_clarification FOREIGN KEY (last_consumed_memory_clarification_id) REFERENCES memory_clarifications(clarification_id) ON DELETE SET NULL;
ALTER TABLE sessions ADD CONSTRAINT fk_sessions_last_consuming_turn FOREIGN KEY (session_id, last_consuming_memory_turn_id) REFERENCES chat_turns(session_id, turn_id) ON DELETE SET NULL (last_consuming_memory_turn_id);

-- 6. Hidden Session Working State Snapshots
CREATE TABLE session_working_state (
    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    source_message_id TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    authority TEXT NOT NULL DEFAULT 'model_proposed',
    request_summary TEXT NOT NULL,
    current_goal TEXT NOT NULL,
    intent_hypothesis TEXT NOT NULL,
    active_constraints JSONB DEFAULT '[]'::jsonb,
    unresolved_questions JSONB DEFAULT '[]'::jsonb,
    clarification_status TEXT NOT NULL DEFAULT 'none',
    next_step_hypothesis TEXT NOT NULL,
    confidence NUMERIC(3, 2) NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    updated_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (session_id, source_message_id) REFERENCES messages(session_id, message_id)
);

-- 7. Preference Observations & Hypotheses
CREATE TABLE preference_observations (
    observation_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    source_turn_id TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    authority TEXT NOT NULL DEFAULT 'inferred',
    category TEXT NOT NULL,
    canonical_value TEXT NOT NULL,
    evidence_kind TEXT NOT NULL,
    evidence_summary TEXT NOT NULL,
    confidence_delta NUMERIC(3, 2) NOT NULL,
    is_active_memory BOOLEAN NOT NULL DEFAULT TRUE,
    can_adapt_response BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (session_id, source_turn_id) REFERENCES chat_turns(session_id, turn_id),
    FOREIGN KEY (session_id, source_message_id) REFERENCES messages(session_id, message_id)
);

CREATE TABLE preference_hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    authority TEXT NOT NULL DEFAULT 'inferred',
    category TEXT NOT NULL,
    canonical_value TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    confidence NUMERIC(3, 2) NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    source_observation_ids JSONB DEFAULT '[]'::jsonb,
    is_active_memory BOOLEAN NOT NULL DEFAULT TRUE,
    can_adapt_response BOOLEAN NOT NULL DEFAULT TRUE,
    first_observed_at TIMESTAMPTZ NOT NULL,
    last_observed_at TIMESTAMPTZ NOT NULL
);

-- 8. Artifacts, Blueprints, & Feedback
CREATE TABLE blueprints (
    blueprint_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    originating_session_id TEXT NOT NULL REFERENCES sessions(session_id),
    originating_turn_id TEXT,
    artifact_contract_version TEXT NOT NULL DEFAULT '1.0',
    artifact_type TEXT NOT NULL,
    model_name TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    parent_artifact_id TEXT REFERENCES blueprints(blueprint_id),
    feedback_counts JSONB DEFAULT '{}'::jsonb,
    adaptation_receipts JSONB DEFAULT '[]'::jsonb,
    applied_feedback_ids JSONB DEFAULT '[]'::jsonb,
    blueprint JSONB NOT NULL, -- Unindexed JSON document store per firestore.indexes.json
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (originating_session_id, originating_turn_id) REFERENCES chat_turns(session_id, turn_id)
);

CREATE TABLE blueprint_feedback (
    feedback_id TEXT PRIMARY KEY,
    blueprint_id TEXT NOT NULL REFERENCES blueprints(blueprint_id) ON DELETE CASCADE,
    target_id TEXT NOT NULL,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('blueprint', 'module', 'file', 'interface', 'dependency')),
    decision TEXT NOT NULL CHECK (decision IN ('accepted', 'corrected', 'rejected')),
    feedback_text TEXT,
    correction_text TEXT,
    originating_session_id TEXT NOT NULL REFERENCES sessions(session_id),
    source_message_id TEXT NOT NULL,
    originating_turn_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    feedback_contract_version TEXT NOT NULL DEFAULT '1.0',
    schema_version TEXT NOT NULL DEFAULT '1.0',
    status TEXT NOT NULL DEFAULT 'active', -- Source writes 'active' and does not mutate status on supersession
    supersedes_feedback_id TEXT REFERENCES blueprint_feedback(feedback_id),
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (originating_session_id, source_message_id) REFERENCES messages(session_id, message_id),
    FOREIGN KEY (originating_session_id, originating_turn_id) REFERENCES chat_turns(session_id, turn_id)
);

-- Separate relational table representing Firestore subcollection projects/{project_id}/blueprints/{blueprint_id}/feedback_supersessions/{supersession_id}
CREATE TABLE blueprint_feedback_supersessions (
    supersession_id TEXT PRIMARY KEY, -- Document ID is supersedes_feedback_id
    blueprint_id TEXT NOT NULL REFERENCES blueprints(blueprint_id) ON DELETE CASCADE,
    supersedes_feedback_id TEXT NOT NULL REFERENCES blueprint_feedback(feedback_id) ON DELETE CASCADE,
    superseded_by_feedback_id TEXT NOT NULL REFERENCES blueprint_feedback(feedback_id) ON DELETE CASCADE,
    supersession_contract_version TEXT NOT NULL DEFAULT '1.0',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    originating_session_id TEXT NOT NULL REFERENCES sessions(session_id),
    originating_turn_id TEXT,
    artifact_contract_version TEXT NOT NULL DEFAULT '1.0',
    artifact_type TEXT NOT NULL,
    model_name TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    display_label TEXT NOT NULL,
    filename TEXT NOT NULL,
    artifact_family TEXT NOT NULL,
    format TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('active', 'archived', 'deleted')),
    deleted BOOLEAN NOT NULL DEFAULT FALSE, -- Source checks deleted == True OR lifecycle_status == 'deleted'
    deleted_at TIMESTAMPTZ, -- Set when soft deleted
    parent_artifact_id TEXT REFERENCES artifacts(artifact_id),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (originating_session_id, originating_turn_id) REFERENCES chat_turns(session_id, turn_id)
);

-- 9. Background AgentJobs
CREATE TABLE agent_jobs (
    job_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    source_turn_id TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    action_kind TEXT NOT NULL CHECK (action_kind IN ('create_artifact', 'propose_collaborative_note', 'propose_memory_signal', 'retrieve_chat_context')),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    display_label TEXT NOT NULL,
    agent_label TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    -- TARGET WORKER-RUNTIME EXTENSION. Current Firestore AgentJob starts at 1;
    -- PostgreSQL defines attempts as successful execution lease acquisitions.
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    lease_generation BIGINT NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    result_refs JSONB DEFAULT '{}'::jsonb,
    failure_summary JSONB,
    retry_of_job_id TEXT REFERENCES agent_jobs(job_id),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (session_id, source_turn_id) REFERENCES chat_turns(session_id, turn_id),
    FOREIGN KEY (session_id, source_message_id) REFERENCES messages(session_id, message_id)
);

-- Derived table representing Firestore subcollection users/{user_id}/workspaces/{workspace_id}/agent_jobs/{job_id}/private_payloads/payload
CREATE TABLE agent_job_private_payloads (
    job_id TEXT PRIMARY KEY REFERENCES agent_jobs(job_id) ON DELETE CASCADE,
    -- Full AgentJobPayload envelope, not only its inner payload member.
    payload_document JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE agent_job_events (
    event_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES agent_jobs(job_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('queued', 'started', 'progress', 'completed', 'failed', 'cancelled')),
    message TEXT NOT NULL,
    status TEXT NOT NULL,
    public_visibility BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE agent_job_reports (
    report_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES agent_jobs(job_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    action_kind TEXT NOT NULL,
    agent_label TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    public_resource_label TEXT,
    public_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);
```

---

## D. Firestore Field → PostgreSQL Column Mapping Table

| Firestore Entity / Subcollection | Firestore Field Path | PostgreSQL Table | PostgreSQL Column | Data Type | Constraint / Default | Parity Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `users` | Document ID | `users` | `user_id` | `TEXT` | `PRIMARY KEY` | `PASS` |
| `users` | Top-level profile fields | `users` | `collaboration_profile` | `JSONB` | `DEFAULT '{}'::jsonb` | `POSTGRESQL NORMALIZATION — NOT A LITERAL FIRESTORE FIELD` |
| `users` | (Operational metadata) | `users` | `created_at` / `updated_at` | `TIMESTAMPTZ` | `DEFAULT CURRENT_TIMESTAMP` | `POSTGRESQL NORMALIZATION — NOT A LITERAL FIRESTORE FIELD` |
| `workspaces` | `workspace_id` | `workspaces` | `workspace_id` | `TEXT` | `PRIMARY KEY` | `PASS` |
| `workspaces` | `user_id` | `workspaces` | `user_id` | `TEXT` | `NOT NULL REFERENCES users(user_id)` | `PASS` |
| `sessions` | `session_id` | `sessions` | `session_id` | `TEXT` | `PRIMARY KEY` | `PASS` |
| `sessions` | `active_memory_clarification_id` | `sessions` | `active_memory_clarification_id` | `TEXT` | `REFERENCES memory_clarifications ON DELETE SET NULL` | `CORRECTED` |
| `sessions` | `last_consumed_memory_clarification_id` | `sessions` | `last_consumed_memory_clarification_id` | `TEXT` | `REFERENCES memory_clarifications ON DELETE SET NULL` | `CORRECTED` |
| `sessions` | `last_consuming_memory_turn_id` | `sessions` | `last_consuming_memory_turn_id` | `TEXT` | `REFERENCES chat_turns ON DELETE SET NULL` | `CORRECTED` |
| `messages` | Session-scoped document ID | `messages` | `(session_id, message_id)` | `TEXT, TEXT` | Composite primary key | `TARGET NORMALIZATION` |
| `note_proposals` | `proposal_id` | `note_proposals` | `proposal_id` | `TEXT` | `PRIMARY KEY` | `PASS` |
| `collaborative_notes` | `note_id` | `collaborative_notes` | `note_id` | `TEXT` | `PRIMARY KEY` | `PASS` |
| `note_events` | `note_id` | `note_events` | `note_id` | `TEXT` | `NOT NULL` (Unconstrained locator metadata; parent note doc not required) | `CORRECTED` |
| `note_events` | `proposal_id` | `note_events` | `proposal_id` | `TEXT` | Nullable (Direct lifecycle actions) | `CORRECTED` |
| `note_events` | `note_kind` / `title` / `body` / `source_session_id` | `note_events` | `note_kind` / `title` / `body` / `source_session_id` | `TEXT` | Nullable (Deleted/rejected events) | `CORRECTED` |
| `memory_proposals` | Document ID | `memory_proposals` | `category` | `TEXT` | `UNIQUE (user_id, category)` mutable slot across all statuses | `VERIFIED SOURCE PARITY` |
| `memory_proposal_origins` | `proposal_id` | `memory_proposal_origins` | `proposal_id` | `TEXT` | `NOT NULL` (Unconstrained provenance metadata) | `PASS` |
| `memory_events` | `value` | `memory_events` | `value` | `JSONB` | `NOT NULL` | `PASS` |
| `memory_events` | `memory_revision` | `memory_events` | `memory_revision` | `INTEGER` | `NOT NULL DEFAULT 1` | `PASS` |
| `memory_events` | `evidence_message_id` / `clarification_id` | `memory_events` | `evidence_message_id` / `clarification_id` | `TEXT` | Nullable (V2 fields) | `CORRECTED` |
| `memory_clarifications` | Document envelope | `memory_clarifications` | Envelope columns | Multiple | Full `MemoryClarificationEnvelope` schema | `CORRECTED` |
| `chat_turns` | Session-scoped document ID derived from idempotency | `chat_turns` | `(session_id, turn_id)` and `(session_id, idempotency_key)` | Composite keys | Session-scoped uniqueness | `TARGET NORMALIZATION` |
| `blueprints` | `blueprint` | `blueprints` | `blueprint` | `JSONB` | `NOT NULL` (Unindexed) | `PASS` |
| `blueprint_feedback` | `status` | `blueprint_feedback` | `status` | `TEXT` | `DEFAULT 'active'` | `PASS` |
| `.../feedback_supersessions/{id}` | Subcollection doc | `blueprint_feedback_supersessions` | Relational table | Multiple | `PRIMARY KEY (supersession_id)` | `CORRECTED` |
| `artifacts` | `deleted` / `deleted_at` / `lifecycle_status` | `artifacts` | `deleted` / `deleted_at` / `lifecycle_status` | `BOOLEAN/TIMESTAMPTZ/TEXT` | Preserves `deleted` OR `lifecycle_status == 'deleted'` | `CORRECTED` |
| `.../private_payloads/payload` | Full subcollection document | `agent_job_private_payloads` | `job_id`, `payload_document` | `TEXT`, `JSONB` | One full envelope per job | `TARGET NORMALIZATION` |
| `agent_jobs` | `attempt_count` starts at `1`; no generation/max fields | `agent_jobs` | `attempt_count`, `lease_generation`, `max_attempts` | Integer columns | Target worker semantics begin attempts at `0` and increment on claim | `TARGET WORKER-RUNTIME CHANGE` |
| `agent_job_reports` | Distinct worker-derived `report_id` plus `job_id` | `agent_job_reports` | `report_id`, `job_id` | `TEXT`, `TEXT` | Independent PK plus `UNIQUE(job_id)` FK | `VERIFIED SOURCE PARITY` |

---

## E. Foreign-Key Relationship Table

| Child Table | Foreign Key Column | Parent Table | Parent Key Column | On Delete Action | Source Relationship Grounding |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `workspaces` | `user_id` | `users` | `user_id` | `CASCADE` | Subcollection path `users/{user_id}/workspaces` |
| `projects` | `workspace_id` (target normalization) | `workspaces` | `workspace_id` | `CASCADE` | Nullable until migration preflight proves the current ID convention for each record |
| `sessions` | `user_id` | `users` | `user_id` | `CASCADE` | `session.user_id` validation in `database.py` |
| `sessions` | `project_id` | `projects` | `project_id` | `CASCADE` | `session.project_id` validation |
| `sessions` | `active_memory_clarification_id` | `memory_clarifications` | `clarification_id` | `SET NULL` | Active clarification lifecycle pointer |
| `sessions` | `last_consumed_memory_clarification_id` | `memory_clarifications` | `clarification_id` | `SET NULL` | Consumed clarification lifecycle pointer |
| `sessions` | `(session_id, last_consuming_memory_turn_id)` | `chat_turns` | `(session_id, turn_id)` | `SET NULL` | Session-scoped consuming turn lifecycle pointer |
| `messages` | `session_id` | `sessions` | `session_id` | `CASCADE` | Subcollection path `sessions/{session_id}/messages` |
| `note_proposals` | `workspace_id` | `workspaces` | `workspace_id` | `CASCADE` | Subcollection path `workspaces/{id}/note_proposals` |
| `note_proposal_source_messages` | `proposal_id` | `note_proposals` | `proposal_id` | `CASCADE` | Normalized `source_message_ids` tuple |
| `note_proposal_source_messages` | `(session_id, message_id)` | `messages` | `(session_id, message_id)` | `CASCADE` | Session-scoped source message validation |
| `collaborative_notes` | `workspace_id` | `workspaces` | `workspace_id` | `CASCADE` | Subcollection path `workspaces/{id}/collaborative_notes` |
| `note_events` | `note_id` | `None (Provenance metadata)` | `N/A` | `None` | Unconstrained locator metadata; parent note doc not required (e.g. rejected proposals, deleted notes) |
| `note_events` | `workspace_id` | `workspaces` | `workspace_id` | `CASCADE` | Relational ownership scope |
| `memory_proposals` | `user_id` | `users` | `user_id` | `CASCADE` | Subcollection path `users/{id}/memory_proposals` |
| `memory_proposal_origins` | `user_id` | `users` | `user_id` | `CASCADE` | Subcollection path `users/{id}/memory_proposal_origins` |
| `memory_proposal_origins` | `proposal_id` | `None (Provenance metadata)` | `N/A` | `None` | Unconstrained provenance column; preserves historical origin logs across category slot proposal replacements |
| `memory_clarifications` | `session_id` | `sessions` | `session_id` | `CASCADE` | Subcollection path `sessions/{session_id}/memory_clarifications` |
| `memory_clarifications` | `(session_id, clarification_turn_id)` | `chat_turns` | `(session_id, turn_id)` | `CASCADE` | Session-scoped clarification turn provenance |
| `chat_turns` | `session_id` | `sessions` | `session_id` | `CASCADE` | Subcollection path `sessions/{id}/turns` |
| `session_working_state` | `session_id` | `sessions` | `session_id` | `CASCADE` | Subcollection path `sessions/{id}/working_state/current` |
| `blueprints` | `project_id` | `projects` | `project_id` | `CASCADE` | Subcollection path `projects/{id}/blueprints` |
| `blueprint_feedback` | `blueprint_id` | `blueprints` | `blueprint_id` | `CASCADE` | Subcollection path `blueprints/{id}/feedback` |
| `blueprint_feedback_supersessions` | `blueprint_id` | `blueprints` | `blueprint_id` | `CASCADE` | Subcollection path `blueprints/{id}/feedback_supersessions` |
| `artifacts` | `project_id` | `projects` | `project_id` | `CASCADE` | Subcollection path `projects/{id}/artifacts` |
| `agent_jobs` | `workspace_id` | `workspaces` | `workspace_id` | `CASCADE` | Subcollection path `workspaces/{id}/agent_jobs` |
| `agent_job_private_payloads` | `job_id` | `agent_jobs` | `job_id` | `CASCADE` | Subcollection path `agent_jobs/{id}/private_payloads/payload` |
| `agent_job_reports` | `job_id` | `agent_jobs` | `job_id` | `CASCADE` | Subcollection path `workspaces/{id}/agent_job_reports` |

---

## F. PostgreSQL Index & Query Mapping

```sql
-- Query Path: List Chat Sessions by User & Project sorted by updated_at
CREATE INDEX idx_sessions_user_project_updated ON sessions(user_id, project_id, updated_at DESC);

-- Query Path: Stream Chronological Session Messages
CREATE INDEX idx_messages_session_timestamp ON messages(session_id, timestamp ASC);

-- Query Path: Session-scoped idempotency claim lookup
-- Already enforced by UNIQUE (session_id, idempotency_key) in chat_turns.

-- Query Path: List Visible Active Workspaces for User
CREATE INDEX idx_workspaces_user_active ON workspaces(user_id) WHERE deleted IS FALSE;

-- Query Path: Lookup Category Slot Proposal for User
CREATE UNIQUE INDEX idx_memory_proposals_user_category ON memory_proposals(user_id, category);

-- Query Path: Historical Origin Lookup by User & Category
CREATE INDEX idx_memory_proposal_origins_user_category ON memory_proposal_origins(user_id, category);

-- Query Path: Active Clarification Envelope Lookup
CREATE INDEX idx_memory_clarifications_session_status ON memory_clarifications(session_id, status);

-- Query Path: Active Artifacts Lookup by Project
CREATE INDEX idx_artifacts_project_lifecycle ON artifacts(project_id, lifecycle_status) WHERE deleted IS FALSE;

-- Query Path: AgentJob idempotency within its workspace authority boundary
CREATE UNIQUE INDEX idx_agent_jobs_workspace_idempotency ON agent_jobs(workspace_id, idempotency_key);

-- Query Path: Queue claims and expired-lease recovery by action kind
CREATE INDEX idx_agent_jobs_claim ON agent_jobs(action_kind, created_at)
WHERE status = 'queued';
CREATE INDEX idx_agent_jobs_expired_lease ON agent_jobs(lease_expires_at)
WHERE status = 'running';
```

---

## G. Source-Parity and Target-Normalization Verification

The table below summarizes the source verification status for every domain in the PostgreSQL migration mapping contract:

| Domain | Parity Status | Canonical Source Evidence | Resulting PostgreSQL Representation |
| :--- | :--- | :--- | :--- |
| **User Profile & Timestamps** | `POSTGRESQL NORMALIZATION — NOT A LITERAL FIRESTORE FIELD` | `database.py:7896` (`_collaboration_profile_document` dumps profile into top-level fields) | `users.collaboration_profile JSONB` packs top-level profile fields including `memory_updated_at`. `created_at`/`updated_at` are operational SQL timestamps. |
| **Note Event Locator Metadata** | `CORRECTED` | `database.py:7500` / `schemas.py:672` (Note events created under `note_id` subcollection path even when parent note document does not exist, e.g., rejected proposals or deleted notes) | `note_events.note_id TEXT NOT NULL` preserved as unconstrained locator/provenance metadata without FK to `collaborative_notes(note_id)`. |
| **Session Clarification Pointers** | `CORRECTED` | `database.py:1691`, `5891` (`active_memory_clarification_id`, `last_consumed_memory_clarification_id`, `last_consuming_memory_turn_id`) | Added 3 lifecycle pointer columns in `sessions` with `ON DELETE SET NULL` foreign keys to `memory_clarifications` and `chat_turns`. |
| **Turn and Message Identity Scope** | `TARGET NORMALIZATION` | `chat_turns.py:127-133` derives IDs from the idempotency key while `database.py` stores them below a session path | Composite `(session_id, logical_id)` keys and session-scoped idempotency prevent cross-session collisions. |
| **Note Event Nullability** | `CORRECTED` | `schemas.py:673-680` (`CollaborativeNoteEvent` permits null proposal_id, note_kind, title, body, source_session_id) | `note_events` columns made nullable; source-message junction table permits 0 rows for direct actions. |
| **Memory Event Source Fields** | `CORRECTED` | `schemas.py:1115,1124,1338,1339` (`value`, `memory_revision`, `evidence_message_id`, `clarification_id`) | `memory_events` schema aligned to exact source field names (`value`, `memory_revision`) and V2 provenance fields. |
| **Memory Clarification Envelope** | `CORRECTED` | `memory_clarifications.py:78-98` (`MemoryClarificationEnvelope`) | `memory_clarifications` table updated with complete 14-field envelope schema and `open`/`consumed`/`expired` status. |
| **Blueprint Feedback Lifecycle** | `CORRECTED` | `database.py:2961,2983` (`status: "active"`, `feedback_supersessions` subcollection) | `blueprint_feedback.status` defaults to `'active'`; separate `blueprint_feedback_supersessions` table created. |
| **Artifact Soft Deletion** | `CORRECTED` | `database.py:4642,5068` (`deleted`, `deleted_at`, `lifecycle_status`) | `artifacts` preserves `deleted BOOLEAN`, `deleted_at TIMESTAMPTZ`, and `lifecycle_status CHECK (...)`. |
| **Artifact Lineage and Summary Nullability** | `CORRECTED` | `database.py:4352-4366,4386-4396,4420-4448`; `schemas.py:263-268` | Blueprint/artifact turn lineage and single-file summary remain nullable; IDs remain source-generated unless a later idempotent effect-key design replaces them. |
| **Note Expected Revision Pair** | `CORRECTED` | `schemas.py:623-629` | Removed the revision default and added paired-nullability enforcement for expected note ID/revision. |
| **AgentJob Private Payload Path** | `CORRECTED` / `POSTGRESQL NORMALIZATION` | `agent_job_repository.py:803` (`.../agent_jobs/{job_id}/private_payloads/payload`) | Corrected Firestore path inventory; `agent_job_private_payloads` table normalized per job. |
| **AgentJob Runtime Extensions** | `TARGET WORKER-RUNTIME CHANGE` | `agent_col_agent_jobs.py:81-103`; worker target in `docs/agent-jobs/postgresql-agentjob-worker-runtime-research.md` | Source fields are preserved while `lease_generation` and `max_attempts` are explicit target additions; target attempt semantics start at zero and increment per acquired lease. |
| **AgentJob Report Identity** | `CORRECTED` | `collaborative_note_job_worker.py:98-99`; `memory_proposal_job_worker.py:450-452`; `agent_col_artifact_executor.py:816-818` | `report_id` is independent from `job_id`; `job_id` remains the one-report-per-job foreign key. |
| **Governed Memory Category Slots** | `VERIFIED SOURCE PARITY` | `database.py:5728,6260` (`users/{id}/memory_proposals/{category}`) | `memory_proposals` models one mutable row per `(user_id, category)` across all statuses; origins/events retain history separately. |
