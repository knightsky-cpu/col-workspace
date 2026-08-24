import { appendTextElement, humanLabel, setText } from "./render.mjs";

function compactText(parts) {
  return parts
    .filter((part) => part !== undefined && part !== null && part !== "")
    .map(String)
    .join(" · ");
}

function appendList(parent, values) {
  const list = document.createElement("ul");
  for (const value of values ?? []) {
    appendTextElement(list, "li", "", value);
  }
  parent.append(list);
}

function appendSectionText(parent, title, values) {
  appendTextElement(parent, "h4", "", title);
  appendList(parent, values);
}

function slug(value) {
  return String(value ?? "blueprint")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "blueprint";
}

function artifactReference(detail) {
  return detail.metadata?.reference ?? detail.reference ?? {};
}

function isSingleFileArtifactDetail(detail) {
  return artifactReference(detail).artifact_type === "single_file_artifact";
}

function artifactTypeLabel(item) {
  const format = item.format ?? item.metadata?.format ?? item.artifact?.format;
  const family = item.artifact_family
    ?? item.metadata?.artifact_family
    ?? item.artifact?.artifact_family;
  return [
    format ? humanLabel(format) : "",
    family ? humanLabel(family).toLowerCase() : "",
  ].filter(Boolean).join(" ");
}

function feedbackCounts(item) {
  const counts = item.feedback_counts ?? {};
  return compactText([
    `Accepted ${counts.accepted ?? 0}`,
    `Rejected ${counts.rejected ?? 0}`,
    `Edited ${counts.edited ?? 0}`,
  ]);
}

export function buildArtifactCreateRequest(formData) {
  const request = {
    artifact_family: String(formData.get("artifact_family") ?? "").trim(),
    format: String(formData.get("format") ?? "").trim(),
    filename: String(formData.get("filename") ?? "").trim(),
    source_text: String(formData.get("source_text") ?? "").trim(),
  };
  const displayLabel = String(formData.get("display_label") ?? "").trim();
  if (displayLabel) {
    request.display_label = displayLabel;
  }
  return request;
}

export function buildBlueprintDownload(detail) {
  return buildBlueprintExports(detail).find((item) => item.format === "json")
    ?? buildBlueprintExports(detail)[0];
}

function blueprintMarkdown(detail) {
  const reference = detail.metadata.reference;
  const blueprint = detail.blueprint;
  const model = blueprint.synthesized_conceptual_model;
  const lines = [
    `# ${model.project_name}`,
    "",
    model.core_value_proposition,
    "",
    `Artifact ID: ${reference.artifact_id}`,
    `Schema version: ${reference.schema_version}`,
    "",
    "## In scope",
    ...(model.in_scope ?? []).map((item) => `- ${item}`),
    "",
    "## Out of scope",
    ...(model.out_of_scope ?? []).map((item) => `- ${item}`),
    "",
    "## Assumptions",
    ...(model.assumptions ?? []).map((item) => `- ${item}`),
    "",
    "## Architectural decisions",
  ];
  for (const decision of blueprint.architectural_decisions ?? []) {
    lines.push(
      "",
      `### ${decision.component_name}`,
      decision.proposed_solution,
      "",
      decision.rationale,
    );
  }
  return lines.join("\n");
}

function dataHref(mimeType, value) {
  return `data:${mimeType};charset=utf-8,${encodeURIComponent(value)}`;
}

function replaceExtension(filename, extension) {
  const base = String(filename ?? "artifact")
    .replace(/[/\\]/g, "-")
    .replace(/\.[^.]*$/, "")
    || "artifact";
  return extension ? `${base}.${extension}` : base;
}

