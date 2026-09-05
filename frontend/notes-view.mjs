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

function isExpanded(disclosure, key, id) {
  return Array.isArray(disclosure?.[key])
    && disclosure[key].includes(String(id ?? ""));
}

function disclosureId(prefix, id) {
  return `${prefix}-${String(id ?? "").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function eventTargetIsInteractive(event) {
  const target = event?.target;
  if (!target || typeof target.tagName !== "string") {
    return false;
  }
  return ["button", "input", "select", "textarea", "label"].includes(
    target.tagName.toLowerCase(),
  );
}

function renderPendingProposal(container, proposal, disabled, handlers, disclosure) {
  const expanded = isExpanded(disclosure, "proposalIds", proposal.proposal_id);
  const card = element("div", "notes-card contain-text");
  card.setAttribute("data-note-proposal", proposal.proposal_id);
  if (expanded) {
    card.setAttribute("data-disclosure-expanded", "true");
  }
  const panelId = disclosureId("note-proposal-details", proposal.proposal_id);
  appendTextElement(card, "p", "muted contain-text", "Pending note proposal");
  const toggle = element("button", "subcard-disclosure-toggle contain-text", proposal.title);
  toggle.setAttribute("type", "button");
  toggle.setAttribute("data-disclosure-toggle", "note-proposal");
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.setAttribute("aria-controls", panelId);
  toggle.addEventListener("click", () => {
    handlers.onToggleProposalDisclosure?.(proposal.proposal_id);
  });
  card.append(toggle);
  appendTextElement(card, "p", "muted contain-text", humanLabel(proposal.note_kind));
  if (!expanded) {
    container.append(card);
    return;
  }
  const details = element("div", "subcard-disclosure-panel contain-text");
  details.setAttribute("id", panelId);
  appendTextElement(details, "p", "contain-text", proposal.body);
  appendTextElement(
    details,
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
  details.append(actions);
  card.append(details);
  container.append(card);
}

function renderPendingProposals(container, proposals, disabled, handlers, disclosure) {
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
    renderPendingProposal(container, proposal, disabled, handlers, disclosure);
  }
}

function renderNoteList(container, notes, state, disabled, handlers, disclosure, drafts) {
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
    if (
      note.note_id === state.selectedNoteId
      && state.detail?.status === "ready"
      && state.detail?.note?.note_id === note.note_id
    ) {
      renderSelectedNoteDetail(
        container,
        state.detail.note,
        state.detail,
        disabled,
        handlers,
        disclosure,
        drafts,
      );
      continue;
    }
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

function updateDraft(drafts, key, patch) {
  drafts.set(key, {
    ...(drafts.get(key) ?? {}),
    ...patch,
  });
}

async function submitAndClearDraft(drafts, key, submit) {
  const draft = drafts.get(key);
  drafts.delete(key);
  try {
    const result = await submit();
    if (result === false && draft !== undefined) {
      drafts.set(key, draft);
    }
    return result;
  } catch (error) {
    if (draft !== undefined) {
      drafts.set(key, draft);
    }
    throw error;
  }
}

function renderNoteProposalForm(container, disabled, handlers, drafts) {
  const draftKey = "note-proposal:create";
  const draft = drafts?.get(draftKey) ?? {};
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
  kind.value = draft.note_kind ?? "decision";
  kind.addEventListener("change", () => {
    updateDraft(drafts, draftKey, { note_kind: kind.value });
  });
  kindLabel.append(kind);
  const titleLabel = element("label", "", "Title");
  const title = element("input");
  title.setAttribute("name", "title");
  title.setAttribute("maxlength", "120");
  title.required = true;
  title.value = draft.title ?? "";
  title.addEventListener("input", () => {
    updateDraft(drafts, draftKey, { title: title.value });
  });
  titleLabel.append(title);
  const bodyLabel = element("label", "", "Body");
  const body = element("textarea");
  body.setAttribute("name", "body");
  body.setAttribute("maxlength", "2000");
  body.required = true;
  body.value = draft.body ?? "";
  body.addEventListener("input", () => {
    updateDraft(drafts, draftKey, { body: body.value });
  });
  bodyLabel.append(body);
  const submit = element("button", "", "Create note proposal");
  submit.setAttribute("type", "submit");
  submit.disabled = disabled;
  form.append(kindLabel, titleLabel, bodyLabel, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const nextTitle = String(title.value ?? "").trim();
    const nextBody = String(body.value ?? "").trim();
    if (!nextTitle || !nextBody || nextTitle.length > 120 || nextBody.length > 2000) {
      return;
    }
    await submitAndClearDraft(drafts, draftKey, () => (
      handlers.onCreateNoteProposal?.({
        note_kind: kind.value,
        title: nextTitle,
        body: nextBody,
      })
    ));
  });
  container.append(form);
}

function renderCorrectionForm(container, note, disabled, handlers, drafts) {
  const draftKey = `note-correction:${note.note_id}:${note.revision}`;
  const draft = drafts?.get(draftKey) ?? {};
  const form = element("form", "notes-correction-form contain-text");
  form.setAttribute("data-note-correction-form", "true");
  appendTextElement(form, "h3", "work-heading contain-text", "Propose correction");
  const titleLabel = element("label", "", "Title");
  const title = element("input");
  title.setAttribute("name", "title");
  title.setAttribute("maxlength", "160");
  title.value = draft.title ?? note.title ?? "";
  title.addEventListener("input", () => {
    updateDraft(drafts, draftKey, { title: title.value });
  });
  titleLabel.append(title);
  const bodyLabel = element("label", "", "Body");
  const body = element("textarea");
  body.setAttribute("name", "body");
  body.setAttribute("maxlength", "2000");
  body.value = draft.body ?? note.body ?? "";
  body.addEventListener("input", () => {
    updateDraft(drafts, draftKey, { body: body.value });
  });
  bodyLabel.append(body);
  const submit = element("button", "", "Create correction proposal");
  submit.setAttribute("type", "submit");
  submit.disabled = disabled;
  form.append(titleLabel, bodyLabel, submit);
  form.addEventListener("submit", async (event) => {
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
    await submitAndClearDraft(drafts, draftKey, () => (
      handlers.onCreateCorrection?.(note, {
        expected_revision: note.revision,
        note_kind: note.note_kind,
        title: nextTitle,
        body: nextBody,
        source_session_id: note.source_session_id,
        source_message_ids: note.source_message_ids ?? [],
      })
    ));
  });
  container.append(form);
}

function renderSelectedNoteDetail(container, note, detail, disabled, handlers, disclosure, drafts) {
  const card = element("div", "notes-card contain-text");
  card.setAttribute("data-note-id", note.note_id);
  card.setAttribute("data-note-detail", note.note_id);
  card.setAttribute("aria-current", "true");
  const expanded = isExpanded(disclosure, "detailNoteIds", note.note_id);
  if (expanded) {
    card.setAttribute("data-disclosure-expanded", "true");
  }
  const panelId = disclosureId("note-detail-details", note.note_id);
  card.addEventListener("click", (event) => {
    if (!eventTargetIsInteractive(event)) {
      handlers.onToggleDetailDisclosure?.(note.note_id);
    }
  });
  appendTextElement(
    card,
    "p",
    "muted contain-text",
    note.status === "archived" ? "Archived note" : "Saved note",
  );
  const toggle = element("button", "subcard-disclosure-toggle contain-text", note.title);
  toggle.setAttribute("type", "button");
  toggle.setAttribute("data-disclosure-toggle", "note-detail");
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.setAttribute("aria-controls", panelId);
  toggle.addEventListener("click", (event) => {
    event.stopPropagation?.();
    handlers.onToggleDetailDisclosure?.(note.note_id);
  });
  card.append(toggle);
  appendTextElement(card, "p", "muted contain-text", humanLabel(note.note_kind));
  if (!expanded) {
    container.append(card);
    return;
  }
  const details = element("div", "subcard-disclosure-panel contain-text");
  details.setAttribute("id", panelId);
  appendTextElement(details, "p", "contain-text", note.body);
  appendTextElement(details, "p", "muted contain-text", `Revision ${note.revision}`);
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
  details.append(actions);
  if (note.status !== "archived") {
    renderCorrectionForm(details, note, disabled, handlers, drafts);
  }
  if (Array.isArray(detail.events) && detail.events.length > 0) {
    appendTextElement(details, "h3", "work-heading contain-text", "Recent note events");
    for (const event of detail.events) {
      appendTextElement(details, "p", "notes-event contain-text", humanLabel(event.event_type));
    }
  }
  card.append(details);
  container.append(card);
}

function renderNoteDetailStatus(container, state) {
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
}

export function renderNotesPanel(container, notesState, handlers = {}, disclosure = {}, drafts = new Map()) {
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
    disclosure,
  );
  renderNoteList(
    container,
    Array.isArray(state.notes) ? state.notes : [],
    state,
    disabled,
    handlers,
    disclosure,
    drafts,
  );
  renderNoteDetailStatus(container, state);
  renderNoteProposalForm(container, disabled, handlers, drafts);
}

export function createNotesView(elements, handlers = {}) {
  const drafts = new Map();
  return {
    render(state) {
      renderNotesPanel(
        elements.panel,
        state.notes,
        handlers,
        state.disclosure?.notes,
        drafts,
      );
    },
  };
}
