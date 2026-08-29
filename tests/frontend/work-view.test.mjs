import test from "node:test";
import assert from "node:assert/strict";

import {
  buildBlueprintExports,
  buildBlueprintDownload,
  renderFeedbackHistory,
  renderWorkDetail,
  renderWorkList,
} from "../../frontend/work-view.mjs";

function node(tagName = "div") {
  return {
    tagName,
    children: [],
    attributes: {},
    dataset: {},
    value: "",
    textContent: "",
    hidden: false,
    append(...items) {
      this.children.push(...items);
    },
    replaceChildren(...items) {
      this.children = items;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    addEventListener(name, handler) {
      this[`on${name}`] = handler;
    },
    classList: {
      values: [],
      add(...values) {
        this.values.push(...values);
      },
    },
  };
}

globalThis.document = {
  createElement(tagName) {
    return node(tagName);
  },
};

function textTree(item) {
  return [
    item.textContent,
    ...item.children.flatMap((child) => textTree(child)),
  ].join(" ");
}

function findTree(item, predicate) {
  if (!item) {
    return null;
  }
  if (predicate(item)) {
    return item;
  }
  for (const child of item.children) {
    const found = findTree(child, predicate);
    if (found) {
      return found;
    }
  }
  return null;
}

const detail = {
  metadata: {
    reference: {
      artifact_id: "blueprint--abc",
      artifact_type: "synthesis_blueprint",
      schema_version: "2.0",
      display_label: "Safe <Blueprint>",
    },
    feedback_counts: { accepted: 1, rejected: 0, edited: 0 },
    adaptation_categories: ["planning_granularity"],
  },
  blueprint: {
    synthesized_conceptual_model: {
      project_name: "Safe <Blueprint>",
      core_value_proposition: "Create useful work without unsafe rendering.",
      in_scope: ["Inspection"],
      out_of_scope: ["Mutation"],
      assumptions: ["Backend owns canonical detail."],
    },
    architectural_decisions: [
      {
        component_name: "Renderer",
        proposed_solution: "Use textContent.",
        rationale: "Prevents HTML injection.",
        alternatives: [
          {
            option_name: "innerHTML",
            tradeoff: "Easy but unsafe.",
            reason_not_selected: "Unsafe.",
          },
        ],
      },
    ],
    socratic_clarifying_questions: [
      {
        question_text: "Which target matters most?",
        why_this_matters: "Feedback needs a target.",
        suggested_options: [
          { label: "Whole artifact", impact: "Broad feedback." },
        ],
      },
    ],
    step_by_step_execution_roadmap: [
      {
        phase_name: "Phase 1",
        objective: "Inspect",
        expected_deliverable: "Detail panel",
        micro_tasks: [
          {
            task_description: "Render safely",
            complexity_level: "Low",
            verification_steps: ["Assert textContent"],
          },
        ],
      },
    ],
    diagnostic_warnings: [
      {
        affected_component: "Renderer",
        severity: "High",
        risk_identified: "Unsafe HTML",
        preventative_guidance: "Never use innerHTML.",
      },
    ],
  },
  feedback_targets: [
    {
      target_id: "target--whole",
      target_kind: "whole_blueprint",
      display_label: "Safe <Blueprint>",
    },
  ],
  adaptations: [
    {
      category: "planning_granularity",
      status: "provided_to_model",
      signal_id: "planning_granularity--1",
    },
  ],
  applied_feedback_ids: [],
};

const genericDetail = {
  metadata: {
    reference: {
      artifact_id: "artifact--script",
      artifact_type: "single_file_artifact",
      schema_version: "1.0",
      display_label: "Password Generator",
    },
    filename: "password_generator.py",
    artifact_family: "code",
    format: "python",
    byte_size: 32,
  },
  artifact: {
    artifact_family: "code",
    format: "python",
    filename: "password_generator.py",
    content: "print('secure')\n",
    summary: "Generates a secure password.",
  },
};

const textArtifactDetail = {
  metadata: {
    reference: {
      artifact_id: "artifact--note",
      artifact_type: "single_file_artifact",
      schema_version: "1.0",
      display_label: "Plain note",
    },
    filename: "note.txt",
    artifact_family: "document",
    format: "text",
    byte_size: 18,
  },
  artifact: {
    artifact_family: "document",
    format: "text",
    filename: "note.txt",
    content: "Plain text note.\n",
    summary: "A plain text note.",
  },
};

test("renderWorkList renders blueprint metadata and selection controls", () => {
  const selected = [];
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        items: [{
          reference: detail.metadata.reference,
          created_at: "2026-08-23T00:00:00Z",
          feedback_counts: { accepted: 1, rejected: 0, edited: 0 },
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    { onSelectArtifact: (artifactId) => selected.push(artifactId) },
  );

  const card = container.children.find((child) => (
    child.attributes["data-artifact-id"] === "blueprint--abc"
  ));
  const selectButton = card.children[0];
  assert.equal(textTree(card).includes("Safe <Blueprint>"), true);
  assert.equal(textTree(card).includes("blueprint--abc"), false);
  assert.equal(textTree(card).includes("Accepted 1"), true);
  assert.equal(
    card.classList.values.includes("contain-text"),
    true,
  );
  selectButton.onclick();
  assert.deepEqual(selected, ["blueprint--abc"]);
});

test("renderWorkList renders single-file artifact metadata collapsed by default", () => {
  const toggled = [];
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        items: [{
          reference: genericDetail.metadata.reference,
          filename: "password_generator.py",
          artifact_family: "code",
          format: "python",
          byte_size: 32,
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    { onToggleArtifactDisclosure: (artifactId) => toggled.push(artifactId) },
  );

  const card = container.children.find((child) => (
    child.attributes["data-artifact-id"] === "artifact--script"
  ));
  const archiveButton = findTree(card, (child) => (
    child.attributes["data-archive-artifact"] === ""
  ));
  const deleteButton = findTree(card, (child) => (
    child.attributes["data-delete-artifact"] === ""
  ));
  assert.equal(textTree(card).includes("Password Generator"), true);
  assert.equal(textTree(card).includes("Python code"), true);
  assert.equal(textTree(card).includes("artifact--script"), false);
  assert.equal(card.attributes["data-disclosure-expanded"], undefined);
  assert.equal(archiveButton, null);
  assert.equal(deleteButton, null);
  card.children[0].onclick();
  assert.deepEqual(toggled, ["artifact--script"]);
});

test("renderWorkList labels generic artifact versions without exposing parent ids", () => {
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        items: [{
          reference: {
            ...genericDetail.metadata.reference,
            artifact_id: "artifact--script-v2",
          },
          filename: "password_generator_v2.py",
          artifact_family: "code",
          format: "python",
          parent_artifact_id: "artifact--script",
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    { onSelectArtifact: () => {} },
  );

  const card = container.children.find((child) => (
    child.attributes["data-artifact-id"] === "artifact--script-v2"
  ));
  assert.equal(textTree(card).includes("Revised version"), true);
  assert.equal(textTree(card).includes("artifact--script"), false);
});

test("renderWorkList marks the selected artifact and avoids Work terminology", () => {
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        items: [{
          reference: detail.metadata.reference,
          created_at: "2026-08-23T00:00:00Z",
          feedback_counts: { accepted: 1, rejected: 0, edited: 0 },
        }],
        error: null,
      },
      selectedArtifactId: "blueprint--abc",
    },
    { onSelectArtifact: () => {} },
  );

  const card = container.children.find((child) => (
    child.attributes["data-artifact-id"] === "blueprint--abc"
  ));
  assert.equal(card.attributes["aria-current"], "true");
  assert.equal(textTree(card).includes("Work"), false);
});

test("renderWorkList uses artifact terminology for list states", () => {
  const container = node();

  renderWorkList(
    container,
    {
      list: { status: "loading", items: [], error: null },
      selectedArtifactId: null,
    },
    { onSelectArtifact: () => {} },
  );
  assert.equal(container.children[0].textContent, "Loading Artifacts...");

  renderWorkList(
    container,
    {
      list: { status: "ready", items: [], error: null },
      selectedArtifactId: null,
    },
    { onSelectArtifact: () => {} },
  );
  assert.equal(container.children[1].textContent, "No Artifacts loaded yet.");
});

test("renderWorkList can switch between active and archived artifact views", () => {
  const switches = [];
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        lifecycleStatus: "active",
        items: [{
          reference: genericDetail.metadata.reference,
          filename: "password_generator.py",
          artifact_family: "code",
          format: "python",
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    {
      onSelectArtifact: () => {},
      onSetArtifactLifecycleStatus: (status) => switches.push(status),
    },
  );

  const toggle = findTree(container, (child) => (
    child.attributes["data-artifact-lifecycle-filter"] === "archived"
  ));
  assert.ok(toggle);
  assert.equal(toggle.textContent, "Archived");
  toggle.onclick();
  assert.deepEqual(switches, ["archived"]);
});

test("renderWorkList places lifecycle controls before artifact cards", () => {
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        lifecycleStatus: "active",
        items: [{
          reference: genericDetail.metadata.reference,
          filename: "password_generator.py",
          artifact_family: "code",
          format: "python",
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    { onSelectArtifact: () => {} },
  );

  assert.equal(container.children[0].attributes["data-artifact-lifecycle-controls"], "");
  assert.equal(container.children[1].attributes["data-artifact-id"], "artifact--script");
});

test("renderWorkList keeps generic artifact lifecycle actions collapsed until card expansion", () => {
  const toggled = [];
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        lifecycleStatus: "active",
        items: [{
          reference: genericDetail.metadata.reference,
          filename: "password_generator.py",
          artifact_family: "code",
          format: "python",
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    {
      onToggleArtifactDisclosure: (artifactId) => toggled.push(artifactId),
    },
  );

  const card = container.children.find((child) => (
    child.attributes["data-artifact-id"] === "artifact--script"
  ));
  const archiveButton = findTree(card, (child) => (
    child.attributes["data-archive-artifact"] === ""
  ));
  const deleteButton = findTree(card, (child) => (
    child.attributes["data-delete-artifact"] === ""
  ));
  const manageButton = findTree(card, (child) => (
    child.textContent === "Manage"
  ));
  const toggleButton = findTree(card, (child) => (
    child.attributes["data-disclosure-toggle"] === "artifact-lifecycle"
  ));

  assert.equal(archiveButton, null);
  assert.equal(deleteButton, null);
  assert.equal(manageButton, null);
  assert.ok(toggleButton);
  assert.equal(toggleButton.textContent.includes("Password Generator"), true);
  toggleButton.onclick();

  assert.deepEqual(toggled, ["artifact--script"]);
});

test("renderWorkList exposes compact lifecycle actions when artifact card is expanded", () => {
  const selected = [];
  const archived = [];
  const deleted = [];
  let stopped = 0;
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        lifecycleStatus: "active",
        items: [{
          reference: genericDetail.metadata.reference,
          filename: "password_generator.py",
          artifact_family: "code",
          format: "python",
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    {
      onSelectArtifact: (artifactId) => selected.push(artifactId),
      onArchiveArtifact: (artifactId) => archived.push(artifactId),
      onDeleteArtifact: (artifactId) => deleted.push(artifactId),
    },
    { artifactIds: ["artifact--script"] },
  );

  const card = container.children.find((child) => (
    child.attributes["data-artifact-id"] === "artifact--script"
  ));
  const panel = findTree(card, (child) => (
    child.attributes["data-artifact-lifecycle-panel"] === ""
  ));
  const archiveButton = findTree(panel, (child) => (
    child.attributes["data-archive-artifact"] === ""
  ));
  const deleteButton = findTree(panel, (child) => (
    child.attributes["data-delete-artifact"] === ""
  ));
  const openButton = findTree(panel, (child) => (
    child.attributes["data-open-artifact"] === ""
  ));

  assert.equal(card.attributes["data-disclosure-expanded"], "true");
  assert.ok(openButton);
  assert.ok(archiveButton);
  assert.ok(deleteButton);
  assert.equal(openButton.textContent, "Open");
  assert.equal(archiveButton.textContent, "Archive");
  assert.equal(deleteButton.textContent, "Delete");
  openButton.onclick({ stopPropagation() { stopped += 1; } });
  archiveButton.onclick({ stopPropagation() { stopped += 1; } });
  deleteButton.onclick({ stopPropagation() { stopped += 1; } });

  assert.equal(stopped, 3);
  assert.deepEqual(selected, ["artifact--script"]);
  assert.deepEqual(archived, ["artifact--script"]);
  assert.deepEqual(deleted, ["artifact--script"]);
});

test("renderWorkList exposes restore and delete when archived generic artifact is expanded", () => {
  const selected = [];
  const restored = [];
  const deleted = [];
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        lifecycleStatus: "archived",
        items: [{
          reference: genericDetail.metadata.reference,
          filename: "password_generator.py",
          artifact_family: "code",
          format: "python",
          lifecycle_status: "archived",
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    {
      onSelectArtifact: (artifactId) => selected.push(artifactId),
      onRestoreArtifact: (artifactId) => restored.push(artifactId),
      onDeleteArtifact: (artifactId) => deleted.push(artifactId),
    },
    { artifactIds: ["artifact--script"] },
  );

  const card = container.children.find((child) => (
    child.attributes["data-artifact-id"] === "artifact--script"
  ));
  const panel = findTree(card, (child) => (
    child.attributes["data-artifact-lifecycle-panel"] === ""
  ));
  const restoreButton = findTree(panel, (child) => (
    child.attributes["data-restore-artifact"] === ""
  ));
  const archiveButton = findTree(panel, (child) => (
    child.attributes["data-archive-artifact"] === ""
  ));
  const deleteButton = findTree(panel, (child) => (
    child.attributes["data-delete-artifact"] === ""
  ));
  const openButton = findTree(panel, (child) => (
    child.attributes["data-open-artifact"] === ""
  ));

  assert.equal(archiveButton, null);
  assert.ok(openButton);
  assert.ok(restoreButton);
  assert.ok(deleteButton);
  assert.equal(openButton.textContent, "Open");
  assert.equal(restoreButton.textContent, "Restore");
  assert.equal(deleteButton.textContent, "Delete");
  openButton.onclick({ stopPropagation() {} });
  restoreButton.onclick({ stopPropagation() {} });
  deleteButton.onclick({ stopPropagation() {} });

  assert.deepEqual(selected, ["artifact--script"]);
  assert.deepEqual(restored, ["artifact--script"]);
  assert.deepEqual(deleted, ["artifact--script"]);
});

test("renderWorkList does not show generic lifecycle controls for blueprints", () => {
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        lifecycleStatus: "active",
        items: [{
          reference: detail.metadata.reference,
          created_at: "2026-08-23T00:00:00Z",
          feedback_counts: { accepted: 1, rejected: 0, edited: 0 },
        }],
        error: null,
      },
      selectedArtifactId: null,
    },
    { onSelectArtifact: () => {} },
  );

  const card = container.children.find((child) => (
    child.attributes["data-artifact-id"] === "blueprint--abc"
  ));
  assert.equal(findTree(card, (child) => child.attributes["data-archive-artifact"] === ""), null);
  assert.equal(findTree(card, (child) => child.attributes["data-delete-artifact"] === ""), null);
});

test("renderWorkList shows archived empty state and can return to active view", () => {
  const switches = [];
  const container = node();

  renderWorkList(
    container,
    {
      list: {
        status: "ready",
        lifecycleStatus: "archived",
        items: [],
        error: null,
      },
      selectedArtifactId: null,
    },
    {
      onSelectArtifact: () => {},
      onSetArtifactLifecycleStatus: (status) => switches.push(status),
    },
  );

  const toggle = findTree(container, (child) => (
    child.attributes["data-artifact-lifecycle-filter"] === "active"
  ));
  assert.ok(toggle);
  assert.equal(toggle.textContent, "Active");
  assert.equal(textTree(container).includes("No Archived Artifacts."), true);
  toggle.onclick();
  assert.deepEqual(switches, ["active"]);
});

test("renderWorkDetail projects canonical schema-2 blueprint text safely", () => {
  const container = node();

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: detail, error: null },
      feedback: { status: "ready", events: [], error: null },
    },
    { onSubmitFeedback: () => {} },
  );

  const text = textTree(container);
  assert.equal(text.includes("Safe <Blueprint>"), true);
  assert.equal(text.includes("Use textContent."), true);
  assert.equal(text.includes("Which target matters most?"), true);
  assert.equal(text.includes("Never use innerHTML."), true);
});

