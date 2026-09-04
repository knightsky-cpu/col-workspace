import {
  apiFetchJson,
  apiFetchSse,
  archiveNote,
  archiveArtifact,
  createArtifactVersion,
  createNoteCorrection,
  createNoteProposal,
  createWorkspace,
  decideMemoryProposal,
  decideNoteProposal,
  deleteNote,
  deleteArtifact,
  deleteMemorySignal,
  deleteWorkspace,
  getArtifact,
  getAuthConfig,
  getAuthSession,
  getChatSession,
  getBlueprint,
  getNote,
  inspectMemory,
  listAgentJobReports,
  listAgentJobs,
  listNotes,
  listChatSessions,
  listArtifacts,
  listWorkspaces,
  listBlueprintFeedback,
  listBlueprints,
  recordBlueprintFeedback,
  restoreNote,
  restoreArtifact,
  revokeMemorySignal,
  selectContinuityChoice,
  selectMemoryClarification,
  streamAgentJobs,
  synthesizeSpeechAudio,
  transcribeSpeechAudio,
  updateArtifactMetadata,
} from "./api.mjs";
import {
  authRequiresGoogleSignIn,
  googleSessionDisplayLabel,
  googleSessionToContext,
  googleWorkspaceDisplayLabel,
  initializeGoogleSignIn,
  loadGoogleIdentityScript,
} from "./auth-view.mjs";
import { createAgentsView } from "./agents-view.mjs";
import { createChatsView } from "./chats-view.mjs";
import { createChatView } from "./chat-view.mjs";
import {
  clearOrdinaryChatRequest,
  loadOrdinaryChatRequest,
  storeOrdinaryChatRequest,
} from "./chat-request-recovery.mjs";
import { createMemoryView } from "./memory-view.mjs";
import { createNotesView } from "./notes-view.mjs";
import { createWorkView } from "./work-view.mjs";
import { createWorkspaceView } from "./workspace-view.mjs";
import { renderWorkspaceIndicator } from "./workspace-indicator.mjs";
import {
  buildExactRetryRequest,
  buildOrdinaryChatRequest,
  readContextForm,
  selectChatEndpoint,
} from "./requests.mjs";
import {
  createInitialLayoutState,
  isDrawerExpanded,
  isSectionExpanded,
  setArtifactDrawerMode,
  setDrawerCollapsed,
  setSectionExpanded,
} from "./workspace-layout.mjs";
import {
  acceptContext,
  appendPendingResponseDelta,
  beginAgentJobsLoad,
  beginAgentReportsLoad,
  beginWorkspaceListLoad,
  beginChatSessionDetailLoad,
  beginChatSessionListLoad,
  beginMemoryLoad,
  beginNoteDetailLoad,
  beginNoteRequest,
  beginNotesLoad,
  beginPendingTurn,
  beginWorkDetailLoad,
  beginWorkListLoad,
  completeMemoryLoad,
  completeMemorySignalMutation,
  completeNoteDetailLoad,
  completeNoteRequest,
  completeNotesLoad,
  completeChatSessionDetailLoad,
  completeChatSessionListLoad,
  completeWorkspaceCreate,
  completeWorkspaceDelete,
  completeWorkspaceListLoad,
  completeWorkArchive,
  completeWorkDelete,
  completeWorkDetailLoad,
  completeWorkListLoad,
  completeWorkMetadataUpdate,
  completeWorkVersionCreate,
  completeWorkRestore,
  completePendingTurn,
  completeAgentJobsLoad,
  completeAgentReportsLoad,
  createInitialState,
  expandChatDisclosure,
  expandNoteDetailDisclosure,
  failAgentJobsLoad,
  failAgentReportsLoad,
  failMemoryLoad,
  failNoteDetailLoad,
  failNoteRequest,
  failNotesLoad,
  failChatSessionDetailLoad,
  failChatSessionListLoad,
  failWorkspaceListLoad,
  failPendingTurn,
  failWorkDetailLoad,
  failWorkListLoad,
  restoreRecoveredTurn,
  selectCanSubmit,
  selectNeedsReceiptRefresh,
  selectWorkspace,
  selectWorkRefreshPlan,
  setNotesStatusFilter,
  setWorkLifecycleStatus,
  hideAgentReports,
  showAgentReports,
  storePendingNoteProposal,
  startNewConversation,
  toggleArtifactDisclosure,
  toggleChatDisclosure,
  toggleMemoryEventsDisclosure,
  toggleMemoryDisclosure,
  toggleNoteDetailDisclosure,
  toggleNoteProposalDisclosure,
} from "./state.mjs";
import { setText } from "./render.mjs";

let state = createInitialState();
let chatView = null;
let workView = null;
let memoryView = null;
let notesView = null;
let chatsView = null;
let agentsView = null;
let workspaceView = null;
let layoutState = createInitialLayoutState();
let authConfig = null;
let verifiedGoogleContext = null;
let speechRecording = null;
let speechStartPending = false;
let speechPlaybackToken = 0;
let speechPlaybackAudio = null;
let speechPlaybackObjectUrl = null;
let speechPlaybackAbortControllers = new Set();
let agentJobsRefreshTimer = null;
let agentJobsRefreshToken = 0;
let agentJobsConsecutiveFailures = 0;
let agentJobsStreamAbortController = null;
let agentJobsStreamUnavailable = false;
const refreshedCompletedAgentJobs = new Set();

const SPEECH_RECORDING_MIME_TYPES = Object.freeze([
  "audio/webm;codecs=opus",
  "audio/webm",
]);
const SPEECH_TRAILING_SILENCE_MS = 3000;
const SPEECH_ANALYSER_FFT_SIZE = 2048;
const SPEECH_BASELINE_RMS = 0.01;
const SPEECH_MIN_RMS_ABOVE_FLOOR = 0.04;
const AGENT_JOBS_FAST_REFRESH_MS = 300;
const AGENT_JOBS_RETRY_LIMIT = 2;
const AGENT_JOB_ACTIVE_STATUSES = new Set(["queued", "running"]);

function showAuthError(message) {
  const error = document.querySelector("[data-auth-error]");
  setText(error, message);
  error.hidden = false;
}

function clearAuthError() {
  const error = document.querySelector("[data-auth-error]");
  setText(error, "");
  error.hidden = true;
}

function showWorkspace() {
  document.querySelector("[data-context-error]").hidden = true;
  document.querySelector("[data-workspace]").hidden = false;
  document.querySelector(".context-gate").hidden = true;
  document.querySelector("[data-new-conversation]").disabled = false;
  for (const button of document.querySelectorAll("[data-drawer-toggle]")) {
    button.disabled = false;
  }
  const artifactExpandButton = document.querySelector("[data-artifacts-expand]");
  artifactExpandButton.disabled = false;
  const leftRefreshButton = document.querySelector("[data-left-refresh]");
  leftRefreshButton.disabled = false;
  renderLayout();
  document.querySelector("#conversation-workspace").focus();
}

function showContextError(message) {
  const error = document.querySelector("[data-context-error]");
  setText(error, message);
  error.hidden = false;
}

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

function newestFirst(a, b) {
  const left = Date.parse(a.created_at ?? "");
  const right = Date.parse(b.created_at ?? "");
  if (Number.isNaN(left) && Number.isNaN(right)) {
    return 0;
  }
  if (Number.isNaN(left)) {
    return 1;
  }
  if (Number.isNaN(right)) {
    return -1;
  }
  return right - left;
}

function selectedArtifactMetadata(artifactId) {
  return state.work.list.items.find((item) => (
    item.reference?.artifact_id === artifactId
  )) ?? null;
}

function artifactIdSet(items) {
  return new Set(
    items
      .map((item) => item.reference?.artifact_id)
      .filter((artifactId) => typeof artifactId === "string" && artifactId),
  );
}

function showMemoryError(message) {
  const error = document.querySelector("[data-memory-error]");
  setText(error, message);
  error.hidden = false;
}

function showWorkspaceError(message) {
  const error = document.querySelector("[data-workspace-error]");
  setText(error, message);
  error.hidden = false;
}

