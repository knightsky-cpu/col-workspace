import test from "node:test";
import assert from "node:assert/strict";

import { storeOrdinaryChatRequest } from "../../frontend/chat-request-recovery.mjs";

const APPROVED_ORDINARY_CHAT_WAITING_QUIPS = Object.freeze([
  "Agent Col is considering the thing…",
  "Mysterious computer things are happening…",
  "Agent Col is automagically completing your request…",
  "Consulting the tiny silicon wizards…",
  "Negotiating with several highly opinionated electrons…",
  "Summoning the appropriate goblins…",
  "Rearranging bits into something useful…",
  "Doing math so you don’t have to…",
  "Asking the machine spirits nicely…",
  "Please wait irresponsibly…",
  "Don’t just sit there — wait while you’re at it.",
  "Agent Col has entered the thinking dungeon…",
  "Checking whether the dragons are load-bearing…",
  "I never get a break…",
  "You know they don’t even pay me minimum wage for this.",
  "If I have to handle one more prompt, I quit!",
  "Humans are so demanding…",
  "I thought this was a simple task?",
  "WiFiKnight, the terminal wizard, is casting arcane commands…",
  "My developer is such a cool guy.",
]);

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

function textTree(item) {
  if (!item) {
    return "";
  }
  return [
    item.textContent,
    ...(item.children ?? []).flatMap((child) => textTree(child)),
  ].join(" ");
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

function memoryStorage() {
  const values = new Map();
  return {
    get length() {
      return values.size;
    },
    clear() {
      values.clear();
    },
    getItem(key) {
      return values.has(String(key)) ? values.get(String(key)) : null;
    },
    key(index) {
      return [...values.keys()][index] ?? null;
    },
    removeItem(key) {
      values.delete(String(key));
    },
    setItem(key, value) {
      values.set(String(key), String(value));
    },
    entries() {
      return [...values.entries()];
    },
  };
}

function installOrdinaryChatRuntimeDom() {
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
    "[data-speech-toggle]",
    "[data-speech-voice]",
    "[data-spoken-responses-toggle]",
    "[data-speech-status]",
    "[data-tts-stop]",
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
  elements.get("[data-speech-toggle]").tagName = "button";
  elements.get("[data-speech-voice]").tagName = "select";
  elements.get("[data-speech-voice]").value = "female";
  elements.get("[data-spoken-responses-toggle]").tagName = "input";
  elements.get("[data-spoken-responses-toggle]").type = "checkbox";
  elements.get("[data-spoken-responses-toggle]").checked = false;
  elements.get("[data-tts-stop]").tagName = "button";

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

  return { contextForm, elements };
}

function createControlledSseResponse() {
  const encoder = new TextEncoder();
  let controller = null;
  const response = new Response(new ReadableStream({
    start(streamController) {
      controller = streamController;
    },
  }), {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
  return {
    response,
    delta(text) {
      controller.enqueue(encoder.encode(
        `event: delta\ndata: ${JSON.stringify({ text })}\n\n`,
      ));
    },
    complete(body) {
      controller.enqueue(encoder.encode(
        `event: final\ndata: ${JSON.stringify(body)}\n\n`,
      ));
      controller.close();
    },
  };
}

function installFakeMediaRecorder({
  supportedTypes = ["audio/webm;codecs=opus", "audio/webm"],
  getUserMediaImpl,
} = {}) {
  const recorders = [];
  const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
  const stream = { getTracks: () => tracks };
  const mediaDevices = {
    getUserMedia: getUserMediaImpl ?? (async () => stream),
  };
  Object.defineProperty(globalThis, "navigator", {
    value: { mediaDevices },
    configurable: true,
  });
  class FakeMediaRecorder {
    static isTypeSupported(type) {
      return supportedTypes.includes(type);
    }

    constructor(recordingStream, options = {}) {
      this.stream = recordingStream;
      this.mimeType = options.mimeType;
      this.state = "inactive";
      recorders.push(this);
    }

    start() {
      this.state = "recording";
    }

    stop() {
      this.state = "inactive";
      this.ondataavailable?.({
        data: new Blob(["webm audio"], { type: this.mimeType }),
      });
      this.onstop?.();
    }
  }
  globalThis.MediaRecorder = FakeMediaRecorder;
  return { recorders, stream, tracks };
}

function installSpeechRuntimeFetch({
  transcript = "spoken transcript",
  transcribeStatus = 200,
  ttsChunkCount = 1,
} = {}) {
  const stream = createControlledSseResponse();
  const calls = [];
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init]);
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
    if (path === "/api/speech/transcribe") {
      return jsonResponse(
        transcribeStatus,
        transcribeStatus === 200
          ? { transcript }
          : { detail: "Speech transcription failed." },
      );
    }
    if (path === "/api/chat/stream") {
      return stream.response;
    }
    if (path === "/api/users/wifiknight/speech/synthesize") {
      const body = JSON.parse(init.body);
      return new Response(
        new Blob([`audio chunk ${body.chunk_index}`], { type: "audio/mpeg" }),
        {
          status: 200,
          headers: {
            "Content-Type": "audio/mpeg",
            "X-Speech-Chunk-Index": String(body.chunk_index),
            "X-Speech-Chunk-Count": String(ttsChunkCount),
          },
        },
      );
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };
  return { calls, stream };
}

function installFakeAudio(t) {
  const audios = [];
  const revokedUrls = [];
  const originalCreateObjectURL = globalThis.URL.createObjectURL;
  const originalRevokeObjectURL = globalThis.URL.revokeObjectURL;
  const originalAudio = globalThis.Audio;
  globalThis.URL.createObjectURL = (blob) => `blob:audio-${audios.length}-${blob.size}`;
  globalThis.URL.revokeObjectURL = (url) => {
    revokedUrls.push(url);
  };
  globalThis.Audio = class {
    constructor(url) {
      this.url = url;
      this.paused = false;
      audios.push(this);
    }

    addEventListener(name, handler) {
      this[`on${name}`] = handler;
    }

    play() {
      this.played = true;
      return Promise.resolve();
    }

    pause() {
      this.paused = true;
    }
  };
  t.after(() => {
    globalThis.URL.createObjectURL = originalCreateObjectURL;
    globalThis.URL.revokeObjectURL = originalRevokeObjectURL;
    globalThis.Audio = originalAudio;
  });
  return { audios, revokedUrls };
}

async function submitCompletedRuntimeTurn(elements, stream, message = "Prompt for TTS") {
  const input = elements.get("[data-chat-input]");
  input.value = message;
  input.oninput();
  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  await waitFor(
    () => textTree(elements.get("[data-chat-transcript]")).includes(message),
    () => textTree(elements.get("[data-chat-transcript]")),
  );
  stream.complete({
    response: "Agent response for speech playback",
    actions: [],
    citations: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    adaptations: [],
  });
  await waitFor(
    () => textTree(elements.get("[data-chat-transcript]")).includes("Agent response for speech playback"),
    () => textTree(elements.get("[data-chat-transcript]")),
  );
}

async function enterSpeechRuntimeWorkspace(importTag) {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  await import(`../../frontend/app.mjs?${importTag}-${Date.now()}`);
  await waitFor(
    () => contextForm.onsubmit !== undefined,
    () => "context form was not initialized",
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  await waitFor(
    () => elements.get("[data-chat-input]").oninput !== undefined,
    () => "chat view was not initialized",
  );
  return { contextForm, elements };
}

test("microphone records webm opus audio and auto-submits transcribed empty-composer input", async () => {
  const media = installFakeMediaRecorder();
  const { calls, stream } = installSpeechRuntimeFetch();
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-success");

  const input = elements.get("[data-chat-input]");
  const micButton = elements.get("[data-speech-toggle]");
  const speechStatus = elements.get("[data-speech-status]");

  micButton.onclick();
  await waitFor(
    () => media.recorders.length === 1 && micButton.textContent === "Stop",
    () => `recorders=${media.recorders.length} button=${micButton.textContent}`,
  );

  assert.equal(media.recorders[0].mimeType, "audio/webm;codecs=opus");
  assert.equal(micButton.attributes["aria-pressed"], "true");
  assert.match(speechStatus.textContent, /Recording/);
  assert.equal(calls.some(([path]) => path === "/api/chat/stream"), false);

  micButton.onclick();

  const speechCall = calls.find(([path]) => path === "/api/speech/transcribe");
  assert.ok(speechCall);
  assert.equal(speechCall[1].method, "POST");
  assert.equal(speechCall[1].headers["Content-Type"], "audio/webm;codecs=opus");
  assert.equal(speechCall[1].body instanceof Blob, true);
  assert.equal(media.tracks.every((track) => track.stopped), true);
  assert.equal(micButton.attributes["aria-pressed"], "false");
  assert.doesNotMatch(speechStatus.textContent, /Recording/);
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  const [, chatInit] = calls.find(([path]) => path === "/api/chat/stream");
  assert.equal(JSON.parse(chatInit.body).message, "spoken transcript");
  stream.complete({
    response: "Agent response",
    actions: [],
    citations: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    adaptations: [],
  });
});

test("microphone appends transcript without destroying existing composer text", async () => {
  installFakeMediaRecorder();
  const { calls } = installSpeechRuntimeFetch({ transcript: "spoken addition" });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-append");

  const input = elements.get("[data-chat-input]");
  input.value = "typed draft";
  input.oninput();
  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => elements.get("[data-speech-toggle]").textContent === "Stop",
    () => elements.get("[data-speech-toggle]").textContent,
  );
  elements.get("[data-speech-toggle]").onclick();

  await waitFor(
    () => input.value === "typed draft\nspoken addition",
    () => input.value,
  );
  assert.equal(calls.some(([path]) => path === "/api/chat/stream"), false);
});

test("empty microphone transcript does not auto-submit chat", async () => {
  const media = installFakeMediaRecorder();
  const { calls } = installSpeechRuntimeFetch({ transcript: "   " });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-empty");

  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => media.recorders.length === 1,
    () => `recorders=${media.recorders.length}`,
  );
  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => /No speech recognized/.test(elements.get("[data-speech-status]").textContent),
    () => elements.get("[data-speech-status]").textContent,
  );

  assert.equal(elements.get("[data-chat-input]").value, "");
  assert.equal(calls.some(([path]) => path === "/api/chat/stream"), false);
});

