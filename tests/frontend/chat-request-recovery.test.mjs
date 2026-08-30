import test from "node:test";
import assert from "node:assert/strict";

import {
  clearOrdinaryChatRequest,
  loadOrdinaryChatRequest,
  storeOrdinaryChatRequest,
} from "../../frontend/chat-request-recovery.mjs";

function memoryStorage() {
  const values = new Map();
  return {
    get length() {
      return values.size;
    },
    getItem(key) {
      return values.has(String(key)) ? values.get(String(key)) : null;
    },
    removeItem(key) {
      values.delete(String(key));
    },
    setItem(key, value) {
      values.set(String(key), String(value));
    },
  };
}

function ordinaryRequest(overrides = {}) {
  return {
    key: "chat--request-1",
    body: {
      project_id: "agent-col",
      session_id: "session--original",
      user_id: "wifiknight",
      message: "Retain this exact prompt",
    },
    ...overrides,
  };
}

test("stored ordinary request loads as an independent immutable exact envelope", () => {
  const storage = memoryStorage();
  const request = ordinaryRequest();
  storeOrdinaryChatRequest(request, storage);

  const recovered = loadOrdinaryChatRequest(
    { user_id: "wifiknight", project_id: "agent-col" },
    storage,
  );

  assert.deepEqual(recovered, request);
  assert.notEqual(recovered, request);
  assert.notEqual(recovered.body, request.body);
  assert.equal(Object.isFrozen(recovered), true);
  assert.equal(Object.isFrozen(recovered.body), true);
});

test("ordinary recovery rejects another context, malformed data, and structured turns", () => {
  const storage = memoryStorage();
  storeOrdinaryChatRequest(ordinaryRequest(), storage);
  assert.equal(
    loadOrdinaryChatRequest(
      { user_id: "another-user", project_id: "agent-col" },
      storage,
    ),
    null,
  );

  storeOrdinaryChatRequest(ordinaryRequest({
    body: {
      ...ordinaryRequest().body,
      memory_decision: { proposal_id: "proposal-1", decision: "approve" },
    },
  }), storage);
  assert.equal(
    loadOrdinaryChatRequest(
      { user_id: "wifiknight", project_id: "agent-col" },
      storage,
    ),
    null,
  );
});

test("completion only clears a matching exact recovery envelope", () => {
  const storage = memoryStorage();
  const current = ordinaryRequest({ key: "chat--current" });
  storeOrdinaryChatRequest(current, storage);

  clearOrdinaryChatRequest(ordinaryRequest({ key: "chat--stale" }), storage);
  assert.equal(storage.length, 1);

  clearOrdinaryChatRequest(current, storage);
  assert.equal(storage.length, 0);
});

test("capture failure is reported synchronously", () => {
  const storage = {
    setItem() {
      throw new Error("quota unavailable");
    },
  };

  assert.throws(
    () => storeOrdinaryChatRequest(ordinaryRequest(), storage),
    /quota unavailable/,
  );
});

test("unavailable browser storage fails closed for load and completion cleanup", () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    get() {
      throw new Error("storage access denied");
    },
  });
  try {
    assert.equal(
      loadOrdinaryChatRequest({ user_id: "wifiknight", project_id: "agent-col" }),
      null,
    );
    assert.doesNotThrow(() => clearOrdinaryChatRequest(ordinaryRequest()));
    assert.throws(
      () => storeOrdinaryChatRequest(ordinaryRequest()),
      /storage access denied/,
    );
  } finally {
    if (descriptor) {
      Object.defineProperty(globalThis, "sessionStorage", descriptor);
    } else {
      delete globalThis.sessionStorage;
    }
  }
});