test("renderWorkDetail projects canonical single-file artifact safely", () => {
  const container = node();
  const archived = [];

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: genericDetail, error: null },
      feedback: { status: "idle", events: [], error: null },
    },
    {
      onSubmitFeedback: () => {},
      onPrintWork: () => {},
      onArchiveArtifact: (artifactId) => archived.push(artifactId),
    },
  );

  const text = textTree(container);
  assert.equal(text.includes("Password Generator"), true);
  assert.equal(text.includes("Python code"), true);
  assert.equal(text.includes("Generates a secure password."), true);
  assert.equal(text.includes("print('secure')"), true);
  assert.equal(text.includes("Feedback targets"), false);
  assert.equal(text.includes("artifact--script"), false);
  const archiveButton = container.children.find((child) => (
    child.attributes["data-archive-artifact"] === ""
  ));
  assert.ok(archiveButton);
  assert.equal(archiveButton.textContent, "Archive");
  archiveButton.onclick();
  assert.deepEqual(archived, ["artifact--script"]);
});

test("renderWorkDetail restores archived single-file artifacts", () => {
  const container = node();
  const restored = [];
  const archivedDetail = {
    ...genericDetail,
    metadata: {
      ...genericDetail.metadata,
      lifecycle_status: "archived",
    },
  };

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: archivedDetail, error: null },
      feedback: { status: "idle", events: [], error: null },
    },
    {
      onSubmitFeedback: () => {},
      onPrintWork: () => {},
      onRestoreArtifact: (artifactId) => restored.push(artifactId),
    },
  );

  const restoreButton = container.children.find((child) => (
    child.attributes["data-restore-artifact"] === ""
  ));
  const archiveButton = container.children.find((child) => (
    child.attributes["data-archive-artifact"] === ""
  ));
  assert.ok(restoreButton);
  assert.equal(archiveButton, undefined);
  assert.equal(restoreButton.textContent, "Restore");
  restoreButton.onclick();
  assert.deepEqual(restored, ["artifact--script"]);
});

