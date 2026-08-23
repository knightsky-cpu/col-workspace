# Phase 4A.3 Conversation and Authoritative Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the workspace submit ordinary idempotent chat turns to Agent_Col, render an ephemeral transcript, and display authoritative receipts from structured response fields.

**Architecture:** Keep the frontend dependency-free and same-origin. Add a focused `chat-view.mjs` module for composer, transcript, retry, and receipt DOM rendering; extend pure state/request helpers so behavior is testable in Node without a browser; keep `app.mjs` as composition glue.

**Tech Stack:** Python 3.14, FastAPI, httpx/pytest, semantic HTML, CSS custom properties, browser-native JavaScript ES modules, Node 26 `node --test`.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-4a-lightweight-browser-workspace-design.md`

## Global Constraints

- Use `BACKEND_FRONTEND_INTEGRATION_CONTRACT_INVENTORY.md` as the source of truth for `/api/chat` request and response fields.
- Use only `POST /api/chat` for conversation turns.
- Generate exactly one idempotency key per new submitted turn.
- Exact retry must reuse the original frozen request body and original idempotency key.
- Render backend/model text as untrusted text, never HTML.
- Receipt display must come from response fields, not from parsing prose.
- Transcript state remains page-memory only.
- Do not add session history retrieval, authentication, CORS, external assets, package dependencies, Markdown rendering, streaming, uploads, artifact detail UI, artifact feedback controls, or memory lifecycle controls.
- Preserve `GET /` and existing backend APIs.
- Do not checkpoint this implementation until manual verification succeeds and the user explicitly requests checkpointing.

---

## File Structure

- Create: `frontend/chat-view.mjs`
  - Composer event wiring, transcript rendering, receipt rendering, retry controls, pending and error presentation.
- Create: `tests/frontend/chat-view.test.mjs`
  - Pure DOM-shim tests for safe text rendering and receipt rendering.
- Modify: `frontend/index.html`
  - Add composer form, transcript container, status/error regions, and retry button targets.
- Modify: `frontend/styles.css`
  - Add transcript, composer, receipt, pending, and error styles.
- Modify: `frontend/app.mjs`
  - Wire chat view to `apiFetchJson`, state transitions, request construction, and exact retry.
- Modify: `frontend/state.mjs`
  - Add draft-agnostic transcript entries, failure metadata, receipt-driven refresh flags, and pending-state selectors.
- Modify: `frontend/requests.mjs`
  - Add `buildOrdinaryChatRequest(context, message, crypto)` as a clearer UI-facing wrapper around `buildChatRequest`.
- Modify: `frontend/render.mjs`
  - Add small safe DOM helpers needed by `chat-view.mjs`.
- Modify: `tests/frontend/state.test.mjs`
  - Cover successful transcript entries, failed retry preservation, and new conversation clearing chat state.
- Modify: `tests/frontend/requests.test.mjs`
  - Cover UI-facing ordinary chat request construction.
- Modify: `tests/test_workspace_static.py`
  - Assert the shell exposes composer/status landmarks without external assets.

---

### Task 1: Request and State Contracts for Chat Turns

**Files:**
- Modify: `tests/frontend/requests.test.mjs`
- Modify: `tests/frontend/state.test.mjs`
- Modify: `frontend/requests.mjs`
- Modify: `frontend/state.mjs`

**Interfaces:**
- Produces: `buildOrdinaryChatRequest(context: object, message: string, cryptoLike?: Crypto): { key: string, body: object }`
- Produces: `selectCanSubmit(state: object): boolean`
- Produces: `selectNeedsReceiptRefresh(response: object): object`
- Extends: `completePendingTurn(state, response)` to record user message and structured response.

- [ ] **Step 1: Write failing request tests**

Append to `tests/frontend/requests.test.mjs`:

```javascript
import { buildOrdinaryChatRequest } from "../../frontend/requests.mjs";