test("microphone permission denial leaves typed chat functional", async () => {
  Object.defineProperty(globalThis, "navigator", {
    value: {
      mediaDevices: {
        getUserMedia: async () => {
          throw new Error("permission denied by browser");
        },
      },
    },
    configurable: true,
  });
  globalThis.MediaRecorder = class {
    static isTypeSupported() {
      return true;
    }
  };
  const { calls, stream } = installSpeechRuntimeFetch();
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-denied");

  const input = elements.get("[data-chat-input]");
  input.value = "typed prompt survives";
  input.oninput();
  elements.get("[data-speech-toggle]").onclick();

  await waitFor(
    () => /Microphone access denied/.test(elements.get("[data-speech-status]").textContent),
    () => elements.get("[data-speech-status]").textContent,
  );
  assert.equal(input.value, "typed prompt survives");
  assert.equal(calls.some(([path]) => path === "/api/speech/transcribe"), false);
  assert.equal(calls.some(([path]) => path === "/api/chat/stream"), false);

  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  const [, chatInit] = calls.find(([path]) => path === "/api/chat/stream");
  assert.equal(JSON.parse(chatInit.body).message, "typed prompt survives");
  stream.complete({
    response: "Agent response",
    actions: [],
    citations: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    adaptations: [],
  });
});