test("renderWorkDetail shows generic artifact lineage and opens the original", () => {
  const container = node();
  const opened = [];
  const versionDetail = {
    ...genericDetail,
    metadata: {
      ...genericDetail.metadata,
      reference: {
        ...genericDetail.metadata.reference,
        artifact_id: "artifact--script-v2",
      },
      parent_artifact_id: "artifact--script",
    },
  };

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: versionDetail, error: null },
      feedback: { status: "idle", events: [], error: null },
    },
    {
      onSubmitFeedback: () => {},
      onSelectArtifact: (artifactId) => opened.push(artifactId),
    },
  );

  const text = textTree(container);
  assert.equal(text.includes("Revised version"), true);
  assert.equal(text.includes("Original artifact"), true);
  assert.equal(text.includes("artifact--script"), false);
  const openOriginal = findTree(container, (child) => (
    child.attributes["data-open-parent-artifact"] === ""
  ));
  assert.ok(openOriginal);
  assert.equal(openOriginal.textContent, "Open original artifact");
  openOriginal.onclick();
  assert.deepEqual(opened, ["artifact--script"]);
});

test("renderWorkDetail submits single-file artifact metadata rename", () => {
  const container = node();
  const updates = [];

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: genericDetail, error: null },
      feedback: { status: "idle", events: [], error: null },
    },
    {
      onSubmitFeedback: () => {},
      onUpdateArtifactMetadata: (artifactId, request) => {
        updates.push([artifactId, request]);
      },
    },
  );

  const form = container.children.find((child) => (
    child.attributes["data-artifact-metadata-form"] === ""
  ));
  assert.ok(form);
  const labelInput = form.children.find((child) => (
    child.tagName === "input" && child.name === "display_label"
  ));
  const filenameInput = form.children.find((child) => (
    child.tagName === "input" && child.name === "filename"
  ));
  assert.equal(labelInput.value, "Password Generator");
  assert.equal(filenameInput.value, "password_generator.py");

  labelInput.value = "Renamed Password Generator";
  filenameInput.value = "renamed_password_generator.py";
  form.onsubmit({ preventDefault() {} });

  assert.deepEqual(updates, [[
    "artifact--script",
    {
      display_label: "Renamed Password Generator",
      filename: "renamed_password_generator.py",
    },
  ]]);
});