function clearWorkspaceError() {
  const error = document.querySelector("[data-workspace-error]");
  setText(error, "");
  error.hidden = true;
}

function clearMemoryError() {
  const error = document.querySelector("[data-memory-error]");
  setText(error, "");
  error.hidden = true;
}

function showNotesError(message) {
  const error = document.querySelector("[data-notes-error]");
  setText(error, message);
  error.hidden = false;
}

function clearNotesError() {
  const error = document.querySelector("[data-notes-error]");
  setText(error, "");
  error.hidden = true;
}

const ORDINARY_CHAT_WAITING_QUIPS = Object.freeze([
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

function selectOrdinaryChatWaitingQuip() {
  const index = Math.floor(Math.random() * ORDINARY_CHAT_WAITING_QUIPS.length);
  return ORDINARY_CHAT_WAITING_QUIPS[index];
}

function renderChatStatusLetters(status, message) {
  status.replaceChildren();
  status.setAttribute("aria-label", message);
  [...message].forEach((character, index) => {
    const letter = document.createElement("span");
    letter.classList.add("chat-status__letter");
    letter.setAttribute("aria-hidden", "true");
    letter.style.setProperty("--chat-status-letter-index", String(index));
    setText(letter, character);
    status.append(letter);
  });
}

function setChatStatus(message, statusState = "") {
  const status = document.querySelector("[data-chat-status]");
  status.removeAttribute("aria-label");
  if (statusState) {
    renderChatStatusLetters(status, message);
    status.dataset.chatStatusState = statusState;
    return;
  }
  setText(status, message);
  delete status.dataset.chatStatusState;
}

function setSpeechStatus(message) {
  const statusElement = document.querySelector("[data-speech-status]");
  if (statusElement) {
    setText(statusElement, message);
  }
}

function setSpeechToggleState(stateName, label) {
  const button = document.querySelector("[data-speech-toggle]");
  if (!button) {
    return;
  }
  button.dataset.speechState = stateName;
  button.textContent = label;
  button.disabled = stateName === "starting" || stateName === "transcribing";
  button.setAttribute("aria-pressed", stateName === "recording" ? "true" : "false");
  button.setAttribute(
    "aria-label",
    stateName === "recording" ? "Stop voice input" : "Start voice input",
  );
}

function setSpeechUi(stateName, message) {
  setSpeechToggleState(stateName, stateName === "recording" ? "Stop" : "Mic");
  setSpeechStatus(message);
}

function isComposerEmpty() {
  return !String(document.querySelector("[data-chat-input]")?.value ?? "").trim();
}

function selectSpeechRecordingMimeType() {
  if (!globalThis.MediaRecorder) {
    throw new Error("Microphone recording is unavailable.");
  }
  if (typeof globalThis.MediaRecorder.isTypeSupported !== "function") {
    return "audio/webm";
  }
  for (const mimeType of SPEECH_RECORDING_MIME_TYPES) {
    if (globalThis.MediaRecorder.isTypeSupported(mimeType)) {
      return mimeType;
    }
  }
  throw new Error("Microphone recording is unavailable.");
}

function stopSpeechTracks(stream) {
  for (const track of stream?.getTracks?.() ?? []) {
    track.stop();
  }
}

function computeSpeechRms(buffer) {
  let total = 0;
  for (const value of buffer) {
    const normalized = (value - 128) / 128;
    total += normalized * normalized;
  }
  return Math.sqrt(total / buffer.length);
}

function createSpeechSilenceDetector(recording) {
  const AudioContextConstructor = globalThis.AudioContext ?? globalThis.webkitAudioContext;
  if (
    !AudioContextConstructor
    || typeof globalThis.requestAnimationFrame !== "function"
    || typeof globalThis.cancelAnimationFrame !== "function"
  ) {
    return null;
  }
  let audioContext = null;
  let source = null;
  let analyser = null;
  try {
    audioContext = new AudioContextConstructor();
    source = audioContext.createMediaStreamSource(recording.stream);
    analyser = audioContext.createAnalyser();
  } catch {
    audioContext?.close?.();
    return null;
  }
  analyser.fftSize = SPEECH_ANALYSER_FFT_SIZE;
  source.connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);
  let animationFrame = null;
  let cleanedUp = false;
  let noiseFloor = SPEECH_BASELINE_RMS;
  let speechHasStarted = false;
  let silenceStartedAt = null;

  const cleanup = () => {
    if (cleanedUp) {
      return;
    }
    cleanedUp = true;
    if (animationFrame !== null) {
      globalThis.cancelAnimationFrame(animationFrame);
      animationFrame = null;
    }
    source.disconnect?.();
    analyser.disconnect?.();
    audioContext.close?.();
  };

  const analyze = (time) => {
    if (cleanedUp || speechRecording !== recording || recording.stopRequested) {
      cleanup();
      return;
    }
    analyser.getByteTimeDomainData(samples);
    const rms = computeSpeechRms(samples);
    const speechThreshold = Math.max(
      noiseFloor + SPEECH_MIN_RMS_ABOVE_FLOOR,
      noiseFloor * 3,
    );
    const speechDetected = rms >= speechThreshold;
    if (speechDetected) {
      speechHasStarted = true;
      silenceStartedAt = null;
    } else {
      noiseFloor = Math.min(
        Math.max(rms, SPEECH_BASELINE_RMS),
        noiseFloor * 0.95 + rms * 0.05,
      );
      if (speechHasStarted) {
        if (silenceStartedAt === null) {
          silenceStartedAt = time;
        } else if (time - silenceStartedAt >= SPEECH_TRAILING_SILENCE_MS) {
          stopSpeechRecording();
          return;
        }
      }
    }
    animationFrame = globalThis.requestAnimationFrame(analyze);
  };

  animationFrame = globalThis.requestAnimationFrame(analyze);
  return { cleanup };
}

async function finishSpeechRecording(recording) {
  recording.silenceDetector?.cleanup();
  recording.stopWatchingComposer?.();
  stopSpeechTracks(recording.stream);
  setSpeechUi("transcribing", "Transcribing audio...");
  try {
    const audio = new Blob(recording.chunks, { type: recording.mimeType });
    const response = await transcribeSpeechAudio(audio, authOptions());
    const transcript = String(response?.transcript ?? "").trim();
    ensureChatView().insertComposerText(transcript);
    if (transcript && recording.autoSubmitEligible) {
      ensureChatView().submitComposer();
    }
    setSpeechUi("idle", transcript ? "Transcript added." : "No speech recognized.");
  } catch {
    setSpeechUi("error", "Unable to transcribe audio.");
  } finally {
    if (speechRecording === recording) {
      speechRecording = null;
    }
    speechStartPending = false;
    const button = document.querySelector("[data-speech-toggle]");
    if (button) {
      button.disabled = false;
    }
  }
}

async function startSpeechRecording() {
  if (speechRecording !== null || speechStartPending) {
    return;
  }
  speechStartPending = true;
  setSpeechUi("starting", "Requesting microphone...");
  let stream = null;
  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Microphone access is unavailable.");
    }
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = selectSpeechRecordingMimeType();
    const recorder = new MediaRecorder(stream, { mimeType });
    const composerWasEmpty = isComposerEmpty();
    const recording = {
      recorder,
      stream,
      chunks: [],
      mimeType,
      composerWasEmpty,
      autoSubmitEligible: composerWasEmpty,
      stopRequested: false,
      silenceDetector: null,
      stopWatchingComposer: null,
    };
    const composerInput = document.querySelector("[data-chat-input]");
    const revokeAutoSubmit = () => {
      recording.autoSubmitEligible = false;
    };
    composerInput?.addEventListener?.("input", revokeAutoSubmit);
    recording.stopWatchingComposer = () => {
      composerInput?.removeEventListener?.("input", revokeAutoSubmit);
    };
    recorder.ondataavailable = (event) => {
      if (event.data?.size > 0) {
        recording.chunks.push(event.data);
      }
    };
    recorder.onstop = () => {
      finishSpeechRecording(recording);
    };
    recorder.start();
    speechRecording = recording;
    recording.silenceDetector = createSpeechSilenceDetector(recording);
    speechStartPending = false;
    setSpeechUi("recording", "Recording voice input. Press Stop when finished.");
  } catch {
    stopSpeechTracks(stream);
    speechRecording = null;
    speechStartPending = false;
    setSpeechUi("error", "Microphone access denied or unavailable.");
    const button = document.querySelector("[data-speech-toggle]");
    if (button) {
      button.disabled = false;
    }
  }
}