export function buildBlueprintExports(detail) {
  const reference = detail.metadata.reference;
  const label = reference.display_label
    ?? detail.blueprint?.synthesized_conceptual_model?.project_name
    ?? "blueprint";
  const basename = slug(label);
  const markdown = blueprintMarkdown(detail);
  return [
    {
      format: "md",
      label: "Markdown",
      filename: `${basename}.md`,
      href: dataHref("text/markdown", markdown),
      primary: true,
    },
    {
      format: "txt",
      label: "Text",
      filename: `${basename}.txt`,
      href: dataHref("text/plain", markdown.replace(/^#+ /gm, "")),
    },
    {
      format: "json",
      label: "Metadata JSON",
      filename: `${basename}.json`,
      href: dataHref("application/json", JSON.stringify(detail, null, 2)),
    },
    {
      format: "pdf-print",
      label: "Print / Save as PDF",
      filename: `${basename}.pdf`,
      href: "#print-work",
    },
  ];
}

function singleFileArtifactMarkdown(detail) {
  const artifact = detail.artifact ?? {};
  const metadata = detail.metadata ?? {};
  const reference = artifactReference(detail);
  const label = reference.display_label
    ?? artifact.display_label
    ?? artifact.filename
    ?? metadata.filename
    ?? "Artifact";
  const type = artifactTypeLabel({
    format: artifact.format ?? metadata.format,
    artifact_family: artifact.artifact_family ?? metadata.artifact_family,
  });
  return [
    `# ${label}`,
    "",
    type,
    "",
    artifact.summary ?? "",
    "",
    "```",
    artifact.content ?? "",
    "```",
  ].join("\n");
}

function mimeTypeForArtifact(format) {
  const normalized = String(format ?? "").toLowerCase();
  if (normalized === "json") {
    return "application/json";
  }
  if (normalized === "markdown" || normalized === "md") {
    return "text/markdown";
  }
  if (normalized === "html") {
    return "text/html";
  }
  if (normalized === "css") {
    return "text/css";
  }
  if (normalized === "javascript" || normalized === "js") {
    return "text/javascript";
  }
  return "text/plain";
}

export function buildSingleFileArtifactExports(detail) {
  const artifact = detail.artifact ?? {};
  const metadata = detail.metadata ?? {};
  const reference = artifactReference(detail);
  const label = reference.display_label
    ?? artifact.display_label
    ?? metadata.filename
    ?? "artifact";
  const filename = artifact.filename ?? metadata.filename ?? `${slug(label)}.txt`;
  const markdown = singleFileArtifactMarkdown(detail);
  const content = artifact.content ?? "";
  const original = {
    format: "original",
    label: "Original",
    filename,
    href: dataHref(mimeTypeForArtifact(artifact.format ?? metadata.format), content),
    primary: true,
  };
  const markdownExport = {
    format: "md",
    label: "Markdown",
    filename: replaceExtension(filename, "md"),
    href: dataHref("text/markdown", markdown),
  };
  const textExport = {
    format: "txt",
    label: "Text",
    filename: replaceExtension(filename, "txt"),
    href: dataHref("text/plain", content || markdown),
  };
  const htmlExport = {
    format: "html",
    label: "HTML",
    filename: replaceExtension(filename, "html"),
    href: dataHref(
      "text/html",
      `<pre>${String(content || markdown)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")}</pre>`,
    ),
  };
  const jsonExport = {
    format: "json",
    label: "Metadata JSON",
    filename: replaceExtension(filename, "json"),
    href: dataHref("application/json", JSON.stringify(detail, null, 2)),
  };
  const printExport = {
    format: "pdf-print",
    label: "Print / Save as PDF",
    filename: replaceExtension(filename, "pdf"),
    href: "#print-work",
  };
  const artifactFormat = String(artifact.format ?? metadata.format ?? "")
    .toLowerCase();
  const alternatives = [markdownExport, textExport, htmlExport];
  if (artifactFormat === "json") {
    alternatives.push(jsonExport);
  }
  return [
    original,
    ...alternatives,
    printExport,
  ];
}

function buildArtifactExports(detail) {
  if (isSingleFileArtifactDetail(detail)) {
    return buildSingleFileArtifactExports(detail);
  }
  return buildBlueprintExports(detail);
}

function renderExportControls(parent, detail, handlers) {
  const box = document.createElement("section");
  box.classList.add("export-controls", "contain-text");
  box.setAttribute("data-export-controls", "");
  appendTextElement(box, "h4", "", "Export");
  const exports = buildArtifactExports(detail);
  const primaryExport = exports.find((item) => item.primary)
    ?? exports.find((item) => item.format !== "pdf-print");
  if (primaryExport) {
    const primary = document.createElement("a");
    primary.classList.add("control-compact", "button-link");
    primary.setAttribute("data-primary-export", "");
    primary.href = primaryExport.href;
    primary.download = primaryExport.filename;
    primary.setAttribute("download", primaryExport.filename);
    setText(primary, "Export");
    box.append(primary);
  }
  const alternatives = exports.filter((item) => (
    item !== primaryExport && item.format !== "pdf-print"
  ));
  if (alternatives.length) {
    const alternative = document.createElement("a");
    alternative.classList.add("control-compact", "button-link");
    alternative.setAttribute("data-alternative-export", "");
    setText(alternative, "Export alternative");
    box.append(alternative);

    const select = document.createElement("select");
    select.classList.add("control-compact");
    select.setAttribute("data-export-alternative-select", "");
    for (const item of alternatives) {
      const option = document.createElement("option");
      option.value = item.format;
      setText(option, item.label);
      select.append(option);
    }
    box.append(select);

    const syncAlternative = () => {
      const item = alternatives.find((entry) => entry.format === select.value)
        ?? alternatives[0];
      alternative.href = item.href;
      alternative.download = item.filename;
      alternative.setAttribute("download", item.filename);
    };
    select.addEventListener("change", syncAlternative);
    syncAlternative();
  }
  const printExport = exports.find((item) => item.format === "pdf-print");
  if (printExport) {
    const button = document.createElement("button");
    button.classList.add("control-compact");
    button.type = "button";
    button.setAttribute("data-print-export", "");
    setText(button, printExport.label);
    button.addEventListener("click", () => {
      handlers.onPrintWork?.();
    });
    box.append(button);
  }
  parent.append(box);
}

export function renderWorkList(container, work, handlers) {
  container.replaceChildren();
  if (work.list.status === "loading") {
    appendTextElement(container, "p", "muted", "Loading Artifacts...");
    return;
  }
  if (work.list.status === "error") {
    appendTextElement(container, "p", "form-error", work.list.error);
    return;
  }
  const lifecycleStatus = work.list.lifecycleStatus ?? "active";
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.classList.add("control-compact");
  toggle.setAttribute("data-artifact-lifecycle-toggle", "");
  setText(
    toggle,
    lifecycleStatus === "archived" ? "Show Active" : "Show Archived",
  );
  toggle.addEventListener("click", () => {
    handlers.onSetArtifactLifecycleStatus?.(
      lifecycleStatus === "archived" ? "active" : "archived",
    );
  });
  if (!work.list.items.length) {
    container.append(toggle);
    appendTextElement(
      container,
      "p",
      "muted",
      lifecycleStatus === "archived"
        ? "No Archived Artifacts."
        : "No Artifacts loaded yet.",
    );
    return;
  }
  for (const item of work.list.items) {
    const reference = item.reference;
    const button = document.createElement("button");
    button.type = "button";
    button.classList.add("work-list-item", "contain-text");
    button.setAttribute("data-artifact-id", reference.artifact_id);
    if (work.selectedArtifactId === reference.artifact_id) {
      button.setAttribute("aria-current", "true");
    }
    const secondary = reference.artifact_type === "single_file_artifact"
      ? compactText([
          artifactTypeLabel(item),
          item.parent_artifact_id ? "Revised version" : "",
        ])
      : feedbackCounts(item);
    setText(button, compactText([
      reference.display_label,
      secondary,
    ]));
    button.addEventListener("click", () => {
      handlers.onSelectArtifact(reference.artifact_id);
    });
    container.append(button);
  }
  container.append(toggle);
}

function renderBlueprint(parent, blueprint) {
  const model = blueprint.synthesized_conceptual_model;
  appendTextElement(parent, "h3", "", model.project_name);
  appendTextElement(parent, "p", "", model.core_value_proposition);
  appendSectionText(parent, "In scope", model.in_scope);
  appendSectionText(parent, "Out of scope", model.out_of_scope);
  appendSectionText(parent, "Assumptions", model.assumptions);

  appendTextElement(parent, "h4", "", "Architectural decisions");
  for (const decision of blueprint.architectural_decisions ?? []) {
    appendTextElement(parent, "p", "work-heading", decision.component_name);
    appendTextElement(parent, "p", "", decision.proposed_solution);
    appendTextElement(parent, "p", "muted", decision.rationale);
    for (const alternative of decision.alternatives ?? []) {
      appendTextElement(parent, "p", "muted", compactText([
        alternative.option_name,
        alternative.tradeoff,
        alternative.reason_not_selected,
      ]));
    }
  }

  appendTextElement(parent, "h4", "", "Socratic questions");
  for (const question of blueprint.socratic_clarifying_questions ?? []) {
    appendTextElement(parent, "p", "work-heading", question.question_text);
    appendTextElement(parent, "p", "muted", question.why_this_matters);
    appendList(
      parent,
      (question.suggested_options ?? []).map((option) => compactText([
        option.label,
        option.impact,
      ])),
    );
  }

  appendTextElement(parent, "h4", "", "Roadmap");
  for (const phase of blueprint.step_by_step_execution_roadmap ?? []) {
    appendTextElement(parent, "p", "work-heading", phase.phase_name);
    appendTextElement(parent, "p", "", phase.objective);
    appendTextElement(parent, "p", "muted", phase.expected_deliverable);
    for (const task of phase.micro_tasks ?? []) {
      appendTextElement(parent, "p", "muted", compactText([
        task.task_description,
        task.complexity_level,
        (task.verification_steps ?? []).join("; "),
      ]));
    }
  }

  appendTextElement(parent, "h4", "", "Diagnostic warnings");
  for (const warning of blueprint.diagnostic_warnings ?? []) {
    appendTextElement(parent, "p", "work-heading", compactText([
      warning.severity,
      warning.affected_component,
    ]));
    appendTextElement(parent, "p", "", warning.risk_identified);
    appendTextElement(parent, "p", "muted", warning.preventative_guidance);
  }
}

function renderSingleFileArtifact(parent, detail) {
  const artifact = detail.artifact ?? {};
  const metadata = detail.metadata ?? {};
  const reference = artifactReference(detail);
  const label = reference.display_label
    ?? artifact.display_label
    ?? metadata.filename
    ?? artifact.filename
    ?? "Artifact";
  appendTextElement(parent, "h3", "", label);
  appendTextElement(parent, "p", "work-heading", artifactTypeLabel({
    format: artifact.format ?? metadata.format,
    artifact_family: artifact.artifact_family ?? metadata.artifact_family,
  }));
  if (artifact.summary) {
    appendTextElement(parent, "p", "", artifact.summary);
  }
  const content = document.createElement("pre");
  content.classList.add("artifact-content", "contain-text");
  const code = document.createElement("code");
  setText(code, artifact.content ?? "");
  content.append(code);
  parent.append(content);
}

function renderSingleFileArtifactLineage(parent, detail, handlers) {
  const parentArtifactId = detail.metadata?.parent_artifact_id ?? null;
  if (!parentArtifactId) {
    return;
  }
  const section = document.createElement("section");
  section.classList.add("feedback-form", "contain-text");
  section.setAttribute("data-artifact-lineage", "");
  appendTextElement(section, "h4", "", "Revised version");
  appendTextElement(
    section,
    "p",
    "muted",
    "This artifact is a newer version. Original artifact is preserved.",
  );
  const button = document.createElement("button");
  button.classList.add("control-compact");
  button.type = "button";
  button.setAttribute("data-open-parent-artifact", "");
  setText(button, "Open original artifact");
  button.addEventListener("click", () => {
    handlers.onSelectArtifact?.(parentArtifactId);
  });
  section.append(button);
  parent.append(section);
}

function renderSingleFileArtifactLifecycle(parent, detail, handlers) {
  const reference = artifactReference(detail);
  const lifecycleStatus = detail.metadata?.lifecycle_status ?? "active";
  const button = document.createElement("button");
  button.classList.add("control-compact");
  button.type = "button";
  button.setAttribute(
    lifecycleStatus === "archived"
      ? "data-restore-artifact"
      : "data-archive-artifact",
    "",
  );
  setText(button, lifecycleStatus === "archived" ? "Restore" : "Archive");
  button.addEventListener("click", () => {
    if (lifecycleStatus === "archived") {
      handlers.onRestoreArtifact?.(reference.artifact_id);
      return;
    }
    handlers.onArchiveArtifact?.(reference.artifact_id);
  });
  parent.append(button);
}

function renderSingleFileArtifactMetadataForm(parent, detail, handlers) {
  const artifact = detail.artifact ?? {};
  const metadata = detail.metadata ?? {};
  const reference = artifactReference(detail);
  const form = document.createElement("form");
  form.classList.add("feedback-form");
  form.setAttribute("data-artifact-metadata-form", "");

  appendTextElement(form, "h4", "", "Artifact details");

  const labelInput = document.createElement("input");
  labelInput.name = "display_label";
  labelInput.placeholder = "Display name";
  labelInput.value = reference.display_label
    ?? artifact.display_label
    ?? "";

  const filenameInput = document.createElement("input");
  filenameInput.name = "filename";
  filenameInput.placeholder = "Filename";
  filenameInput.value = metadata.filename
    ?? artifact.filename
    ?? "";

  const submit = document.createElement("button");
  submit.type = "submit";
  setText(submit, "Rename");

  form.append(labelInput, filenameInput, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    handlers.onUpdateArtifactMetadata?.(reference.artifact_id, {
      display_label: labelInput.value,
      filename: filenameInput.value,
    });
  });
  parent.append(form);
}

function renderSingleFileArtifactVersionForm(parent, detail, handlers) {
  const artifact = detail.artifact ?? {};
  const reference = artifactReference(detail);
  const form = document.createElement("form");
  form.classList.add("feedback-form");
  form.setAttribute("data-artifact-version-form", "");

  appendTextElement(form, "h4", "", "Edit artifact content");

  const content = document.createElement("textarea");
  content.name = "content";
  content.placeholder = "Updated artifact content";
  content.value = artifact.content ?? "";
  content.required = true;

  const filename = document.createElement("input");
  filename.name = "filename";
  filename.placeholder = "Filename";
  filename.value = artifact.filename ?? "";

  const displayLabel = document.createElement("input");
  displayLabel.name = "display_label";
  displayLabel.placeholder = "Display name";
  displayLabel.value = reference.display_label ?? "";

  const summary = document.createElement("input");
  summary.name = "summary";
  summary.placeholder = "Summary";
  summary.value = artifact.summary ?? "";

  const submit = document.createElement("button");
  submit.type = "submit";
  setText(submit, "Save new version");

  form.append(content, filename, displayLabel, summary, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    handlers.onCreateArtifactVersion?.(reference.artifact_id, {
      content: content.value,
      filename: filename.value,
      display_label: displayLabel.value,
      summary: summary.value,
    });
  });
  parent.append(form);
}