test("renderWorkDetail submits single-file artifact content replacement", () => {
  const container = node();
  const versions = [];

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: genericDetail, error: null },
      feedback: { status: "idle", events: [], error: null },
    },
    {
      onSubmitFeedback: () => {},
      onCreateArtifactVersion: (artifactId, request) => {
        versions.push([artifactId, request]);
      },
    },
  );

  const form = container.children.find((child) => (
    child.attributes["data-artifact-version-form"] === ""
  ));
  assert.ok(form);
  const contentInput = form.children.find((child) => (
    child.name === "content"
  ));
  const filenameInput = form.children.find((child) => (
    child.name === "filename"
  ));
  assert.equal(contentInput.value, "print('secure')\n");
  assert.equal(filenameInput.value, "password_generator.py");

  contentInput.value = "print('updated')\n";
  filenameInput.value = "password_generator_v2.py";
  form.onsubmit({ preventDefault() {} });

  assert.deepEqual(versions, [[
    "artifact--script",
    {
      content: "print('updated')\n",
      filename: "password_generator_v2.py",
      display_label: "Password Generator",
      summary: "Generates a secure password.",
    },
  ]]);
});

test("renderWorkDetail uses artifact terminology for idle and loading states", () => {
  const container = node();

  renderWorkDetail(
    container,
    {
      detail: { status: "idle", item: null, error: null },
      feedback: { status: "idle", events: [], error: null },
    },
    { onSubmitFeedback: () => {} },
  );
  assert.equal(
    container.children[0].textContent,
    "Select an Artifact to inspect its canonical backend detail.",
  );

  renderWorkDetail(
    container,
    {
      detail: { status: "loading", item: null, error: null },
      feedback: { status: "loading", events: [], error: null },
    },
    { onSubmitFeedback: () => {} },
  );
  assert.equal(container.children[0].textContent, "Loading Artifact detail...");
});