function stopSpeechRecording() {
  if (speechRecording === null) {
    return;
  }
  const { recorder, stream } = speechRecording;
  if (speechRecording.stopRequested) {
    return;
  }
  speechRecording.stopRequested = true;
  speechRecording.silenceDetector?.cleanup();
  stopSpeechTracks(stream);
  if (recorder.state !== "inactive") {
    recorder.stop();
  }
}

function selectedSpeechVoiceId() {
  const select = document.querySelector("[data-speech-voice]");
  return select?.value === "male" ? "male" : "female";
}

function spokenResponsesEnabled() {
  return document.querySelector("[data-spoken-responses-toggle]")?.checked === true;
}

function setSpeechPlaybackUi(active) {
  const stopButton = document.querySelector("[data-tts-stop]");
  if (!stopButton) {
    return;
  }
  stopButton.disabled = !active;
  stopButton.hidden = !active;
}

function cleanupSpeechPlaybackAudio() {
  if (speechPlaybackAudio !== null) {
    speechPlaybackAudio.pause();
    speechPlaybackAudio = null;
  }
  if (speechPlaybackObjectUrl !== null) {
    URL.revokeObjectURL(speechPlaybackObjectUrl);
    speechPlaybackObjectUrl = null;
  }
}

function stopSpeechPlayback() {
  speechPlaybackToken += 1;
  for (const controller of speechPlaybackAbortControllers) {
    controller.abort();
  }
  speechPlaybackAbortControllers.clear();
  cleanupSpeechPlaybackAudio();
  setSpeechPlaybackUi(false);
}

async function deriveModelMessageId(turn) {
  const persistedId = turn?.response?.message_id;
  if (typeof persistedId === "string" && persistedId.trim()) {
    return persistedId;
  }
  const idempotencyKey = turn?.request?.key;
  if (!idempotencyKey || !globalThis.crypto?.subtle) {
    throw new Error("Assistant response cannot be spoken because its message locator is unavailable.");
  }
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(idempotencyKey),
  );
  const hash = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return `turn--${hash}--model`;
}

function playSpeechAudio(audioBlob, token) {
  return new Promise((resolve, reject) => {
    if (token !== speechPlaybackToken) {
      resolve();
      return;
    }
    cleanupSpeechPlaybackAudio();
    const objectUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(objectUrl);
    speechPlaybackObjectUrl = objectUrl;
    speechPlaybackAudio = audio;
    setSpeechPlaybackUi(true);
    audio.addEventListener("ended", () => {
      if (speechPlaybackAudio === audio) {
        speechPlaybackAudio = null;
      }
      if (speechPlaybackObjectUrl === objectUrl) {
        URL.revokeObjectURL(objectUrl);
        speechPlaybackObjectUrl = null;
      }
      resolve();
    });
    audio.addEventListener("error", () => {
      cleanupSpeechPlaybackAudio();
      reject(new Error("Unable to play audio."));
    });
    Promise.resolve(audio.play()).catch((error) => {
      cleanupSpeechPlaybackAudio();
      reject(error);
    });
  });
}

function requestSpeechAudioChunk({
  userId,
  projectId,
  sessionId,
  messageId,
  chunkIndex,
  voiceId,
}) {
  const controller = new AbortController();
  speechPlaybackAbortControllers.add(controller);
  return synthesizeSpeechAudio(
    userId,
    {
      project_id: projectId,
      session_id: sessionId,
      message_id: messageId,
      chunk_index: chunkIndex,
      voice_id: voiceId,
    },
    {
      ...authOptions(),
      signal: controller.signal,
    },
  ).finally(() => {
    speechPlaybackAbortControllers.delete(controller);
  });
}

function settleSpeechChunk(promise) {
  return promise.then(
    (chunk) => ({ chunk, error: null }),
    (error) => ({ chunk: null, error }),
  );
}

async function speakAssistantTurn(turn) {
  if (!state.context) {
    return;
  }
  stopSpeechPlayback();
  const token = speechPlaybackToken + 1;
  speechPlaybackToken = token;
  setSpeechStatus("Preparing speech...");
  try {
    const messageId = await deriveModelMessageId(turn);
    const voiceId = selectedSpeechVoiceId();
    let chunkIndex = 0;
    let chunkCount = 1;
    let nextChunk = requestSpeechAudioChunk({
      userId: state.context.user_id,
      projectId: state.context.project_id,
      sessionId: state.context.session_id,
      messageId,
      chunkIndex,
      voiceId,
    });
    while (chunkIndex < chunkCount) {
      if (token !== speechPlaybackToken) {
        return;
      }
      const chunk = await nextChunk;
      if (token !== speechPlaybackToken) {
        return;
      }
      chunkCount = Number.isFinite(chunk.chunkCount) && chunk.chunkCount > 0
        ? chunk.chunkCount
        : 1;
      const nextChunkIndex = chunkIndex + 1;
      const prefetchedNextChunk = nextChunkIndex < chunkCount
        ? settleSpeechChunk(requestSpeechAudioChunk({
          userId: state.context.user_id,
          projectId: state.context.project_id,
          sessionId: state.context.session_id,
          messageId,
          chunkIndex: nextChunkIndex,
          voiceId,
        }))
        : null;
      await playSpeechAudio(chunk.audio, token);
      chunkIndex += 1;
      if (prefetchedNextChunk !== null) {
        const result = await prefetchedNextChunk;
        if (result.error !== null) {
          throw result.error;
        }
        nextChunk = Promise.resolve(result.chunk);
      }
    }
    if (token === speechPlaybackToken) {
      setSpeechStatus("");
      setSpeechPlaybackUi(false);
    }
  } catch {
    if (token === speechPlaybackToken) {
      setSpeechUi("error", "Unable to play assistant response.");
      setSpeechPlaybackUi(false);
    }
  }
}

function speakCompletedTurnIfEnabled(turn) {
  if (!spokenResponsesEnabled()) {
    return;
  }
  if (!String(turn?.response?.response ?? "").trim()) {
    return;
  }
  speakAssistantTurn(turn);
}

function authOptions(options = {}) {
  return {
    ...options,
    authToken: state.context?.auth_token ?? null,
  };
}

function setAuthModeLabel(text) {
  setText(document.querySelector("[data-auth-mode-label]"), text);
}

function setContextFormEnabled(enabled) {
  for (const input of document.querySelectorAll("[data-context-form] input")) {
    input.disabled = !enabled;
  }
  document.querySelector('[data-context-form] button[type="submit"]').disabled = !enabled;
}

function populateGoogleContext(session, authToken) {
  const projectInput = document.querySelector('[name="project_id"]');
  verifiedGoogleContext = googleSessionToContext(
    session,
    projectInput.value.trim() || "agent-col",
    authToken,
  );
  projectInput.value = googleWorkspaceDisplayLabel();
  projectInput.readOnly = true;
  const userInput = document.querySelector('[name="user_id"]');
  userInput.value = googleSessionDisplayLabel(session);
  userInput.readOnly = true;
  const accountStatus = document.querySelector("[data-google-account-status]");
  setText(accountStatus, googleSessionDisplayLabel(session));
  accountStatus.hidden = false;
  setContextFormEnabled(true);
  setAuthModeLabel(googleSessionDisplayLabel(session));
}

function contextForSubmit(form) {
  if (!authRequiresGoogleSignIn(authConfig)) {
    return readContextForm(new FormData(form));
  }
  if (verifiedGoogleContext === null) {
    throw new Error("Sign in with Google before entering the workspace.");
  }
  const formData = new FormData(form);
  return googleSessionToContext(
    {
      authenticated: true,
      user_id: verifiedGoogleContext.user_id,
      workspace_project_id: verifiedGoogleContext.project_id,
    },
    formData.get("project_id"),
    verifiedGoogleContext.auth_token,
  );
}