test("ordinary chat request uses context locators and one idempotency key", () => {
  const request = buildOrdinaryChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    "Explain receipt authority.",
    cryptoStub,
  );

  assert.equal(request.key, "chat--123e4567-e89b-12d3-a456-426614174000");
  assert.deepEqual(request.body, {
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Explain receipt authority.",
  });
});
```

- [ ] **Step 2: Write failing state tests**

Append to `tests/frontend/state.test.mjs`:

```javascript
import {
  selectCanSubmit,
  selectNeedsReceiptRefresh,
} from "../../frontend/state.mjs";

test("selectCanSubmit requires workspace context and no pending turn", () => {
  assert.equal(selectCanSubmit(createInitialState()), false);
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  assert.equal(selectCanSubmit(accepted), true);
  assert.equal(
    selectCanSubmit(beginPendingTurn(accepted, {
      key: "chat--1",
      body: { message: "hello" },
    })),
    false,
  );
});

test("receipt refresh selector is driven by structured fields", () => {
  assert.deepEqual(
    selectNeedsReceiptRefresh({
      response: "Created.",
      actions: [{ action_name: "synthesize_project", status: "completed" }],
      artifacts: [{ artifact_id: "blueprint--1" }],
      memory_proposals: [{ proposal_id: "response_length--1" }],
      adaptations: [{ signal_id: "planning_granularity--1" }],
    }),
    {
      work: true,
      memory: true,
    },
  );
  assert.deepEqual(
    selectNeedsReceiptRefresh({ response: "I created a blueprint in prose." }),
    {
      work: false,
      memory: false,
    },
  );
});
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
node --test tests/frontend/requests.test.mjs tests/frontend/state.test.mjs
```

Expected: FAIL because `buildOrdinaryChatRequest`, `selectCanSubmit`, and `selectNeedsReceiptRefresh` are not exported.

- [ ] **Step 4: Implement minimal request/state functions**

In `frontend/requests.mjs`:

```javascript
export function buildOrdinaryChatRequest(context, message, cryptoLike = globalThis.crypto) {
  return buildChatRequest({
    project_id: context.project_id,
    session_id: context.session_id,
    user_id: context.user_id,
    message,
    crypto: cryptoLike,
  });
}
```

In `frontend/state.mjs`:

```javascript
export function selectCanSubmit(state) {
  return state.mode === "workspace" && state.context !== null && state.pendingTurn === null;
}

export function selectNeedsReceiptRefresh(response) {
  const actions = Array.isArray(response.actions) ? response.actions : [];
  return {
    work: Array.isArray(response.artifacts) && response.artifacts.length > 0,
    memory: (
      (Array.isArray(response.memory_proposals) && response.memory_proposals.length > 0)
      || (Array.isArray(response.adaptations) && response.adaptations.length > 0)
      || actions.some((action) => action.action_name.includes("memory_signal"))
    ),
  };
}
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
node --test tests/frontend/requests.test.mjs tests/frontend/state.test.mjs
```

Expected: PASS.

---

### Task 2: Safe Transcript and Receipt Rendering

**Files:**
- Create: `tests/frontend/chat-view.test.mjs`
- Create: `frontend/chat-view.mjs`
- Modify: `frontend/render.mjs`

**Interfaces:**
- Produces: `createChatView(elements: object, handlers: object): object`
- Produces: `renderTranscript(container: Element, transcript: array): void`
- Produces: `renderReceipts(container: Element, response: object): void`
- Consumes: `setText(element, value)` from `frontend/render.mjs`

- [ ] **Step 1: Write failing chat-view rendering tests**

Create `tests/frontend/chat-view.test.mjs` with a minimal DOM shim:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import { renderReceipts, renderTranscript } from "../../frontend/chat-view.mjs";

function node(tagName = "div") {
  return {
    tagName,
    children: [],
    attributes: {},
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

test("renderTranscript uses textContent for user and model text", () => {
  const container = node();
  renderTranscript(container, [{
    request: { body: { message: "<img src=x onerror=alert(1)>" } },
    response: { response: "<strong>not html</strong>" },
  }]);

  assert.equal(container.children.length, 1);
  assert.equal(
    container.children[0].children[0].textContent,
    "<img src=x onerror=alert(1)>",
  );
  assert.equal(
    container.children[0].children[1].textContent,
    "<strong>not html</strong>",
  );
});

test("renderReceipts renders structured fields and ignores prose claims", () => {
  const container = node();
  renderReceipts(container, {
    response: "I used google_search in prose.",
    actions: [{ action_name: "url_context", status: "completed" }],
    citations: [{ uri: "https://example.com/", label: "Example Domain" }],
    artifacts: [{
      artifact_type: "synthesis_blueprint",
      project_id: "agent-col",
      artifact_id: "blueprint--1",
      schema_version: "2.0",
      display_label: "Blueprint",
    }],
    memory_proposals: [{ proposal_id: "response_length--1", category: "response_length" }],
    adaptations: [{ signal_id: "planning_granularity--1", category: "planning_granularity" }],
  });

  const text = JSON.stringify(container.children.map((child) => child.textContent));
  assert.match(text, /url_context/);
  assert.match(text, /Example Domain/);
  assert.match(text, /Blueprint/);
  assert.match(text, /response_length--1/);
  assert.match(text, /planning_granularity--1/);
  assert.doesNotMatch(text, /google_search/);
});
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs
```