test("feedback form requires correction text only for edited decisions", () => {
  const container = node();

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: detail, error: null },
      feedback: { status: "ready", events: [], error: null },
    },
    { onSubmitFeedback: () => {} },
  );

  const form = container.children.find((child) => (
    child.attributes["data-feedback-target"] === "target--whole"
  ));
  const select = form.children.find((child) => child.tagName === "select");
  const correction = form.children.find((child) => (
    child.tagName === "textarea" && child.name === "correction_text"
  ));

  assert.equal(correction.required, false);
  select.value = "edited";
  select.onchange();
  assert.equal(correction.required, true);
  select.value = "accepted";
  select.onchange();
  assert.equal(correction.required, false);
});

test("feedback form submits canonical artifact decision fields", () => {
  const submitted = [];
  const container = node();

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: detail, error: null },
      feedback: { status: "ready", events: [], error: null },
    },
    { onSubmitFeedback: (decision) => submitted.push(decision) },
  );

  const form = container.children.find((child) => (
    child.attributes["data-feedback-target"] === "target--whole"
  ));
  const select = form.children.find((child) => child.tagName === "select");
  const feedback = form.children.find((child) => (
    child.tagName === "textarea" && child.name === "feedback_text"
  ));
  const correction = form.children.find((child) => (
    child.tagName === "textarea" && child.name === "correction_text"
  ));
  select.value = "edited";
  feedback.value = "Needs a clearer milestone.";
  correction.value = "Rename Phase 1 to Discovery.";

  form.onsubmit({ preventDefault() {} });

  assert.deepEqual(submitted, [{
    artifact_id: "blueprint--abc",
    target_id: "target--whole",
    decision: "edited",
    feedback_text: "Needs a clearer milestone.",
    correction_text: "Rename Phase 1 to Discovery.",
    expected_schema_version: "2.0",
  }]);
});