async function bootstrapAuth() {
  const form = document.querySelector("[data-context-form]");
  const googleSignIn = document.querySelector("[data-google-signin]");
  try {
    authConfig = await getAuthConfig();
  } catch (error) {
    showContextError(error.message);
    setAuthModeLabel("Authentication unavailable");
    setContextFormEnabled(false);
    return;
  }

  if (!authRequiresGoogleSignIn(authConfig)) {
    setAuthModeLabel("Local development mode");
    googleSignIn.hidden = true;
    form.hidden = false;
    setContextFormEnabled(true);
    return;
  }

  setAuthModeLabel("Google authentication required");
  googleSignIn.hidden = false;
  form.hidden = false;
  setContextFormEnabled(false);
  try {
    await loadGoogleIdentityScript();
    initializeGoogleSignIn({
      clientId: authConfig.google_client_id,
      buttonContainer: document.querySelector("[data-google-button]"),
      async onCredential(authToken) {
        clearAuthError();
        try {
          const session = await getAuthSession(authToken);
          populateGoogleContext(session, authToken);
        } catch (error) {
          showAuthError(error.message);
        }
      },
    });
  } catch (error) {
    showAuthError(error.message);
  }
}

function renderWorkspace() {
  renderTopBarWorkspaceIndicator();
  document.querySelector("[data-new-conversation]").disabled = (
    state.pendingTurn !== null
    || state.lastFailure?.recovered === true
  );
  ensureWorkspaceView().render(state);
  ensureChatView().render(state);
  ensureWorkView().render(state);
  ensureNotesView().render(state);
  ensureMemoryView().render(state);
  ensureChatsView().render(state);
  ensureAgentsView().render(state);
  renderLayout();
}

function renderChatSurface() {
  document.querySelector("[data-new-conversation]").disabled = (
    state.pendingTurn !== null
    || state.lastFailure?.recovered === true
  );
  ensureChatView().render(state);
}

function renderTopBarWorkspaceIndicator() {
  renderWorkspaceIndicator(
    document.querySelector("[data-workspace-indicator]"),
    state,
  );
}

function setButtonLabel(button, label) {
  if (!button) {
    return;
  }
  if (button.matches("[data-section-toggle]")) {
    return;
  }
  setText(button, label);
}

function renderLayout() {
  const workspace = document.querySelector("[data-workspace]");
  workspace.classList.toggle(
    "workspace-grid--left-collapsed",
    !isDrawerExpanded(layoutState, "left"),
  );
  workspace.classList.toggle(
    "workspace-grid--right-collapsed",
    !isDrawerExpanded(layoutState, "right"),
  );
  workspace.classList.toggle(
    "workspace-grid--artifacts-expanded",
    layoutState.artifactDrawerMode === "expanded",
  );

  for (const button of document.querySelectorAll('[data-drawer-toggle="left"]')) {
    const expanded = isDrawerExpanded(layoutState, "left");
    setButtonLabel(button, expanded ? "Hide" : "Show side panel");
    button.setAttribute("aria-expanded", String(expanded));
  }
  for (const button of document.querySelectorAll('[data-drawer-toggle="right"]')) {
    const expanded = isDrawerExpanded(layoutState, "right");
    setButtonLabel(button, expanded ? "Hide" : "Show Artifacts Viewer");
    button.setAttribute("aria-expanded", String(expanded));
  }

  const artifactExpandButton = document.querySelector("[data-artifacts-expand]");
  const artifactsExpanded = layoutState.artifactDrawerMode === "expanded";
  setButtonLabel(
    artifactExpandButton,
    artifactsExpanded ? "Normal Viewer" : "Expand Artifacts Viewer",
  );
  artifactExpandButton.setAttribute("aria-expanded", String(artifactsExpanded));

  for (const section of [
    "workspace",
    "work",
    "notes",
    "memory",
    "chats",
    "agents",
  ]) {
    const expanded = isSectionExpanded(layoutState, section);
    const content = document.querySelector(`[data-section-content="${section}"]`);
    const toggle = document.querySelector(`[data-section-toggle="${section}"]`);
    content.hidden = !expanded;
    toggle.setAttribute("aria-expanded", String(expanded));
    setButtonLabel(toggle, expanded ? "Collapse" : "Expand");
  }
}

async function loadWorkspaces() {
  if (!state.context) {
    return;
  }
  clearWorkspaceError();
  state = beginWorkspaceListLoad(state);
  ensureWorkspaceView().render(state);
  try {
    const response = await listWorkspaces(
      state.context.user_id,
      authOptions({ limit: 20 }),
    );
    state = completeWorkspaceListLoad(state, response);
  } catch (error) {
    state = failWorkspaceListLoad(state, error);
    showWorkspaceError(error.message);
  }
  renderTopBarWorkspaceIndicator();
  ensureWorkspaceView().render(state);
}

async function loadWorkList(options = {}) {
  if (!state.context) {
    return;
  }
  clearWorkError();
  const lifecycleStatus = state.work.list.lifecycleStatus ?? "active";
  const selectedArtifactIdAtStart = state.work.selectedArtifactId;
  const artifactIdsAtStart = artifactIdSet(state.work.list.items);
  state = beginWorkListLoad(state);
  ensureWorkView().render(state);
  try {
    const artifactOptions = authOptions({
      limit: 20,
      lifecycle_status: lifecycleStatus,
    });
    const [blueprints, artifacts] = lifecycleStatus === "archived"
      ? [
          { artifacts: [] },
          await listArtifacts(state.context.project_id, artifactOptions),
        ]
      : await Promise.all([
          listBlueprints(
            state.context.project_id,
            authOptions({ limit: 20 }),
          ),
          listArtifacts(
            state.context.project_id,
            artifactOptions,
          ),
        ]);
    state = completeWorkListLoad(state, {
      artifacts: [
        ...(Array.isArray(artifacts.artifacts) ? artifacts.artifacts : []),
        ...(Array.isArray(blueprints.artifacts) ? blueprints.artifacts : []),
      ].sort(newestFirst),
      next_before: null,
    });
    if (
      options.selectSingleNewArtifact
      && selectedArtifactIdAtStart === null
      && state.work.selectedArtifactId === selectedArtifactIdAtStart
    ) {
      const newArtifacts = state.work.list.items.filter((item) => {
        const artifactId = item.reference?.artifact_id;
        return typeof artifactId === "string"
          && artifactId
          && !artifactIdsAtStart.has(artifactId);
      });
      if (newArtifacts.length === 1) {
        await loadWorkDetail(newArtifacts[0].reference.artifact_id);
        return;
      }
    }
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
    const metadata = selectedArtifactMetadata(artifactId);
    let detail = null;
    let feedback = { events: [], next_before: null };
    if (metadata?.reference?.artifact_type === "single_file_artifact") {
      detail = await getArtifact(
        state.context.project_id,
        artifactId,
        authOptions(),
      );
    } else {
      [detail, feedback] = await Promise.all([
        getBlueprint(state.context.project_id, artifactId, authOptions()),
        listBlueprintFeedback(
          state.context.project_id,
          artifactId,
          authOptions({ limit: 20 }),
        ),
      ]);
    }
    state = completeWorkDetailLoad(state, detail, feedback);
  } catch (error) {
    state = failWorkDetailLoad(state, error);
    showWorkError(error.message);
  }
  ensureWorkView().render(state);
}

async function loadMemory() {
  if (!state.context) {
    return;
  }
  clearMemoryError();
  state = beginMemoryLoad(state);
  ensureMemoryView().render(state);
  try {
    const response = await inspectMemory(
      state.context.user_id,
      authOptions(),
    );
    state = completeMemoryLoad(state, response);
  } catch (error) {
    state = failMemoryLoad(state, error);
    showMemoryError(error.message);
  }
  ensureMemoryView().render(state);
}

async function loadNotes(statusFilter = state.notes.statusFilter ?? "active") {
  if (!state.context) {
    return;
  }
  clearNotesError();
  state = beginNotesLoad(state, statusFilter);
  ensureNotesView().render(state);
  try {
    const response = await listNotes(
      state.context.user_id,
      state.context.project_id,
      authOptions({ limit: 20, status_filter: statusFilter }),
    );
    state = completeNotesLoad(state, response);
  } catch (error) {
    state = failNotesLoad(state, error);
    showNotesError(error.message);
  }
  ensureNotesView().render(state);
}

