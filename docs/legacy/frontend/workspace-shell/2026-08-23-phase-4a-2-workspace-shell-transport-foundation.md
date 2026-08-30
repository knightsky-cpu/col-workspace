# Phase 4A.2 Workspace Shell and Transport Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first same-origin Agent_Col browser workspace shell, local development context gate, and dependency-free frontend transport/request primitives without implementing the full chat, Work, or memory UI.

**Architecture:** FastAPI serves one HTML workspace route and one local static namespace. The browser code is split into small `.mjs` modules for API transport, request construction, ephemeral state, and minimal shell wiring so later passes can add conversation, Work, and memory features without changing the transport foundation.

**Tech Stack:** Python 3.14, FastAPI, httpx/pytest, semantic HTML, CSS custom properties, browser-native JavaScript ES modules, Node 26 `node --test`.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-4a-lightweight-browser-workspace-design.md`

## Global Constraints

- Use `docs/design/BACKEND_FRONTEND_INTEGRATION_CONTRACT_INVENTORY.md` as the primary backend contract reference.
- Preserve `GET /` as the existing JSON health endpoint returning `{"status":"online"}`.
- Add only `GET /workspace` and the bounded static namespace `GET /static/agent-col/*`.
- Use same-origin relative API paths only.
- Do not add React, Vite, TailwindCSS, a component library, package dependencies, CDN assets, CORS middleware, authentication, streaming, jobs, uploads, or direct Firestore/Vertex access.
- Do not implement full chat execution, artifact detail rendering, artifact feedback submission, or governed memory lifecycle controls in this pass.
- Browser state remains ephemeral page memory only.
- Request-provided `project_id`, `user_id`, and `session_id` remain visibly labeled as local development locators, not authentication.
- Backend/model content must be rendered as untrusted text in later passes; this pass must not introduce unsafe HTML rendering helpers.
- Follow repository workflow: do not commit the implementation pass until user manual verification succeeds and the user explicitly requests checkpointing.

---

## File Structure

- Create: `frontend/index.html`
  - Semantic application shell for `/workspace`, local context gate, primary landmarks, empty conversation region, collapsed supporting and Work regions, and local asset references.
- Create: `frontend/styles.css`
  - Initial tokens, layout, responsive behavior, focus states, loading/error utility states, and system light/dark support.
- Create: `frontend/api.mjs`
  - Same-origin HTTP JSON client, response parsing, FastAPI validation error normalization, `Retry-After` extraction, and typed error objects.
- Create: `frontend/requests.mjs`
  - Identifier validation, session/idempotency generation, chat request construction, exact retry envelope, and structured-decision guardrails.
- Create: `frontend/state.mjs`
  - Pure ephemeral state transitions for context acceptance, pending request lifecycle, retry state, and new-conversation reset.
- Create: `frontend/render.mjs`
  - Minimal safe DOM helpers using `textContent`, element construction, and visibility helpers.
- Create: `frontend/app.mjs`
  - Browser composition and event wiring for the context gate, shell visibility, new-conversation action, and placeholder transport status.
- Create: `tests/test_workspace_static.py`
  - Offline FastAPI/static route tests that do not require app lifespan services, Firestore, Vertex, or Uvicorn.
- Create: `tests/frontend/requests.test.mjs`
  - Node tests for identifier, idempotency, immutable request construction, exact retry, and structured-decision exclusions.
- Create: `tests/frontend/api.test.mjs`
  - Node tests for API error normalization and response parsing with stubbed `fetch`.
- Create: `tests/frontend/state.test.mjs`
  - Node tests for context acceptance, request lifecycle, retry preservation, and new-conversation reset.
- Modify: `main.py`
  - Import static/HTML response support, mount `/static/agent-col`, and add `GET /workspace`.

---

### Task 1: FastAPI Workspace and Static Boundary

**Files:**
- Create: `tests/test_workspace_static.py`
- Create: `frontend/index.html`
- Create: `frontend/styles.css`
- Create: `frontend/app.mjs`
- Modify: `main.py`

**Interfaces:**
- Produces: `GET /workspace -> HTMLResponse`
- Produces: `GET /static/agent-col/styles.css -> text/css`
- Produces: `GET /static/agent-col/app.mjs -> JavaScript module`
- Preserves: `GET / -> {"status":"online"}`

- [ ] **Step 1: Write the failing FastAPI static-boundary tests**

Create `tests/test_workspace_static.py`:

```python
import httpx
import pytest

import main


@pytest.mark.asyncio
async def test_workspace_route_serves_html_shell() -> None:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/workspace")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<main id="conversation-workspace"' in response.text
    assert 'src="/static/agent-col/app.mjs"' in response.text
    assert 'href="/static/agent-col/styles.css"' in response.text
    assert "https://" not in response.text
    assert "http://" not in response.text


@pytest.mark.asyncio
async def test_workspace_static_assets_are_local() -> None:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        css_response = await client.get("/static/agent-col/styles.css")
        js_response = await client.get("/static/agent-col/app.mjs")

    assert css_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]
    assert js_response.status_code == 200
    assert "javascript" in js_response.headers["content-type"]


@pytest.mark.asyncio
async def test_health_route_remains_json_liveness_contract() -> None:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "online"}
```

- [ ] **Step 2: Run the FastAPI tests to verify RED**

Run:

```bash
pytest -q tests/test_workspace_static.py
```

Expected: FAIL with `/workspace` returning 404 and static assets returning 404. The health assertion should already pass.

- [ ] **Step 3: Add minimal workspace files**

Create `frontend/index.html` with no inline script and no external assets:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Agent_Col Workspace</title>
    <link rel="stylesheet" href="/static/agent-col/styles.css">
    <script type="module" src="/static/agent-col/app.mjs"></script>
  </head>
  <body>
    <div class="workspace-shell" data-app-root>
      <header class="top-bar" aria-label="Workspace">
        <div>
          <p class="eyebrow">Local development mode</p>
          <h1>Agent_Col</h1>
        </div>
        <button type="button" data-new-conversation disabled>
          New conversation
        </button>
      </header>

      <section class="context-gate" aria-labelledby="context-title">
        <h2 id="context-title">Development context</h2>
        <p>
          These values are local request locators only. They are not
          authentication or ownership.
        </p>
        <form data-context-form>
          <label>
            User ID
            <input name="user_id" autocomplete="off" required>
          </label>
          <label>
            Project ID
            <input name="project_id" autocomplete="off" value="agent-col" required>
          </label>
          <button type="submit">Enter workspace</button>
          <p class="form-error" role="alert" data-context-error hidden></p>
        </form>
      </section>

      <div class="workspace-grid" data-workspace hidden>
        <aside class="supporting-panel" aria-label="Supporting context">
          <section aria-labelledby="work-list-title">
            <h2 id="work-list-title">Work</h2>
            <p data-work-empty>No Work loaded yet.</p>
          </section>
          <section aria-labelledby="memory-title">
            <h2 id="memory-title">Memory</h2>
            <p data-memory-empty>No memory loaded yet.</p>
          </section>
          <section aria-labelledby="activity-title">
            <h2 id="activity-title">Activity</h2>
            <p data-activity-empty>No activity yet.</p>
          </section>
        </aside>

        <main id="conversation-workspace" class="conversation" tabindex="-1">
          <section aria-labelledby="empty-conversation-title">
            <h2 id="empty-conversation-title">Start a conversation</h2>
            <p>
              Ask Agent_Col for help, or ask it to create a structured
              blueprint from source text in your message.
            </p>
          </section>
        </main>

        <aside class="work-panel" aria-label="Work review" hidden>
          <h2>Work review</h2>
          <p>Select a Work item to inspect its canonical backend detail.</p>
        </aside>
      </div>
    </div>
  </body>
</html>
```

Create `frontend/styles.css` with restrained layout and accessible focus:

```css
:root {
  color-scheme: light dark;
  --background: #f7f8f8;
  --surface: #ffffff;
  --surface-muted: #eef1f1;
  --text: #1d2525;
  --muted: #617070;
  --border: #cbd5d5;
  --accent: #235c67;
  --danger: #9d2c2c;
  --radius: 8px;
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
}

@media (prefers-color-scheme: dark) {
  :root {
    --background: #111616;
    --surface: #182020;
    --surface-muted: #202b2b;
    --text: #edf2f2;
    --muted: #a6b5b5;
    --border: #334343;
    --accent: #7db7c2;
    --danger: #ff8c8c;
  }
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: var(--background);
  color: var(--text);
}

button,
input {
  font: inherit;
}

button {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  min-height: 2.5rem;
  padding: 0.5rem 0.75rem;
}

button:not(:disabled) {
  cursor: pointer;
}

button:focus-visible,
input:focus-visible,
main:focus-visible {
  outline: 3px solid var(--accent);
  outline-offset: 2px;
}

.workspace-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

h1,
h2,
p {
  margin-block-start: 0;
}

.eyebrow {
  margin-block-end: 0.25rem;
  color: var(--muted);
  font-size: 0.8125rem;
}

.context-gate {
  width: min(100% - 2rem, 32rem);
  margin: auto;
  padding: 1.25rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.context-gate form {
  display: grid;
  gap: 1rem;
}

.context-gate label {
  display: grid;
  gap: 0.35rem;
}

.context-gate input {
  width: 100%;
  min-height: 2.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--background);
  color: var(--text);
  padding: 0.45rem 0.6rem;
}

.form-error {
  color: var(--danger);
}

.workspace-grid {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(16rem, 22rem) minmax(0, 1fr) minmax(18rem, 26rem);
}

.supporting-panel,
.conversation,
.work-panel {
  min-width: 0;
  padding: 1rem;
}

.supporting-panel,
.work-panel {
  background: var(--surface-muted);
  border-inline-end: 1px solid var(--border);
}

.work-panel {
  border-inline: 1px solid var(--border) 0;
}

.conversation {
  background: var(--background);
}

[hidden] {
  display: none !important;
}

@media (max-width: 900px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .supporting-panel,
  .work-panel {
    border-inline: 0;
    border-block-end: 1px solid var(--border);
  }
}
```

Create `frontend/app.mjs`:

```javascript
import { createInitialState, acceptContext } from "./state.mjs";
import { readContextForm } from "./requests.mjs";
import { setText } from "./render.mjs";

let state = createInitialState();

function showWorkspace() {
  document.querySelector("[data-context-error]").hidden = true;
  document.querySelector("[data-workspace]").hidden = false;
  document.querySelector(".context-gate").hidden = true;
  document.querySelector("[data-new-conversation]").disabled = false;
  document.querySelector("#conversation-workspace").focus();
}

function showContextError(message) {
  const error = document.querySelector("[data-context-error]");
  setText(error, message);
  error.hidden = false;
}

document.querySelector("[data-context-form]").addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    state = acceptContext(state, readContextForm(new FormData(event.currentTarget)));
    showWorkspace();
  } catch (error) {
    showContextError(error.message);
  }
});
```

- [ ] **Step 4: Mount static assets and workspace route in `main.py`**

Add imports near the existing FastAPI imports:

```python
from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
```

Add constants and mount after `app = FastAPI(lifespan=lifespan)`:

```python
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

app = FastAPI(lifespan=lifespan)
app.mount(
    "/static/agent-col",
    StaticFiles(directory=FRONTEND_DIR),
    name="agent_col_static",
)
```

Add the route without changing `GET /`:

```python
@app.get("/workspace", response_class=HTMLResponse)
async def workspace() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
```

- [ ] **Step 5: Run the FastAPI static-boundary tests to verify GREEN**

Run:

```bash
pytest -q tests/test_workspace_static.py
```

Expected: PASS.

---

### Task 2: Request and Idempotency Contracts

**Files:**
- Create: `tests/frontend/requests.test.mjs`
- Create: `frontend/requests.mjs`

**Interfaces:**
- Produces: `isValidIdentifier(value: string): boolean`
- Produces: `generateSessionId(cryptoLike?: Crypto): string`
- Produces: `generateIdempotencyKey(prefix: string, cryptoLike?: Crypto): string`
- Produces: `readContextForm(formData: FormData): { user_id: string, project_id: string }`
- Produces: `buildChatRequest(input: object): { key: string, body: object }`
- Produces: `buildExactRetryRequest(turn: object): { key: string, body: object }`

- [ ] **Step 1: Write the failing Node request-contract tests**

Create `tests/frontend/requests.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import {
  buildChatRequest,
  buildExactRetryRequest,
  generateIdempotencyKey,
  generateSessionId,
  isValidIdentifier,
} from "../../frontend/requests.mjs";

const cryptoStub = {
  randomUUID() {
    return "123e4567-e89b-12d3-a456-426614174000";
  },
};

test("identifier validation mirrors the backend locator shape", () => {
  assert.equal(isValidIdentifier("agent-col"), true);
  assert.equal(isValidIdentifier("wifiknight_01"), true);
  assert.equal(isValidIdentifier(""), false);
  assert.equal(isValidIdentifier("bad id"), false);
  assert.equal(isValidIdentifier("bad/slash"), false);
  assert.equal(isValidIdentifier("x".repeat(129)), false);
});

test("session and idempotency identifiers are generated locally", () => {
  assert.equal(
    generateSessionId(cryptoStub),
    "session--123e4567-e89b-12d3-a456-426614174000",
  );
  assert.equal(
    generateIdempotencyKey("chat", cryptoStub),
    "chat--123e4567-e89b-12d3-a456-426614174000",
  );
});

test("chat request construction freezes exact body and key", () => {
  const request = buildChatRequest({
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Hello Agent_Col",
    crypto: cryptoStub,
  });

  assert.equal(request.key, "chat--123e4567-e89b-12d3-a456-426614174000");
  assert.deepEqual(request.body, {
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Hello Agent_Col",
  });
  assert.throws(() => {
    request.body.message = "mutated";
  }, TypeError);
});

test("exact retry preserves the original key and body", () => {
  const original = buildChatRequest({
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Hello Agent_Col",
    crypto: cryptoStub,
  });

  const retry = buildExactRetryRequest(original);

  assert.equal(retry.key, original.key);
  assert.equal(retry.body, original.body);
});

test("structured memory and artifact decisions are mutually exclusive", () => {
  assert.throws(
    () => buildChatRequest({
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
      message: "structured decision",
      memory_decision: { proposal_id: "response_length--1", decision: "approved" },
      artifact_feedback_decision: {
        artifact_id: "blueprint--1",
        target_id: "target--1",
        decision: "accepted",
        feedback_text: "accepted",
        expected_schema_version: "2.0",
      },
      crypto: cryptoStub,
    }),
    /mutually exclusive/,
  );
});
```

- [ ] **Step 2: Run the request tests to verify RED**

Run:

```bash
node --test tests/frontend/requests.test.mjs
```

Expected: FAIL with module or exported function not found.

- [ ] **Step 3: Implement `frontend/requests.mjs`**

```javascript
const IDENTIFIER_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) {
      deepFreeze(child);
    }
  }
  return value;
}

export function isValidIdentifier(value) {
  return typeof value === "string" && IDENTIFIER_PATTERN.test(value);
}

export function generateSessionId(cryptoLike = globalThis.crypto) {
  return `session--${cryptoLike.randomUUID()}`;
}

export function generateIdempotencyKey(prefix, cryptoLike = globalThis.crypto) {
  if (!isValidIdentifier(prefix)) {
    throw new Error("Idempotency prefix is invalid.");
  }
  return `${prefix}--${cryptoLike.randomUUID()}`;
}

export function readContextForm(formData) {
  const user_id = String(formData.get("user_id") ?? "").trim();
  const project_id = String(formData.get("project_id") ?? "").trim();
  if (!isValidIdentifier(user_id)) {
    throw new Error("User ID must use letters, numbers, underscores, or hyphens.");
  }
  if (!isValidIdentifier(project_id)) {
    throw new Error("Project ID must use letters, numbers, underscores, or hyphens.");
  }
  return { user_id, project_id };
}

export function buildChatRequest(input) {
  const body = {
    project_id: input.project_id,
    session_id: input.session_id,
    user_id: input.user_id,
    message: String(input.message ?? ""),
  };

  if (!body.message.trim()) {
    throw new Error("Message is required.");
  }
  for (const key of ["project_id", "session_id", "user_id"]) {
    if (!isValidIdentifier(body[key])) {
      throw new Error(`${key} is invalid.`);
    }
  }
  if (input.memory_decision && input.artifact_feedback_decision) {
    throw new Error("Structured memory and artifact decisions are mutually exclusive.");
  }
  if (input.memory_decision) {
    body.memory_decision = input.memory_decision;
  }
  if (input.artifact_feedback_decision) {
    body.artifact_feedback_decision = input.artifact_feedback_decision;
  }

  return deepFreeze({
    key: generateIdempotencyKey("chat", input.crypto),
    body,
  });
}

export function buildExactRetryRequest(turn) {
  return {
    key: turn.key,
    body: turn.body,
  };
}
```

- [ ] **Step 4: Run the request tests to verify GREEN**

Run:

```bash
node --test tests/frontend/requests.test.mjs
```

Expected: PASS.

---

### Task 3: Same-Origin API Client and Error Normalization

**Files:**
- Create: `tests/frontend/api.test.mjs`
- Create: `frontend/api.mjs`

**Interfaces:**
- Produces: `apiFetchJson(path: string, options?: object, fetchLike?: Function): Promise<object | null>`
- Produces: `normalizeApiError(response: Response, body: object | string | null): object`
- Consumes: exact request envelopes from `frontend/requests.mjs`

- [ ] **Step 1: Write the failing API client tests**

Create `tests/frontend/api.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import { apiFetchJson } from "../../frontend/api.mjs";

function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

test("apiFetchJson sends same-origin JSON with idempotency key", async () => {
  const calls = [];
  const result = await apiFetchJson(
    "/api/chat",
    {
      method: "POST",
      idempotencyKey: "chat--123",
      body: { message: "hello" },
    },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { response: "ok", actions: [] });
    },
  );

  assert.deepEqual(result, { response: "ok", actions: [] });
  assert.equal(calls[0][0], "/api/chat");
  assert.equal(calls[0][1].headers["Content-Type"], "application/json");
  assert.equal(calls[0][1].headers["Idempotency-Key"], "chat--123");
  assert.equal(calls[0][1].body, JSON.stringify({ message: "hello" }));
});

test("apiFetchJson rejects remote URLs", async () => {
  await assert.rejects(
    () => apiFetchJson("https://example.com/api/chat", {}, async () => {
      throw new Error("fetch should not run");
    }),
    /same-origin/,
  );
});

test("apiFetchJson normalizes FastAPI validation arrays", async () => {
  await assert.rejects(
    () => apiFetchJson("/api/chat", {}, async () => jsonResponse(422, {
      detail: [
        { loc: ["body", "message"], msg: "String should have at most 10000 characters" },
      ],
    })),
    (error) => {
      assert.equal(error.status, 422);
      assert.equal(error.message, "body.message: String should have at most 10000 characters");
      return true;
    },
  );
});

test("apiFetchJson includes retry-after seconds when supplied", async () => {
  await assert.rejects(
    () => apiFetchJson("/api/chat", {}, async () => jsonResponse(
      409,
      { detail: "Chat turn is still in progress." },
      { "retry-after": "3" },
    )),
    (error) => {
      assert.equal(error.status, 409);
      assert.equal(error.retryAfterSeconds, 3);
      assert.equal(error.message, "Chat turn is still in progress.");
      return true;
    },
  );
});
```

- [ ] **Step 2: Run the API tests to verify RED**

Run:

```bash
node --test tests/frontend/api.test.mjs
```

Expected: FAIL with module or exported function not found.

- [ ] **Step 3: Implement `frontend/api.mjs`**

```javascript
export class ApiError extends Error {
  constructor({ status, message, detail, retryAfterSeconds }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

function assertSameOriginPath(path) {
  if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) {
    throw new Error("API path must be a same-origin absolute path.");
  }
  if (path.includes("://")) {
    throw new Error("API path must be same-origin.");
  }
}

function detailToMessage(detail) {
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      const loc = Array.isArray(item.loc) ? item.loc.join(".") : "request";
      return `${loc}: ${item.msg}`;
    }).join("; ");
  }
  if (typeof detail === "string") {
    return detail;
  }
  return "Request failed.";
}

export function normalizeApiError(response, body) {
  const retryAfter = response.headers.get("retry-after");
  const detail = body && typeof body === "object" && "detail" in body
    ? body.detail
    : body;
  return new ApiError({
    status: response.status,
    message: detailToMessage(detail),
    detail,
    retryAfterSeconds: retryAfter === null ? null : Number.parseInt(retryAfter, 10),
  });
}

async function parseBody(response) {
  if (response.status === 204) {
    return null;
  }
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function apiFetchJson(path, options = {}, fetchLike = globalThis.fetch) {
  assertSameOriginPath(path);
  const headers = { ...(options.headers ?? {}) };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  const response = await fetchLike(path, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const body = await parseBody(response);
  if (!response.ok) {
    throw normalizeApiError(response, body);
  }
  return body;
}
```

- [ ] **Step 4: Run the API tests to verify GREEN**

Run:

```bash
node --test tests/frontend/api.test.mjs
```

Expected: PASS.

---

### Task 4: Ephemeral Workspace State and Shell Wiring

**Files:**
- Create: `tests/frontend/state.test.mjs`
- Create: `frontend/state.mjs`
- Create: `frontend/render.mjs`
- Modify: `frontend/app.mjs`
- Modify: `frontend/index.html`

**Interfaces:**
- Produces: `createInitialState(): object`
- Produces: `acceptContext(state, context): object`
- Produces: `beginPendingTurn(state, request): object`
- Produces: `failPendingTurn(state, error): object`
- Produces: `completePendingTurn(state, response): object`
- Produces: `startNewConversation(state, cryptoLike?: Crypto): object`
- Produces: `setText(element: Element, value: string): Element`

- [ ] **Step 1: Write the failing state tests**

Create `tests/frontend/state.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import {
  acceptContext,
  beginPendingTurn,
  completePendingTurn,
  createInitialState,
  failPendingTurn,
  startNewConversation,
} from "../../frontend/state.mjs";

const cryptoStub = {
  randomUUID() {
    return "123e4567-e89b-12d3-a456-426614174000";
  },
};

test("acceptContext stores local locators and creates a session", () => {
  const state = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );

  assert.equal(state.context.user_id, "wifiknight");
  assert.equal(state.context.project_id, "agent-col");
  assert.equal(state.context.session_id, "session--123e4567-e89b-12d3-a456-426614174000");
  assert.equal(state.mode, "workspace");
});

test("pending turn lifecycle preserves exact retry envelope on failure", () => {
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "hello" }),
  });
  const pending = beginPendingTurn(createInitialState(), request);
  const failed = failPendingTurn(pending, { message: "network failed", status: 0 });

  assert.equal(failed.pendingTurn, null);
  assert.equal(failed.lastFailure.request, request);
  assert.equal(failed.lastFailure.message, "network failed");
});

test("completed turn records response and clears pending failure", () => {
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "hello" }),
  });
  const pending = beginPendingTurn(createInitialState(), request);
  const completed = completePendingTurn(pending, { response: "ok", actions: [] });

  assert.equal(completed.pendingTurn, null);
  assert.equal(completed.lastFailure, null);
  assert.equal(completed.transcript.length, 1);
  assert.deepEqual(completed.transcript[0].response, { response: "ok", actions: [] });
});

test("new conversation keeps user and project but replaces session and clears page state", () => {
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const withTranscript = completePendingTurn(
    beginPendingTurn(accepted, { key: "chat--1", body: { message: "hello" } }),
    { response: "ok" },
  );

  const next = startNewConversation(withTranscript, cryptoStub);

  assert.equal(next.context.user_id, "wifiknight");
  assert.equal(next.context.project_id, "agent-col");
  assert.equal(next.transcript.length, 0);
  assert.equal(next.lastFailure, null);
});
```

- [ ] **Step 2: Run the state tests to verify RED**

Run:

```bash
node --test tests/frontend/state.test.mjs
```

Expected: FAIL with module or exported function not found.

- [ ] **Step 3: Implement `frontend/state.mjs` and `frontend/render.mjs`**

`frontend/state.mjs`:

```javascript
import { generateSessionId } from "./requests.mjs";

export function createInitialState() {
  return {
    mode: "context",
    context: null,
    transcript: [],
    pendingTurn: null,
    lastFailure: null,
  };
}

export function acceptContext(state, context) {
  return {
    ...state,
    mode: "workspace",
    context: {
      user_id: context.user_id,
      project_id: context.project_id,
      session_id: generateSessionId(context.crypto),
    },
  };
}

export function beginPendingTurn(state, request) {
  if (state.pendingTurn !== null) {
    throw new Error("A turn is already pending.");
  }
  return {
    ...state,
    pendingTurn: request,
    lastFailure: null,
  };
}

export function failPendingTurn(state, error) {
  return {
    ...state,
    lastFailure: {
      request: state.pendingTurn,
      message: error.message,
      status: error.status ?? null,
      retryAfterSeconds: error.retryAfterSeconds ?? null,
    },
    pendingTurn: null,
  };
}

export function completePendingTurn(state, response) {
  return {
    ...state,
    transcript: [
      ...state.transcript,
      {
        request: state.pendingTurn,
        response,
      },
    ],
    pendingTurn: null,
    lastFailure: null,
  };
}

export function startNewConversation(state, cryptoLike = globalThis.crypto) {
  if (!state.context) {
    throw new Error("Context is required before starting a new conversation.");
  }
  return {
    ...state,
    context: {
      ...state.context,
      session_id: generateSessionId(cryptoLike),
    },
    transcript: [],
    pendingTurn: null,
    lastFailure: null,
  };
}
```

`frontend/render.mjs`:

```javascript
export function setText(element, value) {
  element.textContent = value;
  return element;
}

export function setHidden(element, hidden) {
  element.hidden = Boolean(hidden);
  return element;
}
```

- [ ] **Step 4: Wire the `New conversation` control minimally**

Modify `frontend/app.mjs` to import `startNewConversation` and reset the empty shell:

```javascript
import { createInitialState, acceptContext, startNewConversation } from "./state.mjs";
import { readContextForm } from "./requests.mjs";
import { setText } from "./render.mjs";

let state = createInitialState();

function showWorkspace() {
  document.querySelector("[data-context-error]").hidden = true;
  document.querySelector("[data-workspace]").hidden = false;
  document.querySelector(".context-gate").hidden = true;
  document.querySelector("[data-new-conversation]").disabled = false;
  document.querySelector("#conversation-workspace").focus();
}

function showContextError(message) {
  const error = document.querySelector("[data-context-error]");
  setText(error, message);
  error.hidden = false;
}

document.querySelector("[data-context-form]").addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    state = acceptContext(state, readContextForm(new FormData(event.currentTarget)));
    showWorkspace();
  } catch (error) {
    showContextError(error.message);
  }
});

document.querySelector("[data-new-conversation]").addEventListener("click", () => {
  if (state.pendingTurn !== null) {
    return;
  }
  state = startNewConversation(state);
  document.querySelector("#conversation-workspace").focus();
});
```

- [ ] **Step 5: Run state and request tests to verify GREEN**

Run:

```bash
node --test tests/frontend/requests.test.mjs tests/frontend/state.test.mjs
```

Expected: PASS.

---

## Final Verification for the Approved Pass

Run the focused checks:

```bash
pytest -q tests/test_workspace_static.py
node --test tests/frontend/requests.test.mjs tests/frontend/api.test.mjs tests/frontend/state.test.mjs
git diff --check
```

Run this optional local server check for manual verification setup:

```bash
source venv/bin/activate
uvicorn main:app --reload
```

Manual verification targets:

1. Open `http://127.0.0.1:8000/` and confirm it still returns `{"status":"online"}`.
2. Open `http://127.0.0.1:8000/workspace` and confirm the workspace shell loads without external network assets.
3. Enter `user_id=wifiknight` and `project_id=agent-col`; expected result is the local workspace shell appearing with the empty conversation state.
4. Try an invalid user ID such as `bad id`; expected result is a visible validation message and no workspace entry.
5. Click `New conversation`; expected result is no visual crash and no backend deletion or persistence claim.
6. Inspect browser console; expected result is no unexpected JavaScript errors and no user content logging.
7. Narrow the viewport to mobile width; expected result is a single-column layout with no clipped controls.

Full suite is not required for this pass because the approved scope adds a static workspace boundary and pure frontend primitives only. It does not change backend chat, routing, persistence, synthesis, expert execution, or memory behavior.

## Scope Notes and Stop Conditions

- Stop if mounting static assets changes `GET /` or any existing API route behavior.
- Stop if FastAPI static mounting requires a new dependency.
- Stop if Node 26 cannot execute `.mjs` tests without adding `package.json`.
- Stop if implementing the shell requires CORS, a remote API origin, external assets, or browser-held credentials.
- Stop if the pass starts implementing full chat turns, Work detail, artifact feedback lifecycle, or memory controls; those belong to later Phase 4A passes.

## Proposed Next Pass After Manual Acceptance

- Goal: Phase 4A.3 Conversation and Authoritative Receipts.
- Proposed approach: add the active transcript, composer, idempotent `/api/chat` submission, exact retry, structured receipt rendering, and new-conversation behavior using the primitives from Phase 4A.2.
- Expected files/surfaces: `frontend/chat-view.mjs`, `frontend/app.mjs`, `frontend/state.mjs`, `frontend/api.mjs`, `frontend/requests.mjs`, CSS additions, Node tests, and a focused manual local chat check.
- Approval required before implementation.