Expected: FAIL because `frontend/chat-view.mjs` does not exist.

- [ ] **Step 3: Implement safe render helpers**

Extend `frontend/render.mjs`:

```javascript
export function element(tagName, className, text) {
  const created = document.createElement(tagName);
  if (className) {
    created.classList.add(className);
  }
  if (text !== undefined) {
    created.textContent = String(text);
  }
  return created;
}
```

- [ ] **Step 4: Implement `frontend/chat-view.mjs`**

```javascript
import { element, setText } from "./render.mjs";

function appendReceipt(container, label, value) {
  const item = element("li", "receipt-item");
  item.textContent = `${label}: ${value}`;
  container.append(item);
}

export function renderReceipts(container, response) {
  container.replaceChildren();
  const list = element("ul", "receipt-list");
  for (const action of response.actions ?? []) {
    appendReceipt(list, "Action", `${action.action_name} ${action.status}`);
  }
  for (const citation of response.citations ?? []) {
    appendReceipt(list, "Citation", citation.label);
  }
  for (const artifact of response.artifacts ?? []) {
    appendReceipt(list, "Work", artifact.display_label);
  }
  for (const feedback of response.artifact_feedback ?? []) {
    appendReceipt(list, "Feedback", `${feedback.decision} ${feedback.feedback_id}`);
  }
  for (const proposal of response.memory_proposals ?? []) {
    appendReceipt(list, "Memory proposal", proposal.proposal_id);
  }
  for (const adaptation of response.adaptations ?? []) {
    appendReceipt(list, "Adaptation", adaptation.signal_id);
  }
  if (list.children.length > 0) {
    container.append(list);
  }
}

export function renderTranscript(container, transcript) {
  container.replaceChildren();
  for (const turn of transcript) {
    const article = element("article", "turn");
    const user = element("p", "turn-user");
    const model = element("p", "turn-model");
    setText(user, turn.request?.body?.message ?? "");
    setText(model, turn.response?.response ?? "");
    article.append(user, model);
    const receipts = element("div", "turn-receipts");
    renderReceipts(receipts, turn.response ?? {});
    article.append(receipts);
    container.append(article);
  }
}

export function createChatView(elements, handlers) {
  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    handlers.onSubmit(elements.input.value);
  });
  elements.retryButton.addEventListener("click", () => {
    handlers.onRetry();
  });
  return {
    render(state) {
      renderTranscript(elements.transcript, state.transcript);
      elements.retryButton.hidden = state.lastFailure === null;
      elements.submitButton.disabled = state.pendingTurn !== null;
    },
  };
}
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs
```