async function loadNoteDetail(noteId) {
  if (!state.context) {
    return;
  }
  clearNotesError();
  state = beginNoteDetailLoad(state, noteId);
  ensureNotesView().render(state);
  try {
    const response = await getNote(
      state.context.user_id,
      state.context.project_id,
      noteId,
      authOptions({ limit: 20 }),
    );
    state = completeNoteDetailLoad(state, response);
    state = expandNoteDetailDisclosure(state, response.note?.note_id ?? noteId);
  } catch (error) {
    state = failNoteDetailLoad(state, error);
    showNotesError(error.message);
  }
  ensureNotesView().render(state);
}

async function loadChatSessions() {
  if (!state.context) {
    return;
  }
  state = beginChatSessionListLoad(state);
  ensureChatsView().render(state);
  try {
    const response = await listChatSessions(
      state.context.user_id,
      state.context.project_id,
      authOptions({ limit: 20 }),
    );
    state = completeChatSessionListLoad(state, response);
  } catch (error) {
    state = failChatSessionListLoad(state, error);
  }
  ensureChatsView().render(state);
}

function sameAgentJobsContext(left, right) {
  return (
    left !== null
    && right !== null
    && left.user_id === right.user_id
    && left.project_id === right.project_id
    && left.session_id === right.session_id
  );
}

function hasActiveAgentJobs(jobs) {
  return Array.isArray(jobs)
    && jobs.some((job) => AGENT_JOB_ACTIVE_STATUSES.has(job.status));
}

function shouldRefreshAgentJobs() {
  return Boolean(
    state.context
    && (
      state.pendingTurn !== null
      || hasActiveAgentJobs(state.agents.jobs)
    ),
  );
}

function refreshAuthoritativeResourcesForCompletedJobs(jobs) {
  if (!state.context || !Array.isArray(jobs)) {
    return;
  }
  let shouldRefreshWork = false;
  let shouldRefreshNotes = false;
  let shouldRefreshMemory = false;
  for (const job of jobs) {
    const status = String(job?.status ?? "").toLowerCase();
    const actionKind = job?.action_kind;
    const jobRef = job?.job_ref;
    if (
      status !== "completed"
      || typeof jobRef !== "string"
      || !jobRef
    ) {
      continue;
    }
    const refreshKey = `${actionKind}:${jobRef}`;
    if (refreshedCompletedAgentJobs.has(refreshKey)) {
      continue;
    }
    refreshedCompletedAgentJobs.add(refreshKey);
    if (actionKind === "create_artifact") {
      shouldRefreshWork = true;
    } else if (actionKind === "propose_collaborative_note") {
      shouldRefreshNotes = true;
    } else if (actionKind === "propose_memory_signal") {
      shouldRefreshMemory = true;
    }
  }
  if (shouldRefreshWork) {
    loadWorkList({ selectSingleNewArtifact: true });
  }
  if (shouldRefreshNotes) {
    loadNotes(state.notes.statusFilter);
  }
  if (shouldRefreshMemory) {
    loadMemory();
  }
}

function clearAgentJobsRefreshTimer() {
  if (agentJobsRefreshTimer !== null) {
    globalThis.clearTimeout(agentJobsRefreshTimer);
    agentJobsRefreshTimer = null;
  }
}

function resetAgentJobsRefreshLoop() {
  clearAgentJobsRefreshTimer();
  if (agentJobsStreamAbortController !== null) {
    agentJobsStreamAbortController.abort();
    agentJobsStreamAbortController = null;
  }
  agentJobsRefreshToken += 1;
  agentJobsConsecutiveFailures = 0;
  agentJobsStreamUnavailable = false;
}

function scheduleAgentJobsRefresh(options = {}) {
  clearAgentJobsRefreshTimer();
  if (!shouldRefreshAgentJobs()) {
    return;
  }
  if (
    options.preferStream !== false
    && !agentJobsStreamUnavailable
    && startAgentJobsStream()
  ) {
    return;
  }
  const refreshToken = agentJobsRefreshToken;
  agentJobsRefreshTimer = globalThis.setTimeout(() => {
    agentJobsRefreshTimer = null;
    if (refreshToken !== agentJobsRefreshToken) {
      return;
    }
    loadAgentJobs();
  }, AGENT_JOBS_FAST_REFRESH_MS);
}

function startAgentJobsStream() {
  if (
    !state.context
    || agentJobsStreamAbortController !== null
    || agentJobsStreamUnavailable
  ) {
    return false;
  }
  const streamContext = { ...state.context };
  const refreshToken = agentJobsRefreshToken;
  const abortController = new AbortController();
  agentJobsStreamAbortController = abortController;

  streamAgentJobs(
    streamContext.user_id,
    streamContext.project_id,
    authOptions({
      limit: 50,
      session_id: streamContext.session_id,
      signal: abortController.signal,
    }),
    {
      onSnapshot(payload) {
        if (
          abortController.signal.aborted
          || refreshToken !== agentJobsRefreshToken
          || !sameAgentJobsContext(streamContext, state.context)
        ) {
          return;
        }
        state = completeAgentJobsLoad(state, payload);
        agentJobsConsecutiveFailures = 0;
        ensureAgentsView().render(state);
        refreshAuthoritativeResourcesForCompletedJobs(state.agents.jobs);
      },
    },
  ).catch((error) => {
    if (
      abortController.signal.aborted
      || refreshToken !== agentJobsRefreshToken
      || !sameAgentJobsContext(streamContext, state.context)
    ) {
      return;
    }
    agentJobsStreamUnavailable = true;
    if (!state.agents.jobs.length) {
      state = failAgentJobsLoad(state, error);
      ensureAgentsView().render(state);
    }
  }).finally(() => {
    if (agentJobsStreamAbortController === abortController) {
      agentJobsStreamAbortController = null;
    }
    if (
      !abortController.signal.aborted
      && refreshToken === agentJobsRefreshToken
      && sameAgentJobsContext(streamContext, state.context)
      && shouldRefreshAgentJobs()
    ) {
      scheduleAgentJobsRefresh({ preferStream: false });
    }
  });
  return true;
}

async function loadAgentJobReports() {
  if (!state.context) {
    return;
  }
  const loadContext = { ...state.context };
  const refreshToken = agentJobsRefreshToken;
  state = beginAgentReportsLoad(state);
  ensureAgentsView().render(state);
  try {
    const response = await listAgentJobReports(
      loadContext.user_id,
      loadContext.project_id,
      authOptions({
        limit: 50,
        session_id: loadContext.session_id,
      }),
    );
    if (
      refreshToken !== agentJobsRefreshToken
      || !sameAgentJobsContext(loadContext, state.context)
    ) {
      return;
    }
    state = completeAgentReportsLoad(state, response);
  } catch (error) {
    if (
      refreshToken !== agentJobsRefreshToken
      || !sameAgentJobsContext(loadContext, state.context)
    ) {
      return;
    }
    state = failAgentReportsLoad(state, error);
  }
  ensureAgentsView().render(state);
}

async function loadAgentJobs() {
  if (!state.context) {
    return;
  }
  const loadContext = { ...state.context };
  const refreshToken = agentJobsRefreshToken;
  clearAgentJobsRefreshTimer();
  state = beginAgentJobsLoad(state);
  ensureAgentsView().render(state);
  try {
    const response = await listAgentJobs(
      loadContext.user_id,
      loadContext.project_id,
      authOptions({
        limit: 50,
        session_id: loadContext.session_id,
      }),
    );
    if (
      refreshToken !== agentJobsRefreshToken
      || !sameAgentJobsContext(loadContext, state.context)
    ) {
      return;
    }
    state = completeAgentJobsLoad(state, response);
    agentJobsConsecutiveFailures = 0;
    refreshAuthoritativeResourcesForCompletedJobs(state.agents.jobs);
  } catch (error) {
    if (
      refreshToken !== agentJobsRefreshToken
      || !sameAgentJobsContext(loadContext, state.context)
    ) {
      return;
    }
    state = failAgentJobsLoad(state, error);
    agentJobsConsecutiveFailures += 1;
  }
  ensureAgentsView().render(state);
  if (
    agentJobsConsecutiveFailures < AGENT_JOBS_RETRY_LIMIT
    && shouldRefreshAgentJobs()
  ) {
    scheduleAgentJobsRefresh();
  }
}