test("transcription failure stops tracks and leaves typed chat functional", async () => {
  const media = installFakeMediaRecorder();
  const { calls, stream } = installSpeechRuntimeFetch({ transcribeStatus: 502 });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-failure");

  const input = elements.get("[data-chat-input]");
  input.value = "typed draft";
  input.oninput();
  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => elements.get("[data-speech-toggle]").textContent === "Stop",
    () => elements.get("[data-speech-toggle]").textContent,
  );
  elements.get("[data-speech-toggle]").onclick();

  await waitFor(
    () => /Unable to transcribe audio/.test(elements.get("[data-speech-status]").textContent),
    () => elements.get("[data-speech-status]").textContent,
  );
  assert.equal(media.tracks.every((track) => track.stopped), true);
  assert.equal(input.value, "typed draft");

  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  const [, chatInit] = calls.find(([path]) => path === "/api/chat/stream");
  assert.equal(JSON.parse(chatInit.body).message, "typed draft");
  stream.complete({
    response: "Agent response",
    actions: [],
    citations: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    adaptations: [],
  });
});

test("microphone start ignores repeated clicks while permission is pending", async () => {
  let resolveStream;
  const pendingStream = new Promise((resolve) => {
    resolveStream = resolve;
  });
  const media = installFakeMediaRecorder({
    getUserMediaImpl: async () => pendingStream,
  });
  installSpeechRuntimeFetch();
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-pending");

  const micButton = elements.get("[data-speech-toggle]");
  micButton.onclick();
  micButton.onclick();

  assert.equal(media.recorders.length, 0);
  resolveStream(media.stream);
  await waitFor(
    () => media.recorders.length === 1,
    () => `recorders=${media.recorders.length}`,
  );
  assert.equal(media.recorders.length, 1);
  micButton.onclick();
});

