const RECOVERY_VERSION = 1;
const STORAGE_PREFIX = "agent-col:ordinary-chat-recovery:v1:";
const IDENTIFIER_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const REQUEST_FIELDS = new Set(["key", "body"]);
const BODY_FIELDS = new Set(["project_id", "session_id", "user_id", "message"]);

function storageKeyForContext(context) {
  const userId = encodeURIComponent(String(context?.user_id ?? ""));
  const projectId = encodeURIComponent(String(context?.project_id ?? ""));
  return `${STORAGE_PREFIX}${userId}:${projectId}`;
}

function storageKey(request) {
  return storageKeyForContext(request?.body);
}

function hasOnlyFields(value, allowedFields) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && Object.keys(value).every((field) => allowedFields.has(field));
}

function isValidStoredRequest(request, context) {
  if (!hasOnlyFields(request, REQUEST_FIELDS) || !hasOnlyFields(request.body, BODY_FIELDS)) {
    return false;
  }
  const { body } = request;
  return typeof request.key === "string"
    && request.key.startsWith("chat--")
    && IDENTIFIER_PATTERN.test(request.key)
    && IDENTIFIER_PATTERN.test(body.user_id)
    && IDENTIFIER_PATTERN.test(body.project_id)
    && IDENTIFIER_PATTERN.test(body.session_id)
    && typeof body.message === "string"
    && body.message.trim().length > 0
    && body.user_id === context?.user_id
    && body.project_id === context?.project_id;
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) {
      deepFreeze(child);
    }
  }
  return value;
}

export function storeOrdinaryChatRequest(
  request,
  storage,
) {
  const availableStorage = storage === undefined ? globalThis.sessionStorage : storage;
  if (!availableStorage) {
    throw new Error("This browser cannot safely retain the submitted prompt.");
  }
  availableStorage.setItem(storageKey(request), JSON.stringify({
    version: RECOVERY_VERSION,
    request,
  }));
}

export function clearOrdinaryChatRequest(
  request,
  storage,
) {
  try {
    const availableStorage = storage === undefined ? globalThis.sessionStorage : storage;
    if (!availableStorage) {
      return;
    }
    const key = storageKey(request);
    const record = JSON.parse(availableStorage.getItem(key));
    if (record?.request?.key === request?.key) {
      availableStorage.removeItem(key);
    }
  } catch {
    // A malformed or unavailable recovery record must not invalidate a completed turn.
  }
}

export function loadOrdinaryChatRequest(
  context,
  storage,
) {
  try {
    const availableStorage = storage === undefined ? globalThis.sessionStorage : storage;
    if (!availableStorage) {
      return null;
    }
    const record = JSON.parse(availableStorage.getItem(storageKeyForContext(context)));
    if (
      record?.version !== RECOVERY_VERSION
      || !isValidStoredRequest(record.request, context)
    ) {
      return null;
    }
    return deepFreeze(record.request);
  } catch {
    return null;
  }
}