function renderFeedbackTargets(parent, detail, handlers) {
  appendTextElement(parent, "h4", "", "Feedback targets");
  for (const target of detail.feedback_targets ?? []) {
    const form = document.createElement("form");
    form.classList.add("feedback-form");
    form.setAttribute("data-feedback-target", target.target_id);

    appendTextElement(form, "p", "work-heading", compactText([
      target.display_label,
      humanLabel(target.target_kind),
    ]));

    const select = document.createElement("select");
    select.name = "decision";
    for (const value of ["accepted", "rejected", "edited"]) {
      const option = document.createElement("option");
      option.value = value;
      setText(option, value);
      select.append(option);
    }

    const feedback = document.createElement("textarea");
    feedback.name = "feedback_text";
    feedback.required = true;
    feedback.placeholder = "Feedback text";

    const correction = document.createElement("textarea");
    correction.name = "correction_text";
    correction.placeholder = "Correction text for edited feedback";
    correction.required = false;

    select.addEventListener("change", () => {
      correction.required = select.value === "edited";
    });

    const supersedes = document.createElement("input");
    supersedes.name = "supersedes_feedback_id";
    supersedes.placeholder = "Optional feedback ID to supersede";

    const submit = document.createElement("button");
    submit.type = "submit";
    setText(submit, "Record feedback");

    form.append(select, feedback, correction, supersedes, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      handlers.onSubmitFeedback({
        artifact_id: detail.metadata.reference.artifact_id,
        target_id: target.target_id,
        decision: select.value,
        feedback_text: feedback.value,
        correction_text: correction.value,
        supersedes_feedback_id: supersedes.value,
        expected_schema_version: detail.metadata.reference.schema_version,
      });
    });
    parent.append(form);
  }
}