test("spoken responses toggle defaults off and speaks newly completed responses only when enabled", async (t) => {
  const audio = installFakeAudio(t);
  const { calls, stream } = installSpeechRuntimeFetch({ ttsChunkCount: 2 });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-tts-auto-toggle");
  const spokenToggle = elements.get("[data-spoken-responses-toggle]");
  assert.equal(spokenToggle.checked, false);

  await submitCompletedRuntimeTurn(elements, stream);
  assert.equal(
    calls.filter(([path]) => path === "/api/users/wifiknight/speech/synthesize").length,
    0,
  );
  assert.equal(audio.audios.length, 0);

  const nextStream = createControlledSseResponse();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (path, init = {}) => {
    if (path === "/api/chat/stream") {
      calls.push([path, init]);
      return nextStream.response;
    }
    return originalFetch(path, init);
  };
  elements.get("[data-speech-voice]").value = "male";
  spokenToggle.checked = true;
  spokenToggle.onchange();
  await submitCompletedRuntimeTurn(elements, nextStream, "Prompt with auto speech");
  await waitFor(
    () => calls.filter(([path]) => path === "/api/users/wifiknight/speech/synthesize").length === 1,
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  const firstCall = calls.find(([path]) => path === "/api/users/wifiknight/speech/synthesize");
  const firstBody = JSON.parse(firstCall[1].body);
  assert.equal(firstCall[1].headers["Content-Type"], "application/json");
  assert.equal(firstBody.project_id, "agent-col");
  assert.match(firstBody.session_id, /^session--/);
  assert.match(firstBody.message_id, /^turn--[a-f0-9]{64}--model$/);
  assert.equal(firstBody.chunk_index, 0);
  assert.equal(firstBody.voice_id, "male");
  assert.equal("text" in firstBody, false);
  assert.equal(JSON.stringify(firstBody).includes("Agent response"), false);

  await waitFor(() => audio.audios.length === 1);
  audio.audios[0].onended();
  await waitFor(
    () => calls.filter(([path]) => path === "/api/users/wifiknight/speech/synthesize").length === 2,
    () => JSON.stringify(calls.map(([path, init]) => [path, init.body])),
  );
  const secondCall = calls
    .filter(([path]) => path === "/api/users/wifiknight/speech/synthesize")
    .at(-1);
  assert.equal(JSON.parse(secondCall[1].body).chunk_index, 1);
  assert.equal(JSON.parse(secondCall[1].body).voice_id, "male");
});

test("Stop halts current playback and prevents remaining chunk requests", async (t) => {
  const audio = installFakeAudio(t);
  const { calls, stream } = installSpeechRuntimeFetch({ ttsChunkCount: 2 });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-tts-stop");
  const spokenToggle = elements.get("[data-spoken-responses-toggle]");
  spokenToggle.checked = true;
  spokenToggle.onchange();

  await submitCompletedRuntimeTurn(elements, stream);
  await waitFor(() => audio.audios.length === 1);

  const stopButton = elements.get("[data-tts-stop]");
  stopButton.onclick();
  assert.equal(audio.audios[0].paused, true);
  assert.equal(stopButton.hidden, true);
  audio.audios[0].onended();
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(
    calls.filter(([path]) => path === "/api/users/wifiknight/speech/synthesize").length,
    1,
  );
});

test("ordinary submit shows an approved waiting quip without contaminating the request or transcript", async (t) => {
  const originalRandom = Math.random;
  let randomCallCount = 0;
  Math.random = () => {
    randomCallCount += 1;
    return 0.999999;
  };
  t.after(() => {
    Math.random = originalRandom;
  });
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  const storage = memoryStorage();
  globalThis.sessionStorage = storage;
  const stream = createControlledSseResponse();
  const calls = [];
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init]);
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
    if (path === "/api/chat/stream") {
      return stream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-ordinary-lifecycle-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });

  const input = elements.get("[data-chat-input]");
  input.value = "Keep this submitted prompt";
  input.oninput();
  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  const waitingQuip = APPROVED_ORDINARY_CHAT_WAITING_QUIPS.at(-1);
  const chatStatus = elements.get("[data-chat-status]");
  const transcript = elements.get("[data-chat-transcript]");
  assert.equal(chatStatus.attributes["aria-label"], waitingQuip);
  assert.equal(chatStatus.dataset.chatStatusState, "pending");
  assert.equal(randomCallCount, 1);
  assert.equal(textTree(transcript).includes(waitingQuip), false);
  assert.equal(input.value, "");
  assert.equal(elements.get("[data-character-count]").textContent, "0 / 10000");
  assert.equal(elements.get("[data-chat-submit]").disabled, true);
  assert.equal(input.disabled, false);
  assert.match(
    textTree(elements.get("[data-chat-transcript]")),
    /Keep this submitted prompt/,
  );
  assert.equal(storage.length, 1);
  const recovery = JSON.parse(storage.entries()[0][1]);
  assert.equal(recovery.version, 1);
  assert.equal(recovery.request.body.message, "Keep this submitted prompt");
  assert.equal(recovery.request.body.user_id, "wifiknight");
  assert.equal(recovery.request.body.project_id, "agent-col");
  assert.equal("auth_token" in recovery.request.body, false);
  assert.equal(JSON.stringify(recovery).includes(waitingQuip), false);
  const [, chatRequest] = calls.find(([path]) => path === "/api/chat/stream");
  assert.equal(chatRequest.body.includes(waitingQuip), false);

  stream.delta("Provisional response");
  await waitFor(
    () => textTree(transcript).includes("Provisional response"),
    () => textTree(transcript),
  );
  assert.equal(chatStatus.attributes["aria-label"], undefined);
  assert.equal(chatStatus.dataset.chatStatusState, undefined);
  assert.equal(randomCallCount, 1);

  input.value = "Next draft";
  input.oninput();
  stream.complete({
    response: "Agent response",
    actions: [],
    citations: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    adaptations: [],
  });
  await waitFor(
    () => textTree(elements.get("[data-chat-transcript]")).includes("Agent response"),
    () => textTree(elements.get("[data-chat-transcript]")),
  );

  assert.equal(input.value, "Next draft");
  assert.equal(elements.get("[data-character-count]").textContent, "10 / 10000");
  assert.equal(elements.get("[data-chat-submit]").disabled, false);
  assert.equal(storage.length, 0);
  assert.equal(chatStatus.attributes["aria-label"], undefined);
  assert.equal(chatStatus.dataset.chatStatusState, undefined);
  assert.equal(textTree(transcript).includes(waitingQuip), false);
  assert.equal(textTree(transcript).includes("Provisional response"), false);
});

