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

export function renderChatsPanel(container, chats, handlers = {}) {
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
    const button = document.createElement("button");
    button.type = "button";
    button.classList.add("work-list-item", "contain-text");
    button.setAttribute("data-session-id", session.session_id);
    if (session.session_id === chats.selectedSessionId) {
      button.setAttribute("aria-current", "true");
    }
    const label = appendTextElement(
      button,
      "strong",
      "",
      sessionLabel(session),
    );
    label.classList.add("contain-text");
    const meta = sessionMeta(session);
    if (meta) {
      appendTextElement(button, "span", "muted contain-text", meta);
    }
    button.addEventListener("click", () => {
      handlers.onSelectSession?.(session.session_id);
    });
    container.append(button);
  }
}

export function createChatsView(elements, handlers = {}) {
  return {
    render(state) {
      renderChatsPanel(elements.list, state.chats, handlers);
    },
  };
}
