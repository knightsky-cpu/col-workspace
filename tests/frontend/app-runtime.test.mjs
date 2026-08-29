import test from "node:test";
import assert from "node:assert/strict";

function node(tagName = "div") {
  return {
    tagName,
    children: [],
    attributes: {},
    dataset: {},
    style: { setProperty() {} },
    value: "",
    name: "",
    type: "",
    disabled: false,
    hidden: false,
    readOnly: false,
    textContent: "",
    scrollHeight: 0,
    scrollTop: 0,
    append(...items) {
      this.children.push(...items);
    },
    replaceChildren(...items) {
      this.children = items;
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
    addEventListener(name, handler) {
      this[`on${name}`] = handler;
    },
    focus() {},
    matches(selector) {
      return selector === "[data-section-toggle]"
        && this.attributes["data-section-toggle"] !== undefined;
    },
    classList: {
      values: [],
      add(...values) {
        this.values.push(...values);
      },
      toggle(value, force) {
        const exists = this.values.includes(value);
        if (force && !exists) {
          this.values.push(value);
        }
        if (!force && exists) {
          this.values = this.values.filter((item) => item !== value);
        }
      },
    },
  };
}

function findTree(item, predicate) {
  if (!item) {
    return null;
  }
  if (predicate(item)) {
    return item;
  }
  for (const child of item.children ?? []) {
    const found = findTree(child, predicate);
    if (found) {
      return found;
    }
  }
  return null;
}

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function waitFor(predicate, describe = () => "") {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const poll = () => {
      if (predicate()) {
        resolve();
        return;
      }
      attempts += 1;
      if (attempts > 20) {
        reject(new Error(`Timed out waiting for app runtime condition. ${describe()}`));
        return;
      }
      setTimeout(poll, 0);
    };
    poll();
  });
}

