# Phase 4A.4 Work Inspection and Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the lightweight workspace load canonical Work artifacts, inspect schema-2.0 synthesis blueprint detail, and submit explicit artifact feedback through the existing chat boundary.

**Architecture:** Keep the browser same-origin and dependency-free. Add a focused Work view module for artifact list, detail, download, feedback controls, and feedback history; extend API, request, and state helpers so artifact behavior is testable without a browser; keep `app.mjs` as composition glue. The frontend reads canonical artifact data from backend read APIs and writes feedback only through structured `/api/chat` turns.

**Tech Stack:** Python 3.14, FastAPI, httpx/pytest, semantic HTML, CSS custom properties, browser-native JavaScript ES modules, Node 26 `node --test`.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-4a-lightweight-browser-workspace-design.md`

## Global Constraints

- Use `BACKEND_FRONTEND_INTEGRATION_CONTRACT_INVENTORY.md` as the source of truth for implemented HTTP contracts.
- User-facing copy must say `Agent Col`; keep `Agent_Col` only where it is a technical identifier, code symbol, file path, schema name, or backend contract value.
- Use only the implemented artifact read APIs:
  - `GET /api/projects/{project_id}/blueprints?limit=20&before=CURSOR`
  - `GET /api/projects/{project_id}/blueprints/{blueprint_id}`
  - `GET /api/projects/{project_id}/blueprints/{blueprint_id}/feedback?limit=20&before=CURSOR`
- Submit artifact feedback only through `POST /api/chat` with `artifact_feedback_decision`.
- Render only `synthesis_blueprint` artifacts with stored `schema_version: "2.0"`.
- Treat backend and model content as untrusted text; never render artifact, feedback, citation, action, or response content through `innerHTML`.
- Do not call Firestore, Vertex AI, or `/api/synthesize` from the browser.
- Do not implement artifact mutation, deletion, versioning, parent-based regeneration, session history, project listing, authentication, durable jobs, uploads, Markdown rendering, or memory lifecycle controls in this pass.
- The active chat transcript remains page-memory only; Work list/detail state can be reloaded from backend after entering context or after a page refresh.
- Do not checkpoint this implementation until manual verification succeeds and the user explicitly requests checkpointing.

---

## File Structure

- Create: `frontend/work-view.mjs`
  - Work list/detail rendering, feedback target controls, feedback history rendering, JSON download creation, and user interactions.
- Create: `tests/frontend/work-view.test.mjs`
  - DOM-shim tests for safe rendering, detail projection, feedback forms, and JSON download data.
- Modify: `frontend/api.mjs`
  - Add same-origin wrappers for blueprint list, blueprint detail, and blueprint feedback history.
- Modify: `frontend/requests.mjs`
  - Add artifact-feedback chat request construction and validation.
- Modify: `frontend/state.mjs`
  - Add Work state, selectors, refresh planning, selected artifact state, and feedback state transitions.
- Modify: `frontend/app.mjs`
  - Wire Work loading after context acceptance, artifact receipt refresh after chat, selected artifact detail loading, feedback submission, and post-feedback refresh.
- Modify: `frontend/index.html`
  - Replace visible `Agent_Col` copy with `Agent Col`; add Work list/detail/feedback targets to the existing shell.
- Modify: `frontend/styles.css`
  - Add Work list, detail, feedback form, feedback event, download, loading, empty, and error styles.
- Modify: `tests/frontend/api.test.mjs`
  - Cover path construction and same-origin API wrappers.
- Modify: `tests/frontend/requests.test.mjs`
  - Cover artifact-feedback chat body construction, edited correction requirement, and exact idempotency behavior.
- Modify: `tests/frontend/state.test.mjs`
  - Cover Work state loading, detail selection, receipt-driven refresh flags, and post-feedback refresh.
- Modify: `tests/test_workspace_static.py`
  - Assert user-facing naming convention and Work panel DOM hooks.

---

### Task 1: Artifact API Wrappers and Feedback Request Contracts

**Files:**
- Modify: `tests/frontend/api.test.mjs`
- Modify: `tests/frontend/requests.test.mjs`
- Modify: `frontend/api.mjs`
- Modify: `frontend/requests.mjs`

**Interfaces:**
- Produces: `listBlueprints(projectId: string, options?: { limit?: number, before?: string }, fetchLike?: Function): Promise<object>`
- Produces: `getBlueprint(projectId: string, artifactId: string, fetchLike?: Function): Promise<object>`
- Produces: `listBlueprintFeedback(projectId: string, artifactId: string, options?: { limit?: number, before?: string }, fetchLike?: Function): Promise<object>`
- Produces: `buildArtifactFeedbackChatRequest(context: object, message: string, decision: object, cryptoLike?: Crypto): { key: string, body: object }`
- Consumes: `apiFetchJson(path, options, fetchLike)`
- Consumes: `buildChatRequest(input)`

- [ ] **Step 1: Write failing API wrapper tests**

Append to `tests/frontend/api.test.mjs`:

```javascript
import {
  getBlueprint,
  listBlueprintFeedback,
  listBlueprints,
} from "../../frontend/api.mjs";

test("listBlueprints calls the canonical project blueprint list path", async () => {
  const calls = [];
  const result = await listBlueprints(
    "agent-col",
    { limit: 5, before: "cursor--1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifacts: [], next_before: null });
    },
  );

  assert.deepEqual(result, { artifacts: [], next_before: null });
  assert.equal(
    calls[0][0],
    "/api/projects/agent-col/blueprints?limit=5&before=cursor--1",
  );
  assert.equal(calls[0][1].method, "GET");
});

test("getBlueprint calls the canonical blueprint detail path", async () => {
  const calls = [];
  await getBlueprint("agent-col", "blueprint--abc", async (path, init) => {
    calls.push([path, init]);
    return jsonResponse(200, { artifact_contract_version: "1.0" });
  });

  assert.equal(calls[0][0], "/api/projects/agent-col/blueprints/blueprint--abc");
  assert.equal(calls[0][1].method, "GET");
});

