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

test("buildBlueprintExports offers JSON, Markdown, text, and print export options", () => {
  const exports = buildBlueprintExports(detail);

  assert.deepEqual(
    exports.map((item) => item.format),
    ["json", "md", "txt", "pdf-print"],
  );
  assert.equal(exports[0].filename, "safe-blueprint.json");
  assert.equal(exports[1].filename, "safe-blueprint.md");
  assert.equal(exports[2].filename, "safe-blueprint.txt");
  assert.equal(exports[1].href.startsWith("data:text/markdown;charset=utf-8,"), true);
  assert.equal(exports[2].href.startsWith("data:text/plain;charset=utf-8,"), true);
  assert.equal(exports[3].href, "#print-work");
  assert.match(
    decodeURIComponent(exports[1].href.split(",", 2)[1]),
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
  assert.equal(
    exportBox.children.map((child) => child.textContent).join(" ").includes("Markdown"),
    true,
  );
  assert.equal(
    exportBox.children.map((child) => child.textContent).join(" ").includes("PDF / Print"),
    true,
  );
});
