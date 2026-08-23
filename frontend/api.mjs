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
