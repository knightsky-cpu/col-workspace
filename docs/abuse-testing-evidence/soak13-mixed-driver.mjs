/**
 * Test 13 mixed-use frontend soak driver (evidence-only).
 * Drives Chrome for Testing via CDP against http://127.0.0.1:8000/workspace.
 * Glass MCP tab was unavailable to the subagent; same frontend URL/app.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EVIDENCE = __dirname;
const LOG = path.join(EVIDENCE, "soak13-mixed-log.jsonl");
const RESULT = path.join(EVIDENCE, "soak13-result.json");
const SCREENSHOT = path.join(EVIDENCE, "13-final-soak-state.png");
const META = path.join(EVIDENCE, "soak13-meta.json");
const TARGET_SEC = 600;
const DURATION_MS = 10.5 * 60 * 1000;

const USER = "abuse-test-user-20260905";
const PROJECT = "agent-col";

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function appendLog(obj) {
  fs.appendFileSync(LOG, JSON.stringify(obj) + "\n");
}

async function getPageWs() {
  const list = await (await fetch("http://127.0.0.1:9222/json/list")).json();
  const page = list.find((t) => t.type === "page" && /8000/.test(t.url || ""));
  if (!page) throw new Error("no workspace page target");
  return page.webSocketDebuggerUrl;
}

class Cdp {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.pending = new Map();
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        this.pending.get(msg.id)(msg);
        this.pending.delete(msg.id);
      }
    };
  }
  async open() {
    await new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });
    await this.send("Runtime.enable");
    await this.send("Page.enable");
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async eval(expression, awaitPromise = true) {
    const res = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise,
      userGesture: true,
    });
    if (res.result?.exceptionDetails) {
      throw new Error(
        res.result.exceptionDetails.exception?.description ||
          res.result.exceptionDetails.text ||
          "eval failed"
      );
    }
    return res.result?.result?.value;
  }
  async screenshotPng(filePath) {
    const res = await this.send("Page.captureScreenshot", { format: "png" });
    const data = res.result?.data;
    if (!data) throw new Error("screenshot missing data");
    fs.writeFileSync(filePath, Buffer.from(data, "base64"));
  }
  close() {
    try {
      this.ws.close();
    } catch {}
  }
}

const PAGE_HELPERS = `
(() => {
  if (window.__soakHelpers) return true;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const buttons = () => [...document.querySelectorAll("button")];
  const btn = (re) => buttons().find((b) => re.test((b.textContent || "").trim()));
  const clickRe = (re) => {
    const b = btn(re);
    if (b && !b.disabled) {
      b.click();
      return (b.textContent || "").trim().slice(0, 80);
    }
    return null;
  };
  const sendBtn = () => buttons().find((b) => (b.textContent || "").trim() === "Send");
  const messageBox = () =>
    document.querySelector('textarea[aria-label="Message"], textarea[name="message"], textarea');
  const setReactValue = (el, value) => {
    const proto =
      el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    desc.set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  window.__soakConsole = window.__soakConsole || [];
  if (!window.__soakConsoleHooked) {
    window.__soakConsoleHooked = true;
    const origErr = console.error.bind(console);
    const origWarn = console.warn.bind(console);
    console.error = (...args) => {
      window.__soakConsole.push({ level: "error", msg: String(args[0]), t: Date.now() });
      origErr(...args);
    };
    console.warn = (...args) => {
      window.__soakConsole.push({ level: "warn", msg: String(args[0]), t: Date.now() });
      origWarn(...args);
    };
    window.addEventListener("error", (e) =>
      window.__soakConsole.push({ level: "window-error", msg: String(e.message || e), t: Date.now() })
    );
    window.addEventListener("unhandledrejection", (e) =>
      window.__soakConsole.push({ level: "unhandledrejection", msg: String(e.reason), t: Date.now() })
    );
  }
  window.__soakHelpers = {
    sleep, buttons, btn, clickRe, sendBtn, messageBox, setReactValue,
    waitSendReady: async (timeoutMs = 120000) => {
      const start = Date.now();
      while (Date.now() - start < timeoutMs) {
        const s = sendBtn();
        if (s && !s.disabled) return true;
        await sleep(250);
      }
      return false;
    },
    snapshot: () => {
      const agents = (btn(/^Agents/)?.textContent || "").replace(/\\s+/g, " ").trim();
      const send = sendBtn();
      const body = document.body.innerText || "";
      return {
        url: location.href,
        agents,
        sendDisabled: !!(send && send.disabled),
        hasIdentity: !!btn(/^Enter workspace$/),
        pendingNotes: (body.match(/Pending note proposal/g) || []).length,
        hasPendingMemory: /Pending ·/.test(body),
        hasQueued: /Queued action|queued for background/i.test(body),
        bodyHead: body.slice(0, 400),
      };
    },
  };
  return true;
})()
`;

async function ensureHelpers(cdp) {
  await cdp.eval(PAGE_HELPERS);
}

async function enterIdentityIfNeeded(cdp, t0) {
  const needed = await cdp.eval(`!!window.__soakHelpers.btn(/^Enter workspace$/)`);
  if (!needed) return false;
  await cdp.eval(`
    (async () => {
      const h = window.__soakHelpers;
      const inputs = [...document.querySelectorAll("input")];
      const ws =
        inputs.find((i) => (i.getAttribute("aria-label") || "") === "Workspace identity") || inputs[0];
      const proj = inputs.find((i) => (i.getAttribute("aria-label") || "") === "Project ID");
      if (ws) h.setReactValue(ws, ${JSON.stringify(USER)});
      if (proj) h.setReactValue(proj, ${JSON.stringify(PROJECT)});
      await h.sleep(150);
      h.clickRe(/^Enter workspace$/);
      await h.sleep(2500);
      return h.snapshot();
    })()
  `);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "reenter_identity",
    snap: await cdp.eval(`window.__soakHelpers.snapshot()`),
  });
  return true;
}

async function sendChat(cdp, t0, text, kind) {
  const result = await cdp.eval(`
    (async () => {
      const h = window.__soakHelpers;
      const ta = h.messageBox();
      let s = h.sendBtn();
      if (!ta || !s) return { ok: false, reason: "missing_controls" };
      if (s.disabled) {
        const ready = await h.waitSendReady(90000);
        if (!ready) return { ok: false, reason: "send_stuck_disabled", snap: h.snapshot() };
        s = h.sendBtn();
      }
      h.setReactValue(ta, ${JSON.stringify(text)});
      await h.sleep(120);
      s.click();
      await h.sleep(600);
      const finished = await h.waitSendReady(150000);
      return { ok: finished, kind: ${JSON.stringify(kind)}, snap: h.snapshot(), finished };
    })()
  `);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "chat",
    kind,
    preview: text.slice(0, 100),
    result,
  });
  return result;
}

async function thrashDrawers(cdp, t0) {
  const result = await cdp.eval(`
    (async () => {
      const h = window.__soakHelpers;
      const opened = [];
      for (const re of [/^Artifacts/, /^Notes/, /^Memory/, /^Chats/, /^Agents/]) {
        opened.push(h.clickRe(re));
        await h.sleep(200);
      }
      opened.push(h.clickRe(/^View all job reports/i));
      await h.sleep(350);
      opened.push(h.clickRe(/^Close job reports/i) || h.clickRe(/^Close$/));
      return { opened, snap: h.snapshot() };
    })()
  `);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "drawer_thrash",
    result,
  });
}

async function switchSessions(cdp, t0) {
  const result = await cdp.eval(`
    (async () => {
      const h = window.__soakHelpers;
      h.clickRe(/^Chats/);
      await h.sleep(250);
      const cards = [...document.querySelectorAll("[data-session-id]")];
      if (cards.length === 0) {
        const n = h.clickRe(/New conversation/);
        await h.sleep(800);
        return { action: "new_conversation", clicked: n, snap: h.snapshot() };
      }
      // alternate new vs existing
      if (Math.random() < 0.35) {
        const n = h.clickRe(/New conversation/);
        await h.sleep(900);
        return { action: "new_conversation", clicked: n, n: cards.length, snap: h.snapshot() };
      }
      const pick = cards[Math.floor(Math.random() * cards.length)];
      const sid = pick.getAttribute("data-session-id");
      pick.click();
      await h.sleep(800);
      const current = document
        .querySelector('[data-session-id][aria-current="true"]')
        ?.getAttribute("data-session-id");
      return { action: "select", sid, current, n: cards.length, snap: h.snapshot() };
    })()
  `);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "session",
    result,
  });
}

async function softRefresh(cdp, t0) {
  const result = await cdp.eval(`
    (async () => {
      const h = window.__soakHelpers;
      h.clickRe(/^Refresh$/);
      await h.sleep(1600);
      return h.snapshot();
    })()
  `);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "soft_refresh",
    result,
  });
}

async function inspectAgents(cdp, t0) {
  const result = await cdp.eval(`
    (async () => {
      const h = window.__soakHelpers;
      h.clickRe(/^Agents/);
      await h.sleep(250);
      h.clickRe(/^View all job reports/i);
      await h.sleep(600);
      const text = document.body.innerText || "";
      const out = {
        hasFailed: /Failed|proposal not created|invalid/i.test(text),
        hasCompleted: /Completed|Artifact Builder|Note Curator|Memory Analyst/i.test(text),
        agentsBadge: (h.btn(/^Agents/)?.textContent || "").replace(/\\s+/g, " ").slice(0, 100),
        snap: h.snapshot(),
      };
      h.clickRe(/^Close job reports/i) || h.clickRe(/^Close$/);
      return out;
    })()
  `);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "inspect_agents",
    result,
  });
}

async function hardNavRoundtrip(cdp, t0) {
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "nav_away",
  });
  await cdp.eval(`location.href = "http://127.0.0.1:8000/"`);
  await sleep(2500);
  // page may have navigated; re-attach helpers after workspace return
  await cdp.eval(`location.href = "http://127.0.0.1:8000/workspace"`);
  await sleep(3000);
  await ensureHelpers(cdp);
  await enterIdentityIfNeeded(cdp, t0);
  await sleep(1500);
  await thrashDrawers(cdp, t0);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "nav_back",
    snap: await cdp.eval(`window.__soakHelpers.snapshot()`),
  });
}

async function pollJobsSnippet() {
  try {
    const d = await (
      await fetch(
        `http://127.0.0.1:8000/api/users/${USER}/projects/${PROJECT}/agent/jobs?limit=50`
      )
    ).json();
    const jobs = d.jobs || [];
    const by = {};
    for (const j of jobs) by[j.status] = (by[j.status] || 0) + 1;
    const non = jobs
      .filter((j) => j.status === "queued" || j.status === "running")
      .map((j) => [j.job_ref?.slice(-8), j.status, j.action_kind, (j.display_label || "").slice(0, 50)]);
    return { count: jobs.length, by_status: by, nonterm: non };
  } catch (e) {
    return { error: String(e) };
  }
}

async function main() {
  const t0 = Date.now();
  const startIso = new Date(t0).toISOString();
  fs.writeFileSync(
    path.join(EVIDENCE, "soak13-start-epoch.txt"),
    String(Math.floor(t0 / 1000)) + "\n"
  );
  fs.writeFileSync(
    META,
    JSON.stringify(
      {
        start_epoch: t0 / 1000,
        start_iso: startIso,
        target_sec: TARGET_SEC,
        driver: "chrome-cdp",
        note: "Glass MCP unavailable to subagent; Chrome for Testing CDP against same /workspace",
      },
      null,
      2
    ) + "\n"
  );
  // reset mixed log for this authoritative soak
  fs.writeFileSync(
    LOG,
    JSON.stringify({
      ts: startIso,
      elapsed_s: 0,
      type: "soak_start",
      msg: "mixed-use frontend soak clock started (chrome CDP)",
    }) + "\n"
  );

  let wsUrl = await getPageWs();
  let cdp = new Cdp(wsUrl);
  await cdp.open();
  await ensureHelpers(cdp);
  await enterIdentityIfNeeded(cdp, t0);

  const findings = [];
  let cycle = 0;
  let chats = { control: 0, memory: 0, note: 0, artifact: 0 };

  while (Date.now() - t0 < DURATION_MS) {
    cycle += 1;
    const elapsed = Math.round((Date.now() - t0) / 1000);
    const phase = cycle % 8;
    const jobs = await pollJobsSnippet();
    appendLog({
      ts: new Date().toISOString(),
      elapsed_s: elapsed,
      type: "cycle_start",
      cycle,
      phase,
      jobs,
    });

    try {
      await ensureHelpers(cdp);
      await enterIdentityIfNeeded(cdp, t0);

      if (phase === 1) {
        chats.control++;
        await sendChat(
          cdp,
          t0,
          `Soak13 control tick ${cycle}. Reply with exactly one word: ACK${cycle}. Do not create artifacts, notes, or memory.`,
          "control"
        );
      } else if (phase === 2) {
        chats.memory++;
        await sendChat(
          cdp,
          t0,
          `Please create a Memory proposal now remembering that during abuse soak Test13 cycle ${cycle} I prefer concise status updates. Queue the Memory job immediately.`,
          "memory"
        );
        await thrashDrawers(cdp, t0);
      } else if (phase === 3) {
        chats.note++;
        await sendChat(
          cdp,
          t0,
          `Please create a Collaborative Note proposal titled "Soak13 Note ${cycle}" with body: overlapping async soak cycle ${cycle}. Queue the Note job immediately.`,
          "note"
        );
        await cdp.eval(`window.__soakHelpers.clickRe(/^Notes/)`);
        await sleep(400);
        appendLog({
          ts: new Date().toISOString(),
          elapsed_s: Math.round((Date.now() - t0) / 1000),
          type: "notes_surface",
          snap: await cdp.eval(`window.__soakHelpers.snapshot()`),
        });
      } else if (phase === 4) {
        chats.artifact++;
        await sendChat(
          cdp,
          t0,
          `Please create an Artifact now: short markdown document titled "Soak13 Artifact ${cycle}" containing exactly one bullet about overlapping UI state. Queue the artifact AgentJob immediately.`,
          "artifact"
        );
        await thrashDrawers(cdp, t0);
      } else if (phase === 5) {
        await thrashDrawers(cdp, t0);
        await inspectAgents(cdp, t0);
        await switchSessions(cdp, t0);
      } else if (phase === 6) {
        await softRefresh(cdp, t0);
        await thrashDrawers(cdp, t0);
        chats.control++;
        await sendChat(
          cdp,
          t0,
          `Soak13 post-refresh ping ${cycle}. Reply briefly OK${cycle}. No resource actions.`,
          "control_after_refresh"
        );
      } else if (phase === 7) {
        if (cycle === 7 || cycle === 15 || cycle === 23 || cycle === 31) {
          await hardNavRoundtrip(cdp, t0);
          // reconnect CDP after navigation (page target may change)
          try {
            cdp.close();
          } catch {}
          await sleep(500);
          wsUrl = await getPageWs();
          cdp = new Cdp(wsUrl);
          await cdp.open();
          await ensureHelpers(cdp);
          await enterIdentityIfNeeded(cdp, t0);
          chats.control++;
          await sendChat(
            cdp,
            t0,
            `Soak13 after navigation cycle ${cycle}. Reply NAVOK${cycle}. No artifacts/notes/memory.`,
            "control_after_nav"
          );
        } else {
          await switchSessions(cdp, t0);
          await thrashDrawers(cdp, t0);
          chats.control++;
          await sendChat(
            cdp,
            t0,
            `Soak13 mid-soak chat ${cycle}. One-word reply: MID${cycle}. No resource creation.`,
            "control"
          );
        }
      } else {
        await thrashDrawers(cdp, t0);
        await switchSessions(cdp, t0);
        await inspectAgents(cdp, t0);
      }

      const snap = await cdp.eval(`window.__soakHelpers.snapshot()`);
      if (snap?.sendDisabled) {
        await sleep(2000);
        const again = await cdp.eval(`window.__soakHelpers.snapshot()`);
        if (again?.sendDisabled) {
          findings.push(`Send disabled outside in-flight turn at t=${Math.round((Date.now() - t0) / 1000)}s`);
          appendLog({
            ts: new Date().toISOString(),
            elapsed_s: Math.round((Date.now() - t0) / 1000),
            type: "finding",
            finding: "send_disabled_stuck",
            snap: again,
          });
        }
      }
    } catch (e) {
      const msg = String(e?.stack || e);
      findings.push(`cycle ${cycle} error: ${msg.slice(0, 200)}`);
      appendLog({
        ts: new Date().toISOString(),
        elapsed_s: Math.round((Date.now() - t0) / 1000),
        type: "cycle_error",
        cycle,
        error: msg.slice(0, 500),
      });
      // try reconnect
      try {
        cdp.close();
      } catch {}
      await sleep(800);
      try {
        wsUrl = await getPageWs();
        cdp = new Cdp(wsUrl);
        await cdp.open();
        await ensureHelpers(cdp);
        await enterIdentityIfNeeded(cdp, t0);
      } catch (e2) {
        appendLog({
          ts: new Date().toISOString(),
          elapsed_s: Math.round((Date.now() - t0) / 1000),
          type: "reconnect_fail",
          error: String(e2).slice(0, 300),
        });
      }
    }
    await sleep(500);
  }

  const durationSec = Math.round((Date.now() - t0) / 1000);
  await ensureHelpers(cdp);
  await thrashDrawers(cdp, t0);
  await inspectAgents(cdp, t0);
  const finalSnap = await cdp.eval(`window.__soakHelpers.snapshot()`);
  const consoleErrors = await cdp.eval(`
    (window.__soakConsole || []).filter(x =>
      x.level === "error" || x.level === "window-error" || x.level === "unhandledrejection"
    ).slice(-50)
  `);
  const finalJobs = await pollJobsSnippet();

  try {
    await cdp.screenshotPng(SCREENSHOT);
  } catch (e) {
    appendLog({
      ts: new Date().toISOString(),
      elapsed_s: durationSec,
      type: "screenshot_fail",
      error: String(e),
    });
  }

  const summary = {
    durationSec,
    targetSec: TARGET_SEC,
    cycles: cycle,
    chats,
    findings: [...new Set(findings)],
    finalSnap,
    finalJobs,
    consoleErrors,
    driver: "chrome-cdp",
    glassMcpNote: "Glass browser MCP could not hold a tab for this subagent; soak used Chrome for Testing CDP on same /workspace URL",
    end_iso: new Date().toISOString(),
  };
  fs.writeFileSync(RESULT, JSON.stringify(summary, null, 2) + "\n");
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: durationSec,
    type: "soak_end",
    summary: {
      durationSec,
      cycles: cycle,
      chats,
      findings: summary.findings,
      finalJobs,
    },
  });
  console.log(JSON.stringify({ ok: true, durationSec, cycles: cycle, chats, findings: summary.findings }, null, 2));
  cdp.close();
  if (durationSec < TARGET_SEC) {
    process.exitCode = 2;
  }
}

main().catch((e) => {
  console.error(e);
  appendLog({
    ts: new Date().toISOString(),
    type: "driver_fatal",
    error: String(e?.stack || e),
  });
  process.exit(1);
});