async function loadChatSession(sessionId) {
  if (!state.context || !selectCanSubmit(state)) {
    return;
  }
  stopSpeechPlayback();
  resetAgentJobsRefreshLoop();
  state = beginChatSessionDetailLoad(state, sessionId);
  renderWorkspace();
  try {
    const response = await getChatSession(
      state.context.user_id,
      state.context.project_id,
      sessionId,
      authOptions({ limit: 100 }),
    );
    state = completeChatSessionDetailLoad(state, response);
    document.querySelector("[data-chat-error]").hidden = true;
    setChatStatus("");
    await loadAgentJobs();
  } catch (error) {
    state = failChatSessionDetailLoad(state, error);
  }
  renderWorkspace();
}

async function refreshAuthoritativeEffects(response) {
  const refreshPlan = selectWorkRefreshPlan(response);
  if (refreshPlan.reloadList) {
    await loadWorkList();
  }
  if (refreshPlan.selectArtifactId !== null) {
    await loadWorkDetail(refreshPlan.selectArtifactId);
  }
  const receiptRefresh = selectNeedsReceiptRefresh(response);
  if (receiptRefresh.memory) {
    await loadMemory();
  }
  if (receiptRefresh.notes) {
    await loadNotes();
  }
  await loadAgentJobs();
}

async function submitRequest(request) {
  state = beginPendingTurn(state, request);
  renderWorkspace();
  document.querySelector("[data-chat-error]").hidden = true;
  try {
    const endpoint = selectChatEndpoint(request);
    const waitingMessage = endpoint === "/api/chat/stream"
      ? selectOrdinaryChatWaitingQuip()
      : "Waiting for Agent Col";
    setChatStatus(waitingMessage, "pending");
    loadAgentJobs().finally(() => {
      startAgentJobsStream();
    });
    const options = {
      method: "POST",
      idempotencyKey: request.key,
      authToken: state.context?.auth_token ?? null,
      body: request.body,
    };
    const response = endpoint === "/api/chat/stream"
      ? await apiFetchSse(endpoint, {
        ...options,
        onDelta(text) {
          const firstDelta = state.pendingResponseText.length === 0;
          state = appendPendingResponseDelta(state, text);
          if (firstDelta) {
            setChatStatus("");
          }
          renderChatSurface();
        },
      })
      : await apiFetchJson(endpoint, options);
    state = completePendingTurn(state, response);
    const completedTurn = state.transcript.at(-1) ?? null;
    clearOrdinaryChatRequest(request);
    setChatStatus("");
    renderWorkspace();
    speakCompletedTurnIfEnabled(completedTurn);
    await refreshAuthoritativeEffects(response);
    await loadChatSessions();
  } catch (error) {
    state = failPendingTurn(state, error);
    setChatStatus("");
    setText(document.querySelector("[data-chat-error]"), error.message);
    document.querySelector("[data-chat-error]").hidden = false;
    renderWorkspace();
    if (error.partialFailure) {
      await refreshAuthoritativeEffects(error.partialFailure);
    }
  }
  renderWorkspace();
}

function ensureChatView() {
  if (chatView !== null) {
    return chatView;
  }
  chatView = createChatView(
    {
      form: document.querySelector("[data-chat-form]"),
      input: document.querySelector("[data-chat-input]"),
      submitButton: document.querySelector("[data-chat-submit]"),
      retryButton: document.querySelector("[data-retry-turn]"),
      transcript: document.querySelector("[data-chat-transcript]"),
      characterCount: document.querySelector("[data-character-count]"),
      clarificationChoices: document.querySelector("[data-memory-clarification-choices]"),
      continuityChoices: document.querySelector("[data-continuity-choices]"),
    },
    {
      onSubmit(message) {
        if (!selectCanSubmit(state)) {
          return;
        }
        const request = buildOrdinaryChatRequest(state.context, message);
        try {
          storeOrdinaryChatRequest(request);
        } catch {
          setText(
            document.querySelector("[data-chat-error]"),
            "The prompt was not sent because this browser could not safely retain it.",
          );
          document.querySelector("[data-chat-error]").hidden = false;
          return;
        }
        chatView.clearComposer();
        submitRequest(request);
      },
      onRetry() {
        if (state.lastFailure === null) {
          return;
        }
        submitRequest(buildExactRetryRequest(state.lastFailure.request));
      },
      onSelectMemoryClarification(choice) {
        if (!state.context) {
          return;
        }
        submitMemoryClarificationSelection(choice);
      },
      onSelectContinuityChoice(choice) {
        if (!state.context) {
          return;
        }
        submitContinuitySelection(choice);
      },
    },
  );
  return chatView;
}

function ensureWorkspaceView() {
  if (workspaceView !== null) {
    return workspaceView;
  }
  workspaceView = createWorkspaceView(
    {
      panel: document.querySelector("[data-workspace-list]"),
    },
    {
      async onSelectWorkspace(workspace) {
        if (!state.context || state.pendingTurn !== null) {
          return;
        }
        stopSpeechPlayback();
        resetAgentJobsRefreshLoop();
        state = selectWorkspace(state, workspace);
        renderWorkspace();
        await loadWorkList();
        await loadNotes();
        await loadMemory();
        await loadChatSessions();
        await loadAgentJobs();
      },
      async onCreateWorkspace(displayName) {
        if (!state.context || state.pendingTurn !== null) {
          return;
        }
        resetAgentJobsRefreshLoop();
        clearWorkspaceError();
        try {
          const response = await createWorkspace(
            state.context.user_id,
            { display_name: displayName },
            authOptions(),
          );
          state = completeWorkspaceCreate(state, response);
          renderWorkspace();
          await loadWorkspaces();
          await loadWorkList();
          await loadNotes();
          await loadMemory();
          await loadChatSessions();
          await loadAgentJobs();
        } catch (error) {
          showWorkspaceError(error.message);
        }
      },
      async onDeleteWorkspace(workspace) {
        if (!state.context || state.pendingTurn !== null) {
          return;
        }
        clearWorkspaceError();
        const deletedSelected = (
          workspace.workspace_id === state.workspaces.selectedWorkspaceId
        );
        try {
          if (deletedSelected) {
            resetAgentJobsRefreshLoop();
          }
          await deleteWorkspace(
            state.context.user_id,
            workspace.workspace_id,
            authOptions(),
          );
          state = completeWorkspaceDelete(state, workspace.workspace_id);
          renderWorkspace();
          await loadWorkspaces();
          if (deletedSelected) {
            await loadWorkList();
            await loadNotes();
            await loadMemory();
            await loadChatSessions();
            await loadAgentJobs();
          }
        } catch (error) {
          showWorkspaceError(error.message);
        }
      },
    },
  );
  return workspaceView;
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
      onPrintWork() {
        window.print();
      },
      onArchiveArtifact(artifactId) {
        archiveGenericArtifact(artifactId);
      },
      onRestoreArtifact(artifactId) {
        restoreGenericArtifact(artifactId);
      },
      onDeleteArtifact(artifactId) {
        deleteGenericArtifact(artifactId);
      },
      onToggleArtifactDisclosure(artifactId) {
        state = toggleArtifactDisclosure(state, artifactId);
        ensureWorkView().render(state);
      },
      onUpdateArtifactMetadata(artifactId, metadata) {
        updateGenericArtifactMetadata(artifactId, metadata);
      },
      onCreateArtifactVersion(artifactId, request) {
        createGenericArtifactVersion(artifactId, request);
      },
      onSetArtifactLifecycleStatus(lifecycleStatus) {
        setArtifactLifecycleStatus(lifecycleStatus);
      },
    },
  );
  return workView;
}

