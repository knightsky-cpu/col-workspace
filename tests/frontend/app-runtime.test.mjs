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
    replaceChildrenCount: 0,
    append(...items) {
      this.children.push(...items);
    },
    replaceChildren(...items) {
      this.replaceChildrenCount += 1;
      this.children = items;
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
    addEventListener(name, handler) {
      this[`on${name}`] = (...args) => {
        const results = [];
        for (const listener of this[`_${name}Listeners`] ?? []) {
          results.push(listener.apply(this, args));
        }
        return results.length === 1 ? results[0] : Promise.all(results);
      };
      this[`_${name}Listeners`] = [
        ...(this[`_${name}Listeners`] ?? []),
        handler,
      ];
    },
    removeEventListener(name, handler) {
      this[`_${name}Listeners`] = (this[`_${name}Listeners`] ?? [])
        .filter((listener) => listener !== handler);
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

function blueprintDetailResponse(metadata, summary = "Loaded blueprint detail.") {
  const label = metadata.reference.display_label ?? "Blueprint";
  return {
    artifact_contract_version: "1.0",
    metadata,
    blueprint: {
      synthesized_conceptual_model: {
        project_name: label,
        core_value_proposition: summary,
        in_scope: [],
        out_of_scope: [],
        assumptions: [],
      },
      architectural_decisions: [],
      socratic_clarifying_questions: [],
      step_by_step_execution_roadmap: [],
      diagnostic_warnings: [],
    },
    feedback_targets: [],
  };
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
    "[data-agents-panel]",
    "[data-agents-summary]",
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
  const sectionButtons = ["workspace", "work", "notes", "memory", "chats", "agents"]
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
    event(name, body) {
      controller.enqueue(encoder.encode(
        `event: ${name}\ndata: ${JSON.stringify(body)}\n\n`,
      ));
    },
    complete(body) {
      controller.enqueue(encoder.encode(
        `event: final\ndata: ${JSON.stringify(body)}\n\n`,
      ));
      controller.close();
    },
    close() {
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
      this.stopCalls = 0;
      recorders.push(this);
    }

    start() {
      this.state = "recording";
    }

    stop() {
      this.stopCalls += 1;
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

function installFakeSilenceDetection(t) {
  const frames = [];
  const contexts = [];
  const analysers = [];
  const samples = [];
  const originalAudioContext = globalThis.AudioContext;
  const originalWebkitAudioContext = globalThis.webkitAudioContext;
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;

  class FakeAnalyser {
    constructor() {
      this.fftSize = 2048;
      this.disconnected = false;
      analysers.push(this);
    }

    getByteTimeDomainData(buffer) {
      const value = samples.length > 0 ? samples.shift() : 128;
      buffer.fill(value);
    }

    disconnect() {
      this.disconnected = true;
    }
  }

  class FakeSource {
    constructor() {
      this.disconnected = false;
    }

    connect(analyser) {
      this.analyser = analyser;
    }

    disconnect() {
      this.disconnected = true;
    }
  }

  class FakeAudioContext {
    constructor() {
      this.closed = false;
      this.sources = [];
      contexts.push(this);
    }

    createMediaStreamSource(stream) {
      const source = new FakeSource();
      source.stream = stream;
      this.sources.push(source);
      return source;
    }

    createAnalyser() {
      return new FakeAnalyser();
    }

    close() {
      this.closed = true;
      return Promise.resolve();
    }
  }

  globalThis.AudioContext = FakeAudioContext;
  globalThis.webkitAudioContext = undefined;
  globalThis.requestAnimationFrame = (callback) => {
    const id = frames.length + 1;
    frames.push({ id, callback, cancelled: false });
    return id;
  };
  globalThis.cancelAnimationFrame = (id) => {
    const frame = frames.find((item) => item.id === id);
    if (frame) {
      frame.cancelled = true;
    }
  };

  t.after(() => {
    globalThis.AudioContext = originalAudioContext;
    globalThis.webkitAudioContext = originalWebkitAudioContext;
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
    globalThis.cancelAnimationFrame = originalCancelAnimationFrame;
  });

  return {
    contexts,
    analysers,
    pushSample(value) {
      samples.push(value);
    },
    tick(time) {
      const frame = frames.shift();
      if (frame && !frame.cancelled) {
        frame.callback(time);
      }
    },
    pendingFrameCount() {
      return frames.filter((frame) => !frame.cancelled).length;
    },
  };
}

function installSpeechRuntimeFetch({
  transcript = "spoken transcript",
  transcribeStatus = 200,
  ttsChunkCount = 1,
  ttsStatusByChunk = {},
  deferredTtsChunks = new Map(),
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
      if (deferredTtsChunks.has(body.chunk_index)) {
        await deferredTtsChunks.get(body.chunk_index).promise;
      }
      const status = ttsStatusByChunk[body.chunk_index] ?? 200;
      return new Response(
        status === 200
          ? new Blob([`audio chunk ${body.chunk_index}`], { type: "audio/mpeg" })
          : JSON.stringify({ detail: "Speech synthesis failed." }),
        {
          status,
          headers: {
            "Content-Type": status === 200 ? "audio/mpeg" : "application/json",
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
  const objectUrls = [];
  const revokedUrls = [];
  const originalCreateObjectURL = globalThis.URL.createObjectURL;
  const originalRevokeObjectURL = globalThis.URL.revokeObjectURL;
  const originalAudio = globalThis.Audio;
  globalThis.URL.createObjectURL = (blob) => {
    const url = `blob:audio-${objectUrls.length}-${blob.size}`;
    objectUrls.push({ url, blob });
    return url;
  };
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
  return { audios, objectUrls, revokedUrls };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
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

test("speech followed by three seconds of trailing silence automatically stops through transcription", async (t) => {
  const media = installFakeMediaRecorder();
  const vad = installFakeSilenceDetection(t);
  const { calls, stream } = installSpeechRuntimeFetch();
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-auto-stop");

  const micButton = elements.get("[data-speech-toggle]");
  micButton.onclick();
  await waitFor(
    () => media.recorders.length === 1 && vad.pendingFrameCount() === 1,
    () => `recorders=${media.recorders.length} frames=${vad.pendingFrameCount()}`,
  );

  vad.pushSample(190);
  vad.tick(100);
  vad.pushSample(128);
  vad.tick(1100);
  assert.equal(media.recorders[0].state, "recording");
  assert.equal(calls.some(([path]) => path === "/api/speech/transcribe"), false);

  vad.pushSample(128);
  vad.tick(3100);
  assert.equal(media.recorders[0].state, "recording");
  assert.equal(calls.some(([path]) => path === "/api/speech/transcribe"), false);

  vad.pushSample(128);
  vad.tick(4100);
  await waitFor(
    () => calls.some(([path]) => path === "/api/speech/transcribe"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  assert.equal(media.recorders[0].state, "inactive");
  assert.equal(media.tracks.every((track) => track.stopped), true);
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

test("microphone enabled without speech does not stop after three seconds", async (t) => {
  const media = installFakeMediaRecorder();
  const vad = installFakeSilenceDetection(t);
  const { calls } = installSpeechRuntimeFetch();
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-no-initial-silence-stop");

  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => media.recorders.length === 1 && vad.pendingFrameCount() === 1,
    () => `recorders=${media.recorders.length} frames=${vad.pendingFrameCount()}`,
  );

  vad.pushSample(128);
  vad.tick(100);
  vad.pushSample(128);
  vad.tick(2100);
  vad.pushSample(128);
  vad.tick(6100);

  assert.equal(media.recorders[0].state, "recording");
  assert.equal(media.recorders[0].stopCalls, 0);
  assert.equal(calls.some(([path]) => path === "/api/speech/transcribe"), false);

  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => calls.some(([path]) => path === "/api/speech/transcribe"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
});

test("speech resuming before three seconds resets trailing silence", async (t) => {
  const media = installFakeMediaRecorder();
  const vad = installFakeSilenceDetection(t);
  const { calls } = installSpeechRuntimeFetch();
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-silence-reset");

  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => media.recorders.length === 1 && vad.pendingFrameCount() === 1,
    () => `recorders=${media.recorders.length} frames=${vad.pendingFrameCount()}`,
  );

  vad.pushSample(190);
  vad.tick(100);
  vad.pushSample(128);
  vad.tick(1100);
  vad.pushSample(190);
  vad.tick(2500);
  vad.pushSample(128);
  vad.tick(3000);
  vad.pushSample(128);
  vad.tick(5500);

  assert.equal(media.recorders[0].state, "recording");
  assert.equal(calls.some(([path]) => path === "/api/speech/transcribe"), false);

  vad.pushSample(128);
  vad.tick(6100);
  await waitFor(
    () => calls.some(([path]) => path === "/api/speech/transcribe"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  assert.equal(media.recorders[0].state, "inactive");
});

test("silence-stop appends to existing composer text without auto-send", async (t) => {
  installFakeMediaRecorder();
  const vad = installFakeSilenceDetection(t);
  const { calls } = installSpeechRuntimeFetch({ transcript: "Google streaming TTS API" });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-existing-text-no-autosend");

  const input = elements.get("[data-chat-input]");
  input.value = "Also compare this against";
  input.oninput();
  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => vad.pendingFrameCount() === 1,
    () => `frames=${vad.pendingFrameCount()}`,
  );

  vad.pushSample(190);
  vad.tick(100);
  vad.pushSample(128);
  vad.tick(1100);
  vad.pushSample(128);
  vad.tick(4100);

  await waitFor(
    () => input.value === "Also compare this against\nGoogle streaming TTS API",
    () => input.value,
  );
  assert.equal(calls.some(([path]) => path === "/api/speech/transcribe"), true);
  assert.equal(calls.some(([path]) => path === "/api/chat/stream"), false);
});

test("editing the composer during recording prevents silence-stop auto-send", async (t) => {
  installFakeMediaRecorder();
  const vad = installFakeSilenceDetection(t);
  const { calls } = installSpeechRuntimeFetch({ transcript: "spoken addition" });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-edit-revokes-autosend");

  const input = elements.get("[data-chat-input]");
  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => vad.pendingFrameCount() === 1,
    () => `frames=${vad.pendingFrameCount()}`,
  );

  input.value = "typed while recording";
  input.oninput();
  vad.pushSample(190);
  vad.tick(100);
  vad.pushSample(128);
  vad.tick(1100);
  vad.pushSample(128);
  vad.tick(4100);

  await waitFor(
    () => input.value === "typed while recording\nspoken addition",
    () => input.value,
  );
  assert.equal(calls.some(([path]) => path === "/api/speech/transcribe"), true);
  assert.equal(calls.some(([path]) => path === "/api/chat/stream"), false);
});

test("automatic and manual microphone stop share one stop lifecycle", async (t) => {
  const media = installFakeMediaRecorder();
  const vad = installFakeSilenceDetection(t);
  const { calls } = installSpeechRuntimeFetch();
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-single-stop-lifecycle");

  const micButton = elements.get("[data-speech-toggle]");
  micButton.onclick();
  await waitFor(
    () => media.recorders.length === 1 && vad.pendingFrameCount() === 1,
    () => `recorders=${media.recorders.length} frames=${vad.pendingFrameCount()}`,
  );

  vad.pushSample(190);
  vad.tick(100);
  vad.pushSample(128);
  vad.tick(1100);
  vad.pushSample(128);
  vad.tick(4100);
  micButton.onclick();

  await waitFor(
    () => calls.some(([path]) => path === "/api/speech/transcribe"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  assert.equal(media.recorders[0].stopCalls, 1);
  assert.equal(
    calls.filter(([path]) => path === "/api/speech/transcribe").length,
    1,
  );
});

test("manual microphone stop cleans up silence detection resources", async (t) => {
  const media = installFakeMediaRecorder();
  const vad = installFakeSilenceDetection(t);
  const { calls } = installSpeechRuntimeFetch();
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-cleanup");

  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => media.recorders.length === 1 && vad.contexts.length === 1,
    () => `recorders=${media.recorders.length} contexts=${vad.contexts.length}`,
  );

  elements.get("[data-speech-toggle]").onclick();
  await waitFor(
    () => calls.some(([path]) => path === "/api/speech/transcribe"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  assert.equal(vad.pendingFrameCount(), 0);
  assert.equal(vad.contexts[0].closed, true);
  assert.equal(vad.contexts[0].sources[0].disconnected, true);
  assert.equal(vad.analysers[0].disconnected, true);
});

test("microphone recording still works when browser audio analysis fails", async (t) => {
  installFakeMediaRecorder();
  const originalAudioContext = globalThis.AudioContext;
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;
  globalThis.AudioContext = class {
    constructor() {
      throw new Error("audio analysis unavailable");
    }
  };
  globalThis.requestAnimationFrame = () => 1;
  globalThis.cancelAnimationFrame = () => {};
  t.after(() => {
    globalThis.AudioContext = originalAudioContext;
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
    globalThis.cancelAnimationFrame = originalCancelAnimationFrame;
  });
  const { calls, stream } = installSpeechRuntimeFetch();
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-speech-analysis-unavailable");

  const micButton = elements.get("[data-speech-toggle]");
  micButton.onclick();
  await waitFor(
    () => micButton.textContent === "Stop",
    () => micButton.textContent,
  );
  micButton.onclick();

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
  const { calls, stream } = installSpeechRuntimeFetch();
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
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
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
    () => calls.filter(([path]) => path === "/api/users/wifiknight/speech/synthesize").length >= 1,
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
  const { calls, stream } = installSpeechRuntimeFetch({ ttsChunkCount: 3 });
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
    2,
  );
  assert.equal(audio.audios.length, 1);
});

test("spoken response prefetches exactly one next chunk while current chunk plays", async (t) => {
  const audio = installFakeAudio(t);
  const { calls, stream } = installSpeechRuntimeFetch({ ttsChunkCount: 3 });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-tts-prefetch-one-ahead");
  const spokenToggle = elements.get("[data-spoken-responses-toggle]");
  spokenToggle.checked = true;
  spokenToggle.onchange();

  await submitCompletedRuntimeTurn(elements, stream);
  await waitFor(() => audio.audios.length === 1);
  await waitFor(
    () => calls.filter(([path]) => path === "/api/users/wifiknight/speech/synthesize").length === 2,
    () => JSON.stringify(calls.map(([path, init]) => [path, init.body])),
  );

  const speechBodies = calls
    .filter(([path]) => path === "/api/users/wifiknight/speech/synthesize")
    .map(([, init]) => JSON.parse(init.body));
  assert.deepEqual(speechBodies.map((body) => body.chunk_index), [0, 1]);

  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(
    calls.filter(([path]) => path === "/api/users/wifiknight/speech/synthesize").length,
    2,
  );
});

test("spoken response plays prefetched chunks in strict order", async (t) => {
  const audio = installFakeAudio(t);
  const { calls, stream } = installSpeechRuntimeFetch({ ttsChunkCount: 3 });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-tts-strict-order");
  const spokenToggle = elements.get("[data-spoken-responses-toggle]");
  spokenToggle.checked = true;
  spokenToggle.onchange();

  await submitCompletedRuntimeTurn(elements, stream);
  await waitFor(() => audio.audios.length === 1);
  assert.equal(audio.audios[0].url, "blob:audio-0-13");
  audio.audios[0].onended();

  await waitFor(() => audio.audios.length === 2);
  assert.equal(audio.audios[1].url, "blob:audio-1-13");
  audio.audios[1].onended();

  await waitFor(() => audio.audios.length === 3);
  assert.equal(audio.audios[2].url, "blob:audio-2-13");
  const speechBodies = calls
    .filter(([path]) => path === "/api/users/wifiknight/speech/synthesize")
    .map(([, init]) => JSON.parse(init.body));
  assert.deepEqual(speechBodies.map((body) => body.chunk_index), [0, 1, 2]);
});

test("short spoken response plays without prefetching another chunk", async (t) => {
  const audio = installFakeAudio(t);
  const { calls, stream } = installSpeechRuntimeFetch({ ttsChunkCount: 1 });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-tts-short-response");
  const spokenToggle = elements.get("[data-spoken-responses-toggle]");
  spokenToggle.checked = true;
  spokenToggle.onchange();

  await submitCompletedRuntimeTurn(elements, stream);
  await waitFor(() => audio.audios.length === 1);
  await new Promise((resolve) => setTimeout(resolve, 0));

  const speechBodies = calls
    .filter(([path]) => path === "/api/users/wifiknight/speech/synthesize")
    .map(([, init]) => JSON.parse(init.body));
  assert.deepEqual(speechBodies.map((body) => body.chunk_index), [0]);
});

test("Stop prevents in-flight prefetched audio from playing or requesting later chunks", async (t) => {
  const audio = installFakeAudio(t);
  const delayedChunk = deferred();
  const deferredTtsChunks = new Map([[1, delayedChunk]]);
  const { calls, stream } = installSpeechRuntimeFetch({
    ttsChunkCount: 3,
    deferredTtsChunks,
  });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-tts-stop-prefetch");
  const spokenToggle = elements.get("[data-spoken-responses-toggle]");
  spokenToggle.checked = true;
  spokenToggle.onchange();

  await submitCompletedRuntimeTurn(elements, stream);
  await waitFor(() => audio.audios.length === 1);
  await waitFor(
    () => calls.filter(([path]) => path === "/api/users/wifiknight/speech/synthesize").length === 2,
    () => JSON.stringify(calls.map(([path, init]) => [path, init.body])),
  );

  elements.get("[data-tts-stop]").onclick();
  const speechCalls = calls
    .filter(([path]) => path === "/api/users/wifiknight/speech/synthesize");
  assert.equal(speechCalls[1][1].signal.aborted, true);
  delayedChunk.resolve();
  audio.audios[0].onended();
  await new Promise((resolve) => setTimeout(resolve, 0));

  const speechBodies = speechCalls
    .map(([, init]) => JSON.parse(init.body));
  assert.deepEqual(speechBodies.map((body) => body.chunk_index), [0, 1]);
  assert.equal(audio.audios.length, 1);
});

test("prefetch failure leaves current playback intact and does not play later chunks", async (t) => {
  const audio = installFakeAudio(t);
  const { calls, stream } = installSpeechRuntimeFetch({
    ttsChunkCount: 3,
    ttsStatusByChunk: { 1: 502 },
  });
  const { elements } = await enterSpeechRuntimeWorkspace("runtime-tts-prefetch-failure");
  const spokenToggle = elements.get("[data-spoken-responses-toggle]");
  spokenToggle.checked = true;
  spokenToggle.onchange();

  await submitCompletedRuntimeTurn(elements, stream);
  await waitFor(() => audio.audios.length === 1);
  assert.equal(audio.audios[0].paused, false);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(audio.audios.length, 1);

  audio.audios[0].onended();
  await new Promise((resolve) => setTimeout(resolve, 0));

  const speechBodies = calls
    .filter(([path]) => path === "/api/users/wifiknight/speech/synthesize")
    .map(([, init]) => JSON.parse(init.body));
  assert.deepEqual(speechBodies.map((body) => body.chunk_index), [0, 1]);
  assert.equal(audio.audios.length, 1);
  assert.equal(elements.get("[data-tts-stop]").hidden, true);
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

test("agent jobs refresh while queued or running without blocking chat submit", async (t) => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const stream = createControlledSseResponse();
  const calls = [];
  const agentJobResponses = [
    {
      agent_job_contract_version: "1.0",
	      jobs: [{
	        job_number: "001",
        status: "queued",
        agent_label: "Doc Writer",
        description: "Updating architecture document",
        created_at: "2026-09-01T12:00:00Z",
      }],
    },
    {
      agent_job_contract_version: "1.0",
	      jobs: [{
	        job_number: "001",
        status: "running",
        agent_label: "Doc Writer",
        description: "Updating architecture document",
        created_at: "2026-09-01T12:00:00Z",
        started_at: "2026-09-01T12:00:01Z",
      }],
    },
    {
      agent_job_contract_version: "1.0",
	      jobs: [{
	        job_number: "001",
        status: "completed",
        agent_label: "Doc Writer",
        result_description: "Architecture document updated",
        created_at: "2026-09-01T12:00:00Z",
        started_at: "2026-09-01T12:00:01Z",
        completed_at: "2026-09-01T12:00:04Z",
      }],
    },
  ];
  let agentJobLoadCount = 0;
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
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs/stream")) {
      return jsonResponse(404, { detail: "Agent job stream is unavailable." });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      const response = agentJobResponses[
        Math.min(agentJobLoadCount, agentJobResponses.length - 1)
      ];
      agentJobLoadCount += 1;
      return jsonResponse(200, response);
    }
    if (path === "/api/chat/stream") {
      return stream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-agent-jobs-refresh-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  const realSetTimeout = globalThis.setTimeout;
  const realClearTimeout = globalThis.clearTimeout;
  const timers = [];
  globalThis.setTimeout = (callback, delay) => {
    const timer = {
      id: timers.length + 1,
      callback,
      delay,
      cleared: false,
    };
    timers.push(timer);
    return timer.id;
  };
  globalThis.clearTimeout = (id) => {
    const timer = timers.find((item) => item.id === id);
    if (timer) {
      timer.cleared = true;
    }
  };
  const restoreTimers = () => {
    globalThis.setTimeout = realSetTimeout;
    globalThis.clearTimeout = realClearTimeout;
  };
  t.after(restoreTimers);
  const nextRealTick = () => new Promise((resolve) => realSetTimeout(resolve, 0));
  const settleRealTicks = async () => {
    for (let i = 0; i < 5; i += 1) {
      await nextRealTick();
    }
  };
  const activeTimers = () => timers.filter((timer) => !timer.cleared);
  const runNextTimer = async () => {
    const [timer] = activeTimers();
    assert.ok(timer, "expected an active agent job refresh timer");
    timer.cleared = true;
    timer.callback();
    await nextRealTick();
  };

  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  await nextRealTick();

  assert.equal(agentJobLoadCount, 1);
  assert.match(textTree(elements.get("[data-agents-panel]")), /Updating architecture document/);
  assert.equal(activeTimers().length, 1);
  assert.equal(activeTimers()[0].delay, 300);

  const input = elements.get("[data-chat-input]");
  input.value = "Keep chatting while jobs refresh";
  input.oninput();
  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  await nextRealTick();
  assert.equal(
    calls.some(([path]) => path === "/api/chat/stream"),
    true,
  );
  assert.equal(agentJobLoadCount, 2);
  assert.match(textTree(elements.get("[data-agents-panel]")), /Doc Writer/);
  assert.equal(activeTimers().length, 1);
  assert.equal(activeTimers()[0].delay, 300);

  await runNextTimer();
  assert.equal(agentJobLoadCount, 3);
  assert.match(textTree(elements.get("[data-agents-panel]")), /Architecture document updated/);
  assert.equal(activeTimers().length, 1);
  assert.equal(activeTimers()[0].delay, 300);
  stream.complete({
    response: "Chat stayed usable while jobs refreshed",
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
  await settleRealTicks();
  assert.match(
    textTree(elements.get("[data-chat-transcript]")),
    /Chat stayed usable while jobs refreshed/,
  );
  await nextRealTick();
  assert.equal(activeTimers().length, 0);
  restoreTimers();
});

test("agent report popup loads reports from the background report surface", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
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
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs/stream")) {
      return jsonResponse(404, { detail: "Agent job stream is unavailable." });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/reports")) {
      return jsonResponse(200, {
        agent_job_report_contract_version: "1.0",
        reports: [{
          report_number: "001",
          job_number: "001",
          agent_label: "Memory Analyst",
          status: "failed",
          title: "Memory proposal not created",
          summary: "A pending memory proposal already exists for this category.",
          public_resource_label: null,
          created_at: "2026-09-02T10:00:00Z",
          report_id: "agent-job-report-secret",
          job_id: "agent-job-secret",
          session_id: "session-secret",
        }],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-agent-report-popup-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  await waitFor(
    () => textTree(elements.get("[data-agents-panel]")).includes("View all job reports"),
    () => textTree(elements.get("[data-agents-panel]")),
  );

  const arrow = findTree(elements.get("[data-agents-panel]"), (item) => (
    item.tagName === "button" && item.textContent === "↗"
  ));
  assert.ok(arrow);
  assert.equal(typeof arrow.onclick, "function");
  await arrow.onclick();

  await waitFor(
    () => calls.some(([path]) => path.includes("/agent/reports")),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  assert.match(textTree(elements.get("[data-agents-panel]")), /Job Reports/);
  assert.match(textTree(elements.get("[data-agents-panel]")), /Memory Analyst/);
  assert.match(textTree(elements.get("[data-agents-panel]")), /A pending memory proposal already exists/);
  assert.doesNotMatch(textTree(elements.get("[data-agents-panel]")), /agent-job-report-secret/);
  assert.doesNotMatch(textTree(elements.get("[data-agents-panel]")), /agent-job-secret/);
  assert.doesNotMatch(textTree(elements.get("[data-agents-panel]")), /session-secret/);

  const close = findTree(elements.get("[data-agents-panel]"), (item) => (
    item.tagName === "button" && item.attributes["aria-label"] === "Close job reports"
  ));
  assert.ok(close);
  close.onclick();
  assert.doesNotMatch(textTree(elements.get("[data-agents-panel]")), /Job Reports/);
});

test("agent jobs use fast refresh while chat stream is pending", async (t) => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const stream = createControlledSseResponse();
  const calls = [];
  const agentJobResponses = [
    {
      agent_job_contract_version: "1.0",
      jobs: [],
    },
    {
      agent_job_contract_version: "1.0",
      jobs: [],
    },
    {
      agent_job_contract_version: "1.0",
      jobs: [{
        job_id: "job-running",
        status: "running",
        agent_label: "Note Curator",
        description: "Preparing workspace note",
        created_at: "2026-09-01T12:00:00Z",
        started_at: "2026-09-01T12:00:01Z",
      }],
    },
    {
      agent_job_contract_version: "1.0",
      jobs: [{
        job_id: "job-completed",
        status: "completed",
        agent_label: "Note Curator",
        result_description: "Workspace note proposal created",
        created_at: "2026-09-01T12:00:00Z",
        started_at: "2026-09-01T12:00:01Z",
        completed_at: "2026-09-01T12:00:02Z",
      }],
    },
  ];
  let agentJobLoadCount = 0;
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
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs/stream")) {
      return jsonResponse(404, { detail: "Agent job stream is unavailable." });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      const response = agentJobResponses[
        Math.min(agentJobLoadCount, agentJobResponses.length - 1)
      ];
      agentJobLoadCount += 1;
      return jsonResponse(200, response);
    }
    if (path === "/api/chat/stream") {
      return stream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-agent-jobs-fast-refresh-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  const realSetTimeout = globalThis.setTimeout;
  const realClearTimeout = globalThis.clearTimeout;
  const timers = [];
  globalThis.setTimeout = (callback, delay) => {
    const timer = {
      id: timers.length + 1,
      callback,
      delay,
      cleared: false,
    };
    timers.push(timer);
    return timer.id;
  };
  globalThis.clearTimeout = (id) => {
    const timer = timers.find((item) => item.id === id);
    if (timer) {
      timer.cleared = true;
    }
  };
  const restoreTimers = () => {
    globalThis.setTimeout = realSetTimeout;
    globalThis.clearTimeout = realClearTimeout;
  };
  t.after(restoreTimers);
  const nextRealTick = () => new Promise((resolve) => realSetTimeout(resolve, 0));
  const settleRealTicks = async () => {
    for (let i = 0; i < 5; i += 1) {
      await nextRealTick();
    }
  };
  const activeTimers = () => timers.filter((timer) => !timer.cleared);
  const runNextTimer = async () => {
    const [timer] = activeTimers();
    assert.ok(timer, "expected an active agent job refresh timer");
    timer.cleared = true;
    timer.callback();
    await nextRealTick();
  };

  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  await nextRealTick();

  assert.equal(agentJobLoadCount, 1);
  assert.equal(activeTimers().length, 0);

  const input = elements.get("[data-chat-input]");
  input.value = "Create a workspace note while chat streams";
  input.oninput();
  const submitPromise = elements.get("[data-chat-form]").onsubmit({
    preventDefault() {},
  });
  await nextRealTick();

  assert.equal(agentJobLoadCount, 2);
  assert.equal(activeTimers().length, 1);
  assert.equal(activeTimers()[0].delay, 300);

  await runNextTimer();
  assert.equal(agentJobLoadCount, 3);
  assert.match(textTree(elements.get("[data-agents-panel]")), /Preparing workspace note/);
  assert.equal(activeTimers().length, 1);
  assert.equal(activeTimers()[0].delay, 300);

  stream.complete({
    response: "Queued note visibility stayed live",
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
  await settleRealTicks();
  assert.match(
    textTree(elements.get("[data-chat-transcript]")),
    /Queued note visibility stayed live/,
  );
  if (
    !textTree(elements.get("[data-agents-panel]")).includes(
      "Workspace note proposal created"
    )
    && activeTimers().length > 0
  ) {
    await runNextTimer();
  }
  assert.ok(agentJobLoadCount >= 4);
  assert.match(textTree(elements.get("[data-agents-panel]")), /Workspace note proposal created/);
  await submitPromise;
  restoreTimers();
});

test("agent panel updates from job stream before polling interval", async (t) => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
  const agentStream = createControlledSseResponse();
  const calls = [];
  let listCalls = 0;

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
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs/stream")) {
      return agentStream.response;
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      listCalls += 1;
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    if (path === "/api/chat/stream") {
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-agent-job-stream-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  const realSetTimeout = globalThis.setTimeout;
  const realClearTimeout = globalThis.clearTimeout;
  const timers = [];
  globalThis.setTimeout = (callback, delay) => {
    const timer = {
      id: timers.length + 1,
      callback,
      delay,
      cleared: false,
    };
    timers.push(timer);
    return timer.id;
  };
  globalThis.clearTimeout = (id) => {
    const timer = timers.find((item) => item.id === id);
    if (timer) {
      timer.cleared = true;
    }
  };
  t.after(() => {
    globalThis.setTimeout = realSetTimeout;
    globalThis.clearTimeout = realClearTimeout;
  });
  const nextRealTick = () => new Promise((resolve) => realSetTimeout(resolve, 0));
  const waitForReal = async (predicate, describe = () => "") => {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      if (predicate()) {
        return;
      }
      await nextRealTick();
    }
    throw new Error(`Timed out waiting for app runtime condition. ${describe()}`);
  };

  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  await nextRealTick();

  const input = elements.get("[data-chat-input]");
  input.value = "Create a workspace note while chat streams";
  input.oninput();
  const submitPromise = elements.get("[data-chat-form]").onsubmit({
    preventDefault() {},
  });

  await waitForReal(
    () => calls.some(([path]) => path.includes("/agent/jobs/stream")),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  agentStream.event("snapshot", {
    agent_job_contract_version: "1.0",
    jobs: [{
      job_id: "job-1",
      status: "running",
      action_kind: "propose_collaborative_note",
      agent_label: "Note Curator",
      display_label: "Workspace note",
      description: "Preparing workspace note",
      created_at: "2026-09-01T12:00:00Z",
    }],
  });
  await nextRealTick();
  await nextRealTick();

  assert.match(textTree(elements.get("[data-agents-panel]")), /Note Curator/);
  assert.match(textTree(elements.get("[data-agents-panel]")), /Preparing workspace note/);
  assert.equal(
    timers.some((timer) => !timer.cleared && timer.delay === 300),
    false,
  );
  assert.ok(listCalls <= 2);
  agentStream.close();
  chatStream.complete({
    response: "Chat stayed open while agent jobs streamed",
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
  await submitPromise;
});

test("completed background jobs refresh work notes and memory while chat remains pending", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
  const agentStream = createControlledSseResponse();
  const calls = [];
  let blueprintCalls = 0;
  let noteCalls = 0;
  let memoryCalls = 0;
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init]);
    if (path === "/api/auth/config") {
      return jsonResponse(200, {
        auth_required: false,
        mode: "local_dev",
        user: { user_id: "wifiknight" },
      });
    }
    if (path === "/api/auth/session") {
      return jsonResponse(200, { authenticated: true, user_id: "wifiknight" });
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
    if (path === "/api/projects/agent-col/blueprints/blueprint-1") {
      return jsonResponse(200, blueprintDetailResponse({
        reference: {
          artifact_type: "synthesis_blueprint",
          project_id: "agent-col",
          artifact_id: "blueprint-1",
          schema_version: "2.0",
          display_label: "Async Work Smoke Test",
        },
      }));
    }
    if (path.startsWith("/api/projects/agent-col/blueprints/blueprint-1/feedback")) {
      return jsonResponse(200, { events: [], next_before: null });
    }
    if (path.startsWith("/api/projects/agent-col/blueprints")) {
      blueprintCalls += 1;
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        artifacts: blueprintCalls > 1 ? [{
          reference: {
            artifact_type: "synthesis_blueprint",
            project_id: "agent-col",
            artifact_id: "blueprint-1",
            schema_version: "2.0",
            display_label: "Async Work Smoke Test",
          },
          created_at: "2026-09-01T12:00:01Z",
          originating_session_id: "session-1",
          originating_turn_id: null,
          parent_artifact_id: null,
          feedback_counts: { accepted: 0, rejected: 0, edited: 0 },
          adaptation_categories: [],
        }] : [],
        next_before: null,
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
      memoryCalls += 1;
      return jsonResponse(200, {
        memory_contract_version: "1.0",
        profile: null,
        unresolved_proposals: memoryCalls > 1 ? [{
          proposal_id: "memory-proposal-1",
          category: "user_requested_memory",
          proposed_value: "Prefers source-backed implementation notes.",
          status: "pending",
          expires_at: "2026-09-02T12:00:01Z",
        }] : [],
        events: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/notes")) {
      noteCalls += 1;
      return jsonResponse(200, {
        note_contract_version: "1.0",
        notes: [],
        pending_proposals: noteCalls > 1 ? [{
          note_contract_version: "1.0",
          proposal_id: "note-proposal-1",
          note_kind: "constraint",
          title: "Async background work",
          body: "Background work must continue independently.",
          source_session_id: "session-1",
          source_message_ids: ["message-1"],
          expected_note_id: null,
          expected_revision: null,
          policy_version: "1.0",
          status: "pending",
          created_at: "2026-09-01T12:00:01Z",
          expires_at: "2026-09-02T12:00:01Z",
        }] : [],
        next_note_id: null,
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/chat-sessions")) {
      return jsonResponse(200, {
        chat_contract_version: "1.0",
        sessions: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs/stream")) {
      return agentStream.response;
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    if (path === "/api/chat/stream") {
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-agent-job-resource-refresh-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  const input = elements.get("[data-chat-input]");
  input.value = "Create an artifact and a note";
  input.oninput();
  const submitPromise = elements.get("[data-chat-form]").onsubmit({
    preventDefault() {},
  });

  await waitFor(
    () => calls.some(([path]) => path.includes("/agent/jobs/stream")),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  const chatCallsBeforeSnapshot = calls.filter(([path]) => (
    path === "/api/chat" || path === "/api/chat/stream"
  )).length;
  agentStream.event("snapshot", {
    agent_job_contract_version: "1.0",
    jobs: [
      {
        job_ref: "jobref_artifact",
        job_number: "001",
        status: "completed",
        action_kind: "create_artifact",
        agent_label: "Artifact Builder",
        display_label: "Artifact: Async Work Smoke Test",
        created_at: "2026-09-01T12:00:00Z",
        updated_at: "2026-09-01T12:00:01Z",
      },
      {
        job_ref: "jobref_memory",
        job_number: "003",
        status: "completed",
        action_kind: "propose_memory_signal",
        agent_label: "Memory Analyst",
        display_label: "Memory request: user_requested_memory",
        created_at: "2026-09-01T12:00:00Z",
        updated_at: "2026-09-01T12:00:01Z",
      },
      {
        job_ref: "jobref_note",
        job_number: "002",
        status: "completed",
        action_kind: "propose_collaborative_note",
        agent_label: "Note Curator",
        display_label: "Workspace note: Async background work",
        created_at: "2026-09-01T12:00:00Z",
        updated_at: "2026-09-01T12:00:01Z",
      },
    ],
  });

  await waitFor(
    () => blueprintCalls > 1 && noteCalls > 1 && memoryCalls > 1,
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  assert.match(textTree(elements.get("[data-work-list]")), /Async Work Smoke Test/);
  assert.match(textTree(elements.get("[data-notes-panel]")), /Async background work/);
  assert.match(textTree(elements.get("[data-memory-panel]")), /source backed implementation notes/);
  const blueprintCallsAfterFirstRefresh = blueprintCalls;
  const noteCallsAfterFirstRefresh = noteCalls;
  const memoryCallsAfterFirstRefresh = memoryCalls;
  agentStream.event("snapshot", {
    agent_job_contract_version: "1.0",
    jobs: [
      {
        job_ref: "jobref_artifact",
        job_number: "003",
        status: "completed",
        action_kind: "create_artifact",
        agent_label: "Artifact Builder",
        display_label: "Artifact: Async Work Smoke Test",
        created_at: "2026-09-01T12:00:00Z",
        updated_at: "2026-09-01T12:00:01Z",
      },
      {
        job_ref: "jobref_memory",
        job_number: "007",
        status: "completed",
        action_kind: "propose_memory_signal",
        agent_label: "Memory Analyst",
        display_label: "Memory request: user_requested_memory",
        created_at: "2026-09-01T12:00:00Z",
        updated_at: "2026-09-01T12:00:01Z",
      },
      {
        job_ref: "jobref_note",
        job_number: "004",
        status: "completed",
        action_kind: "propose_collaborative_note",
        agent_label: "Note Curator",
        display_label: "Workspace note: Async background work",
        created_at: "2026-09-01T12:00:00Z",
        updated_at: "2026-09-01T12:00:01Z",
      },
    ],
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(blueprintCalls, blueprintCallsAfterFirstRefresh);
  assert.equal(noteCalls, noteCallsAfterFirstRefresh);
  assert.equal(memoryCalls, memoryCallsAfterFirstRefresh);
  assert.equal(
    calls.filter(([path]) => path === "/api/chat" || path === "/api/chat/stream").length,
    chatCallsBeforeSnapshot,
  );

  agentStream.close();
  chatStream.complete({
    response: "Background work is still independent.",
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
  await submitPromise;
});

test("chat stream deltas update chat without replacing resource panels", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
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
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    if (path === "/api/chat/stream") {
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-chat-delta-narrow-render-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  const input = elements.get("[data-chat-input]");
  input.value = "Stream a response";
  input.oninput();
  const submitPromise = elements.get("[data-chat-form]").onsubmit({
    preventDefault() {},
  });
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  const workReplacements = elements.get("[data-work-list]").replaceChildrenCount;
  const notesReplacements = elements.get("[data-notes-panel]").replaceChildrenCount;
  const memoryReplacements = elements.get("[data-memory-panel]").replaceChildrenCount;
  const agentsReplacements = elements.get("[data-agents-panel]").replaceChildrenCount;

  chatStream.delta("Partial response");
  await waitFor(
    () => textTree(elements.get("[data-chat-transcript]")).includes("Partial response"),
    () => textTree(elements.get("[data-chat-transcript]")),
  );

  assert.equal(elements.get("[data-work-list]").replaceChildrenCount, workReplacements);
  assert.equal(elements.get("[data-notes-panel]").replaceChildrenCount, notesReplacements);
  assert.equal(elements.get("[data-memory-panel]").replaceChildrenCount, memoryReplacements);
  assert.equal(elements.get("[data-agents-panel]").replaceChildrenCount, agentsReplacements);

  chatStream.complete({
    response: "Finished response.",
    actions: [],
    citations: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    memory_clarifications: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    adaptations: [],
  });
  await submitPromise;
});

test("completed artifact job auto-selects exactly one new artifact unless user selected later", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
  const agentStream = createControlledSseResponse();
  const calls = [];
  let blueprintListCalls = 0;
  let blueprintDetailCalls = 0;
  const artifactsByCall = [
    [],
    [{
      reference: {
        artifact_type: "synthesis_blueprint",
        project_id: "agent-col",
        artifact_id: "blueprint-new",
        schema_version: "2.0",
        display_label: "Refresh Verification Artifact",
      },
      created_at: "2026-09-01T12:00:01Z",
      originating_session_id: "session-1",
      originating_turn_id: null,
      parent_artifact_id: null,
      feedback_counts: { accepted: 0, rejected: 0, edited: 0 },
      adaptation_categories: [],
    }],
  ];
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init]);
    if (path === "/api/auth/config") {
      return jsonResponse(200, {
        auth_required: false,
        mode: "local_dev",
        user: { user_id: "wifiknight" },
      });
    }
    if (path === "/api/auth/session") {
      return jsonResponse(200, { authenticated: true, user_id: "wifiknight" });
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
    if (path === "/api/projects/agent-col/blueprints/blueprint-new") {
      blueprintDetailCalls += 1;
      return jsonResponse(
        200,
        blueprintDetailResponse(
          {
            reference: {
              artifact_type: "synthesis_blueprint",
              project_id: "agent-col",
            artifact_id: "blueprint-new",
            schema_version: "2.0",
            display_label: "Refresh Verification Artifact",
          },
          created_at: "2026-09-01T12:00:01Z",
          originating_session_id: "session-1",
          originating_turn_id: null,
          parent_artifact_id: null,
            feedback_counts: { accepted: 0, rejected: 0, edited: 0 },
            adaptation_categories: [],
          },
          "Completed resources become visible without manual refresh.",
        ),
      );
    }
    if (path.startsWith("/api/projects/agent-col/blueprints/blueprint-new/feedback")) {
      return jsonResponse(200, { events: [], next_before: null });
    }
    if (path.startsWith("/api/projects/agent-col/blueprints")) {
      const artifacts = artifactsByCall[Math.min(blueprintListCalls, artifactsByCall.length - 1)];
      blueprintListCalls += 1;
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        artifacts,
        next_before: null,
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
        next_note_id: null,
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/chat-sessions")) {
      return jsonResponse(200, {
        chat_contract_version: "1.0",
        sessions: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs/stream")) {
      return agentStream.response;
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    if (path === "/api/chat/stream") {
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-auto-select-artifact-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  const input = elements.get("[data-chat-input]");
  input.value = "Create an artifact";
  input.oninput();
  const submitPromise = elements.get("[data-chat-form]").onsubmit({
    preventDefault() {},
  });
  await waitFor(
    () => calls.some(([path]) => path.includes("/agent/jobs/stream")),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  agentStream.event("snapshot", {
    agent_job_contract_version: "1.0",
    jobs: [{
      job_ref: "jobref_artifact",
      job_number: "001",
      status: "completed",
      action_kind: "create_artifact",
      agent_label: "Artifact Builder",
      display_label: "Artifact: Refresh Verification Artifact",
      created_at: "2026-09-01T12:00:00Z",
      updated_at: "2026-09-01T12:00:01Z",
    }],
  });

  await waitFor(
    () => blueprintDetailCalls === 1,
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  assert.match(textTree(elements.get("[data-work-list]")), /Refresh Verification Artifact/);
  assert.match(textTree(elements.get("[data-work-detail]")), /Refresh Verification Artifact/);

  agentStream.close();
  chatStream.complete({
    response: "Queued.",
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
  await submitPromise;
});

test("completed artifact refresh does not overwrite a newer user artifact selection", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
  const agentStream = createControlledSseResponse();
  const calls = [];
  let completedJobObserved = false;
  let newArtifactDetailCalls = 0;
  let existingArtifactDetailCalls = 0;
  const initialArtifact = {
    reference: {
      artifact_type: "synthesis_blueprint",
      project_id: "agent-col",
      artifact_id: "blueprint-existing",
      schema_version: "2.0",
      display_label: "Existing Artifact",
    },
    created_at: "2026-09-01T11:00:00Z",
    originating_session_id: "session-1",
    originating_turn_id: null,
    parent_artifact_id: null,
    feedback_counts: { accepted: 0, rejected: 0, edited: 0 },
    adaptation_categories: [],
  };
  const newArtifact = {
    reference: {
      artifact_type: "synthesis_blueprint",
      project_id: "agent-col",
      artifact_id: "blueprint-new",
      schema_version: "2.0",
      display_label: "New Background Artifact",
    },
    created_at: "2026-09-01T12:00:01Z",
    originating_session_id: "session-1",
    originating_turn_id: null,
    parent_artifact_id: null,
    feedback_counts: { accepted: 0, rejected: 0, edited: 0 },
    adaptation_categories: [],
  };
  const blueprintDetail = (artifact) => blueprintDetailResponse(
    artifact,
    `${artifact.reference.display_label} detail`,
  );
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init]);
    if (path === "/api/auth/config") {
      return jsonResponse(200, {
        auth_required: false,
        mode: "local_dev",
        user: { user_id: "wifiknight" },
      });
    }
    if (path === "/api/auth/session") {
      return jsonResponse(200, { authenticated: true, user_id: "wifiknight" });
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
    if (path === "/api/projects/agent-col/blueprints/blueprint-existing") {
      existingArtifactDetailCalls += 1;
      return jsonResponse(200, blueprintDetail(initialArtifact));
    }
    if (path === "/api/projects/agent-col/blueprints/blueprint-new") {
      newArtifactDetailCalls += 1;
      return jsonResponse(200, blueprintDetail(newArtifact));
    }
    if (path.includes("/feedback")) {
      return jsonResponse(200, { events: [], next_before: null });
    }
    if (path.startsWith("/api/projects/agent-col/blueprints")) {
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        artifacts: completedJobObserved
          ? [newArtifact, initialArtifact]
          : [initialArtifact],
        next_before: null,
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
        next_note_id: null,
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/chat-sessions")) {
      return jsonResponse(200, {
        chat_contract_version: "1.0",
        sessions: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs/stream")) {
      return agentStream.response;
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    if (path === "/api/chat/stream") {
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-auto-select-guard-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  await waitFor(
    () => textTree(elements.get("[data-work-list]")).includes("Existing Artifact"),
    () => textTree(elements.get("[data-work-list]")),
  );
  const existingButton = findTree(
    elements.get("[data-work-list]"),
    (item) => typeof item.onclick === "function"
      && item.textContent.includes("Existing Artifact"),
  );
  assert.ok(existingButton, textTree(elements.get("[data-work-list]")));
  existingButton.onclick();
  await waitFor(
    () => existingArtifactDetailCalls === 1,
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  const input = elements.get("[data-chat-input]");
  input.value = "Create an artifact";
  input.oninput();
  const submitPromise = elements.get("[data-chat-form]").onsubmit({
    preventDefault() {},
  });
  await waitFor(
    () => calls.some(([path]) => path.includes("/agent/jobs/stream")),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  completedJobObserved = true;
  agentStream.event("snapshot", {
    agent_job_contract_version: "1.0",
    jobs: [{
      job_ref: "jobref_artifact",
      job_number: "001",
      status: "completed",
      action_kind: "create_artifact",
      agent_label: "Artifact Builder",
      display_label: "Artifact: New Background Artifact",
      created_at: "2026-09-01T12:00:00Z",
      updated_at: "2026-09-01T12:00:01Z",
    }],
  });

  await waitFor(
    () => textTree(elements.get("[data-work-list]")).includes("New Background Artifact"),
    () => textTree(elements.get("[data-work-list]")),
  );
  assert.equal(newArtifactDetailCalls, 0);
  assert.match(textTree(elements.get("[data-work-detail]")), /Existing Artifact/);

  agentStream.close();
  chatStream.complete({
    response: "Queued.",
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
  await submitPromise;
});

test("queued background work keeps polling after chat final until resource refresh", async (t) => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
  const calls = [];
  let agentJobLoadCount = 0;
  let blueprintCalls = 0;
  let noteCalls = 0;
  globalThis.fetch = async (path, init = {}) => {
    calls.push([path, init]);
    if (path === "/api/auth/config") {
      return jsonResponse(200, {
        auth_required: false,
        mode: "local_dev",
        user: { user_id: "wifiknight" },
      });
    }
    if (path === "/api/auth/session") {
      return jsonResponse(200, { authenticated: true, user_id: "wifiknight" });
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
    if (path === "/api/projects/agent-col/blueprints/blueprint-1") {
      return jsonResponse(200, blueprintDetailResponse({
        reference: {
          artifact_type: "synthesis_blueprint",
          project_id: "agent-col",
          artifact_id: "blueprint-1",
          schema_version: "2.0",
          display_label: "Async Work Smoke Test",
        },
      }));
    }
    if (path.startsWith("/api/projects/agent-col/blueprints/blueprint-1/feedback")) {
      return jsonResponse(200, { events: [], next_before: null });
    }
    if (path.startsWith("/api/projects/agent-col/blueprints")) {
      blueprintCalls += 1;
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        artifacts: blueprintCalls > 1 ? [{
          reference: {
            artifact_type: "synthesis_blueprint",
            project_id: "agent-col",
            artifact_id: "blueprint-1",
            schema_version: "2.0",
            display_label: "Async Work Smoke Test",
          },
          created_at: "2026-09-01T12:00:01Z",
          originating_session_id: "session-1",
          originating_turn_id: null,
          parent_artifact_id: null,
          feedback_counts: { accepted: 0, rejected: 0, edited: 0 },
          adaptation_categories: [],
        }] : [],
        next_before: null,
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
      noteCalls += 1;
      return jsonResponse(200, {
        note_contract_version: "1.0",
        notes: [],
        pending_proposals: noteCalls > 1 ? [{
          note_contract_version: "1.0",
          proposal_id: "note-proposal-1",
          note_kind: "constraint",
          title: "Async background work",
          body: "Background work must continue independently.",
          source_session_id: "session-1",
          source_message_ids: ["message-1"],
          expected_note_id: null,
          expected_revision: null,
          policy_version: "1.0",
          status: "pending",
          created_at: "2026-09-01T12:00:01Z",
          expires_at: "2026-09-02T12:00:01Z",
        }] : [],
        next_note_id: null,
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/chat-sessions")) {
      return jsonResponse(200, {
        chat_contract_version: "1.0",
        sessions: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs/stream")) {
      return jsonResponse(404, { detail: "Agent job stream is unavailable." });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      agentJobLoadCount += 1;
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: agentJobLoadCount >= 4 ? [
          {
            job_ref: "jobref_artifact",
            job_number: "001",
            status: "completed",
            action_kind: "create_artifact",
            agent_label: "Artifact Builder",
            display_label: "Artifact: Async Work Smoke Test",
            created_at: "2026-09-01T12:00:00Z",
            updated_at: "2026-09-01T12:00:01Z",
          },
          {
            job_ref: "jobref_note",
            job_number: "002",
            status: "completed",
            action_kind: "propose_collaborative_note",
            agent_label: "Note Curator",
            display_label: "Workspace note: Async background work",
            created_at: "2026-09-01T12:00:00Z",
            updated_at: "2026-09-01T12:00:01Z",
          },
        ] : [],
      });
    }
    if (path === "/api/chat/stream") {
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-queued-work-poll-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  const realSetTimeout = globalThis.setTimeout;
  const realClearTimeout = globalThis.clearTimeout;
  const timers = [];
  globalThis.setTimeout = (callback, delay) => {
    const timer = {
      id: timers.length + 1,
      callback,
      delay,
      cleared: false,
    };
    timers.push(timer);
    return timer.id;
  };
  globalThis.clearTimeout = (id) => {
    const timer = timers.find((item) => item.id === id);
    if (timer) {
      timer.cleared = true;
    }
  };
  t.after(() => {
    globalThis.setTimeout = realSetTimeout;
    globalThis.clearTimeout = realClearTimeout;
  });
  const nextRealTick = () => new Promise((resolve) => realSetTimeout(resolve, 0));
  const settleRealTicks = async () => {
    for (let i = 0; i < 5; i += 1) {
      await nextRealTick();
    }
  };
  const waitForQueuedWorkReal = async (predicate, describe = () => "") => {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      if (predicate()) {
        return;
      }
      await nextRealTick();
    }
    throw new Error(`Timed out waiting for app runtime condition. ${describe()}`);
  };
  const runNextTimer = async () => {
    const timer = timers.find((item) => !item.cleared);
    assert.ok(timer, "expected a scheduled agent job refresh timer");
    timer.cleared = true;
    timer.callback();
    await settleRealTicks();
  };

  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  const input = elements.get("[data-chat-input]");
  input.value = "Create an artifact and a note";
  input.oninput();
  const submitPromise = elements.get("[data-chat-form]").onsubmit({
    preventDefault() {},
  });

  await waitForQueuedWorkReal(
    () => calls.some(([path]) => path.includes("/agent/jobs/stream")),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  chatStream.complete({
    response: "Background work has been queued.",
    actions: [],
    citations: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    queued_actions: [
      {
        action_kind: "create_artifact",
        status: "queued",
        agent_label: "Artifact Builder",
        display_label: "Artifact: Async Work Smoke Test",
      },
      {
        action_kind: "propose_collaborative_note",
        status: "queued",
        agent_label: "Note Curator",
        display_label: "Workspace note: Async background work",
      },
    ],
    continuity_receipts: [],
    adaptations: [],
  });
  await submitPromise;

  assert.equal(blueprintCalls, 1);
  assert.equal(noteCalls, 1);
  await runNextTimer();

  await waitForQueuedWorkReal(
    () => blueprintCalls > 1 && noteCalls > 1,
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  assert.match(textTree(elements.get("[data-work-list]")), /Async Work Smoke Test/);
  assert.match(textTree(elements.get("[data-notes-panel]")), /Async background work/);
  assert.equal(
    calls.filter(([path]) => path === "/api/chat" || path === "/api/chat/stream").length,
    1,
  );
});

test("memory proposal approval during a pending chat uses direct memory API", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
  const calls = [];
  let memoryApproved = false;
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
    if (
      path === "/api/users/wifiknight/memory/proposals/response_length--proposal-1/approve"
      && init.method === "POST"
    ) {
      memoryApproved = true;
      return jsonResponse(200, {
        action: { action_name: "approve_memory_signal", status: "completed" },
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
      });
    }
    if (path.startsWith("/api/users/wifiknight/memory")) {
      return jsonResponse(200, {
        memory_contract_version: "1.0",
        profile: memoryApproved
          ? {
            active_preferences: {
              response_length: {
                category: "response_length",
                signal_id: "response_length--signal-1",
                value: "concise",
                source_event_id: "response_length--signal-1--approved",
              },
            },
            identity_context: {},
          }
          : null,
        unresolved_proposals: memoryApproved
          ? []
          : [{
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
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/reports")) {
      return jsonResponse(200, {
        agent_job_report_contract_version: "1.0",
        reports: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    if (path === "/api/chat/stream") {
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-memory-direct-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  const input = elements.get("[data-chat-input]");
  input.value = "Keep chat pending";
  input.oninput();
  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
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
    () => calls.some(([path, init]) => (
      path === "/api/users/wifiknight/memory/proposals/response_length--proposal-1/approve"
      && init.method === "POST"
    )),
    () => JSON.stringify(calls.map(([path, init]) => [path, init.method])),
  );
  await waitFor(
    () => !findTree(
      elements.get("[data-memory-panel]"),
      (item) => item.attributes["data-memory-proposal"] === "response_length--proposal-1",
    ),
    () => elements.get("[data-memory-panel]").textContent,
  );

  assert.equal(
    calls.filter(([path]) => path === "/api/chat/stream").length,
    1,
  );
  assert.equal(calls.some(([path]) => path === "/api/chat"), false);
  assert.equal(elements.get("[data-chat-error]").textContent, "");
  chatStream.complete({
    response: "Done",
    actions: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    memory_clarifications: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    continuity_choices: [],
    adaptations: [],
  });
});

test("note proposal approval during a pending chat uses direct note API", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
  const calls = [];
  let noteApproved = false;
  let chatStreamCount = 0;
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
    if (
      path === "/api/users/wifiknight/projects/agent-col/notes/proposals/note-proposal-1/approve"
      && init.method === "POST"
    ) {
      noteApproved = true;
      return jsonResponse(200, {
        note_contract_version: "1.0",
        action: {
          action_name: "approve_collaborative_note",
          status: "completed",
        },
        event: { event_id: "note-event-1", event_type: "approved" },
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/notes")) {
      return jsonResponse(200, {
        note_contract_version: "1.0",
        notes: noteApproved
          ? [{
            note_id: "note-1",
            note_kind: "constraint",
            title: "API version",
            body: "Use API version 3.",
            revision: 1,
            status: "active",
          }]
          : [],
        pending_proposals: noteApproved
          ? []
          : [{
            proposal_id: "note-proposal-1",
            note_kind: "constraint",
            title: "API version",
            body: "Use API version 3.",
            status: "pending",
            expires_at: "2099-09-02T12:00:00Z",
          }],
        next_cursor: null,
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/chat-sessions")) {
      return jsonResponse(200, {
        chat_contract_version: "1.0",
        sessions: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/reports")) {
      return jsonResponse(200, {
        agent_job_report_contract_version: "1.0",
        reports: [],
      });
    }
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    if (path === "/api/chat/stream") {
      chatStreamCount += 1;
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-note-direct-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  const input = elements.get("[data-chat-input]");
  input.value = "Keep chat pending";
  input.oninput();
  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  await waitFor(
    () => chatStreamCount === 1,
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  await waitFor(
    () => findTree(
      elements.get("[data-notes-panel]"),
      (item) => item.attributes["data-disclosure-toggle"] === "note-proposal",
    ),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  const proposalToggle = findTree(
    elements.get("[data-notes-panel]"),
    (item) => item.attributes["data-disclosure-toggle"] === "note-proposal",
  );
  proposalToggle.onclick();
  const approve = findTree(
    elements.get("[data-notes-panel]"),
    (item) => item.attributes["data-note-decision"] === "approve",
  );
  approve.onclick();
  await waitFor(
    () => calls.some(([path, init]) => (
      path === "/api/users/wifiknight/projects/agent-col/notes/proposals/note-proposal-1/approve"
      && init.method === "POST"
    )),
    () => JSON.stringify(calls.map(([path, init]) => [path, init.method])),
  );

  assert.equal(
    calls.filter(([path]) => path === "/api/chat/stream").length,
    1,
  );
  assert.equal(calls.some(([path]) => path === "/api/chat"), false);
  assert.equal(elements.get("[data-chat-error]").textContent, "");
  chatStream.complete({
    response: "Done",
    actions: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    memory_clarifications: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    continuity_choices: [],
    adaptations: [],
  });
});

test("artifact lifecycle actions during a pending chat use direct work API", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
  const calls = [];
  let archived = false;
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
    if (
      path === "/api/projects/agent-col/artifacts/artifact--script/archive"
      && init.method === "POST"
    ) {
      archived = true;
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        metadata: {
          reference: {
            artifact_id: "artifact--script",
            artifact_type: "single_file_artifact",
            display_label: "Build script",
          },
          lifecycle_status: "archived",
        },
      });
    }
    if (path.startsWith("/api/projects/agent-col/blueprints")) {
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        artifacts: [],
        next_before: null,
      });
    }
    if (path.startsWith("/api/projects/agent-col/artifacts")) {
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        artifacts: archived
          ? []
          : [{
            reference: {
              artifact_id: "artifact--script",
              artifact_type: "single_file_artifact",
              display_label: "Build script",
            },
            created_at: "2026-09-01T12:00:00Z",
          }],
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
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    if (path === "/api/chat/stream") {
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-artifact-direct-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  const input = elements.get("[data-chat-input]");
  input.value = "Keep chat pending";
  input.oninput();
  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );

  await waitFor(
    () => findTree(
      elements.get("[data-work-list]"),
      (item) => item.attributes["data-disclosure-toggle"] === "artifact-lifecycle",
    ),
    () => textTree(elements.get("[data-work-list]")),
  );
  const artifactToggle = findTree(
    elements.get("[data-work-list]"),
    (item) => item.attributes["data-disclosure-toggle"] === "artifact-lifecycle",
  );
  artifactToggle.onclick();
  const archive = findTree(
    elements.get("[data-work-list]"),
    (item) => item.attributes["data-archive-artifact"] === "",
  );
  archive.onclick({ stopPropagation() {} });
  await waitFor(
    () => calls.some(([path, init]) => (
      path === "/api/projects/agent-col/artifacts/artifact--script/archive"
      && init.method === "POST"
    )),
    () => JSON.stringify(calls.map(([path, init]) => [path, init.method])),
  );

  assert.equal(
    calls.filter(([path]) => path === "/api/chat/stream").length,
    1,
  );
  assert.equal(elements.get("[data-chat-error]").textContent, "");
  chatStream.complete({
    response: "Done",
    actions: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    memory_clarifications: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    continuity_choices: [],
    adaptations: [],
  });
});

test("artifact feedback during a pending chat uses direct work API", async () => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  globalThis.sessionStorage = memoryStorage();
  const chatStream = createControlledSseResponse();
  const calls = [];
  let feedbackRecorded = false;
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
    if (path === "/api/projects/agent-col/blueprints/blueprint--plan") {
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        metadata: {
          reference: {
            project_id: "agent-col",
            artifact_id: "blueprint--plan",
            artifact_type: "blueprint",
            display_label: "Launch plan",
            schema_version: "2.0",
          },
        },
        blueprint: {
          synthesized_conceptual_model: {
            project_name: "Launch plan",
            core_value_proposition: "Coordinate the release.",
            in_scope: [],
            out_of_scope: [],
            assumptions: [],
          },
          architectural_decisions: [],
          socratic_clarifying_questions: [],
          step_by_step_execution_roadmap: [],
          diagnostic_warnings: [],
        },
        feedback_targets: [{
          target_id: "target--whole",
          target_kind: "whole_blueprint",
          display_label: "Whole artifact",
        }],
      });
    }
    if (
      path === "/api/projects/agent-col/blueprints/blueprint--plan/feedback"
      && init.method === "POST"
    ) {
      feedbackRecorded = true;
      return jsonResponse(200, {
        feedback_contract_version: "1.0",
        action: {
          action_name: "record_blueprint_feedback",
          status: "completed",
        },
        feedback: {
          feedback_id: "feedback--artifact-feedback--1",
          artifact_id: "blueprint--plan",
          target_id: "target--whole",
          target_kind: "whole_blueprint",
          decision: "accepted",
          schema_version: "2.0",
          created_at: "2026-09-02T12:00:00Z",
        },
      });
    }
    if (path === "/api/projects/agent-col/blueprints/blueprint--plan/feedback?limit=20") {
      return jsonResponse(200, {
        feedback_contract_version: "1.0",
        artifact_id: "blueprint--plan",
        events: feedbackRecorded
          ? [{
            reference: {
              feedback_id: "feedback--artifact-feedback--1",
              artifact_id: "blueprint--plan",
              target_id: "target--whole",
              target_kind: "whole_blueprint",
              decision: "accepted",
              schema_version: "2.0",
              created_at: "2026-09-02T12:00:00Z",
            },
            feedback_text: "Keep this direction.",
            correction_text: null,
            originating_session_id: "session--1",
            source_message_id: "artifact-feedback--1",
            originating_turn_id: "artifact-feedback--1",
            status: "active",
          }]
          : [],
        next_before: null,
      });
    }
    if (path.startsWith("/api/projects/agent-col/blueprints")) {
      return jsonResponse(200, {
        artifact_contract_version: "1.0",
        artifacts: [{
          reference: {
            project_id: "agent-col",
            artifact_id: "blueprint--plan",
            artifact_type: "blueprint",
            display_label: "Launch plan",
            schema_version: "2.0",
          },
          created_at: "2026-09-01T12:00:00Z",
          feedback_counts: { accepted: feedbackRecorded ? 1 : 0 },
        }],
        next_before: null,
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
    if (path.startsWith("/api/users/wifiknight/projects/agent-col/agent/jobs")) {
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    }
    if (path === "/api/chat/stream") {
      return chatStream.response;
    }
    throw new Error(`Unexpected fetch: ${path}`);
  };

  await import(`../../frontend/app.mjs?runtime-artifact-feedback-direct-${Date.now()}`);
  await waitFor(
    () => calls.some(([path]) => path === "/api/auth/config"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  const input = elements.get("[data-chat-input]");
  input.value = "Keep chat pending";
  input.oninput();
  elements.get("[data-chat-form]").onsubmit({ preventDefault() {} });
  await waitFor(
    () => calls.some(([path]) => path === "/api/chat/stream"),
    () => JSON.stringify(calls.map(([path]) => path)),
  );
  await waitFor(
    () => findTree(
      elements.get("[data-work-list]"),
      (item) => item.attributes["data-artifact-id"] === "blueprint--plan",
    ),
    () => textTree(elements.get("[data-work-list]")),
  );
  const blueprint = findTree(
    elements.get("[data-work-list]"),
    (item) => item.attributes["data-artifact-id"] === "blueprint--plan",
  );
  blueprint.onclick({ target: blueprint });
  await waitFor(
    () => findTree(
      elements.get("[data-work-detail]"),
      (item) => item.attributes["data-feedback-target"] === "target--whole",
    ),
    () => textTree(elements.get("[data-work-detail]")),
  );

  const form = findTree(
    elements.get("[data-work-detail]"),
    (item) => item.attributes["data-feedback-target"] === "target--whole",
  );
  const feedback = form.children.find((child) => (
    child.tagName === "textarea" && child.name === "feedback_text"
  ));
  feedback.value = "Keep this direction.";
  form.onsubmit({ preventDefault() {} });
  await waitFor(
    () => calls.some(([path, init]) => (
      path === "/api/projects/agent-col/blueprints/blueprint--plan/feedback"
      && init.method === "POST"
    )),
    () => JSON.stringify(calls.map(([path, init]) => [path, init.method])),
  );

  assert.equal(
    calls.filter(([path]) => path === "/api/chat/stream").length,
    1,
  );
  assert.equal(calls.some(([path]) => path === "/api/chat"), false);
  assert.equal(elements.get("[data-chat-error]").textContent, "");
  chatStream.complete({
    response: "Done",
    actions: [],
    artifacts: [],
    artifact_feedback: [],
    memory_proposals: [],
    memory_clarifications: [],
    collaborative_note_proposals: [],
    collaborative_note_events: [],
    continuity_receipts: [],
    continuity_choices: [],
    adaptations: [],
  });
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
    "[data-agents-panel]",
    "[data-agents-summary]",
  ]) {
    if (!elements.has(selector)) {
      elements.set(selector, node());
    }
  }
  elements.get("[data-chat-form]").tagName = "form";

  const drawerButtons = [node("button"), node("button")];
  drawerButtons[0].setAttribute("data-drawer-toggle", "left");
  drawerButtons[1].setAttribute("data-drawer-toggle", "right");
  const sectionButtons = ["workspace", "work", "notes", "memory", "chats", "agents"]
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
