import { isValidIdentifier } from "./requests.mjs";

export class ApiError extends Error {
  constructor({
    status,
    message,
    detail,
    retryAfterSeconds,
    provisional = false,
    partialFailure = null,
  }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.retryAfterSeconds = retryAfterSeconds;
    this.provisional = provisional;
    this.partialFailure = partialFailure;
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

const BACKEND_AGENT_COL_NAME = "Agent" + "_Col";
const TIMEOUT_DETAIL_WITHOUT_COMPLETED_EFFECT = (
  `${BACKEND_AGENT_COL_NAME} response timed out.`
);
const TIMEOUT_DETAIL_AFTER_COMPLETED_EFFECT = (
  `${BACKEND_AGENT_COL_NAME} response timed out after a completed action.`
);

function detailToTimeoutMessage(status, detail) {
  if (status !== 504 || typeof detail !== "string") {
    return null;
  }
  if (detail === TIMEOUT_DETAIL_WITHOUT_COMPLETED_EFFECT) {
    return (
      "Agent Col timed out before completing this response. "
      + "No completed action was recorded."
    );
  }
  if (detail === TIMEOUT_DETAIL_AFTER_COMPLETED_EFFECT) {
    return (
      "Agent Col timed out after recording a completed action. "
      + "Retry will reuse completed receipts."
    );
  }
  return null;
}

export function normalizeApiError(response, body) {
  const retryAfter = response.headers.get("retry-after");
  const detail = body && typeof body === "object" && "detail" in body
    ? body.detail
    : body;
  const partialFailure = (
    body
    && typeof body === "object"
    && typeof body.response === "string"
    && (
      Array.isArray(body.actions)
      || Array.isArray(body.artifacts)
      || Array.isArray(body.artifact_feedback)
      || Array.isArray(body.memory_proposals)
      || Array.isArray(body.memory_clarifications)
      || Array.isArray(body.collaborative_note_proposals)
      || Array.isArray(body.collaborative_note_events)
      || Array.isArray(body.continuity_receipts)
      || Array.isArray(body.continuity_choices)
      || Array.isArray(body.adaptations)
    )
  ) ? body : null;
  const timeoutMessage = detailToTimeoutMessage(response.status, detail);
  return new ApiError({
    status: response.status,
    message: timeoutMessage ?? detailToMessage(detail),
    detail,
    retryAfterSeconds: retryAfter === null
      ? null
      : Number.parseInt(retryAfter, 10),
    partialFailure,
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

export async function apiFetchJson(
  path,
  options = {},
  fetchLike = globalThis.fetch,
) {
  assertSameOriginPath(path);
  const headers = { ...(options.headers ?? {}) };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  if (options.authToken) {
    headers.Authorization = `Bearer ${options.authToken}`;
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

function nextSseFrame(buffer) {
  const lfIndex = buffer.indexOf("\n\n");
  const crlfIndex = buffer.indexOf("\r\n\r\n");
  if (lfIndex === -1 && crlfIndex === -1) {
    return null;
  }
  const useCrlf = crlfIndex !== -1 && (lfIndex === -1 || crlfIndex < lfIndex);
  const index = useCrlf ? crlfIndex : lfIndex;
  const delimiterLength = useCrlf ? 4 : 2;
  return {
    frame: buffer.slice(0, index),
    rest: buffer.slice(index + delimiterLength),
  };
}

function parseSseFrame(frame) {
  let event = "message";
  const dataLines = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return { event, data: JSON.parse(dataLines.join("\n")) };
}

export async function apiFetchSse(
  path,
  options = {},
  fetchLike = globalThis.fetch,
) {
  assertSameOriginPath(path);
  const headers = { ...(options.headers ?? {}) };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  if (options.authToken) {
    headers.Authorization = `Bearer ${options.authToken}`;
  }
  const response = await fetchLike(path, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!response.ok) {
    throw normalizeApiError(response, await parseBody(response));
  }
  if (!response.body) {
    throw new ApiError({
      status: 0,
      message: "Chat response stream was unavailable.",
      detail: null,
      retryAfterSeconds: null,
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      let pendingDelta = "";
      const flushDelta = async () => {
        if (pendingDelta) {
          const text = pendingDelta;
          pendingDelta = "";
          await options.onDelta?.(text);
        }
      };
      let extracted = nextSseFrame(buffer);
      while (extracted !== null) {
        buffer = extracted.rest;
        const parsed = parseSseFrame(extracted.frame);
        if (parsed?.event === "delta") {
          const text = parsed.data?.text;
          if (typeof text === "string" && text.length > 0) {
            pendingDelta += text;
          }
        } else if (parsed?.event === "final") {
          await flushDelta();
          return parsed.data;
        } else if (parsed?.event === "error") {
          await flushDelta();
          const detail = parsed.data?.detail;
          const status = Number.isInteger(parsed.data?.status)
            ? parsed.data.status
            : 500;
          throw new ApiError({
            status,
            message: detailToTimeoutMessage(status, detail) ?? detailToMessage(detail),
            detail,
            retryAfterSeconds: null,
            provisional: parsed.data?.provisional === true,
            partialFailure: parsed.data?.partial_failure ?? null,
          });
        }
        extracted = nextSseFrame(buffer);
      }
      await flushDelta();
      if (done) {
        break;
      }
    }
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError({
      status: 0,
      message: "Chat response stream was interrupted.",
      detail: null,
      retryAfterSeconds: null,
      provisional: true,
    });
  } finally {
    reader.releaseLock();
  }
  throw new ApiError({
    status: 0,
    message: "Chat response stream ended before completion.",
    detail: null,
    retryAfterSeconds: null,
    provisional: true,
  });
}

export async function streamAgentJobs(
  userId,
  projectId,
  options = {},
  handlers = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  const path = `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/agent/jobs/stream${buildAgentJobQuery(options)}`;
  assertSameOriginPath(path);
  const headers = { ...(options.headers ?? {}) };
  if (options.authToken) {
    headers.Authorization = `Bearer ${options.authToken}`;
  }
  const response = await fetchLike(path, {
    method: "GET",
    headers,
    signal: options.signal,
  });
  if (!response.ok) {
    throw normalizeApiError(response, await parseBody(response));
  }
  if (!response.body) {
    throw new ApiError({
      status: 0,
      message: "Agent job stream was unavailable.",
      detail: null,
      retryAfterSeconds: null,
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      let extracted = nextSseFrame(buffer);
      while (extracted !== null) {
        buffer = extracted.rest;
        const parsed = parseSseFrame(extracted.frame);
        if (parsed?.event === "snapshot") {
          await handlers.onSnapshot?.(parsed.data);
        } else if (parsed?.event === "heartbeat") {
          await handlers.onHeartbeat?.(parsed.data);
        } else if (parsed?.event === "error") {
          const detail = parsed.data?.detail;
          const status = Number.isInteger(parsed.data?.status)
            ? parsed.data.status
            : 500;
          throw new ApiError({
            status,
            message: detailToMessage(detail),
            detail,
            retryAfterSeconds: null,
          });
        }
        extracted = nextSseFrame(buffer);
      }
      if (done) {
        break;
      }
    }
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError({
      status: 0,
      message: "Agent job stream was interrupted.",
      detail: null,
      retryAfterSeconds: null,
      provisional: true,
    });
  } finally {
    reader.releaseLock();
  }
}

export function getAuthSession(
  authToken = null,
  fetchLike = globalThis.fetch,
) {
  return apiFetchJson(
    "/api/auth/session",
    {
      method: "GET",
      authToken,
    },
    fetchLike,
  );
}

export function getAuthConfig(fetchLike = globalThis.fetch) {
  return apiFetchJson(
    "/api/auth/config",
    {
      method: "GET",
    },
    fetchLike,
  );
}

export async function transcribeSpeechAudio(
  audio,
  options = {},
  fetchLike = globalThis.fetch,
) {
  assertSameOriginPath("/api/speech/transcribe");
  const headers = {
    "Content-Type": audio?.type ?? "application/octet-stream",
  };
  if (options.authToken) {
    headers.Authorization = `Bearer ${options.authToken}`;
  }
  const response = await fetchLike("/api/speech/transcribe", {
    method: "POST",
    headers,
    body: audio,
  });
  const body = await parseBody(response);
  if (!response.ok) {
    throw normalizeApiError(response, body);
  }
  return body;
}

export async function synthesizeSpeechAudio(
  userId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", request?.project_id);
  assertIdentifier("session_id", request?.session_id);
  assertIdentifier("message_id", request?.message_id);
  const response = await fetchLike(
    `/api/users/${encodeURIComponent(userId)}/speech/synthesize`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(options.authToken ? { Authorization: `Bearer ${options.authToken}` } : {}),
      },
      body: JSON.stringify(request),
      signal: options.signal,
    },
  );
  if (!response.ok) {
    throw normalizeApiError(response, await parseBody(response));
  }
  return {
    audio: await response.blob(),
    contentType: response.headers.get("content-type") ?? "application/octet-stream",
    chunkIndex: Number.parseInt(response.headers.get("x-speech-chunk-index") ?? "0", 10),
    chunkCount: Number.parseInt(response.headers.get("x-speech-chunk-count") ?? "1", 10),
  };
}

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
  if (options.lifecycle_status !== undefined && options.lifecycle_status !== null) {
    params.set("lifecycle_status", String(options.lifecycle_status));
  }
  if (options.status_filter !== undefined && options.status_filter !== null) {
    params.set("status_filter", String(options.status_filter));
  }
  if (options.cursor !== undefined && options.cursor !== null) {
    params.set("cursor", String(options.cursor));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

function buildMemoryQuery(options = {}) {
  const params = new URLSearchParams();
  if (options.after_event_id !== undefined && options.after_event_id !== null) {
    const eventId = String(options.after_event_id);
    if (!isValidIdentifier(eventId)) {
      throw new Error("after_event_id is invalid.");
    }
    params.set("after_event_id", eventId);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

function buildAgentJobQuery(options = {}) {
  const params = new URLSearchParams();
  if (options.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options.session_id !== undefined && options.session_id !== null) {
    const sessionId = String(options.session_id);
    assertIdentifier("session_id", sessionId);
    params.set("session_id", sessionId);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

function normalizeOptionsAndFetch(options, fetchLike) {
  if (typeof options === "function") {
    return [{}, options];
  }
  return [options ?? {}, fetchLike];
}

export function listBlueprints(
  projectId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/blueprints${buildQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function getBlueprint(
  projectId,
  artifactId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/blueprints/${encodeURIComponent(artifactId)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function listBlueprintFeedback(
  projectId,
  artifactId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/blueprints/${encodeURIComponent(artifactId)}/feedback${buildQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function listArtifacts(
  projectId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/artifacts${buildQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function getArtifact(
  projectId,
  artifactId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function createArtifact(
  projectId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/artifacts`,
    {
      method: "POST",
      authToken: options.authToken,
      body: request,
    },
    fetchLike,
  );
}

export function archiveArtifact(
  projectId,
  artifactId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/archive`,
    { method: "POST", authToken: options.authToken },
    fetchLike,
  );
}

export function restoreArtifact(
  projectId,
  artifactId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/restore`,
    { method: "POST", authToken: options.authToken },
    fetchLike,
  );
}

export function deleteArtifact(
  projectId,
  artifactId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}`,
    { method: "DELETE", authToken: options.authToken },
    fetchLike,
  );
}

export function updateArtifactMetadata(
  projectId,
  artifactId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/metadata`,
    {
      method: "PATCH",
      authToken: options.authToken,
      body: request,
    },
    fetchLike,
  );
}

export function createArtifactVersion(
  projectId,
  artifactId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("project_id", projectId);
  assertIdentifier("artifact_id", artifactId);
  return apiFetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/versions`,
    {
      method: "POST",
      authToken: options.authToken,
      body: request,
    },
    fetchLike,
  );
}

export function inspectMemory(
  userId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/memory${buildMemoryQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function listWorkspaces(
  userId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/workspaces${buildQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function listAgentJobs(
  userId,
  projectId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/agent/jobs${buildAgentJobQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function listAgentJobReports(
  userId,
  projectId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/agent/reports${buildAgentJobQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function createWorkspace(
  userId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/workspaces`,
    {
      method: "POST",
      authToken: options.authToken,
      body: request,
    },
    fetchLike,
  );
}

export function deleteWorkspace(
  userId,
  workspaceId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("workspace_id", workspaceId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/workspaces/${encodeURIComponent(workspaceId)}`,
    { method: "DELETE", authToken: options.authToken },
    fetchLike,
  );
}

export function revokeMemorySignal(
  userId,
  signalId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("signal_id", signalId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/memory/signals/${encodeURIComponent(signalId)}/revoke`,
    { method: "POST", authToken: options.authToken },
    fetchLike,
  );
}

export function deleteMemorySignal(
  userId,
  signalId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("signal_id", signalId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/memory/signals/${encodeURIComponent(signalId)}`,
    { method: "DELETE", authToken: options.authToken },
    fetchLike,
  );
}

function assertNoteStatusFilter(value) {
  if (value !== undefined && value !== null && !["active", "archived"].includes(value)) {
    throw new Error("status_filter must be active or archived.");
  }
}

export function listNotes(
  userId,
  projectId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  assertNoteStatusFilter(options.status_filter);
  if (options.cursor !== undefined && options.cursor !== null) {
    assertIdentifier("cursor", String(options.cursor));
  }
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/notes${buildQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function getNote(
  userId,
  projectId,
  noteId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  assertIdentifier("note_id", noteId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/notes/${encodeURIComponent(noteId)}${buildQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function createNoteCorrection(
  userId,
  projectId,
  noteId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  assertIdentifier("note_id", noteId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/notes/${encodeURIComponent(noteId)}/corrections`,
    {
      method: "POST",
      idempotencyKey: options.idempotencyKey,
      authToken: options.authToken,
      body: request,
    },
    fetchLike,
  );
}

export function createNoteProposal(
  userId,
  projectId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/notes/proposals`,
    {
      method: "POST",
      idempotencyKey: options.idempotencyKey,
      authToken: options.authToken,
      body: request,
    },
    fetchLike,
  );
}

export function archiveNote(
  userId,
  projectId,
  noteId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  assertIdentifier("note_id", noteId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/notes/${encodeURIComponent(noteId)}/archive`,
    { method: "POST", authToken: options.authToken, body: request },
    fetchLike,
  );
}

export function restoreNote(
  userId,
  projectId,
  noteId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  assertIdentifier("note_id", noteId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/notes/${encodeURIComponent(noteId)}/restore`,
    { method: "POST", authToken: options.authToken, body: request },
    fetchLike,
  );
}

export function deleteNote(
  userId,
  projectId,
  noteId,
  request,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  assertIdentifier("note_id", noteId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/notes/${encodeURIComponent(noteId)}`,
    { method: "DELETE", authToken: options.authToken, body: request },
    fetchLike,
  );
}

export function listChatSessions(
  userId,
  projectId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/chat-sessions${buildQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}

export function getChatSession(
  userId,
  projectId,
  sessionId,
  options = {},
  fetchLike = globalThis.fetch,
) {
  [options, fetchLike] = normalizeOptionsAndFetch(options, fetchLike);
  assertIdentifier("user_id", userId);
  assertIdentifier("project_id", projectId);
  assertIdentifier("session_id", sessionId);
  return apiFetchJson(
    `/api/users/${encodeURIComponent(userId)}/projects/${encodeURIComponent(projectId)}/chat-sessions/${encodeURIComponent(sessionId)}${buildQuery(options)}`,
    { method: "GET", authToken: options.authToken },
    fetchLike,
  );
}