test("renderWorkDetail uses human target kind and adaptation labels", () => {
  const container = node();

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: detail, error: null },
      feedback: { status: "ready", events: [], error: null },
    },
    { onSubmitFeedback: () => {} },
  );

  const text = textTree(container);
  assert.equal(text.includes("Whole blueprint"), true);
  assert.equal(text.includes("whole_blueprint"), false);
  assert.equal(text.includes("Planning granularity"), true);
  assert.equal(text.includes("planning_granularity--1"), false);
});

test("blueprint markdown export does not expose raw artifact identifiers", () => {
  const markdown = decodeURIComponent(
    buildBlueprintExports(detail)
      .find((item) => item.format === "md")
      .href.split(",", 2)[1],
  );

  assert.equal(markdown.includes("Artifact ID:"), false);
  assert.equal(markdown.includes("blueprint--abc"), false);
  assert.equal(markdown.includes("Safe <Blueprint>"), true);
});

test("feedback form does not ask users to enter internal feedback ids", () => {
  const container = node();

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: detail, error: null },
      feedback: { status: "ready", events: [], error: null },
    },
    { onSubmitFeedback: () => {} },
  );

  const text = textTree(container);
  assert.equal(text.includes("feedback ID"), false);
  assert.equal(findTree(container, (child) => child.name === "supersedes_feedback_id"), null);
});

