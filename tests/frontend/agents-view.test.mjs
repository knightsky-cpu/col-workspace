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
    addEventListener(name, handler) {
      this[`on${name}`] = handler;
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

test("renderAgentsPanel opens job reports from the existing footer arrow", () => {
  const container = node();
  let opened = false;

  renderAgentsPanel(container, {
    status: "loaded",
    jobs: [],
    reportsStatus: "loaded",
    reports: [{
      report_number: "001",
      job_number: "002",
      agent_label: "Memory Analyst",
      status: "failed",
      title: "Memory proposal not created",
      summary: "A pending memory proposal already exists for this category.",
      public_resource_label: null,
      created_at: "2026-09-02T10:00:00Z",
      report_id: "agent-job-report-secret",
      job_id: "memory-job-secret",
      session_id: "session-secret",
    }],
    reportsVisible: false,
  }, {
    onOpenReports() {
      opened = true;
    },
  });

  assert.match(container.textContent, /View all job reports/);
  const footer = container.children.at(-1);
  const arrow = footer.children.at(-1);
  assert.equal(arrow.textContent, "↗");
  assert.equal(arrow.tagName, "button");
  arrow.onclick();
  assert.equal(opened, true);
  assert.doesNotMatch(container.textContent, /agent-job-report-secret/);
  assert.doesNotMatch(container.textContent, /memory-job-secret/);
  assert.doesNotMatch(container.textContent, /session-secret/);
});

test("renderAgentsPanel shows report popup as a compact public-safe list", () => {
  const container = node();
  let closed = false;

  renderAgentsPanel(container, {
    status: "loaded",
    jobs: [],
    reportsStatus: "loaded",
    reports: [
      {
        report_number: "001",
        job_number: "002",
        agent_label: "Memory Analyst",
        status: "failed",
        title: "Memory proposal not created",
        summary: "A pending memory proposal already exists for this category.",
        public_resource_label: null,
        created_at: "2026-09-02T10:00:00Z",
        report_id: "agent-job-report-secret",
        job_id: "memory-job-secret",
        source_message_id: "message-secret",
      },
      {
        report_number: "002",
        job_number: "001",
        agent_label: "Artifact Builder",
        status: "completed",
        title: "Artifact created",
        summary: "The requested artifact was created.",
        public_resource_label: "git_update.sh",
        created_at: "2026-09-02T10:01:00Z",
      },
    ],
    reportsVisible: true,
  }, {
    onCloseReports() {
      closed = true;
    },
  });

  assert.match(container.textContent, /Job Reports/);
  assert.match(container.textContent, /Memory Analyst/);
  assert.match(container.textContent, /Failed/);
  assert.match(container.textContent, /A pending memory proposal already exists/);
  assert.match(container.textContent, /Artifact Builder/);
  assert.match(container.textContent, /git_update\.sh/);
  assert.doesNotMatch(container.textContent, /agent-job-report-secret/);
  assert.doesNotMatch(container.textContent, /memory-job-secret/);
  assert.doesNotMatch(container.textContent, /message-secret/);

  const popup = container.children.at(-1);
  assert.equal(popup.getAttribute("role"), "dialog");
  assert.equal(popup.getAttribute("aria-modal"), "true");
  const close = popup.children[0].children.at(-1);
  close.onclick();
  assert.equal(closed, true);
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