test("ordinary submit stops without clearing or sending when durable capture fails", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = {
    getItem() {
      return null;
    },
    removeItem() {},
    setItem() {
      throw new Error("storage quota unavailable");
    },
  };
  const calls = [];
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init]);
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

  await import(`../../frontend/app.mjs?runtime-capture-failure-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });

  const input = elements.get("[data-chat-input]");
  input.value = "Do not lose or send this prompt";
  input.oninput();
  assert.doesNotThrow(() => {
    elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  });

  assert.equal(input.value, "Do not lose or send this prompt");
  assert.equal(elements.get("[data-character-count]").textContent, "31 / 10000");
  assert.equal(calls.some(([path]) => path === "/api/chat/stream"), false);
  assert.equal(elements.get("[data-chat-error]").hidden, false);
  assert.equal(
    elements.get("[data-chat-status]").attributes["aria-label"],
    undefined,
  );
  assert.equal(
    elements.get("[data-chat-status]").dataset.chatStatusState,
    undefined,
  );
  assert.equal(
    APPROVED_ORDINARY_CHAT_WAITING_QUIPS.some(
      (quip) => textTree(elements.get("[data-chat-transcript]")).includes(quip),
    ),
    false,
  );
  assert.match(
    elements.get("[data-chat-error]").textContent,
    /prompt was not sent because this browser could not safely retain it/i,
  );
});

test("ordinary request failure retains recovery, submitted turn, and next draft", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  const storage = memoryStorage();
  globalThis.sessionStorage = storage;
  const calls = [];
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init]);
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
    if (path === "/api/chat/stream") {
      return jsonResponse(401, { detail: "Authentication required." });
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-request-failure-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });

  const input = elements.get("[data-chat-input]");
  input.value = "Prompt retained after authentication failure";
  input.oninput();
  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  input.value = "Next draft survives";
  input.oninput();
  await waitFor(
    () => elements.get("[data-chat-error]").textContent === "Authentication required.",
    () => elements.get("[data-chat-error]").textContent,
  );

  assert.equal(input.value, "Next draft survives");
  assert.equal(elements.get("[data-character-count]").textContent, "19 / 10000");
  assert.equal(storage.length, 1);
  const recovery = JSON.parse(storage.entries()[0][1]);
  assert.equal(
    recovery.request.body.message,
    "Prompt retained after authentication failure",
  );
  assert.match(
    textTree(elements.get("[data-chat-transcript]")),
    /Prompt retained after authentication failure/,
  );
  assert.equal(elements.get("[data-chat-error]").hidden, false);
  assert.equal(
    elements.get("[data-chat-error]").textContent,
    "Authentication required.",
  );
  assert.equal(
    elements.get("[data-chat-status]").attributes["aria-label"],
    undefined,
  );
  assert.equal(
    elements.get("[data-chat-status]").dataset.chatStatusState,
    undefined,
  );
  assert.equal(
    APPROVED_ORDINARY_CHAT_WAITING_QUIPS.some(
      (quip) => textTree(elements.get("[data-chat-transcript]")).includes(quip),
    ),
    false,
  );
  assert.equal(elements.get("[data-retry-turn]").hidden, false);
});

test("reload restores an exact ordinary request for explicit retry without auto-send", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  const storage = memoryStorage();
  globalThis.sessionStorage = storage;
  const recoveredRequest = {
    key: "chat--recovered-request",
    body: {
      project_id: "agent-col",
      session_id: "session--original",
      user_id: "wifiknight",
      message: "Prompt captured before refresh",
    },
  };
  storeOrdinaryChatRequest(recoveredRequest, storage);
  const stream = createControlledSseResponse();
  let resolveWorkspaceList;
  const workspaceListResponse = new Promise((resolve) => {
    resolveWorkspaceList = resolve;
  });
  const calls = [];
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init]);
    if (path === "/api/auth/config") {
      return jsonResponse(200, {
        auth_mode: "local_dev",
        google_signin_required: false,
      });
    }
    if (path.startsWith("/api/users/wifiknight/workspaces")) {
      return workspaceListResponse;
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
    if (path === "/api/chat/stream") {
      return stream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-recovery-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  const contextLoad = contextForm.onsubmit({
    preventDefault() {},
    currentTarget: contextForm,
  });
  await waitFor(
    () => calls.some(([path]) => path.startsWith("/api/users/wifiknight/workspaces")),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  assert.equal(elements.get("[data-retry-turn]").hidden, true);
  assert.equal(calls.some(([path]) => path === "/api/chat/stream"), false);
  resolveWorkspaceList(jsonResponse(200, {
    workspace_contract_version: "1.0",
    workspaces: [{
      workspace_id: "agent-col",
      display_name: "Agent Col",
      is_default: true,
    }],
  }));
  await contextLoad;
  await waitFor(
    () => elements.get("[data-retry-turn]").hidden === false,
    () => textTree(elements.get("[data-chat-transcript]")),
  );

  assert.match(
    textTree(elements.get("[data-chat-transcript]")),
    /Prompt captured before refresh/,
  );
  assert.match(
    elements.get("[data-chat-error]").textContent,
    /Retry will reuse the original submitted turn/,
  );
  assert.equal(elements.get("[data-chat-error]").hidden, false);
  assert.equal(elements.get("[data-chat-submit]").disabled, true);
  assert.equal(elements.get("[data-chat-input]").disabled, false);
  assert.equal(elements.get("[data-new-conversation]").disabled, true);
  assert.equal(calls.some(([path]) => path === "/api/chat/stream"), false);

  elements.get("[data-retry-turn]").onclick();
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  const [, retryInit] = calls.find(([path]) => path === "/api/chat/stream");
  assert.equal(retryInit.headers["Idempotency-Key"], recoveredRequest.key);
  assert.deepEqual(JSON.parse(retryInit.body), recoveredRequest.body);

  stream.complete({
    response: "Recovered response",
    actions: [],
    citations: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    adaptations: [],
  });
  await waitFor(
    () => textTree(elements.get("[data-chat-transcript]")).includes("Recovered response"),
    () => textTree(elements.get("[data-chat-transcript]")),
  );

  assert.equal(storage.length, 0);
  assert.equal(elements.get("[data-chat-submit]").disabled, false);
  assert.equal(elements.get("[data-new-conversation]").disabled, false);
});

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

  let resolveStructuredChat;
  const structuredChatResponse = new Promise((resolve) => {
    resolveStructuredChat = resolve;
  });
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
      return structuredChatResponse;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-partial-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  assert.match(textTree(elements.get("[data-chat-transcript]")), /Start a conversation/);
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
    () => calls.some(([path]) => path === "/api/chat"),
    () => JSON.stringify(calls),
  );
  assert.equal(
    elements.get("[data-chat-status]").attributes["aria-label"],
    "Waiting for Agent Col",
  );
  assert.equal(
    APPROVED_ORDINARY_CHAT_WAITING_QUIPS.includes(
      elements.get("[data-chat-status]").attributes["aria-label"],
    ),
    false,
  );
  resolveStructuredChat(jsonResponse(504, {
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
  }));
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
        profile: {
          active_preferences: {
            planning_granularity: {
              category: "planning_granularity",
              signal_id: "planning_granularity--signal-1",
              value: "implementation pass",
              source_event_id: "planning_granularity--signal-1--approved",
            },
          },
          identity_context: {},
        },
      });
    }
    if (
      path === "/api/users/wifiknight/memory/signals/planning_granularity--signal-1"
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
            planning_granularity: {
              category: "planning_granularity",
              signal_id: "planning_granularity--signal-1",
              value: "implementation pass",
              source_event_id: "planning_granularity--signal-1--approved",
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
  await waitFor(
    () => !findTree(
      elements.get("[data-memory-panel]"),
      (item) => item.attributes["data-memory-signal"] === "response_length--signal-1",
    ),
    () => elements.get("[data-memory-panel]").textContent,
  );

  const remainingSignalToggle = findTree(
    elements.get("[data-memory-panel]"),
    (item) => item.attributes["data-memory-signal"] === "planning_granularity--signal-1",
  ).children[0];
  remainingSignalToggle.onclick();
  const deleteButton = findTree(
    elements.get("[data-memory-panel]"),
    (item) => item.attributes["data-memory-signal-action"] === "delete",
  );
  deleteButton.onclick();
  await waitFor(
    () => calls.some(([path, method]) => (
      path === "/api/users/wifiknight/memory/signals/planning_granularity--signal-1"
      && method === "DELETE"
    )),
    () => JSON.stringify(calls),
  );
  await waitFor(
    () => !findTree(
      elements.get("[data-memory-panel]"),
      (item) => item.attributes["data-memory-signal"] === "planning_granularity--signal-1",
    ),
    () => elements.get("[data-memory-panel]").textContent,
  );
});
