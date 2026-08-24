import { appendTextElement, setText } from "./render.mjs";

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

function feedbackCounts(item) {
  const counts = item.feedback_counts ?? {};
  return compactText([
    `accepted ${counts.accepted ?? 0}`,
    `rejected ${counts.rejected ?? 0}`,
    `edited ${counts.edited ?? 0}`,
  ]);
}

export function buildBlueprintDownload(detail) {
  return buildBlueprintExports(detail)[0];
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

export function buildBlueprintExports(detail) {
  const reference = detail.metadata.reference;
  const label = reference.display_label
    ?? detail.blueprint?.synthesized_conceptual_model?.project_name
    ?? "blueprint";
  const basename = `${slug(label)}-${reference.artifact_id}`;
  const markdown = blueprintMarkdown(detail);
  return [
    {
      format: "json",
      label: "JSON",
      filename: `${basename}.json`,
      href: dataHref("application/json", JSON.stringify(detail, null, 2)),
    },
    {
      format: "md",
      label: "Markdown",
      filename: `${basename}.md`,
      href: dataHref("text/markdown", markdown),
    },
    {
      format: "txt",
      label: "Text",
      filename: `${basename}.txt`,
      href: dataHref("text/plain", markdown.replace(/^#+ /gm, "")),
    },
    {
      format: "pdf-print",
      label: "PDF / Print",
      filename: `${basename}.pdf`,
      href: "#print-work",
    },
  ];
}

function renderExportControls(parent, detail, handlers) {
  const box = document.createElement("section");
  box.classList.add("export-controls", "contain-text");
  box.setAttribute("data-export-controls", "");
  appendTextElement(box, "h4", "", "Export");
  for (const item of buildBlueprintExports(detail)) {
    if (item.format === "pdf-print") {
      const button = document.createElement("button");
      button.type = "button";
      setText(button, item.label);
      button.addEventListener("click", () => {
        handlers.onPrintWork?.();
      });
      box.append(button);
      continue;
    }
    const link = document.createElement("a");
    link.href = item.href;
    link.download = item.filename;
    setText(link, item.label);
    box.append(link);
  }
  parent.append(box);
}

export function renderWorkList(container, work, handlers) {
  container.replaceChildren();
  if (work.list.status === "loading") {
    appendTextElement(container, "p", "muted", "Loading Work...");
    return;
  }
  if (work.list.status === "error") {
    appendTextElement(container, "p", "form-error", work.list.error);
    return;
  }
  if (!work.list.items.length) {
    appendTextElement(container, "p", "muted", "No Work loaded yet.");
    return;
  }
  for (const item of work.list.items) {
    const button = document.createElement("button");
    button.type = "button";
    button.classList.add("work-list-item", "contain-text");
    button.setAttribute("data-artifact-id", item.reference.artifact_id);
    setText(button, compactText([
      item.reference.display_label,
      item.reference.artifact_id,
      feedbackCounts(item),
    ]));
    button.addEventListener("click", () => {
      handlers.onSelectArtifact(item.reference.artifact_id);
    });
    container.append(button);
  }
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

function renderFeedbackTargets(parent, detail, handlers) {
  appendTextElement(parent, "h4", "", "Feedback targets");
  for (const target of detail.feedback_targets ?? []) {
    const form = document.createElement("form");
    form.classList.add("feedback-form");
    form.setAttribute("data-feedback-target", target.target_id);

    appendTextElement(form, "p", "work-heading", compactText([
      target.display_label,
      target.target_kind,
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
      event.reference.feedback_id,
      event.reference.decision,
      event.status,
      event.feedback_text,
      event.supersedes_feedback_id
        ? `supersedes ${event.supersedes_feedback_id}`
        : "",
      event.superseded_by_feedback_id
        ? `superseded by ${event.superseded_by_feedback_id}`
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
      "Select a Work item to inspect its canonical backend detail.",
    );
    return;
  }
  if (work.detail.status === "loading") {
    appendTextElement(container, "p", "muted", "Loading Work detail...");
    return;
  }
  if (work.detail.status === "error") {
    appendTextElement(container, "p", "form-error", work.detail.error);
    return;
  }

  const detail = work.detail.item;
  renderExportControls(container, detail, handlers);

  renderBlueprint(container, detail.blueprint);
  appendTextElement(container, "h4", "", "Verified adaptations");
  appendList(container, (detail.adaptations ?? []).map((item) => compactText([
    item.category,
    item.status,
    item.signal_id,
  ])));
  renderFeedbackTargets(container, detail, handlers);

  const feedbackContainer = document.createElement("section");
  feedbackContainer.setAttribute("data-feedback-history", "");
  renderFeedbackHistory(feedbackContainer, work);
  container.append(feedbackContainer);
}

export function createWorkView(elements, handlers) {
  return {
    render(state) {
      renderWorkList(elements.list, state.work, handlers);
      renderWorkDetail(elements.detail, state.work, handlers);
    },
  };
}