test("renderFeedbackHistory shows supersession state without mutating artifacts", () => {
  const container = node();

  renderFeedbackHistory(container, {
    feedback: {
      status: "ready",
      events: [
        {
          reference: {
            feedback_id: "feedback--new",
            decision: "rejected",
          },
          feedback_text: "Reversing earlier acceptance.",
          status: "active",
          supersedes_feedback_id: "feedback--old",
        },
        {
          reference: {
            feedback_id: "feedback--old",
            decision: "accepted",
          },
          feedback_text: "Accepted earlier.",
          status: "superseded",
          superseded_by_feedback_id: "feedback--new",
        },
      ],
    },
  });

  const text = container.children.map((child) => child.textContent).join(" ");
  assert.equal(text.includes("Feedback · Rejected"), true);
  assert.equal(text.includes("Superseded"), true);
  assert.equal(text.includes("feedback--new"), false);
  assert.equal(text.includes("feedback--old"), false);
  assert.equal(
    container.children.every((child) => (
      child.classList.values.includes("contain-text")
    )),
    true,
  );
});

test("buildBlueprintDownload creates a safe filename and JSON data URL", () => {
  const download = buildBlueprintDownload(detail);

  assert.equal(download.filename, "safe-blueprint.json");
  assert.equal(
    download.href.startsWith("data:application/json;charset=utf-8,"),
    true,
  );
  assert.equal(
    JSON.parse(decodeURIComponent(download.href.split(",", 2)[1]))
      .metadata.reference.artifact_id,
    "blueprint--abc",
  );
});

test("buildBlueprintExports offers Markdown, text, metadata, and print export options", () => {
  const exports = buildBlueprintExports(detail);

  assert.deepEqual(
    exports.map((item) => item.format),
    ["md", "txt", "json", "pdf-print"],
  );
  assert.equal(exports[0].filename, "safe-blueprint.md");
  assert.equal(exports[1].filename, "safe-blueprint.txt");
  assert.equal(exports[2].filename, "safe-blueprint.json");
  assert.equal(exports[0].primary, true);
  assert.equal(exports[0].href.startsWith("data:text/markdown;charset=utf-8,"), true);
  assert.equal(exports[1].href.startsWith("data:text/plain;charset=utf-8,"), true);
  assert.equal(exports[3].href, "#print-work");
  assert.match(
    decodeURIComponent(exports[0].href.split(",", 2)[1]),
    /# Safe <Blueprint>/,
  );
});

