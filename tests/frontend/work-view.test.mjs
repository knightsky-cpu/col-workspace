import test from "node:test";
import assert from "node:assert/strict";

import {
  buildArtifactCreateRequest,
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

test("buildArtifactCreateRequest maps form data to API payload", () => {
  const formData = new FormData();
  formData.set("artifact_family", "code");
  formData.set("format", "python");
  formData.set("filename", "password_generator.py");
  formData.set("display_label", "Password Generator");
  formData.set("source_text", "Create a password generator.");

  assert.deepEqual(buildArtifactCreateRequest(formData), {
    artifact_family: "code",
    format: "python",
    filename: "password_generator.py",
    display_label: "Password Generator",
    source_text: "Create a password generator.",
  });
});

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

  assert.equal(container.children.length, 1);
  assert.equal(container.children[0].textContent.includes("Safe <Blueprint>"), true);
  assert.equal(container.children[0].textContent.includes("blueprint--abc"), false);
  assert.equal(container.children[0].textContent.includes("Accepted 1"), true);
  assert.equal(
    container.children[0].classList.values.includes("contain-text"),
    true,
  );
  container.children[0].onclick();
  assert.deepEqual(selected, ["blueprint--abc"]);
});

test("renderWorkList renders single-file artifact metadata and selection controls", () => {
  const selected = [];
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
    { onSelectArtifact: (artifactId) => selected.push(artifactId) },
  );

  assert.equal(container.children[0].textContent.includes("Password Generator"), true);
  assert.equal(container.children[0].textContent.includes("Python code"), true);
  assert.equal(container.children[0].textContent.includes("artifact--script"), false);
  container.children[0].onclick();
  assert.deepEqual(selected, ["artifact--script"]);
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

  assert.equal(container.children[0].attributes["aria-current"], "true");
  assert.equal(container.children[0].textContent.includes("Work"), false);
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
  assert.equal(container.children[0].textContent, "No Artifacts loaded yet.");
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
  const supersedes = form.children.find((child) => (
    child.tagName === "input" && child.name === "supersedes_feedback_id"
  ));
  select.value = "edited";
  feedback.value = "Needs a clearer milestone.";
  correction.value = "Rename Phase 1 to Discovery.";
  supersedes.value = "feedback--old";

  form.onsubmit({ preventDefault() {} });

  assert.deepEqual(submitted, [{
    artifact_id: "blueprint--abc",
    target_id: "target--whole",
    decision: "edited",
    feedback_text: "Needs a clearer milestone.",
    correction_text: "Rename Phase 1 to Discovery.",
    supersedes_feedback_id: "feedback--old",
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
