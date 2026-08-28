import { appendTextElement, setText } from "./render.mjs";

function compactText(parts) {
  return parts
    .filter((part) => part !== undefined && part !== null && part !== "")
    .map(String)
    .join(" · ");
}

function sessionLabel(session) {
  if (session.last_message_preview) {
    return String(session.last_message_preview);
  }
  return "Untitled chat";
}

function sessionMeta(session) {
  const updated = session.updated_at
    ? new Date(session.updated_at).toLocaleString()
    : "";
  return compactText([
    updated,
    session.last_message_role ? `last: ${session.last_message_role}` : "",
  ]);
}

function isExpanded(disclosure, sessionId) {
  return Array.isArray(disclosure?.sessionIds)
    && disclosure.sessionIds.includes(String(sessionId ?? ""));
}

function disclosureId(prefix, id) {
  return `${prefix}-${String(id ?? "").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export function renderChatsPanel(container, chats, handlers = {}, disclosure = {}) {
  container.replaceChildren();
  if (chats.status === "loading") {
    appendTextElement(container, "p", "muted", "Loading chats...");
    return;
  }
  if (chats.status === "error") {
    appendTextElement(container, "p", "form-error", chats.error);
    return;
  }
  const sessions = Array.isArray(chats.sessions) ? chats.sessions : [];
  if (sessions.length === 0) {
    appendTextElement(container, "p", "muted", "No saved chats yet.");
    return;
  }
  for (const session of sessions) {
    const expanded = isExpanded(disclosure, session.session_id);
    const card = document.createElement("button");
    card.type = "button";
    card.classList.add("work-list-item", "chat-session-card", "contain-text");
    card.setAttribute("data-session-id", session.session_id);
    card.setAttribute("data-session-open", session.session_id);
    card.setAttribute("data-disclosure-toggle", "chat-session");
    card.setAttribute("aria-expanded", String(expanded));
    if (session.session_id === chats.selectedSessionId) {
      card.setAttribute("aria-current", "true");
    }
    if (expanded) {
      card.setAttribute("data-disclosure-expanded", "true");
    }
    const label = appendTextElement(
      card,
      "strong",
      "",
      sessionLabel(session),
    );
    label.classList.add("contain-text");
    const panelId = disclosureId("chat-session-details", session.session_id);
    card.setAttribute("aria-controls", panelId);
    card.addEventListener("click", () => {
      if (session.session_id === chats.selectedSessionId) {
        handlers.onToggleSessionDisclosure?.(session.session_id);
        return;
      }
      handlers.onSelectSession?.(session.session_id);
    });
    const meta = sessionMeta(session);
    if (expanded && meta) {
      const details = document.createElement("span");
      details.classList.add("subcard-disclosure-panel", "muted", "contain-text");
      details.setAttribute("id", panelId);
      setText(details, meta);
      card.append(details);
    }
    container.append(card);
  }
}

export function createChatsView(elements, handlers = {}) {
  return {
    render(state) {
      renderChatsPanel(elements.list, state.chats, handlers, state.disclosure?.chats);
    },
  };
}