test("renderWorkDetail renders export controls for every supported format", () => {
  const container = node();

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: detail, error: null },
      feedback: { status: "ready", events: [], error: null },
    },
    { onSubmitFeedback: () => {}, onPrintWork: () => {} },
  );

  const exportBox = container.children.find((child) => (
    child.attributes["data-export-controls"] === ""
  ));
  assert.ok(exportBox);
  const primary = exportBox.children.find((child) => (
    child.attributes["data-primary-export"] === ""
  ));
  const select = exportBox.children.find((child) => (
    child.attributes["data-export-alternative-select"] === ""
  ));
  assert.ok(primary);
  assert.ok(select);
  assert.equal(primary.textContent, "Export");
  assert.equal(primary.attributes.download, "safe-blueprint.md");
  assert.deepEqual(
    select.children.map((child) => child.textContent),
    ["Text", "Metadata JSON"],
  );
  assert.equal(
    exportBox.children.map((child) => child.textContent).join(" ").includes("Print / Save as PDF"),
    true,
  );
});

test("renderWorkDetail renders compact artifact-aware export controls", () => {
  const container = node();
  let printed = false;

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: genericDetail, error: null },
      feedback: { status: "idle", events: [], error: null },
    },
    { onSubmitFeedback: () => {}, onPrintWork: () => { printed = true; } },
  );

  const exportBox = container.children.find((child) => (
    child.attributes["data-export-controls"] === ""
  ));
  assert.ok(exportBox);
  const primary = exportBox.children.find((child) => (
    child.attributes["data-primary-export"] === ""
  ));
  const select = exportBox.children.find((child) => (
    child.attributes["data-export-alternative-select"] === ""
  ));
  const alternative = exportBox.children.find((child) => (
    child.attributes["data-alternative-export"] === ""
  ));
  const print = exportBox.children.find((child) => (
    child.attributes["data-print-export"] === ""
  ));

  assert.ok(primary);
  assert.ok(select);
  assert.ok(alternative);
  assert.ok(print);
  assert.equal(primary.textContent, "Export");
  assert.deepEqual(
    exportBox.children
      .filter((child) => (
        child.attributes["data-primary-export"] === ""
          || child.attributes["data-alternative-export"] === ""
          || child.attributes["data-export-alternative-select"] === ""
          || child.attributes["data-print-export"] === ""
      ))
      .map((child) => {
        if (child.attributes["data-primary-export"] === "") {
          return "primary";
        }
        if (child.attributes["data-alternative-export"] === "") {
          return "alternative";
        }
        if (child.attributes["data-export-alternative-select"] === "") {
          return "select";
        }
        return "print";
      }),
    ["primary", "alternative", "select", "print"],
  );
  assert.equal(
    exportBox.children.some((child) => (
      child.attributes["data-export-alternative-label"] === ""
    )),
    false,
  );
  assert.equal(primary.attributes.download, "password_generator.py");
  assert.equal(primary.classList.values.includes("control-compact"), true);
  assert.equal(select.classList.values.includes("control-compact"), true);
  assert.equal(alternative.classList.values.includes("control-compact"), true);
  assert.equal(print.classList.values.includes("control-compact"), true);
  assert.deepEqual(
    select.children.map((child) => child.textContent),
    ["Markdown", "Text", "HTML"],
  );
  select.value = "html";
  select.onchange();
  assert.equal(alternative.attributes.download.endsWith(".html"), true);
  print.onclick();
  assert.equal(printed, true);
});

test("renderWorkDetail omits metadata JSON from plain text artifact alternatives", () => {
  const container = node();

  renderWorkDetail(
    container,
    {
      detail: { status: "ready", item: textArtifactDetail, error: null },
      feedback: { status: "idle", events: [], error: null },
    },
    { onSubmitFeedback: () => {}, onPrintWork: () => {} },
  );

  const exportBox = container.children.find((child) => (
    child.attributes["data-export-controls"] === ""
  ));
  const primary = exportBox.children.find((child) => (
    child.attributes["data-primary-export"] === ""
  ));
  const select = exportBox.children.find((child) => (
    child.attributes["data-export-alternative-select"] === ""
  ));

  assert.equal(primary.attributes.download, "note.txt");
  assert.deepEqual(
    select.children.map((child) => child.textContent),
    ["Markdown", "Text", "HTML"],
  );
});
