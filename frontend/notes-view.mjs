import { appendTextElement, element, humanLabel } from "./render.mjs";

function noteSummary(note) {
  return [
    humanLabel(note.note_kind),
    note.title,
    note.status ? humanLabel(note.status) : "",
  ].filter(Boolean).join(" · ");
}

function proposalExpired(proposal) {
  const expiresAt = Date.parse(proposal?.expires_at ?? "");
  return Number.isNaN(expiresAt) || expiresAt <= Date.now();
}

function renderPendingProposal(container, proposal, disabled, handlers) {
  const card = element("div", "notes-card contain-text");
  card.setAttribute("data-note-proposal", proposal.proposal_id);
  appendTextElement(card, "p", "muted contain-text", "Pending note proposal");
  appendTextElement(card, "h3", "work-heading contain-text", proposal.title);
  appendTextElement(card, "p", "muted contain-text", humanLabel(proposal.note_kind));
  appendTextElement(card, "p", "contain-text", proposal.body);
  appendTextElement(
    card,
    "p",
    "muted contain-text",
    proposalExpired(proposal)
      ? "Expired"
      : `Expires ${proposal.expires_at ?? "unknown"}`,
  );
  const actions = element("div", "notes-actions contain-text");
  for (const decision of ["approve", "reject"]) {
    const button = element("button", "", humanLabel(decision));
    button.setAttribute("type", "button");
    button.setAttribute("data-note-decision", decision);
    button.disabled = disabled || proposalExpired(proposal);
    button.addEventListener("click", () => {
      if (button.disabled) {
        return;
      }
      handlers.onSubmitDecision?.({
        proposal_id: proposal.proposal_id,
        decision,
      });
    });
    actions.append(button);
  }
  card.append(actions);
  container.append(card);
}

function renderPendingProposals(container, proposals, disabled, handlers) {
  appendTextElement(container, "h3", "work-heading contain-text", "Pending proposals");
  if (!proposals.length) {
    appendTextElement(
      container,
      "p",
      "muted contain-text",
      "No pending note proposals in this browser session.",
    );
    return;
  }
  for (const proposal of proposals) {
    renderPendingProposal(container, proposal, disabled, handlers);
  }
}

function renderNoteList(container, notes, state, disabled, handlers) {
  appendTextElement(
    container,
    "h3",
    "work-heading contain-text",
    state.statusFilter === "archived" ? "Archived notes" : "Active notes",
  );
  const filters = element("div", "notes-actions contain-text");
  for (const filter of ["active", "archived"]) {
    const button = element("button", "", humanLabel(filter));
    button.setAttribute("type", "button");
    button.setAttribute("data-note-filter", filter);
    button.disabled = disabled || state.statusFilter === filter;
    button.addEventListener("click", () => {
      if (!button.disabled) {
        handlers.onSetStatusFilter?.(filter);
      }
    });
    filters.append(button);
  }
  container.append(filters);
  if (!notes.length) {
    appendTextElement(container, "p", "muted contain-text", "No notes loaded.");
    return;
  }
  for (const note of notes) {
    const button = element("button", "notes-card contain-text", noteSummary(note));
    button.setAttribute("type", "button");
    button.setAttribute("data-note-id", note.note_id);
    button.disabled = disabled;
    if (note.note_id === state.selectedNoteId) {
      button.setAttribute("aria-current", "true");
    }
    button.addEventListener("click", () => {
      if (!button.disabled) {
        handlers.onSelectNote?.(note.note_id);
      }
    });
    container.append(button);
  }
}

function renderNoteProposalForm(container, disabled, handlers) {
  const form = element("form", "notes-proposal-form contain-text");
  form.setAttribute("data-note-proposal-form", "true");
  appendTextElement(form, "h3", "work-heading contain-text", "Create note");
  const kindLabel = element("label", "", "Kind");
  const kind = element("select");
  kind.setAttribute("name", "note_kind");
  for (const [value, label] of [
    ["decision", "Decision"],
    ["requirement", "Requirement"],
    ["constraint", "Constraint"],
    ["task_state", "Task state"],
    ["working_context", "Working context"],
  ]) {
    const option = element("option", "", label);
    option.value = value;
    kind.append(option);
  }
  kindLabel.append(kind);
  const titleLabel = element("label", "", "Title");
  const title = element("input");
  title.setAttribute("name", "title");
  title.setAttribute("maxlength", "120");
  title.required = true;
  titleLabel.append(title);
  const bodyLabel = element("label", "", "Body");
  const body = element("textarea");
  body.setAttribute("name", "body");
  body.setAttribute("maxlength", "2000");
  body.required = true;
  bodyLabel.append(body);
  const submit = element("button", "", "Create note proposal");
  submit.setAttribute("type", "submit");
  submit.disabled = disabled;
  form.append(kindLabel, titleLabel, bodyLabel, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const nextTitle = String(title.value ?? "").trim();
    const nextBody = String(body.value ?? "").trim();
    if (!nextTitle || !nextBody || nextTitle.length > 120 || nextBody.length > 2000) {
      return;
    }
    handlers.onCreateNoteProposal?.({
      note_kind: kind.value,
      title: nextTitle,
      body: nextBody,
    });
  });
  container.append(form);
}

