import { isValidIdentifier } from "./requests.mjs";

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
  const timeoutMessage = detailToTimeoutMessage(response.status, detail);
  return new ApiError({
    status: response.status,
    message: timeoutMessage ?? detailToMessage(detail),
    detail,
    retryAfterSeconds: retryAfter === null
      ? null
      : Number.parseInt(retryAfter, 10),
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