async function archiveGenericArtifact(artifactId) {
  if (!state.context) {
    return;
  }
  clearWorkError();
  try {
    await archiveArtifact(
      state.context.project_id,
      artifactId,
      authOptions(),
    );
    state = completeWorkArchive(state, artifactId);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function restoreGenericArtifact(artifactId) {
  if (!state.context) {
    return;
  }
  clearWorkError();
  try {
    await restoreArtifact(
      state.context.project_id,
      artifactId,
      authOptions(),
    );
    state = completeWorkRestore(state, artifactId);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function deleteGenericArtifact(artifactId) {
  if (!state.context) {
    return;
  }
  const confirmed = globalThis.confirm?.(
    "Delete this artifact?\n\nThe artifact is removed from active views, while existing chat history remains unchanged.",
  ) ?? true;
  if (!confirmed) {
    return;
  }
  clearWorkError();
  try {
    await deleteArtifact(
      state.context.project_id,
      artifactId,
      authOptions(),
    );
    state = completeWorkDelete(state, artifactId);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function updateGenericArtifactMetadata(artifactId, metadata) {
  if (!state.context) {
    return;
  }
  clearWorkError();
  try {
    const response = await updateArtifactMetadata(
      state.context.project_id,
      artifactId,
      {
        display_label: metadata.display_label,
        filename: metadata.filename,
      },
      authOptions(),
    );
    state = completeWorkMetadataUpdate(state, response.metadata);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function createGenericArtifactVersion(artifactId, versionRequest) {
  if (!state.context) {
    return;
  }
  clearWorkError();
  try {
    const response = await createArtifactVersion(
      state.context.project_id,
      artifactId,
      {
        session_id: state.context.session_id,
        user_id: state.context.user_id,
        content: versionRequest.content,
        filename: versionRequest.filename || undefined,
        display_label: versionRequest.display_label || undefined,
        summary: versionRequest.summary || undefined,
      },
      authOptions(),
    );
    state = completeWorkVersionCreate(state, response);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function setArtifactLifecycleStatus(lifecycleStatus) {
  if (!state.context) {
    return;
  }
  state = setWorkLifecycleStatus(state, lifecycleStatus);
  ensureWorkView().render(state);
  await loadWorkList();
}

function ensureMemoryView() {
  if (memoryView !== null) {
    return memoryView;
  }
  memoryView = createMemoryView(
    {
      panel: document.querySelector("[data-memory-panel]"),
    },
    {
      onSubmitDecision(decision) {
        submitMemoryDecision(decision);
      },
      onRevokeSignal(signal) {
        revokeActiveMemorySignal(signal);
      },
      onDeleteSignal(signal) {
        deleteActiveMemorySignal(signal);
      },
      onToggleProposalDisclosure(proposalId) {
        state = toggleMemoryDisclosure(state, proposalId, "proposal");
        ensureMemoryView().render(state);
      },
      onToggleSignalDisclosure(signalId) {
        state = toggleMemoryDisclosure(state, signalId, "signal");
        ensureMemoryView().render(state);
      },
      onToggleEventsDisclosure() {
        state = toggleMemoryEventsDisclosure(state);
        ensureMemoryView().render(state);
      },
    },
  );
  return memoryView;
}

function ensureNotesView() {
  if (notesView !== null) {
    return notesView;
  }
  notesView = createNotesView(
    {
      panel: document.querySelector("[data-notes-panel]"),
    },
    {
      onSubmitDecision(decision) {
        submitCollaborativeNoteDecision(decision);
      },
      onSelectNote(noteId) {
        loadNoteDetail(noteId);
      },
      async onSetStatusFilter(statusFilter) {
        state = setNotesStatusFilter(state, statusFilter);
        ensureNotesView().render(state);
        await loadNotes(statusFilter);
      },
      onCreateCorrection(note, request) {
        createCollaborativeNoteCorrection(note, request);
      },
      onCreateNoteProposal(request) {
        createCollaborativeNoteProposal(request);
      },
      onToggleProposalDisclosure(proposalId) {
        state = toggleNoteProposalDisclosure(state, proposalId);
        ensureNotesView().render(state);
      },
      onToggleDetailDisclosure(noteId) {
        state = toggleNoteDetailDisclosure(state, noteId);
        ensureNotesView().render(state);
      },
      onArchiveNote(note) {
        changeCollaborativeNoteLifecycle("archive", note);
      },
      onRestoreNote(note) {
        changeCollaborativeNoteLifecycle("restore", note);
      },
      onDeleteNote(note) {
        changeCollaborativeNoteLifecycle("delete", note);
      },
    },
  );
  return notesView;
}

function ensureChatsView() {
  if (chatsView !== null) {
    return chatsView;
  }
  chatsView = createChatsView(
    {
      list: document.querySelector("[data-chats-list]"),
    },
    {
      onSelectSession(sessionId) {
        stopSpeechPlayback();
        state = expandChatDisclosure(state, sessionId);
        loadChatSession(sessionId);
      },
      onToggleSessionDisclosure(sessionId) {
        state = toggleChatDisclosure(state, sessionId);
        ensureChatsView().render(state);
      },
    },
  );
  return chatsView;
}

function ensureAgentsView() {
  if (agentsView !== null) {
    return agentsView;
  }
  agentsView = createAgentsView({
    panel: document.querySelector("[data-agents-panel]"),
    summary: document.querySelector("[data-agents-summary]"),
    async onOpenReports() {
      state = showAgentReports(state);
      ensureAgentsView().render(state);
      await loadAgentJobReports();
    },
    onCloseReports() {
      state = hideAgentReports(state);
      ensureAgentsView().render(state);
    },
  });
  return agentsView;
}

async function submitArtifactFeedback(decision) {
  if (!state.context) {
    return;
  }
  const artifactId = String(decision.artifact_id ?? "").trim();
  const feedbackRequest = {
    session_id: state.context.session_id,
    user_id: state.context.user_id,
    artifact_id: artifactId,
    target_id: String(decision.target_id ?? "").trim(),
    decision: String(decision.decision ?? "").trim(),
    feedback_text: String(decision.feedback_text ?? "").trim(),
    expected_schema_version: String(
      decision.expected_schema_version ?? "2.0",
    ).trim(),
  };
  const correctionText = String(decision.correction_text ?? "").trim();
  if (correctionText) {
    feedbackRequest.correction_text = correctionText;
  }
  const supersedesFeedbackId = String(
    decision.supersedes_feedback_id ?? "",
  ).trim();
  if (supersedesFeedbackId) {
    feedbackRequest.supersedes_feedback_id = supersedesFeedbackId;
  }
  clearWorkError();
  try {
    await recordBlueprintFeedback(
      state.context.project_id,
      artifactId,
      feedbackRequest,
      {
        ...authOptions(),
        idempotencyKey: `artifact-feedback--${crypto.randomUUID()}`,
      },
    );
    await loadWorkDetail(artifactId);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function submitMemoryDecision(decision) {
  if (!state.context) {
    return;
  }
  clearMemoryError();
  try {
    await decideMemoryProposal(
      state.context.user_id,
      decision.proposal_id,
      decision.decision,
      authOptions(),
    );
    await loadMemory();
    loadAgentJobReports();
    loadAgentJobs();
  } catch (error) {
    showMemoryError(error.message);
  }
}

async function submitMemoryClarificationSelection(choice) {
  if (!state.context) {
    return;
  }
  clearMemoryError();
  try {
    await selectMemoryClarification(
      state.context.user_id,
      state.context.project_id,
      choice.clarification_id,
      {
        session_id: state.context.session_id,
        selected_candidate_index: choice.candidate_index,
      },
      {
        ...authOptions(),
        idempotencyKey: `memory-clarification-selection--${crypto.randomUUID()}`,
      },
    );
    state = {
      ...state,
      activeMemoryClarification: null,
    };
    await loadMemory();
    loadAgentJobReports();
    loadAgentJobs();
  } catch (error) {
    showMemoryError(error.message);
  }
  renderWorkspace();
}

async function submitContinuitySelection(choice) {
  if (!state.context) {
    return;
  }
  document.querySelector("[data-chat-error]").hidden = true;
  try {
    await selectContinuityChoice(
      state.context.user_id,
      state.context.project_id,
      choice.choice_id,
      {
        session_id: state.context.session_id,
        source_kind: choice.source_kind,
        source_id: choice.source_id,
      },
      {
        ...authOptions(),
        idempotencyKey: `continuity-selection--${crypto.randomUUID()}`,
      },
    );
    state = {
      ...state,
      activeContinuityChoices: [],
    };
    await loadChatSessions();
  } catch (error) {
    setText(document.querySelector("[data-chat-error]"), error.message);
    document.querySelector("[data-chat-error]").hidden = false;
  }
  renderWorkspace();
}

async function submitCollaborativeNoteDecision(decision) {
  if (!state.context) {
    return;
  }
  clearNotesError();
  state = beginNoteRequest(state, `${decision.decision}:${decision.proposal_id}`);
  ensureNotesView().render(state);
  try {
    await decideNoteProposal(
      state.context.user_id,
      state.context.project_id,
      decision.proposal_id,
      decision.decision,
      authOptions(),
    );
    state = completeNoteRequest(state);
    await loadNotes(state.notes.statusFilter);
    loadAgentJobReports();
    loadAgentJobs();
  } catch (error) {
    state = failNoteRequest(state, error);
    showNotesError(error.message);
  }
  renderWorkspace();
}

async function createCollaborativeNoteCorrection(note, request) {
  if (!state.context) {
    return;
  }
  clearNotesError();
  state = beginNoteRequest(state, `correction:${note.note_id}`);
  ensureNotesView().render(state);
  try {
    const response = await createNoteCorrection(
      state.context.user_id,
      state.context.project_id,
      note.note_id,
      request,
      {
        ...authOptions(),
        idempotencyKey: `note-correction--${crypto.randomUUID()}`,
      },
    );
    state = completeNoteRequest(storePendingNoteProposal(state, response.proposal));
    await loadNotes();
  } catch (error) {
    state = failNoteRequest(state, error);
    showNotesError(error.message);
  }
  renderWorkspace();
}

async function createCollaborativeNoteProposal(request) {
  if (!state.context) {
    return;
  }
  clearNotesError();
  state = beginNoteRequest(state, "proposal:create");
  ensureNotesView().render(state);
  try {
    const response = await createNoteProposal(
      state.context.user_id,
      state.context.project_id,
      {
        ...request,
        session_id: state.context.session_id,
      },
      {
        ...authOptions(),
        idempotencyKey: `note-proposal--${crypto.randomUUID()}`,
      },
    );
    state = completeNoteRequest(storePendingNoteProposal(state, response.proposal));
    await loadNotes();
  } catch (error) {
    state = failNoteRequest(state, error);
    showNotesError(error.message);
  }
  renderWorkspace();
}

async function changeCollaborativeNoteLifecycle(action, note) {
  if (!state.context) {
    return;
  }
  clearNotesError();
  state = beginNoteRequest(state, `${action}:${note.note_id}`);
  ensureNotesView().render(state);
  try {
    const request = { expected_revision: note.revision };
    if (action === "archive") {
      await archiveNote(
        state.context.user_id,
        state.context.project_id,
        note.note_id,
        request,
        authOptions(),
      );
    } else if (action === "restore") {
      await restoreNote(
        state.context.user_id,
        state.context.project_id,
        note.note_id,
        request,
        authOptions(),
      );
    } else {
      await deleteNote(
        state.context.user_id,
        state.context.project_id,
        note.note_id,
        request,
        authOptions(),
      );
    }
    state = completeNoteRequest(state);
    await loadNotes(state.notes.statusFilter);
  } catch (error) {
    state = failNoteRequest(state, error);
    showNotesError(error.message);
  }
  renderWorkspace();
}

async function revokeActiveMemorySignal(signal) {
  if (!state.context) {
    return;
  }
  clearMemoryError();
  try {
    const response = await revokeMemorySignal(
      state.context.user_id,
      signal.signal_id,
      authOptions(),
    );
    state = completeMemorySignalMutation(
      state,
      signal.signal_id,
      response.profile,
    );
  } catch (error) {
    showMemoryError(error.message);
  }
  renderWorkspace();
}

async function deleteActiveMemorySignal(signal) {
  if (!state.context) {
    return;
  }
  clearMemoryError();
  try {
    await deleteMemorySignal(
      state.context.user_id,
      signal.signal_id,
      authOptions(),
    );
    state = completeMemorySignalMutation(state, signal.signal_id);
  } catch (error) {
    showMemoryError(error.message);
  }
  renderWorkspace();
}

document.querySelector("[data-context-form]").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    stopSpeechPlayback();
    resetAgentJobsRefreshLoop();
    state = acceptContext(
      state,
      contextForSubmit(event.currentTarget),
    );
    const recoveredRequest = loadOrdinaryChatRequest(state.context);
    ensureChatView();
    ensureWorkView();
    ensureNotesView();
    ensureMemoryView();
    ensureChatsView();
    ensureAgentsView();
    ensureWorkspaceView();
    showWorkspace();
    renderWorkspace();
    await loadWorkspaces();
    const canRestoreRequest = (
      recoveredRequest !== null
      && recoveredRequest.body.user_id === state.context?.user_id
      && recoveredRequest.body.project_id === state.context?.project_id
      && selectCanSubmit(state)
    );
    if (canRestoreRequest) {
      state = restoreRecoveredTurn(state, recoveredRequest);
      renderWorkspace();
      setText(
        document.querySelector("[data-chat-error]"),
        state.lastFailure.message,
      );
      document.querySelector("[data-chat-error]").hidden = false;
    }
    loadWorkList();
    loadNotes();
    loadMemory();
    loadChatSessions();
    loadAgentJobs();
  } catch (error) {
    showContextError(error.message);
  }
});

document.querySelector("[data-new-conversation]").addEventListener("click", () => {
  if (state.pendingTurn !== null || state.lastFailure?.recovered === true) {
    return;
  }
  stopSpeechPlayback();
  resetAgentJobsRefreshLoop();
  state = startNewConversation(state);
  document.querySelector("[data-chat-error]").hidden = true;
  setChatStatus("");
  renderWorkspace();
  loadNotes();
  loadChatSessions();
  loadAgentJobs();
  document.querySelector("#conversation-workspace").focus();
});

for (const button of document.querySelectorAll("[data-drawer-toggle]")) {
  button.addEventListener("click", () => {
    const drawer = button.getAttribute("data-drawer-toggle");
    if (drawer === "right") {
      layoutState = setArtifactDrawerMode(
        layoutState,
        isDrawerExpanded(layoutState, "right") ? "hidden" : "normal",
      );
      renderLayout();
      return;
    }
    layoutState = setDrawerCollapsed(
      layoutState,
      drawer,
      isDrawerExpanded(layoutState, drawer),
    );
    renderLayout();
  });
}

for (const button of document.querySelectorAll("[data-section-toggle]")) {
  button.addEventListener("click", () => {
    const section = button.getAttribute("data-section-toggle");
    layoutState = setSectionExpanded(
      layoutState,
      section,
      !isSectionExpanded(layoutState, section),
    );
    renderLayout();
  });
}

document.querySelector("[data-artifacts-expand]").addEventListener("click", () => {
  layoutState = setArtifactDrawerMode(
    layoutState,
    layoutState.artifactDrawerMode === "expanded" ? "normal" : "expanded",
  );
  renderLayout();
});

document.querySelector("[data-left-refresh]").addEventListener("click", () => {
  clearAgentJobsRefreshTimer();
  loadWorkspaces();
  loadWorkList();
  loadNotes();
  loadMemory();
  loadChatSessions();
  loadAgentJobs();
});

document.querySelector("[data-speech-toggle]")?.addEventListener("click", () => {
  if (speechRecording !== null) {
    stopSpeechRecording();
    return;
  }
  startSpeechRecording();
});

document.querySelector("[data-tts-stop]")?.addEventListener("click", () => {
  stopSpeechPlayback();
});

document.querySelector("[data-spoken-responses-toggle]")?.addEventListener("change", () => {
  if (!spokenResponsesEnabled()) {
    stopSpeechPlayback();
  }
});

bootstrapAuth();