function renderCorrectionForm(container, note, disabled, handlers) {
  const form = element("form", "notes-correction-form contain-text");
  appendTextElement(form, "h3", "work-heading contain-text", "Propose correction");
  const titleLabel = element("label", "", "Title");
  const title = element("input");
  title.setAttribute("name", "title");
  title.setAttribute("maxlength", "160");
  title.value = note.title ?? "";
  titleLabel.append(title);
  const bodyLabel = element("label", "", "Body");
  const body = element("textarea");
  body.setAttribute("name", "body");
  body.setAttribute("maxlength", "2000");
  body.value = note.body ?? "";
  bodyLabel.append(body);
  const submit = element("button", "", "Create correction proposal");
  submit.setAttribute("type", "submit");
  submit.disabled = disabled;
  form.append(titleLabel, bodyLabel, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const nextTitle = String(title.value ?? "").trim();
    const nextBody = String(body.value ?? "").trim();
    if (
      !nextTitle
      || !nextBody
      || nextTitle.length > 160
      || nextBody.length > 2000
    ) {
      return;
    }
    handlers.onCreateCorrection?.(note, {
      expected_revision: note.revision,
      note_kind: note.note_kind,
      title: nextTitle,
      body: nextBody,
      source_session_id: note.source_session_id,
      source_message_ids: note.source_message_ids ?? [],
    });
  });
  container.append(form);
}

function renderNoteDetail(container, state, disabled, handlers) {
  const detail = state.detail ?? {};
  if (detail.status === "loading") {
    appendTextElement(container, "p", "muted contain-text", "Loading note detail...");
    return;
  }
  if (detail.status === "error") {
    appendTextElement(
      container,
      "p",
      "form-error contain-text",
      detail.error ?? "Note detail unavailable.",
    );
    return;
  }
  const note = detail.note;
  if (!note) {
    return;
  }
  const card = element("div", "notes-card contain-text");
  appendTextElement(
    card,
    "p",
    "muted contain-text",
    note.status === "archived" ? "Archived note" : "Saved note",
  );
  appendTextElement(card, "h3", "work-heading contain-text", note.title);
  appendTextElement(card, "p", "muted contain-text", humanLabel(note.note_kind));
  appendTextElement(card, "p", "contain-text", note.body);
  appendTextElement(card, "p", "muted contain-text", `Revision ${note.revision}`);
  const actions = element("div", "notes-actions contain-text");
  if (note.status === "archived") {
    const restore = element("button", "", "Restore");
    restore.setAttribute("type", "button");
    restore.setAttribute("data-note-action", "restore");
    restore.disabled = disabled;
    restore.addEventListener("click", () => handlers.onRestoreNote?.(note));
    actions.append(restore);
  } else {
    const archive = element("button", "", "Archive");
    archive.setAttribute("type", "button");
    archive.setAttribute("data-note-action", "archive");
    archive.disabled = disabled;
    archive.addEventListener("click", () => handlers.onArchiveNote?.(note));
    actions.append(archive);
  }
  const deleteButton = element("button", "", "Delete");
  deleteButton.setAttribute("type", "button");
  deleteButton.setAttribute("data-note-action", "delete");
  deleteButton.disabled = disabled;
  deleteButton.addEventListener("click", () => {
    if (deleteButton.disabled) {
      return;
    }
    if (globalThis.confirm?.(`Delete workspace note: ${note.title}?`) === false) {
      return;
    }
    handlers.onDeleteNote?.(note);
  });
  actions.append(deleteButton);
  card.append(actions);
  container.append(card);
  if (note.status !== "archived") {
    renderCorrectionForm(container, note, disabled, handlers);
  }
  if (Array.isArray(detail.events) && detail.events.length > 0) {
    appendTextElement(container, "h3", "work-heading contain-text", "Recent note events");
    for (const event of detail.events) {
      appendTextElement(container, "p", "notes-event contain-text", humanLabel(event.event_type));
    }
  }
}

export function renderNotesPanel(container, notesState, handlers = {}) {
  container.replaceChildren();
  const state = notesState ?? {};
  if (state.status === "loading") {
    appendTextElement(container, "p", "muted contain-text", "Loading notes...");
  }
  if (state.status === "error") {
    appendTextElement(
      container,
      "p",
      "form-error contain-text",
      state.error ?? "Notes unavailable.",
    );
  }
  const disabled = state.pendingRequest !== null;
  renderPendingProposals(
    container,
    Array.isArray(state.pendingProposals) ? state.pendingProposals : [],
    disabled,
    handlers,
  );
  renderNoteList(
    container,
    Array.isArray(state.notes) ? state.notes : [],
    state,
    disabled,
    handlers,
  );
  renderNoteProposalForm(container, disabled, handlers);
  renderNoteDetail(container, state, disabled, handlers);
}

export function createNotesView(elements, handlers = {}) {
  return {
    render(state) {
      renderNotesPanel(elements.panel, state.notes, handlers);
    },
  };
}