test("listBlueprintFeedback calls the canonical feedback history path", async () => {
  const calls = [];
  await listBlueprintFeedback(
    "agent-col",
    "blueprint--abc",
    { limit: 20 },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { events: [], next_before: null });
    },
  );

  assert.equal(
    calls[0][0],
    "/api/projects/agent-col/blueprints/blueprint--abc/feedback?limit=20",
  );
  assert.equal(calls[0][1].method, "GET");
});

test("artifact API wrappers reject invalid project and artifact identifiers", async () => {
  await assert.rejects(
    () => listBlueprints("bad/slash", {}, async () => jsonResponse(200, {})),
    /invalid/i,
  );
  await assert.rejects(
    () => getBlueprint("agent-col", "bad/slash", async () => jsonResponse(200, {})),
    /invalid/i,
  );
});
```

- [ ] **Step 2: Write failing artifact feedback request tests**

Append to `tests/frontend/requests.test.mjs`:

```javascript
import { buildArtifactFeedbackChatRequest } from "../../frontend/requests.mjs";

test("artifact feedback chat request includes the structured feedback decision", () => {
  const request = buildArtifactFeedbackChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    "I accept this blueprint.",
    {
      artifact_id: "blueprint--abc",
      target_id: "target--whole",
      decision: "accepted",
      feedback_text: "This is useful.",
      expected_schema_version: "2.0",
    },
    cryptoStub,
  );

  assert.equal(request.key, "chat--123e4567-e89b-12d3-a456-426614174000");
  assert.deepEqual(request.body.artifact_feedback_decision, {
    artifact_id: "blueprint--abc",
    target_id: "target--whole",
    decision: "accepted",
    feedback_text: "This is useful.",
    expected_schema_version: "2.0",
  });
  assert.equal(request.body.message, "I accept this blueprint.");
});

test("edited artifact feedback requires correction text", () => {
  assert.throws(
    () => buildArtifactFeedbackChatRequest(
      {
        project_id: "agent-col",
        session_id: "session-1",
        user_id: "wifiknight",
      },
      "I want to edit this target.",
      {
        artifact_id: "blueprint--abc",
        target_id: "target--whole",
        decision: "edited",
        feedback_text: "Needs a correction.",
        expected_schema_version: "2.0",
      },
      cryptoStub,
    ),
    /Correction text is required/,
  );
});

test("artifact feedback can supersede a previous feedback event", () => {
  const request = buildArtifactFeedbackChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    "I am reversing my earlier artifact feedback.",
    {
      artifact_id: "blueprint--abc",
      target_id: "target--whole",
      decision: "rejected",
      feedback_text: "I am reversing the acceptance.",
      expected_schema_version: "2.0",
      supersedes_feedback_id: "feedback--old",
    },
    cryptoStub,
  );

  assert.equal(
    request.body.artifact_feedback_decision.supersedes_feedback_id,
    "feedback--old",
  );
});
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
node --test tests/frontend/api.test.mjs tests/frontend/requests.test.mjs
```

Expected: FAIL because the wrapper and artifact-feedback request functions are not exported.

- [ ] **Step 4: Implement minimal API wrapper helpers**

In `frontend/api.mjs`, import `isValidIdentifier` from `requests.mjs` and add:

```javascript
function assertIdentifier(name, value) {
  if (!isValidIdentifier(value)) {
    throw new Error(`${name} is invalid.`);
  }
}