Expected: PASS.

---

### Task 3: Composer Shell and App Wiring

**Files:**
- Modify: `tests/test_workspace_static.py`
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Modify: `frontend/app.mjs`
- Modify: `tests/frontend/chat-view.test.mjs`

**Interfaces:**
- Consumes: `apiFetchJson("/api/chat", { method: "POST", idempotencyKey, body })`
- Consumes: `buildOrdinaryChatRequest(...)`
- Consumes: `buildExactRetryRequest(...)`
- Consumes: `beginPendingTurn`, `completePendingTurn`, `failPendingTurn`

- [ ] **Step 1: Write failing shell test assertions**

Extend `test_workspace_route_serves_html_shell` in `tests/test_workspace_static.py`:

```python
    assert 'data-chat-form' in response.text
    assert 'name="message"' in response.text
    assert 'data-chat-transcript' in response.text
    assert 'data-chat-status' in response.text
    assert 'data-retry-turn' in response.text
```

- [ ] **Step 2: Run shell test to verify RED**

Run:

```bash
venv/bin/python -m pytest -q tests/test_workspace_static.py::test_workspace_route_serves_html_shell
```

Expected: FAIL because composer/status markup is absent.

- [ ] **Step 3: Add composer and transcript markup**

Modify `frontend/index.html` inside `<main id="conversation-workspace"...>`:

```html
<div class="chat-transcript" data-chat-transcript aria-live="polite"></div>
<p class="chat-status" data-chat-status role="status"></p>
<p class="chat-error" data-chat-error role="alert" hidden></p>
<button type="button" data-retry-turn hidden>Retry exact request</button>
<form class="composer" data-chat-form>
  <label for="chat-message">Message</label>
  <textarea
    id="chat-message"
    name="message"
    data-chat-input
    rows="4"
    maxlength="10000"
    required
  ></textarea>
  <div class="composer-actions">
    <span data-character-count>0 / 10000</span>
    <button type="submit" data-chat-submit>Send</button>
  </div>
</form>
```

- [ ] **Step 4: Add focused composer/transcript styles**

Modify `frontend/styles.css` with:

```css
.chat-transcript {
  display: grid;
  gap: 1rem;
  margin-block-end: 1rem;
}

.turn {
  display: grid;
  gap: 0.75rem;
  border-block-end: 1px solid var(--border);
  padding-block-end: 1rem;
}

.turn-user,
.turn-model {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.turn-user {
  color: var(--muted);
}

.receipt-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  list-style: none;
  margin: 0;
  padding: 0;
}

.receipt-item {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.25rem 0.45rem;
  background: var(--surface);
  font-size: 0.875rem;
}

.composer {
  position: sticky;
  bottom: 0;
  display: grid;
  gap: 0.5rem;
  padding-block-start: 1rem;
  background: var(--background);
}

.composer textarea {
  width: 100%;
  resize: vertical;
  min-height: 7rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  padding: 0.75rem;
  font: inherit;
}

.composer-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.chat-error {
  color: var(--danger);
}
```

- [ ] **Step 5: Wire `app.mjs` to submit and retry chat**

Replace `frontend/app.mjs` composition with imports and handlers that:

```javascript
import { apiFetchJson } from "./api.mjs";
import { createChatView } from "./chat-view.mjs";
import {
  buildExactRetryRequest,
  buildOrdinaryChatRequest,
  readContextForm,
} from "./requests.mjs";
import {
  createInitialState,
  acceptContext,
  startNewConversation,
  beginPendingTurn,
  completePendingTurn,
  failPendingTurn,
  selectCanSubmit,
} from "./state.mjs";
import { setText } from "./render.mjs";
```

Add helpers:

```javascript
let chatView = null;

async function submitRequest(request) {
  state = beginPendingTurn(state, request);
  chatView.render(state);
  setText(document.querySelector("[data-chat-status]"), "Waiting for Agent_Col");
  try {
    const response = await apiFetchJson("/api/chat", {
      method: "POST",
      idempotencyKey: request.key,
      body: request.body,
    });
    state = completePendingTurn(state, response);
    setText(document.querySelector("[data-chat-status]"), "");
  } catch (error) {
    state = failPendingTurn(state, error);
    setText(document.querySelector("[data-chat-error]"), error.message);
    document.querySelector("[data-chat-error]").hidden = false;
  }
  chatView.render(state);
}
```

Wire `createChatView` after context acceptance:

```javascript
chatView = createChatView(
  {
    form: document.querySelector("[data-chat-form]"),
    input: document.querySelector("[data-chat-input]"),
    submitButton: document.querySelector("[data-chat-submit]"),
    retryButton: document.querySelector("[data-retry-turn]"),
    transcript: document.querySelector("[data-chat-transcript]"),
  },
  {
    onSubmit(message) {
      if (!selectCanSubmit(state)) {
        return;
      }
      const request = buildOrdinaryChatRequest(state.context, message);
      submitRequest(request);
    },
    onRetry() {
      if (state.lastFailure === null) {
        return;
      }
      submitRequest(buildExactRetryRequest(state.lastFailure.request));
    },
  },
);
```

Ensure Enter behavior remains default textarea behavior in this pass. Enter-to-submit can be a later refinement; this pass proves transport and receipts first.

- [ ] **Step 6: Run focused tests to verify GREEN**

Run:

```bash
venv/bin/python -m pytest -q tests/test_workspace_static.py
node --test tests/frontend/requests.test.mjs tests/frontend/api.test.mjs tests/frontend/state.test.mjs tests/frontend/chat-view.test.mjs
```

Expected: PASS.

---

## Final Verification for the Approved Pass

Run:

```bash
venv/bin/python -m pytest -q tests/test_workspace_static.py
node --test tests/frontend/requests.test.mjs tests/frontend/api.test.mjs tests/frontend/state.test.mjs tests/frontend/chat-view.test.mjs
git diff --check
```

Run full pytest if static route or `main.py` changes beyond markup assertions. If `main.py` is untouched in this pass, focused verification is sufficient.

Manual verification targets:

1. Start `uvicorn main:app --reload`.
2. Open `http://127.0.0.1:8000/workspace`.
3. Enter `user_id=wifiknight`, `project_id=agent-col`.
4. Send `Explain in one paragraph why receipt authority matters.`
5. Expected: one user message, one Agent_Col response, no receipt fabrication if response fields are empty.
6. Send a source or artifact-producing prompt only if the backend is configured and you want live receipt coverage.
7. Expected: displayed receipts match JSON fields returned by `/api/chat`.
8. Trigger an invalid/failed request if practical; expected retry button preserves the exact original request.
9. Reload page; expected transcript disappears and the UI does not claim restoration.
10. Check browser console for unexpected errors.

## Scope Notes and Stop Conditions

- Stop if implementing receipts requires parsing response prose.
- Stop if chat submission requires session-history APIs, authentication, CORS, or backend route changes.
- Stop if retries generate a new idempotency key.
- Stop if the frontend needs Markdown/HTML rendering to present model output.
- Stop if the work starts implementing artifact detail, artifact feedback controls, or memory lifecycle controls.

## Proposed Next Pass After Manual Acceptance

- Goal: Phase 4A.4 Work Inspection and Feedback.
- Proposed approach: load bounded Work list and canonical blueprint detail, render schema-2.0 blueprint sections, support safe JSON download, and submit explicit artifact feedback through structured `/api/chat`.
- Expected files/surfaces: `frontend/work-view.mjs`, `frontend/app.mjs`, `frontend/state.mjs`, `frontend/api.mjs`, `frontend/styles.css`, Node tests, and focused manual artifact checks.
- Approval required before implementation.