test("JSON partial failure from submit refreshes authoritative memory and notes", async () => {
  const elements = new Map();
  const contextForm = node("form");
  const projectInput = node("input");
  projectInput.name = "project_id";
  projectInput.value = "agent-col";
  const userInput = node("input");
  userInput.name = "user_id";
  userInput.value = "wifiknight";
  const contextSubmit = node("button");
  contextSubmit.type = "submit";
  contextForm.fields = { project_id: projectInput, user_id: userInput };
  elements.set("[data-context-form]", contextForm);
  elements.set('[name="project_id"]', projectInput);
  elements.set('[name="user_id"]', userInput);
  elements.set('[data-context-form] button[type="submit"]', contextSubmit);

  for (const selector of [
    "[data-auth-error]",
    "[data-context-error]",
    "[data-workspace]",
    ".context-gate",
    "[data-new-conversation]",
    "[data-artifacts-expand]",
    "[data-left-refresh]",
    "#conversation-workspace",
    "[data-work-error]",
    "[data-memory-error]",
    "[data-workspace-error]",
    "[data-notes-error]",
    "[data-chat-status]",
    "[data-auth-mode-label]",
    "[data-google-account-status]",
    "[data-google-signin]",
    "[data-google-button]",
    "[data-workspace-indicator]",
    "[data-chat-error]",
    "[data-chat-form]",
    "[data-chat-input]",
    "[data-chat-submit]",
    "[data-retry-turn]",
    "[data-chat-transcript]",
    "[data-character-count]",
    "[data-memory-clarification-choices]",
    "[data-continuity-choices]",
    "[data-workspace-list]",
    "[data-work-list]",
    "[data-work-detail]",
    "[data-memory-panel]",
    "[data-notes-panel]",
    "[data-chats-list]",
  ]) {
    if (!elements.has(selector)) {
      elements.set(selector, node());
    }
  }
  elements.get("[data-chat-form]").tagName = "form";
  elements.get("[data-chat-input]").value = "";

  const drawerButtons = [node("button"), node("button")];
  drawerButtons[0].setAttribute("data-drawer-toggle", "left");
  drawerButtons[1].setAttribute("data-drawer-toggle", "right");
  const sectionButtons = ["workspace", "work", "notes", "memory", "chats"]
    .map((section) => {
      const button = node("button");
      const content = node("div");
      button.setAttribute("data-section-toggle", section);
      content.setAttribute("data-section-content", section);
      elements.set(`[data-section-toggle="${section}"]`, button);
      elements.set(`[data-section-content="${section}"]`, content);
      return button;
    });

  globalThis.document = {
    head: node("head"),
    createElement(tagName) {
      return node(tagName);
    },
    createTextNode(text) {
      const textNode = node("#text");
      textNode.textContent = String(text);
      return textNode;
    },
    querySelector(selector) {
      return elements.get(selector) ?? null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-context-form] input") {
        return [projectInput, userInput];
      }
      if (selector === "[data-drawer-toggle]") {
        return drawerButtons;
      }
      if (selector === '[data-drawer-toggle="left"]') {
        return [drawerButtons[0]];
      }
      if (selector === '[data-drawer-toggle="right"]') {
        return [drawerButtons[1]];
      }
      if (selector === "[data-section-toggle]") {
        return sectionButtons;
      }
      return [];
    },
  };

  class FakeFormData {
    constructor(form) {
      this.form = form;
    }
    get(name) {
      return this.form.fields?.[name]?.value ?? "";
    }
    has(name) {
      return this.form.fields?.[name] !== undefined;
    }
  }
  globalThis.FormData = FakeFormData;

  const calls = [];
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init?.method ?? "GET"]);
    if (path === "/api/auth/config") {
      return jsonResponse(200, {
        auth_mode: "local_dev",
        google_signin_required: false,
      });
    }
    if (path.startsWith("/api/users/wifiknight/workspaces")) {
      return jsonResponse(200, {
        workspace_contract_version: "1.0",
        workspaces: [{
          workspace_id: "agent-col",
          display_name: "Agent Col",
          is_default: true,
        }],
      });
    }
    if (path.startsWith("/api/projects/agent-col/artifacts")) {
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        artifacts: [],
        next_before: null,
      });
    }
    if (path.startsWith("/api/users/wifiknight/memory")) {
      return jsonResponse(200, {
        memory_contract_version: "1.0",
        profile: null,
        unresolved_proposals: [{
          proposal_id: "response_length--proposal-1",
          category: "response_length",
          proposed_value: "concise",
          status: "pending",
        }],
        events: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/notes")) {
      return jsonResponse(200, {
        note_contract_version: "1.0",
        notes: [],
        pending_proposals: [],
        next_cursor: null,
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/chat-sessions")) {
      return jsonResponse(200, {
        chat_contract_version: "1.0",
        sessions: [],
      });
    }
    if (path === "/api/chat") {
      return jsonResponse(504, {
        detail: "Agent_Col response timed out after a completed action.",
        response: "",
        actions: [{
          action_name: "approve_memory_signal",
          status: "completed",
        }],
        memory_proposals: [],
        collaborative_note_events: [{
          event_type: "approved",
          title: "API version",
        }],
      });
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-partial-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  await waitFor(
    () => findTree(
      elements.get("[data-memory-panel]"),
      (item) => item.attributes["data-disclosure-toggle"] === "memory-proposal",
    ),
    () => JSON.stringify({
      calls,
      contextError: elements.get("[data-context-error]").textContent,
    }),
  );

  const proposalToggle = findTree(
    elements.get("[data-memory-panel]"),
    (item) => item.attributes["data-disclosure-toggle"] === "memory-proposal",
  );
  proposalToggle.onclick();
  const approve = findTree(
    elements.get("[data-memory-panel]"),
    (item) => item.attributes["data-memory-decision"] === "approve",
  );
  approve.onclick();
  await waitFor(
    () => (
      calls.filter(([path]) => path.startsWith("/api/users/wifiknight/memory")).length >= 2
      && calls.filter(([path]) => path.startsWith("/api/users/wifiknight/projects/agent-col/notes")).length >= 2
    ),
    () => JSON.stringify(calls),
  );

  assert.equal(calls.some(([path]) => path === "/api/chat"), true);
  assert.equal(
    elements.get("[data-chat-error]").textContent,
    "Agent Col timed out after recording a completed action. Retry will reuse completed receipts.",
  );
});

test("memory sub-card revoke and delete do not depend on chat submit readiness", async () => {
  const elements = new Map();
  const contextForm = node("form");
  const projectInput = node("input");
  projectInput.name = "project_id";
  projectInput.value = "agent-col";
  const userInput = node("input");
  userInput.name = "user_id";
  userInput.value = "wifiknight";
  const contextSubmit = node("button");
  contextSubmit.type = "submit";
  contextForm.fields = { project_id: projectInput, user_id: userInput };
  elements.set("[data-context-form]", contextForm);
  elements.set('[name="project_id"]', projectInput);
  elements.set('[name="user_id"]', userInput);
  elements.set('[data-context-form] button[type="submit"]', contextSubmit);

  for (const selector of [
    "[data-auth-error]",
    "[data-context-error]",
    "[data-workspace]",
    ".context-gate",
    "[data-new-conversation]",
    "[data-artifacts-expand]",
    "[data-left-refresh]",
    "#conversation-workspace",
    "[data-work-error]",
    "[data-memory-error]",
    "[data-workspace-error]",
    "[data-notes-error]",
    "[data-chat-status]",
    "[data-auth-mode-label]",
    "[data-google-account-status]",
    "[data-google-signin]",
    "[data-google-button]",
    "[data-workspace-indicator]",
    "[data-chat-error]",
    "[data-chat-form]",
    "[data-chat-input]",
    "[data-chat-submit]",
    "[data-retry-turn]",
    "[data-chat-transcript]",
    "[data-character-count]",
    "[data-memory-clarification-choices]",
    "[data-continuity-choices]",
    "[data-workspace-list]",
    "[data-work-list]",
    "[data-work-detail]",
    "[data-memory-panel]",
    "[data-notes-panel]",
    "[data-chats-list]",
  ]) {
    if (!elements.has(selector)) {
      elements.set(selector, node());
    }
  }
  elements.get("[data-chat-form]").tagName = "form";

  const drawerButtons = [node("button"), node("button")];
  drawerButtons[0].setAttribute("data-drawer-toggle", "left");
  drawerButtons[1].setAttribute("data-drawer-toggle", "right");
  const sectionButtons = ["workspace", "work", "notes", "memory", "chats"]
    .map((section) => {
      const button = node("button");
      const content = node("div");
      button.setAttribute("data-section-toggle", section);
      content.setAttribute("data-section-content", section);
      elements.set(`[data-section-toggle="${section}"]`, button);
      elements.set(`[data-section-content="${section}"]`, content);
      return button;
    });

  globalThis.document = {
    head: node("head"),
    createElement(tagName) {
      return node(tagName);
    },
    createTextNode(text) {
      const textNode = node("#text");
      textNode.textContent = String(text);
      return textNode;
    },
    querySelector(selector) {
      return elements.get(selector) ?? null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-context-form] input") {
        return [projectInput, userInput];
      }
      if (selector === "[data-drawer-toggle]") {
        return drawerButtons;
      }
      if (selector === '[data-drawer-toggle="left"]') {
        return [drawerButtons[0]];
      }
      if (selector === '[data-drawer-toggle="right"]') {
        return [drawerButtons[1]];
      }
      if (selector === "[data-section-toggle]") {
        return sectionButtons;
      }
      return [];
    },
  };

  class FakeFormData {
    constructor(form) {
      this.form = form;
    }
    get(name) {
      return this.form.fields?.[name]?.value ?? "";
    }
    has(name) {
      return this.form.fields?.[name] !== undefined;
    }
  }
  globalThis.FormData = FakeFormData;
  globalThis.confirm = () => true;

  const calls = [];
  globalThis.fetch = async (path, init = {}) => {
    const method = init?.method ?? "GET";
    calls.push([path, method]);
    if (path === "/api/auth/config") {
      return jsonResponse(200, {
        auth_mode: "local_dev",
        google_signin_required: false,
      });
    }
    if (
      path === "/api/users/wifiknight/memory/signals/response_length--signal-1/revoke"
      && method === "POST"
    ) {
      return jsonResponse(200, {
        action: { action_name: "revoke_memory_signal", status: "completed" },
        profile: { active_preferences: {} },
      });
    }
    if (
      path === "/api/users/wifiknight/memory/signals/response_length--signal-1"
      && method === "DELETE"
    ) {
      return new Response(null, { status: 204 });
    }
    if (path.startsWith("/api/users/wifiknight/workspaces")) {
      return jsonResponse(200, {
        workspace_contract_version: "1.0",
        workspaces: [],
      });
    }
    if (path.startsWith("/api/projects/agent-col/artifacts")) {
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        artifacts: [],
        next_before: null,
      });
    }
    if (path.startsWith("/api/users/wifiknight/memory")) {
      return jsonResponse(200, {
        memory_contract_version: "1.0",
        profile: {
          active_preferences: {
            response_length: {
              category: "response_length",
              signal_id: "response_length--signal-1",
              value: "concise",
              source_event_id: "response_length--signal-1--approved",
            },
          },
          identity_context: {},
        },
        unresolved_proposals: [],
        events: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/notes")) {
      return jsonResponse(200, {
        note_contract_version: "1.0",
        notes: [],
        pending_proposals: [],
        next_cursor: null,
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/chat-sessions")) {
      return jsonResponse(200, {
        chat_contract_version: "1.0",
        sessions: [],
      });
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-memory-actions-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  await waitFor(
    () => findTree(
      elements.get("[data-memory-panel]"),
      (item) => item.attributes["data-disclosure-toggle"] === "memory-signal",
    ),
    () => JSON.stringify(calls),
  );

  const signalToggle = findTree(
    elements.get("[data-memory-panel]"),
    (item) => item.attributes["data-disclosure-toggle"] === "memory-signal",
  );
  signalToggle.onclick();
  const revoke = findTree(
    elements.get("[data-memory-panel]"),
    (item) => item.attributes["data-memory-signal-action"] === "revoke",
  );
  revoke.onclick();
  await waitFor(
    () => calls.some(([path, method]) => (
      path === "/api/users/wifiknight/memory/signals/response_length--signal-1/revoke"
      && method === "POST"
    )),
    () => JSON.stringify(calls),
  );

  const deleteButton = findTree(
    elements.get("[data-memory-panel]"),
    (item) => item.attributes["data-memory-signal-action"] === "delete",
  );
  deleteButton.onclick();
  await waitFor(
    () => calls.some(([path, method]) => (
      path === "/api/users/wifiknight/memory/signals/response_length--signal-1"
      && method === "DELETE"
    )),
    () => JSON.stringify(calls),
  );
});