function buildQuery(options = {}) {
  const params = new URLSearchParams();
  if (options.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options.before !== undefined && options.before !== null) {
    params.set("before", String(options.before));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function listBlueprints(projectId, options = {}, fetchLike = globalThis.fetch) {
  assertIdentifier("project_id", projectId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/blueprints${buildQuery(options)}`,
    { method: "GET" },
    fetchLike,
  );
}

export function getBlueprint(projectId, artifactId, fetchLike = globalThis.fetch) {
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/blueprints/${encodeURIComponent(artifactId)}`,
    { method: "GET" },
    fetchLike,
  );
}

export function listBlueprintFeedback(
  projectId,
  artifactId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/blueprints/${encodeURIComponent(artifactId)}/feedback${buildQuery(options)}`,
    { method: "GET" },
    fetchLike,
  );
}
```

- [ ] **Step 5: Implement minimal artifact feedback request helper**

In `frontend/requests.mjs`, add:

```javascript
const ARTIFACT_FEEDBACK_DECISIONS = new Set(["accepted", "rejected", "edited"]);

function normalizeOptionalText(value) {
  if (value === undefined || value === null) {
    return undefined;
  }
  const text = String(value).trim();
  return text ? text : undefined;
}

export function buildArtifactFeedbackChatRequest(
  context,
  message,
  decision,
  cryptoLike = globalThis.crypto,
) {
  const artifactDecision = {
    artifact_id: String(decision.artifact_id ?? "").trim(),
    target_id: String(decision.target_id ?? "").trim(),
    decision: String(decision.decision ?? "").trim(),
    feedback_text: String(decision.feedback_text ?? "").trim(),
    expected_schema_version: String(
      decision.expected_schema_version ?? "2.0",
    ).trim(),
  };

  const correctionText = normalizeOptionalText(decision.correction_text);
  const supersedesFeedbackId = normalizeOptionalText(
    decision.supersedes_feedback_id,
  );

  if (!isValidIdentifier(artifactDecision.artifact_id)) {
    throw new Error("artifact_id is invalid.");
  }
  if (!isValidIdentifier(artifactDecision.target_id)) {
    throw new Error("target_id is invalid.");
  }
  if (!ARTIFACT_FEEDBACK_DECISIONS.has(artifactDecision.decision)) {
    throw new Error("Artifact feedback decision is invalid.");
  }
  if (!artifactDecision.feedback_text) {
    throw new Error("Feedback text is required.");
  }
  if (
    artifactDecision.decision === "edited"
    && correctionText === undefined
  ) {
    throw new Error("Correction text is required for edited feedback.");
  }
  if (correctionText !== undefined) {
    artifactDecision.correction_text = correctionText;
  }
  if (supersedesFeedbackId !== undefined) {
    if (!isValidIdentifier(supersedesFeedbackId)) {
      throw new Error("supersedes_feedback_id is invalid.");
    }
    artifactDecision.supersedes_feedback_id = supersedesFeedbackId;
  }

  return buildChatRequest({
    project_id: context.project_id,
    session_id: context.session_id,
    user_id: context.user_id,
    message,
    artifact_feedback_decision: artifactDecision,
    crypto: cryptoLike,
  });
}
```

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
node --test tests/frontend/api.test.mjs tests/frontend/requests.test.mjs
```

Expected: PASS.

---

### Task 2: Work State and Receipt-Driven Refresh Planning

**Files:**
- Modify: `tests/frontend/state.test.mjs`
- Modify: `frontend/state.mjs`

**Interfaces:**
- Produces: `beginWorkListLoad(state): object`
- Produces: `completeWorkListLoad(state, response): object`
- Produces: `failWorkListLoad(state, error): object`
- Produces: `beginWorkDetailLoad(state, artifactId: string): object`
- Produces: `completeWorkDetailLoad(state, detail: object, feedback: object): object`
- Produces: `failWorkDetailLoad(state, error): object`
- Produces: `selectFirstSupportedArtifact(response: object): object | null`
- Produces: `selectWorkRefreshPlan(response: object): { reloadList: boolean, selectArtifactId: string | null, reloadSelectedFeedback: boolean }`
- Extends: `createInitialState()` with `work`.

- [ ] **Step 1: Write failing Work state tests**

Append to `tests/frontend/state.test.mjs`:

```javascript
import {
  beginWorkDetailLoad,
  beginWorkListLoad,
  completeWorkDetailLoad,
  completeWorkListLoad,
  failWorkDetailLoad,
  failWorkListLoad,
  selectFirstSupportedArtifact,
  selectWorkRefreshPlan,
} from "../../frontend/state.mjs";

test("work list lifecycle stores newest-first metadata and cursor", () => {
  const loading = beginWorkListLoad(createInitialState());
  assert.equal(loading.work.list.status, "loading");

  const completed = completeWorkListLoad(loading, {
    artifacts: [
      {
        reference: {
          artifact_type: "synthesis_blueprint",
          artifact_id: "blueprint--abc",
          schema_version: "2.0",
          display_label: "Blueprint",
        },
        created_at: "2026-08-23T00:00:00Z",
        feedback_counts: { accepted: 0, rejected: 0, edited: 0 },
      },
    ],
    next_before: "cursor--1",
  });

  assert.equal(completed.work.list.status, "ready");
  assert.equal(completed.work.list.items[0].reference.artifact_id, "blueprint--abc");
  assert.equal(completed.work.list.next_before, "cursor--1");
});

test("work detail lifecycle stores canonical detail and feedback history", () => {
  const loading = beginWorkDetailLoad(createInitialState(), "blueprint--abc");
  assert.equal(loading.work.detail.status, "loading");
  assert.equal(loading.work.selectedArtifactId, "blueprint--abc");

  const completed = completeWorkDetailLoad(
    loading,
    {
      metadata: {
        reference: {
          artifact_id: "blueprint--abc",
          schema_version: "2.0",
          display_label: "Blueprint",
        },
      },
      blueprint: {
        synthesized_conceptual_model: { project_name: "Blueprint" },
      },
      feedback_targets: [{ target_id: "target--whole" }],
      adaptations: [],
      applied_feedback_ids: [],
    },
    {
      events: [{ reference: { feedback_id: "feedback--1" }, status: "active" }],
      next_before: null,
    },
  );

  assert.equal(completed.work.detail.status, "ready");
  assert.equal(completed.work.detail.item.metadata.reference.artifact_id, "blueprint--abc");
  assert.equal(completed.work.feedback.events[0].reference.feedback_id, "feedback--1");
});

test("work load failures store safe error messages", () => {
  assert.equal(
    failWorkListLoad(beginWorkListLoad(createInitialState()), { message: "boom" })
      .work.list.error,
    "boom",
  );
  assert.equal(
    failWorkDetailLoad(beginWorkDetailLoad(createInitialState(), "blueprint--abc"), { message: "missing" })
      .work.detail.error,
    "missing",
  );
});

test("receipt refresh plan follows artifact and feedback response fields", () => {
  assert.deepEqual(
    selectFirstSupportedArtifact({
      artifacts: [
        {
          artifact_type: "synthesis_blueprint",
          artifact_id: "blueprint--abc",
          schema_version: "2.0",
        },
      ],
    }),
    {
      artifact_type: "synthesis_blueprint",
      artifact_id: "blueprint--abc",
      schema_version: "2.0",
    },
  );

  assert.deepEqual(
    selectWorkRefreshPlan({
      artifacts: [
        {
          artifact_type: "synthesis_blueprint",
          artifact_id: "blueprint--abc",
          schema_version: "2.0",
        },
      ],
      artifact_feedback: [],
    }),
    {
      reloadList: true,
      selectArtifactId: "blueprint--abc",
      reloadSelectedFeedback: false,
    },
  );

  assert.deepEqual(
    selectWorkRefreshPlan({
      artifact_feedback: [
        {
          artifact_id: "blueprint--abc",
          feedback_id: "feedback--1",
        },
      ],
    }),
    {
      reloadList: true,
      selectArtifactId: "blueprint--abc",
      reloadSelectedFeedback: true,
    },
  );
});
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
node --test tests/frontend/state.test.mjs
```

Expected: FAIL because Work state functions are not exported.

- [ ] **Step 3: Implement minimal Work state model**

In `frontend/state.mjs`, extend `createInitialState()`:

```javascript
work: {
  list: {
    status: "idle",
    items: [],
    next_before: null,
    error: null,
  },
  selectedArtifactId: null,
  detail: {
    status: "idle",
    item: null,
    error: null,
  },
  feedback: {
    status: "idle",
    events: [],
    next_before: null,
    error: null,
  },
},
```

Add:

```javascript
function errorMessage(error) {
  return error && typeof error.message === "string"
    ? error.message
    : "Request failed.";
}

export function beginWorkListLoad(state) {
  return {
    ...state,
    work: {
      ...state.work,
      list: { ...state.work.list, status: "loading", error: null },
    },
  };
}

export function completeWorkListLoad(state, response) {
  return {
    ...state,
    work: {
      ...state.work,
      list: {
        status: "ready",
        items: Array.isArray(response.artifacts) ? response.artifacts : [],
        next_before: response.next_before ?? null,
        error: null,
      },
    },
  };
}

export function failWorkListLoad(state, error) {
  return {
    ...state,
    work: {
      ...state.work,
      list: { ...state.work.list, status: "error", error: errorMessage(error) },
    },
  };
}

export function beginWorkDetailLoad(state, artifactId) {
  return {
    ...state,
    work: {
      ...state.work,
      selectedArtifactId: artifactId,
      detail: { status: "loading", item: null, error: null },
      feedback: { status: "loading", events: [], next_before: null, error: null },
    },
  };
}

export function completeWorkDetailLoad(state, detail, feedback) {
  return {
    ...state,
    work: {
      ...state.work,
      detail: { status: "ready", item: detail, error: null },
      feedback: {
        status: "ready",
        events: Array.isArray(feedback.events) ? feedback.events : [],
        next_before: feedback.next_before ?? null,
        error: null,
      },
    },
  };
}

export function failWorkDetailLoad(state, error) {
  return {
    ...state,
    work: {
      ...state.work,
      detail: { ...state.work.detail, status: "error", error: errorMessage(error) },
      feedback: { ...state.work.feedback, status: "error", error: errorMessage(error) },
    },
  };
}

export function selectFirstSupportedArtifact(response) {
  const artifacts = Array.isArray(response.artifacts) ? response.artifacts : [];
  return artifacts.find((artifact) => (
    artifact.artifact_type === "synthesis_blueprint"
    && artifact.schema_version === "2.0"
    && typeof artifact.artifact_id === "string"
  )) ?? null;
}

export function selectWorkRefreshPlan(response) {
  const artifact = selectFirstSupportedArtifact(response);
  const feedback = Array.isArray(response.artifact_feedback)
    && response.artifact_feedback.length > 0
    ? response.artifact_feedback[0]
    : null;
  return {
    reloadList: artifact !== null || feedback !== null,
    selectArtifactId: artifact?.artifact_id ?? feedback?.artifact_id ?? null,
    reloadSelectedFeedback: feedback !== null,
  };
}
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
node --test tests/frontend/state.test.mjs
```

Expected: PASS.

---

### Task 3: Work View Rendering, Download, and Feedback Controls

**Files:**
- Create: `tests/frontend/work-view.test.mjs`
- Create: `frontend/work-view.mjs`
- Modify: `frontend/render.mjs`

**Interfaces:**
- Produces: `renderWorkList(container: Element, workState: object, handlers: object): void`
- Produces: `renderWorkDetail(container: Element, workState: object, handlers: object): void`
- Produces: `renderFeedbackHistory(container: Element, workState: object): void`
- Produces: `createWorkView(elements: object, handlers: object): { render(state: object): void }`
- Produces: `buildBlueprintDownload(detail: object): { filename: string, href: string }`
- Consumes: `setText(element, value)` and `appendTextElement(parent, tag, className, value)` from `frontend/render.mjs`

- [ ] **Step 1: Write failing Work view tests**

Create `tests/frontend/work-view.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import {
  buildBlueprintDownload,
  renderFeedbackHistory,
  renderWorkDetail,
  renderWorkList,
} from "../../frontend/work-view.mjs";

function node(tagName = "div") {
  return {
    tagName,
    children: [],
    attributes: {},
    dataset: {},
    value: "",
    textContent: "",
    hidden: false,
    append(...items) {
      this.children.push(...items);
    },
    replaceChildren(...items) {
      this.children = items;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    addEventListener(name, handler) {
      this[`on${name}`] = handler;
    },
    classList: {
      values: [],
      add(...values) {
        this.values.push(...values);
      },
    },
  };
}

globalThis.document = {
  createElement(tagName) {
    return node(tagName);
  },
};

const detail = {
  metadata: {
    reference: {
      artifact_id: "blueprint--abc",
      artifact_type: "synthesis_blueprint",
      schema_version: "2.0",
      display_label: "Safe <Blueprint>",
    },
    feedback_counts: { accepted: 1, rejected: 0, edited: 0 },
    adaptation_categories: ["planning_granularity"],
  },
  blueprint: {
    synthesized_conceptual_model: {
      project_name: "Safe <Blueprint>",
      core_value_proposition: "Create useful work without unsafe rendering.",
      in_scope: ["Inspection"],
      out_of_scope: ["Mutation"],
      assumptions: ["Backend owns canonical detail."],
    },
    architectural_decisions: [
      {
        component_name: "Renderer",
        proposed_solution: "Use textContent.",
        rationale: "Prevents HTML injection.",
        alternatives: [
          {
            option_name: "innerHTML",
            tradeoff: "Easy but unsafe.",
            reason_not_selected: "Unsafe.",
          },
        ],
      },
    ],
    socratic_clarifying_questions: [
      {
        question_text: "Which target matters most?",
        why_this_matters: "Feedback needs a target.",
        suggested_options: [
          { label: "Whole artifact", impact: "Broad feedback." },
        ],
      },
    ],
    step_by_step_execution_roadmap: [
      {
        phase_name: "Phase 1",
        objective: "Inspect",
        expected_deliverable: "Detail panel",
        micro_tasks: [
          {
            task_description: "Render safely",
            complexity_level: "Low",
            verification_steps: ["Assert textContent"],
          },
        ],
      },
    ],
    diagnostic_warnings: [
      {
        affected_component: "Renderer",
        severity: "High",
        risk_identified: "Unsafe HTML",
        preventative_guidance: "Never use innerHTML.",
      },
    ],
  },
  feedback_targets: [
    {
      target_id: "target--whole",
      target_kind: "whole_blueprint",
      display_label: "Safe <Blueprint>",
    },
  ],
  adaptations: [
    {
      category: "planning_granularity",
      status: "provided_to_model",
      signal_id: "planning_granularity--1",
    },
  ],
  applied_feedback_ids: [],
};

test("renderWorkList renders blueprint metadata and selection controls", () => {
  const selected = [];
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        items: [{
          reference: detail.metadata.reference,
          created_at: "2026-08-23T00:00:00Z",
          feedback_counts: { accepted: 1, rejected: 0, edited: 0 },
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    { onSelectArtifact: (artifactId) => selected.push(artifactId) },
  );

  assert.equal(container.children.length, 1);
  assert.equal(container.children[0].textContent.includes("Safe <Blueprint>"), true);
  container.children[0].onclick();
  assert.deepEqual(selected, ["blueprint--abc"]);
});

test("renderWorkDetail projects canonical schema-2 blueprint text safely", () => {
  const container = node();

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: detail, error: null },
      feedback: { status: "ready", events: [], error: null },
    },
    { onSubmitFeedback: () => {} },
  );

  const text = container.children.map((child) => child.textContent).join(" ");
  assert.equal(text.includes("Safe <Blueprint>"), true);
  assert.equal(text.includes("Use textContent."), true);
  assert.equal(text.includes("Which target matters most?"), true);
  assert.equal(text.includes("Never use innerHTML."), true);
});

test("renderFeedbackHistory shows supersession state without mutating artifacts", () => {
  const container = node();

  renderFeedbackHistory(container, {
    feedback: {
      status: "ready",
      events: [
        {
          reference: {
            feedback_id: "feedback--new",
            decision: "rejected",
          },
          feedback_text: "Reversing earlier acceptance.",
          status: "active",
          supersedes_feedback_id: "feedback--old",
        },
        {
          reference: {
            feedback_id: "feedback--old",
            decision: "accepted",
          },
          feedback_text: "Accepted earlier.",
          status: "superseded",
          superseded_by_feedback_id: "feedback--new",
        },
      ],
    },
  });

  const text = container.children.map((child) => child.textContent).join(" ");
  assert.equal(text.includes("feedback--new"), true);
  assert.equal(text.includes("superseded"), true);
  assert.equal(text.includes("feedback--old"), true);
});

test("buildBlueprintDownload creates a safe filename and JSON data URL", () => {
  const download = buildBlueprintDownload(detail);

  assert.equal(download.filename, "safe-blueprint-blueprint--abc.json");
  assert.equal(download.href.startsWith("data:application/json;charset=utf-8,"), true);
  assert.equal(
    JSON.parse(decodeURIComponent(download.href.split(",", 2)[1]))
      .metadata.reference.artifact_id,
    "blueprint--abc",
  );
});
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
node --test tests/frontend/work-view.test.mjs
```

Expected: FAIL because `frontend/work-view.mjs` does not exist.

- [ ] **Step 3: Add safe DOM helpers if missing**

In `frontend/render.mjs`, ensure these helpers exist:

```javascript
export function setText(element, value) {
  element.textContent = value === undefined || value === null ? "" : String(value);
}

export function appendTextElement(parent, tagName, className, value) {
  const element = document.createElement(tagName);
  if (className) {
    element.classList.add(className);
  }
  setText(element, value);
  parent.append(element);
  return element;
}
```

- [ ] **Step 4: Implement minimal Work view**

Create `frontend/work-view.mjs` with:

```javascript
import { appendTextElement, setText } from "./render.mjs";

function textLine(parts) {
  return parts.filter((part) => part !== undefined && part !== null && part !== "")
    .map(String)
    .join(" · ");
}

function appendList(parent, values) {
  const list = document.createElement("ul");
  for (const value of values ?? []) {
    appendTextElement(list, "li", "", value);
  }
  parent.append(list);
}

function slug(value) {
  return String(value ?? "blueprint")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "blueprint";
}

export function buildBlueprintDownload(detail) {
  const reference = detail.metadata.reference;
  const label = reference.display_label
    ?? detail.blueprint?.synthesized_conceptual_model?.project_name
    ?? "blueprint";
  return {
    filename: `${slug(label)}-${reference.artifact_id}.json`,
    href: `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(detail, null, 2))}`,
  };
}

export function renderWorkList(container, work, handlers) {
  container.replaceChildren();
  if (work.list.status === "loading") {
    appendTextElement(container, "p", "muted", "Loading Work...");
    return;
  }
  if (work.list.status === "error") {
    appendTextElement(container, "p", "form-error", work.list.error);
    return;
  }
  if (!work.list.items.length) {
    appendTextElement(container, "p", "muted", "No Work loaded yet.");
    return;
  }
  for (const item of work.list.items) {
    const button = document.createElement("button");
    button.type = "button";
    button.classList.add("work-list-item");
    button.setAttribute("data-artifact-id", item.reference.artifact_id);
    setText(button, textLine([
      item.reference.display_label,
      item.reference.artifact_id,
      `accepted ${item.feedback_counts?.accepted ?? 0}`,
      `rejected ${item.feedback_counts?.rejected ?? 0}`,
      `edited ${item.feedback_counts?.edited ?? 0}`,
    ]));
    button.addEventListener("click", () => {
      handlers.onSelectArtifact(item.reference.artifact_id);
    });
    container.append(button);
  }
}

function renderBlueprint(parent, blueprint) {
  const model = blueprint.synthesized_conceptual_model;
  appendTextElement(parent, "h3", "", model.project_name);
  appendTextElement(parent, "p", "", model.core_value_proposition);
  appendTextElement(parent, "h4", "", "In scope");
  appendList(parent, model.in_scope);
  appendTextElement(parent, "h4", "", "Out of scope");
  appendList(parent, model.out_of_scope);
  appendTextElement(parent, "h4", "", "Assumptions");
  appendList(parent, model.assumptions);

  appendTextElement(parent, "h4", "", "Architectural decisions");
  for (const decision of blueprint.architectural_decisions ?? []) {
    appendTextElement(parent, "p", "work-heading", decision.component_name);
    appendTextElement(parent, "p", "", decision.proposed_solution);
    appendTextElement(parent, "p", "muted", decision.rationale);
    for (const alternative of decision.alternatives ?? []) {
      appendTextElement(parent, "p", "muted", textLine([
        alternative.option_name,
        alternative.tradeoff,
        alternative.reason_not_selected,
      ]));
    }
  }

  appendTextElement(parent, "h4", "", "Socratic questions");
  for (const question of blueprint.socratic_clarifying_questions ?? []) {
    appendTextElement(parent, "p", "work-heading", question.question_text);
    appendTextElement(parent, "p", "muted", question.why_this_matters);
    appendList(
      parent,
      (question.suggested_options ?? []).map((option) => textLine([
        option.label,
        option.impact,
      ])),
    );
  }

  appendTextElement(parent, "h4", "", "Roadmap");
  for (const phase of blueprint.step_by_step_execution_roadmap ?? []) {
    appendTextElement(parent, "p", "work-heading", phase.phase_name);
    appendTextElement(parent, "p", "", phase.objective);
    appendTextElement(parent, "p", "muted", phase.expected_deliverable);
    for (const task of phase.micro_tasks ?? []) {
      appendTextElement(parent, "p", "muted", textLine([
        task.task_description,
        task.complexity_level,
        (task.verification_steps ?? []).join("; "),
      ]));
    }
  }

  appendTextElement(parent, "h4", "", "Diagnostic warnings");
  for (const warning of blueprint.diagnostic_warnings ?? []) {
    appendTextElement(parent, "p", "work-heading", textLine([
      warning.severity,
      warning.affected_component,
    ]));
    appendTextElement(parent, "p", "", warning.risk_identified);
    appendTextElement(parent, "p", "muted", warning.preventative_guidance);
  }
}

function renderFeedbackTargets(parent, detail, handlers) {
  appendTextElement(parent, "h4", "", "Feedback targets");
  for (const target of detail.feedback_targets ?? []) {
    const form = document.createElement("form");
    form.classList.add("feedback-form");
    form.setAttribute("data-feedback-target", target.target_id);
    appendTextElement(form, "p", "work-heading", textLine([
      target.display_label,
      target.target_kind,
    ]));
    const select = document.createElement("select");
    select.name = "decision";
    for (const value of ["accepted", "rejected", "edited"]) {
      const option = document.createElement("option");
      option.value = value;
      setText(option, value);
      select.append(option);
    }
    const feedback = document.createElement("textarea");
    feedback.name = "feedback_text";
    feedback.required = true;
    const correction = document.createElement("textarea");
    correction.name = "correction_text";
    const supersedes = document.createElement("input");
    supersedes.name = "supersedes_feedback_id";
    supersedes.placeholder = "Optional feedback ID to supersede";
    const submit = document.createElement("button");
    submit.type = "submit";
    setText(submit, "Record feedback");
    form.append(select, feedback, correction, supersedes, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      handlers.onSubmitFeedback({
        artifact_id: detail.metadata.reference.artifact_id,
        target_id: target.target_id,
        decision: select.value,
        feedback_text: feedback.value,
        correction_text: correction.value,
        supersedes_feedback_id: supersedes.value,
        expected_schema_version: detail.metadata.reference.schema_version,
      });
    });
    parent.append(form);
  }
}

export function renderFeedbackHistory(container, work) {
  container.replaceChildren();
  if (work.feedback.status === "loading") {
    appendTextElement(container, "p", "muted", "Loading feedback...");
    return;
  }
  if (work.feedback.status === "error") {
    appendTextElement(container, "p", "form-error", work.feedback.error);
    return;
  }
  if (!work.feedback.events.length) {
    appendTextElement(container, "p", "muted", "No feedback recorded yet.");
    return;
  }
  for (const event of work.feedback.events) {
    appendTextElement(container, "p", "feedback-event", textLine([
      event.reference.feedback_id,
      event.reference.decision,
      event.status,
      event.feedback_text,
      event.supersedes_feedback_id ? `supersedes ${event.supersedes_feedback_id}` : "",
      event.superseded_by_feedback_id ? `superseded by ${event.superseded_by_feedback_id}` : "",
    ]));
  }
}

export function renderWorkDetail(container, work, handlers) {
  container.replaceChildren();
  if (work.detail.status === "idle") {
    appendTextElement(container, "p", "muted", "Select a Work item to inspect its canonical backend detail.");
    return;
  }
  if (work.detail.status === "loading") {
    appendTextElement(container, "p", "muted", "Loading Work detail...");
    return;
  }
  if (work.detail.status === "error") {
    appendTextElement(container, "p", "form-error", work.detail.error);
    return;
  }
  const detail = work.detail.item;
  const download = buildBlueprintDownload(detail);
  const link = document.createElement("a");
  link.href = download.href;
  link.download = download.filename;
  setText(link, "Download canonical JSON");
  container.append(link);
  renderBlueprint(container, detail.blueprint);
  appendTextElement(container, "h4", "", "Verified adaptations");
  appendList(container, (detail.adaptations ?? []).map((item) => textLine([
    item.category,
    item.status,
    item.signal_id,
  ])));
  renderFeedbackTargets(container, detail, handlers);
  const feedbackContainer = document.createElement("section");
  feedbackContainer.setAttribute("data-feedback-history", "");
  renderFeedbackHistory(feedbackContainer, work);
  container.append(feedbackContainer);
}

export function createWorkView(elements, handlers) {
  return {
    render(state) {
      renderWorkList(elements.list, state.work, handlers);
      renderWorkDetail(elements.detail, state.work, handlers);
    },
  };
}
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
node --test tests/frontend/work-view.test.mjs
```

Expected: PASS.

- [ ] **Step 6: Refactor only after GREEN**

If the module is hard to read after GREEN, extract only local helpers inside `work-view.mjs`. Do not add a frontend framework, Markdown renderer, sanitizer dependency, or component system.

- [ ] **Step 7: Run Work view tests again**

Run:

```bash
node --test tests/frontend/work-view.test.mjs
```

Expected: PASS.

---

### Task 4: Workspace Shell, User-Facing Name Correction, and App Wiring

**Files:**
- Modify: `tests/test_workspace_static.py`
- Modify: `tests/frontend/state.test.mjs`
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Modify: `frontend/app.mjs`
- Modify: `frontend/state.mjs`

**Interfaces:**
- Consumes: API wrappers from Task 1.
- Consumes: Work state functions from Task 2.
- Consumes: `createWorkView()` from Task 3.
- Produces: visible Work panel that can load list/detail, submit feedback, and refresh from authoritative receipts.

- [ ] **Step 1: Write failing static shell tests**

Extend `tests/test_workspace_static.py::test_workspace_route_serves_html_shell`:

```python
assert "<h1>Agent Col</h1>" in response.text
assert "Ask Agent Col for help" in response.text
assert ">Agent_Col<" not in response.text
assert "Ask Agent_Col" not in response.text
assert "data-work-list" in response.text
assert "data-work-detail" in response.text
assert "data-work-error" in response.text
assert "data-work-refresh" in response.text
```

- [ ] **Step 2: Write failing state reset test for new conversations**

Append to `tests/frontend/state.test.mjs`:

```javascript
test("new conversation preserves loaded work because artifacts are project scoped", () => {
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const withWork = completeWorkListLoad(beginWorkListLoad(accepted), {
    artifacts: [{
      reference: {
        artifact_id: "blueprint--abc",
        artifact_type: "synthesis_blueprint",
        schema_version: "2.0",
        display_label: "Blueprint",
      },
    }],
    next_before: null,
  });

  const next = startNewConversation(withWork, cryptoStub);

  assert.equal(next.transcript.length, 0);
  assert.equal(next.work.list.items[0].reference.artifact_id, "blueprint--abc");
});
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
venv/bin/python -m pytest -q tests/test_workspace_static.py
node --test tests/frontend/state.test.mjs
```

Expected: static test FAILS because visible copy still uses `Agent_Col` and Work hooks are absent. State test may PASS if Task 2 preserved Work by default; if it fails, update only the reset logic described below.

- [ ] **Step 4: Update shell copy and Work DOM hooks**

In `frontend/index.html`:

```html
<title>Agent Col Workspace</title>
...
<h1>Agent Col</h1>
...
Ask Agent Col for help, or ask it to create a structured
blueprint from source text in your message.
```

Replace the current Work placeholder section with:

```html
<section aria-labelledby="work-list-title">
  <div class="section-heading">
    <h2 id="work-list-title">Work</h2>
    <button type="button" data-work-refresh>Refresh</button>
  </div>
  <p class="form-error" role="alert" data-work-error hidden></p>
  <div data-work-list></div>
</section>
```

Replace the current hidden Work review placeholder with:

```html
<aside class="work-panel" aria-label="Work review">
  <h2>Work review</h2>
  <div data-work-detail></div>
</aside>
```

- [ ] **Step 5: Wire Work loading and feedback submission in `app.mjs`**

In `frontend/app.mjs`, import:

```javascript
import {
  getBlueprint,
  listBlueprintFeedback,
  listBlueprints,
} from "./api.mjs";
import { createWorkView } from "./work-view.mjs";
import { buildArtifactFeedbackChatRequest } from "./requests.mjs";
import {
  beginWorkDetailLoad,
  beginWorkListLoad,
  completeWorkDetailLoad,
  completeWorkListLoad,
  failWorkDetailLoad,
  failWorkListLoad,
  selectWorkRefreshPlan,
} from "./state.mjs";
```

Add module state:

```javascript
let workView = null;
```

Add helpers:

```javascript
function showWorkError(message) {
  const error = document.querySelector("[data-work-error]");
  setText(error, message);
  error.hidden = false;
}

function clearWorkError() {
  const error = document.querySelector("[data-work-error]");
  setText(error, "");
  error.hidden = true;
}

function ensureWorkView() {
  if (workView !== null) {
    return workView;
  }
  workView = createWorkView(
    {
      list: document.querySelector("[data-work-list]"),
      detail: document.querySelector("[data-work-detail]"),
    },
    {
      onSelectArtifact(artifactId) {
        loadWorkDetail(artifactId);
      },
      onSubmitFeedback(decision) {
        submitArtifactFeedback(decision);
      },
    },
  );
  return workView;
}

function renderWorkspace() {
  ensureChatView().render(state);
  ensureWorkView().render(state);
}

async function loadWorkList() {
  if (!state.context) {
    return;
  }
  clearWorkError();
  state = beginWorkListLoad(state);
  ensureWorkView().render(state);
  try {
    const response = await listBlueprints(state.context.project_id, { limit: 20 });
    state = completeWorkListLoad(state, response);
  } catch (error) {
    state = failWorkListLoad(state, error);
    showWorkError(error.message);
  }
  ensureWorkView().render(state);
}

async function loadWorkDetail(artifactId) {
  if (!state.context) {
    return;
  }
  clearWorkError();
  state = beginWorkDetailLoad(state, artifactId);
  ensureWorkView().render(state);
  try {
    const [detail, feedback] = await Promise.all([
      getBlueprint(state.context.project_id, artifactId),
      listBlueprintFeedback(state.context.project_id, artifactId, { limit: 20 }),
    ]);
    state = completeWorkDetailLoad(state, detail, feedback);
  } catch (error) {
    state = failWorkDetailLoad(state, error);
    showWorkError(error.message);
  }
  ensureWorkView().render(state);
}

async function submitArtifactFeedback(decision) {
  if (!selectCanSubmit(state)) {
    return;
  }
  const message = `Record ${decision.decision} feedback for Work artifact ${decision.artifact_id}.`;
  const request = buildArtifactFeedbackChatRequest(
    state.context,
    message,
    decision,
  );
  await submitRequest(request);
}
```

After chat response completion in `submitRequest`, before final render, add:

```javascript
const refreshPlan = selectWorkRefreshPlan(response);
if (refreshPlan.reloadList) {
  await loadWorkList();
}
if (refreshPlan.selectArtifactId !== null) {
  await loadWorkDetail(refreshPlan.selectArtifactId);
}
```

After context acceptance in the context form submit handler, call:

```javascript
ensureWorkView();
showWorkspace();
loadWorkList();
```

Add refresh button handling:

```javascript
document.querySelector("[data-work-refresh]").addEventListener("click", () => {
  loadWorkList();
});
```

When existing code calls `chatView.render(state)`, update to `renderWorkspace()` where both chat and Work should refresh.

- [ ] **Step 6: Preserve Work state on new conversations**

If the RED state test failed, update `startNewConversation()` so it clears transcript, pending turn, and failure state while preserving `work`.

- [ ] **Step 7: Add focused Work styles**

In `frontend/styles.css`, add only styles required to keep Work readable:

```css
.section-heading {
  align-items: center;
  display: flex;
  gap: 0.75rem;
  justify-content: space-between;
}

.work-list-item {
  display: block;
  margin-block: 0.5rem;
  text-align: left;
  width: 100%;
}

.work-panel {
  border-left: 1px solid var(--border);
  overflow: auto;
  padding: 1rem;
}

.work-heading {
  font-weight: 700;
}

.feedback-form {
  border: 1px solid var(--border);
  border-radius: 0.75rem;
  display: grid;
  gap: 0.5rem;
  margin-block: 0.75rem;
  padding: 0.75rem;
}

.feedback-event {
  border-top: 1px solid var(--border);
  padding-block: 0.5rem;
}
```

Use existing CSS variable names from the current stylesheet. If `--border` does not exist, use the established border token already present in `frontend/styles.css` instead of adding a broad design-system change.

- [ ] **Step 8: Run tests to verify GREEN**

Run:

```bash
venv/bin/python -m pytest -q tests/test_workspace_static.py
node --test tests/frontend/state.test.mjs
```

Expected: PASS.

---

### Task 5: Focused Integration Verification and Cleanup

**Files:**
- Modify only files changed by Tasks 1-4 if verification exposes defects.

**Interfaces:**
- Confirms all Phase 4A.4 frontend contracts work together.

- [ ] **Step 1: Run the focused frontend test set**

Run:

```bash
node --test tests/frontend/requests.test.mjs tests/frontend/api.test.mjs tests/frontend/state.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/work-view.test.mjs
```

Expected: PASS.

- [ ] **Step 2: Run the focused FastAPI static boundary tests**

Run:

```bash
venv/bin/python -m pytest -q tests/test_workspace_static.py
```

Expected: PASS.

- [ ] **Step 3: Run whitespace/static diff validation**

Run:

```bash
git diff --check
```

Expected: no output and exit 0.

- [ ] **Step 4: Inspect source for forbidden unsafe rendering**

Run:

```bash
rg -n "innerHTML|insertAdjacentHTML|outerHTML|/api/synthesize|firebase|firestore|aiplatform|Agent_Col" frontend tests/frontend tests/test_workspace_static.py
```

Expected:

- No `innerHTML`, `insertAdjacentHTML`, or `outerHTML` matches in `frontend`.
- No browser calls to `/api/synthesize`, Firestore, Firebase, or Vertex AI.
- No user-facing `Agent_Col` copy in `frontend/index.html`.
- `Agent_Col` may remain in test messages or technical comments only when explicitly testing backend naming or preserving technical identifiers.

- [ ] **Step 5: Do not run full suite by default**

Full suite is not required for this pass unless focused verification exposes a shared backend regression. This pass changes the static workspace frontend and pure frontend helper modules; it does not change FastAPI route behavior, Firestore persistence, routing, expert execution, synthesis, or memory services.

---

## Manual visual/runtime verification targets

1. Start the API with:

   ```bash
   source venv/bin/activate
   uvicorn main:app --reload
   ```

2. Open:

   ```text
   http://127.0.0.1:8000/workspace
   ```

3. Confirm visible naming:

   - Header title says `Agent Col`.
   - Empty conversation guidance says `Ask Agent Col for help`.
   - No visible user-facing `Agent_Col` appears in the shell.

4. Enter local development context:

   - User ID: `wifiknight`
   - Project ID: `agent-col`

   Expected: workspace opens, Work panel attempts to load existing project blueprints, and any errors appear as visible UI errors instead of console-only failures.

5. Select an existing Work item.

   Expected: detail panel loads canonical backend detail, including project name, core value proposition, architectural decisions, Socratic questions, roadmap, diagnostic warnings, feedback targets, adaptation receipts when present, and feedback history.

6. Use a chat prompt that creates a blueprint through `/api/chat`, for example:

   ```text
   Create a structured blueprint from this source text:
   Build a lightweight collaborative study workflow with explicit approval,
   small verifiable milestones, and governed cross-session adaptation.
   ```

   Expected:

   - Chat response returns an authoritative `synthesize_project` action receipt and artifact receipt.
   - Work list refreshes.
   - The newly returned artifact is selected.
   - Detail shown in the panel is loaded from the canonical detail API, not copied from the chat response.

7. Use feedback controls on the whole-blueprint target.

   Expected:

   - `accepted` and `rejected` feedback can be submitted with feedback text.
   - `edited` feedback requires correction text.
   - Chat response shows `record_blueprint_feedback`.
   - Feedback history refreshes and detail feedback counts update.

8. If an earlier feedback event exists, enter its `feedback_id` in the supersession field and submit a reversing decision.

   Expected: feedback history shows the new event as active and the older event as superseded after refresh.

9. Click the JSON download link.

   Expected: browser downloads or opens a `.json` file with canonical artifact detail. Filename is sanitized and contains the artifact ID.

10. Refresh the page and re-enter the same local context.

    Expected: transcript is empty because no session-history API exists; Work list reloads from the backend because artifacts are project-scoped.

11. Narrow the viewport.

    Expected: chat, Work list, and detail remain readable without horizontal page overflow.

12. Open developer console.

    Expected: no uncaught JavaScript errors during list load, detail load, feedback submission, or download.

## Proposed next pass after Phase 4A.4

- Goal: implement the frontend governed-memory inspection and lifecycle controls currently represented only as a placeholder panel.
- Proposed approach: use existing memory inspection, revoke, and hard-delete APIs; submit structured memory decisions through `/api/chat`; render pending proposals, active signals, and lifecycle events from authoritative response fields.
- Expected files/surfaces: `frontend/memory-view.mjs`, `frontend/api.mjs`, `frontend/requests.mjs`, `frontend/state.mjs`, `frontend/app.mjs`, `frontend/index.html`, `frontend/styles.css`, `tests/frontend/*`, and `tests/test_workspace_static.py`.
- Approval required before implementation.

## Stop Conditions

- Stop if a Work requirement needs session-history, project-listing, authentication, durable jobs, uploads, or artifact-version APIs.
- Stop if the backend read APIs do not provide the data the UI needs.
- Stop if feedback submission cannot be expressed through existing `artifact_feedback_decision` on `/api/chat`.
- Stop if implementing this pass would require direct browser calls to `/api/synthesize`, Firestore, Vertex AI, or any Google credential-bearing service.
- Stop if the frontend would need to mutate blueprint documents directly rather than recording immutable feedback events.
- Stop if the user-facing naming change would require renaming backend identifiers, schema values, source filenames, or repository terminology beyond visible copy.
