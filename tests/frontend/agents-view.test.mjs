import test from "node:test";
import assert from "node:assert/strict";

import { renderAgentsPanel } from "../../frontend/agents-view.mjs";

function node(tagName = "div") {
  const children = [];
  const attributes = {};
  return {
    tagName,
    children,
    attributes,
    textContent: "",
    hidden: false,
    classList: {
      classes: [],
      add(...names) {
        this.classes.push(...names);
      },
    },
    append(...items) {
      children.push(...items);
      this.textContent += items.map((item) => item.textContent ?? "").join("");
    },
    replaceChildren(...items) {
      children.length = 0;
      this.textContent = "";
      this.append(...items);
    },
    setAttribute(name, value) {
      attributes[name] = String(value);
    },
    getAttribute(name) {
      return attributes[name] ?? null;
    },
  };
}

globalThis.document = {
  createElement(tagName) {
    return node(tagName);
  },
};

test("renderAgentsPanel groups public jobs by lifecycle and hides private fields", () => {
  const container = node();
  const summary = node("span");

  renderAgentsPanel(container, {
    status: "loaded",
    jobs: [
	      {
	        job_number: "001",
	        status: "running",
        task_type: "create_artifact",
        display_label: "Artifact Builder",
        description: "Creating deployment artifact",
        started_at: "2026-09-01T12:00:00Z",
        internal_prompt: "do not show this",
      },
	      {
	        job_number: "002",
        status: "queued",
        task_type: "write_docs",
        display_label: "Doc Writer",
        description: "Updating architecture document",
      },
	      {
	        job_number: "003",
        status: "completed",
        task_type: "scan_workspace",
        display_label: "Repo Scanner",
        result_description: "Scanned workspace structure",
        completed_at: "2026-09-01T12:10:00Z",
      },
    ],
  }, {
    summaryElement: summary,
    now: Date.parse("2026-09-01T12:08:00Z"),
  });

  assert.match(container.textContent, /ACTIVE AGENTS/);
  assert.match(container.textContent, /Artifact Builder/);
  assert.match(container.textContent, /Creating deployment artifact/);
  assert.match(container.textContent, /8m ago/);
  assert.match(container.textContent, /TASK QUEUE/);
  assert.match(container.textContent, /Doc Writer/);
  assert.match(container.textContent, /Queued/);
  assert.match(container.textContent, /COMPLETED \(THIS SESSION\)/);
  assert.match(container.textContent, /Repo Scanner/);
  assert.match(container.textContent, /Scanned workspace structure/);
  assert.equal(summary.textContent, "1 active · 1 queued");
	  assert.doesNotMatch(container.textContent, /agent-job--secret/);
	  assert.doesNotMatch(container.textContent, /session--/);
	  assert.doesNotMatch(container.textContent, /do not show this/);
	});

test("renderAgentsPanel shows a compact empty state from backend-authoritative data", () => {
  const container = node();
  const summary = node("span");

  renderAgentsPanel(container, {
    status: "loaded",
    jobs: [],
  }, { summaryElement: summary });

  assert.match(container.textContent, /No active agents/);
  assert.match(container.textContent, /No queued tasks/);
  assert.match(container.textContent, /No completed tasks this session/);
  assert.equal(summary.textContent, "0 active · 0 queued");
});

test("renderAgentsPanel sorts active agents chronologically without reordering queued tasks", () => {
  const container = node();

  renderAgentsPanel(container, {
    status: "loaded",
    jobs: [
      {
        status: "running",
        agent_label: "Second Active",
        display_label: "Started second",
        started_at: "2026-09-01T12:02:00Z",
      },
      {
        status: "queued",
        agent_label: "First Queued",
        display_label: "Backend queue position one",
      },
      {
        status: "running",
        agent_label: "First Active",
        display_label: "Started first",
        started_at: "2026-09-01T12:01:00Z",
      },
      {
        status: "queued",
        agent_label: "Second Queued",
        display_label: "Backend queue position two",
      },
    ],
  });

  assert.ok(
    container.textContent.indexOf("First Active")
      < container.textContent.indexOf("Second Active"),
  );
  assert.ok(
    container.textContent.indexOf("First Queued")
      < container.textContent.indexOf("Second Queued"),
  );
});
