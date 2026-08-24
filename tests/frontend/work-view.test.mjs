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
  assert.equal(
    container.children[0].classList.values.includes("contain-text"),
    true,
  );
  container.children[0].onclick();
  assert.deepEqual(selected, ["blueprint--abc"]);
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

  const text = container.children.map((child) => child.textContent).join(" ");
  assert.equal(text.includes("Safe <Blueprint>"), true);
  assert.equal(text.includes("Use textContent."), true);
  assert.equal(text.includes("Which target matters most?"), true);
  assert.equal(text.includes("Never use innerHTML."), true);
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
  assert.equal(text.includes("feedback--new"), true);
  assert.equal(text.includes("superseded"), true);
  assert.equal(text.includes("feedback--old"), true);
  assert.equal(
    container.children.every((child) => (
      child.classList.values.includes("contain-text")
    )),
    true,
  );
});

test("buildBlueprintDownload creates a safe filename and JSON data URL", () => {
  const download = buildBlueprintDownload(detail);

  assert.equal(download.filename, "safe-blueprint-blueprint--abc.json");
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
  assert.equal(exports[0].filename, "safe-blueprint-blueprint--abc.json");
  assert.equal(exports[1].filename, "safe-blueprint-blueprint--abc.md");
  assert.equal(exports[2].filename, "safe-blueprint-blueprint--abc.txt");
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
