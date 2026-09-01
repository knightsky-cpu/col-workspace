import { appendTextElement, element, setText } from "./render.mjs";

const RUNNING_STATUSES = new Set(["running"]);
const QUEUED_STATUSES = new Set(["queued"]);
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

const KIND_LABELS = Object.freeze({
  create_artifact: "Artifact Builder",
  propose_collaborative_note: "Note Curator",
  propose_memory_signal: "Memory Analyst",
  retrieve_chat_context: "Research Agent",
});

function jobStatus(job) {
  return String(job?.status ?? "").toLowerCase();
}

function groupJobs(jobs) {
  const groups = {
    active: [],
    queued: [],
    completed: [],
  };
  for (const job of Array.isArray(jobs) ? jobs : []) {
    const status = jobStatus(job);
    if (RUNNING_STATUSES.has(status)) {
      groups.active.push(job);
    } else if (QUEUED_STATUSES.has(status)) {
      groups.queued.push(job);
    } else if (TERMINAL_STATUSES.has(status)) {
      groups.completed.push(job);
    }
  }
  groups.active.sort((left, right) => (
    Date.parse(left?.started_at ?? left?.created_at ?? "")
    - Date.parse(right?.started_at ?? right?.created_at ?? "")
  ));
  return groups;
}

function labelForJob(job) {
  return (
    job?.agent_label
    ?? job?.display_label
    ?? KIND_LABELS[job?.action_kind]
    ?? KIND_LABELS[job?.task_type]
    ?? job?.task_type
    ?? job?.action_kind
    ?? "Agent Task"
  );
}

function descriptionForJob(job) {
  return (
    job?.description
    ?? job?.result_description
    ?? job?.failure_summary?.summary
    ?? job?.display_label
    ?? ""
  );
}

function timeForJob(job) {
  return (
    job?.completed_at
    ?? job?.updated_at
    ?? job?.started_at
    ?? job?.created_at
    ?? null
  );
}

function formatRelativeTime(value, now = Date.now()) {
  const timestamp = Date.parse(value ?? "");
  if (Number.isNaN(timestamp)) {
    return "";
  }
  const elapsedSeconds = Math.max(0, Math.floor((now - timestamp) / 1000));
  if (elapsedSeconds < 60) {
    return "now";
  }
  const elapsedMinutes = Math.floor(elapsedSeconds / 60);
  if (elapsedMinutes < 60) {
    return `${elapsedMinutes}m ago`;
  }
  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) {
    return `${elapsedHours}h ago`;
  }
  return `${Math.floor(elapsedHours / 24)}d ago`;
}

function humanStatus(status) {
  const normalized = String(status ?? "").toLowerCase();
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function renderCount(value) {
  return element("span", "agents-section__count", value);
}

function renderStatus(status) {
  const marker = element("span", `agent-row__status agent-row__status--${status}`);
  marker.setAttribute("aria-hidden", "true");
  return marker;
}

function renderJobRow(job, group, now) {
  const status = jobStatus(job);
  const row = element("div", `agent-row agent-row--${status || group}`);
  row.append(renderStatus(status || group));

  const body = element("div", "agent-row__body");
  const titleLine = element("div", "agent-row__title-line");
  appendTextElement(titleLine, "strong", "agent-row__title", labelForJob(job));
  const relativeTime = formatRelativeTime(timeForJob(job), now);
  if (relativeTime) {
    appendTextElement(titleLine, "span", "agent-row__time", relativeTime);
  }
  body.append(titleLine);

  const description = descriptionForJob(job);
  if (description) {
    appendTextElement(body, "span", "agent-row__description", description);
  }
  if (group === "queued" || status !== "running") {
    appendTextElement(body, "span", "agent-row__lifecycle", humanStatus(status));
  }
  row.append(body);
  return row;
}

function renderSection(title, jobs, emptyText, group, now) {
  const section = element("section", "agents-section");
  const header = element("div", "agents-section__header");
  appendTextElement(header, "span", "agents-section__title", title);
  header.append(renderCount(jobs.length));
  section.append(header);

  if (!jobs.length) {
    appendTextElement(section, "p", "agents-empty", emptyText);
    return section;
  }
  const list = element("div", "agents-list");
  for (const job of jobs) {
    list.append(renderJobRow(job, group, now));
  }
  section.append(list);
  return section;
}

function updateSummary(summaryElement, groups) {
  if (!summaryElement) {
    return;
  }
  setText(
    summaryElement,
    `${groups.active.length} active · ${groups.queued.length} queued`,
  );
  summaryElement.hidden = false;
}

export function renderAgentsPanel(container, agentsState, options = {}) {
  const groups = groupJobs(agentsState?.jobs);
  updateSummary(options.summaryElement, groups);
  container.replaceChildren();

  if (agentsState?.status === "error" && agentsState.error) {
    appendTextElement(container, "p", "form-error", agentsState.error);
  }

  container.append(
    renderSection(
      "ACTIVE AGENTS",
      groups.active,
      "No active agents.",
      "active",
      options.now,
    ),
    renderSection(
      "TASK QUEUE",
      groups.queued,
      "No queued tasks.",
      "queued",
      options.now,
    ),
    renderSection(
      "COMPLETED (THIS SESSION)",
      groups.completed,
      "No completed tasks this session.",
      "completed",
      options.now,
    ),
  );

  const footer = element("div", "agents-footer");
  appendTextElement(footer, "span", "agents-footer__label", "View all agents");
  appendTextElement(footer, "span", "agents-footer__icon", "↗");
  container.append(footer);
}

export function createAgentsView(elements) {
  return {
    render(state) {
      renderAgentsPanel(elements.panel, state.agents, {
        summaryElement: elements.summary,
      });
    },
  };
}