export function renderFeedbackHistory(container, work) {
  container.replaceChildren();
  if (work.feedback.status === "loading") {
    appendTextElement(container, "p", "muted", "Loading feedback...");
    return;
  }
  if (work.feedback.status === "error") {
    appendTextElement(container, "p", "form-error", work.feedback.error);
    return;
  }
  if (!work.feedback.events.length) {
    appendTextElement(container, "p", "muted", "No feedback recorded yet.");
    return;
  }
  for (const event of work.feedback.events) {
    appendTextElement(container, "p", "feedback-event contain-text", compactText([
      "Feedback",
      humanLabel(event.reference.decision),
      humanLabel(event.status),
      event.feedback_text,
      event.supersedes_feedback_id
        ? "supersedes earlier feedback"
        : "",
      event.superseded_by_feedback_id
        ? "superseded by newer feedback"
        : "",
    ]));
  }
}

export function renderWorkDetail(container, work, handlers) {
  container.replaceChildren();
  if (work.detail.status === "idle") {
    appendTextElement(
      container,
      "p",
      "muted",
      "Select an Artifact to inspect its canonical backend detail.",
    );
    return;
  }
  if (work.detail.status === "loading") {
    appendTextElement(container, "p", "muted", "Loading Artifact detail...");
    return;
  }
  if (work.detail.status === "error") {
    appendTextElement(container, "p", "form-error", work.detail.error);
    return;
  }

  const detail = work.detail.item;
  renderExportControls(container, detail, handlers);

  if (isSingleFileArtifactDetail(detail)) {
    renderSingleFileArtifact(container, detail);
    renderSingleFileArtifactLineage(container, detail, handlers);
    renderSingleFileArtifactMetadataForm(container, detail, handlers);
    renderSingleFileArtifactVersionForm(container, detail, handlers);
    renderSingleFileArtifactLifecycle(container, detail, handlers);
    return;
  }

  renderBlueprint(container, detail.blueprint);
  appendTextElement(container, "h4", "", "Verified adaptations");
  appendList(container, (detail.adaptations ?? []).map((item) => compactText([
    humanLabel(item.category),
    humanLabel(item.status),
  ])));
  renderFeedbackTargets(container, detail, handlers);

  const feedbackContainer = document.createElement("section");
  feedbackContainer.setAttribute("data-feedback-history", "");
  renderFeedbackHistory(feedbackContainer, work);
  container.append(feedbackContainer);
}

export function createWorkView(elements, handlers) {
  elements.createForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    handlers.onCreateArtifact?.(
      buildArtifactCreateRequest(new FormData(event.currentTarget)),
    );
  });

  return {
    render(state) {
      renderWorkList(elements.list, state.work, handlers);
      renderWorkDetail(elements.detail, state.work, handlers);
    },
  };
}
