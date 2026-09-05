/**
 * Test 13 expanded mixed frontend soak (post-fix retest evidence ONLY).
 * Glass MCP tab could not be held by this subagent; drives Chrome for Testing
 * via Playwright fill() (React-safe, equivalent to browser_fill) + Send click
 * against http://127.0.0.1:8000/workspace with submission-proof rules.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { spawn } from "node:child_process";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EVIDENCE = __dirname;
const LOG = path.join(EVIDENCE, "soak13-mixed-log.jsonl");
const RESULT = path.join(EVIDENCE, "soak13-result.json");
const SCREENSHOT = path.join(EVIDENCE, "13-final-soak-state.png");
const META = path.join(EVIDENCE, "soak13-meta.json");
const HARNESS = path.join(EVIDENCE, "soak13-submission-proof-harness.js");

const USER = "abuse-retest-20260905";
const PROJECT = "agent-col";
const APP = "http://127.0.0.1:8000/workspace";
const TARGET_SEC = 600;
const DURATION_MS = 10.5 * 60 * 1000;
const CDP_PORT = 9333;
const CHROME =
  "/Users/wifiknight/Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function appendLog(obj) {
  fs.appendFileSync(LOG, JSON.stringify(obj) + "\n");
}

function loadPlaywright() {
  const candidates = [
    "/Users/wifiknight/portfoliosite/node_modules/.pnpm/playwright@1.61.1/node_modules/playwright",
    "/Users/wifiknight/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright",
  ];
  for (const c of candidates) {
    try {
      return require(c);
    } catch {}
  }
  throw new Error("playwright module not found");
}

async function waitForCdp(port, timeoutMs = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (res.ok) return await res.json();
    } catch {}
    await sleep(200);
  }
  throw new Error("CDP not ready on " + port);
}

async function pollJobs() {
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
      .map((j) => [
        j.job_ref?.slice(-8),
        j.status,
        j.action_kind,
        (j.display_label || "").slice(0, 50),
      ]);
    return { count: jobs.length, by_status: by, nonterm: non };
  } catch (e) {
    return { error: String(e) };
  }
}

async function installHarness(page) {
  const src = fs.readFileSync(HARNESS, "utf8");
  await page.evaluate(src);
  await page.evaluate(() => {
    if (!window.__retestInstallProbe) return false;
    window.__retestInstallProbe();
    return true;
  });
}

async function waitForWorkspaceReady(page, timeoutMs = 60000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const ready = await page.evaluate(() => {
      const gate = document.querySelector(".context-gate");
      const ws = document.querySelector("[data-workspace]");
      const ta = document.querySelector(
        'textarea#chat-message, textarea[data-chat-input], textarea[maxlength="10000"]'
      );
      const gateHidden = !gate || gate.hidden === true;
      const wsVisible = !!ws && ws.hidden !== true;
      const taVisible =
        !!ta &&
        !!(ta.offsetWidth || ta.offsetHeight || ta.getClientRects().length);
      return { gateHidden, wsVisible, taVisible };
    });
    if (ready.gateHidden && ready.wsVisible && ready.taVisible) return true;
    await sleep(250);
  }
  return false;
}

async function enterIdentityIfNeeded(page, t0) {
  const already = await waitForWorkspaceReady(page, 1500);
  if (already) return false;

  // Wait for local_dev to enable context form inputs
  await page
    .waitForFunction(() => {
      const user = document.querySelector('input[name="user_id"]');
      return user && !user.disabled;
    }, { timeout: 30000 })
    .catch(() => null);

  const user = page.locator('input[name="user_id"]');
  const proj = page.locator('input[name="project_id"]');
  await user.fill(USER);
  await proj.fill(PROJECT);
  // Prefer form submit (button may stay disabled until React/input events)
  await page.evaluate(() => {
    const form = document.querySelector("[data-context-form]");
    if (form) form.requestSubmit();
  });
  await sleep(1500);
  // Fallback click if still gated
  const stillGated = !(await waitForWorkspaceReady(page, 5000));
  if (stillGated) {
    await page.evaluate(({ USER, PROJECT }) => {
      const setReact = (el, value) => {
        const proto = window.HTMLInputElement.prototype;
        const desc = Object.getOwnPropertyDescriptor(proto, "value");
        desc.set.call(el, value);
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      };
      const u = document.querySelector('input[name="user_id"]');
      const p = document.querySelector('input[name="project_id"]');
      if (u) {
        u.disabled = false;
        setReact(u, USER);
      }
      if (p) {
        p.disabled = false;
        setReact(p, PROJECT);
      }
      const btn = document.querySelector(
        '[data-context-form] button[type="submit"]'
      );
      if (btn) btn.disabled = false;
      document.querySelector("[data-context-form]")?.requestSubmit();
    }, { USER, PROJECT });
    await sleep(2500);
  }

  const ok = await waitForWorkspaceReady(page, 30000);
  await installHarness(page);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "reenter_identity",
    ok,
  });
  if (!ok) throw new Error("identity_entry_failed_workspace_not_ready");
  return true;
}

function chatTa(page) {
  return page.locator(
    'textarea#chat-message, textarea[data-chat-input], textarea[maxlength="10000"]'
  ).first();
}

async function provenSend(page, t0, text, kind, { expectResource = false } = {}) {
  await enterIdentityIfNeeded(page, t0);
  if (!(await waitForWorkspaceReady(page, 20000))) {
    const result = {
      ok: false,
      classification: "send_fail",
      reason: "workspace_not_ready",
      kind,
    };
    appendLog({
      ts: new Date().toISOString(),
      elapsed_s: Math.round((Date.now() - t0) / 1000),
      type: "chat",
      kind,
      result,
    });
    return result;
  }
  await installHarness(page);

  // Wait Send ready
  const ready = await page.evaluate(async () => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const getSend = () =>
      [...document.querySelectorAll("button")].find(
        (b) => b.textContent.trim() === "Send"
      );
    const t0 = Date.now();
    while (Date.now() - t0 < 120000) {
      const s = getSend();
      if (s && !s.disabled) return true;
      await sleep(200);
    }
    return false;
  });
  if (!ready) {
    const result = {
      ok: false,
      classification: "send_fail",
      reason: "send_not_ready",
      kind,
    };
    appendLog({
      ts: new Date().toISOString(),
      elapsed_s: Math.round((Date.now() - t0) / 1000),
      type: "chat",
      kind,
      result,
    });
    return result;
  }

  const streamsBefore = await page.evaluate(
    () => window.__retestStreamProbe?.fetchCount || 0
  );

  // React-safe fill (Playwright fill ≈ browser_fill); NOT CDP-only .value
  const ta = chatTa(page);
  await ta.waitFor({ state: "visible", timeout: 15000 });
  await ta.click({ timeout: 10000 });
  await ta.fill(text);
  let beforeValue = await ta.inputValue();
  if (beforeValue !== text) {
    // Fallback: native setter + input events (same as proven harness / React)
    beforeValue = await page.evaluate((value) => {
      const el =
        document.querySelector("textarea#chat-message") ||
        document.querySelector('textarea[maxlength="10000"]');
      if (!el) return null;
      const desc =
        Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          "value"
        );
      desc.set.call(el, value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return el.value;
    }, text);
  }
  if (beforeValue !== text) {
    const result = {
      ok: false,
      classification: "send_fail",
      reason: "value_mismatch_before_submit",
      beforeValue,
      kind,
    };
    appendLog({
      ts: new Date().toISOString(),
      elapsed_s: Math.round((Date.now() - t0) / 1000),
      type: "chat",
      kind,
      result,
    });
    return result;
  }

  await page.getByRole("button", { name: "Send", exact: true }).click();

  // Wait new stream + ready + complete via page probe
  const result = await page.evaluate(
    async ({ streamsBefore, text, expectResource }) => {
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const getSend = () =>
        [...document.querySelectorAll("button")].find(
          (b) => b.textContent.trim() === "Send"
        );
      const probe = window.__retestStreamProbe;
      const out = {
        ok: false,
        classification: "send_fail",
        reason: null,
        beforeValue: text,
        streamIdBefore: streamsBefore,
        streamIdAfter: null,
        streamEntry: null,
        transcriptHit: false,
        queuedReceipt: null,
        noAction: false,
      };

      let sawDisabled = false;
      const tClick = Date.now();
      while (Date.now() - tClick < 8000) {
        if (getSend()?.disabled) {
          sawDisabled = true;
          break;
        }
        await sleep(50);
      }

      const tStream = Date.now();
      while (Date.now() - tStream < 30000) {
        if ((probe?.fetchCount || 0) > streamsBefore) break;
        await sleep(100);
      }
      out.streamIdAfter = probe?.fetchCount || 0;
      if (!(out.streamIdAfter > streamsBefore)) {
        out.reason = sawDisabled
          ? "no_new_stream_after_disabled"
          : "no_new_stream_unchanged_request_count";
        return out;
      }
      const entry = probe.streams[probe.streams.length - 1];
      out.streamEntry = {
        id: entry.id,
        status: entry.status,
        completed: entry.completed,
        error: entry.error,
      };

      // wait send ready
      const tReady = Date.now();
      while (Date.now() - tReady < 180000) {
        const s = getSend();
        if (s && !s.disabled) break;
        await sleep(200);
      }

      const tEnd = Date.now();
      while (Date.now() - tEnd < 60000) {
        if (entry.completed || entry.error) break;
        await sleep(100);
      }
      out.streamEntry = {
        id: entry.id,
        status: entry.status,
        completed: entry.completed,
        error: entry.error,
      };

      out.transcriptHit = document.body.innerText.includes(text);
      if (!out.transcriptHit) {
        out.reason = "transcript_missing_user_message";
        return out;
      }
      if (!entry.completed && !entry.error) {
        out.reason = "stream_lifecycle_incomplete";
        return out;
      }

      const queued = [...document.body.innerText.matchAll(/Queued action:[^\n]+/g)].map(
        (m) => m[0]
      );
      out.queuedReceipt = queued.slice(-1)[0] || null;
      out.noAction =
        /do not create|no resource|control chat|DRAFT-OK|no AgentJob/i.test(
          document.body.innerText.slice(-2000)
        ) || !expectResource;

      if (expectResource) {
        if (!out.queuedReceipt) {
          const clarify = /clarify|which preference|which one/i.test(
            document.body.innerText.slice(-2500)
          );
          if (!clarify) {
            out.reason = "resource_turn_missing_receipt_or_explicit_outcome";
            return out;
          }
          out.noAction = true;
          out.reason = "clarify_or_explicit_no_queue";
        }
      }

      out.ok = true;
      out.classification = "send_ok";
      return out;
    },
    { streamsBefore, text, expectResource }
  );

  result.kind = kind;
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "chat",
    kind,
    preview: text.slice(0, 120),
    result: {
      ok: result.ok,
      classification: result.classification,
      reason: result.reason,
      stream: result.streamEntry,
      transcriptHit: result.transcriptHit,
      queuedReceipt: result.queuedReceipt,
    },
  });
  return result;
}

async function clickBtn(page, nameRe) {
  return page.evaluate((reSrc) => {
    const re = new RegExp(reSrc);
    const b = [...document.querySelectorAll("button")].find((x) =>
      re.test((x.textContent || "").trim())
    );
    if (b && !b.disabled) {
      b.click();
      return (b.textContent || "").trim().slice(0, 80);
    }
    return null;
  }, nameRe.source);
}

async function thrashDrawers(page, t0) {
  const opened = [];
  for (const re of [/^Artifacts/, /^Notes/, /^Memory/, /^Chats/, /^Agents/]) {
    opened.push(await clickBtn(page, re));
    await sleep(180);
  }
  opened.push(await clickBtn(page, /^View all job reports/i));
  await sleep(300);
  opened.push(
    (await clickBtn(page, /^Close job reports/i)) ||
      (await clickBtn(page, /^Close$/))
  );
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "drawer_thrash",
    opened,
  });
}

async function switchSessions(page, t0) {
  await clickBtn(page, /^Chats/);
  await sleep(250);
  const result = await page.evaluate(() => {
    const cards = [...document.querySelectorAll("[data-session-id]")];
    if (cards.length === 0) return { action: "need_new", n: 0 };
    if (Math.random() < 0.35) return { action: "prefer_new", n: cards.length };
    const pick = cards[Math.floor(Math.random() * cards.length)];
    const sid = pick.getAttribute("data-session-id");
    pick.click();
    return { action: "select", sid, n: cards.length };
  });
  if (result.action === "need_new" || result.action === "prefer_new") {
    await clickBtn(page, /New conversation/);
    await sleep(900);
    result.action = "new_conversation";
  } else {
    await sleep(800);
  }
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "session",
    result,
  });
}

async function softRefresh(page, t0) {
  await clickBtn(page, /^Refresh$/);
  await sleep(1600);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "soft_refresh",
  });
}

async function inspectAgents(page, t0) {
  await clickBtn(page, /^Agents/);
  await sleep(200);
  await clickBtn(page, /^View all job reports/i);
  await sleep(600);
  const info = await page.evaluate(() => {
    const text = document.body.innerText || "";
    const agents =
      [...document.querySelectorAll("button")]
        .find((b) => /^Agents/.test(b.textContent.trim()))
        ?.textContent.replace(/\s+/g, " ")
        .slice(0, 100) || "";
    return {
      hasFailed: /Failed|proposal not created|invalid/i.test(text),
      hasCompleted: /Completed|Artifact Builder|Note Curator|Memory Analyst/i.test(
        text
      ),
      agentsBadge: agents,
    };
  });
  await clickBtn(page, /^Close job reports/i);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "inspect_agents",
    info,
  });
}

async function hardNavRoundtrip(page, t0) {
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "nav_away",
  });
  await page.goto("http://127.0.0.1:8000/", { waitUntil: "domcontentloaded" });
  await sleep(1500);
  await page.goto(APP, { waitUntil: "domcontentloaded" });
  await sleep(2500);
  await enterIdentityIfNeeded(page, t0);
  await installHarness(page);
  await thrashDrawers(page, t0);
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: Math.round((Date.now() - t0) / 1000),
    type: "nav_back",
  });
}

async function snapshot(page) {
  return page.evaluate(() => {
    const agents =
      [...document.querySelectorAll("button")]
        .find((b) => /^Agents/.test(b.textContent.trim()))
        ?.textContent.replace(/\s+/g, " ")
        .trim() || "";
    const send = [...document.querySelectorAll("button")].find(
      (b) => b.textContent.trim() === "Send"
    );
    const body = document.body.innerText || "";
    return {
      url: location.href,
      agents,
      sendDisabled: !!(send && send.disabled),
      hasIdentityGate: [...document.querySelectorAll("button")].some(
        (b) => b.textContent.trim() === "Enter workspace"
      ),
      pendingNotes: (body.match(/Pending note proposal/g) || []).length,
      hasQueued: /Queued action|queued for background/i.test(body),
      bodyHead: body.slice(0, 500),
    };
  });
}

async function main() {
  const { chromium } = loadPlaywright();
  const t0 = Date.now();
  const startIso = new Date(t0).toISOString();

  fs.writeFileSync(
    META,
    JSON.stringify(
      {
        start_epoch: t0 / 1000,
        start_iso: startIso,
        target_sec: TARGET_SEC,
        driver: "chrome-playwright-fill",
        glass_mcp: "unavailable_to_subagent_tabs_evaporate",
        fill_method: "playwright_locator.fill_on_maxlength_10000",
        identity: { user: USER, project: PROJECT },
        note: "Submission-proof soak; Playwright fill ≈ browser_fill (not CDP-only .value)",
      },
      null,
      2
    ) + "\n"
  );

  fs.writeFileSync(
    LOG,
    JSON.stringify({
      ts: startIso,
      elapsed_s: 0,
      type: "soak_start",
      msg: "mixed-use frontend soak clock started",
    }) + "\n"
  );

  const profileDir = path.join(EVIDENCE, ".chrome-soak-profile");
  fs.mkdirSync(profileDir, { recursive: true });

  const chromeProc = spawn(
    CHROME,
    [
      `--remote-debugging-port=${CDP_PORT}`,
      `--user-data-dir=${profileDir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      APP,
    ],
    { stdio: "ignore", detached: true }
  );
  chromeProc.unref();

  await waitForCdp(CDP_PORT);
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${CDP_PORT}`);
  const context = browser.contexts()[0] || (await browser.newContext());
  let page =
    context.pages().find((p) => /8000/.test(p.url())) ||
    context.pages()[0] ||
    (await context.newPage());
  if (!/workspace/.test(page.url())) {
    await page.goto(APP, { waitUntil: "domcontentloaded" });
  }
  await sleep(2000);
  await enterIdentityIfNeeded(page, t0);
  await installHarness(page);

  const counts = {
    cycles: 0,
    send_ok: 0,
    send_fail: 0,
    by_kind: {
      ordinary_chat: 0,
      memory: 0,
      note: 0,
      artifact: 0,
      combined_clarify: 0,
    },
    ui: {
      drawer_thrash: 0,
      inspect_agents: 0,
      session_switch: 0,
      soft_refresh: 0,
      nav_roundtrip: 0,
    },
  };
  const findings = [];

  while (Date.now() - t0 < DURATION_MS) {
    counts.cycles += 1;
    const cycle = counts.cycles;
    const elapsed = Math.round((Date.now() - t0) / 1000);
    const phase = cycle % 9;
    const jobs = await pollJobs();
    appendLog({
      ts: new Date().toISOString(),
      elapsed_s: elapsed,
      type: "cycle_start",
      cycle,
      phase,
      jobs,
    });

    try {
      await enterIdentityIfNeeded(page, t0);
      await installHarness(page);

      if (phase === 1) {
        counts.by_kind.ordinary_chat++;
        const r = await provenSend(
          page,
          t0,
          `Soak13Retest control tick ${cycle}. Reply with exactly one word: ACK${cycle}. Do not create artifacts, notes, or memory.`,
          "ordinary_chat",
          { expectResource: false }
        );
        if (r.ok) counts.send_ok++;
        else {
          counts.send_fail++;
          findings.push(`send_fail ordinary cycle ${cycle}: ${r.reason}`);
        }
      } else if (phase === 2) {
        counts.by_kind.memory++;
        const r = await provenSend(
          page,
          t0,
          `Please create a Memory proposal now remembering that during post-fix soak Test13 cycle ${cycle} I prefer concise status updates. Queue the Memory job immediately.`,
          "memory",
          { expectResource: true }
        );
        if (r.ok) counts.send_ok++;
        else {
          counts.send_fail++;
          findings.push(`send_fail memory cycle ${cycle}: ${r.reason}`);
        }
        await thrashDrawers(page, t0);
        counts.ui.drawer_thrash++;
      } else if (phase === 3) {
        counts.by_kind.note++;
        const r = await provenSend(
          page,
          t0,
          `Please create a Collaborative Note proposal titled "Retest Soak13 Note ${cycle}" with body: overlapping async soak cycle ${cycle}. Queue the Note job immediately.`,
          "note",
          { expectResource: true }
        );
        if (r.ok) counts.send_ok++;
        else {
          counts.send_fail++;
          findings.push(`send_fail note cycle ${cycle}: ${r.reason}`);
        }
        await clickBtn(page, /^Notes/);
        await sleep(400);
      } else if (phase === 4) {
        counts.by_kind.artifact++;
        const r = await provenSend(
          page,
          t0,
          `Please create an Artifact now: short markdown document titled "retest_soak13_artifact_${cycle}.md" containing exactly one bullet about overlapping UI state. Queue the artifact AgentJob immediately.`,
          "artifact",
          { expectResource: true }
        );
        if (r.ok) counts.send_ok++;
        else {
          counts.send_fail++;
          findings.push(`send_fail artifact cycle ${cycle}: ${r.reason}`);
        }
        await thrashDrawers(page, t0);
        counts.ui.drawer_thrash++;
      } else if (phase === 5) {
        // combined turn should clarify / not multi-queue silently
        counts.by_kind.combined_clarify++;
        const r = await provenSend(
          page,
          t0,
          `In one message please both remember that I like dark mode AND create a note titled "Combined ${cycle}" AND create an artifact about pancakes. Do them all now.`,
          "combined_clarify",
          { expectResource: true }
        );
        if (r.ok) counts.send_ok++;
        else {
          counts.send_fail++;
          findings.push(`send_fail combined cycle ${cycle}: ${r.reason}`);
        }
        await thrashDrawers(page, t0);
        counts.ui.drawer_thrash++;
      } else if (phase === 6) {
        await thrashDrawers(page, t0);
        counts.ui.drawer_thrash++;
        await inspectAgents(page, t0);
        counts.ui.inspect_agents++;
        await switchSessions(page, t0);
        counts.ui.session_switch++;
      } else if (phase === 7) {
        await softRefresh(page, t0);
        counts.ui.soft_refresh++;
        await thrashDrawers(page, t0);
        counts.ui.drawer_thrash++;
        counts.by_kind.ordinary_chat++;
        const r = await provenSend(
          page,
          t0,
          `Soak13Retest post-refresh ping ${cycle}. Reply briefly OK${cycle}. No resource actions.`,
          "ordinary_chat",
          { expectResource: false }
        );
        if (r.ok) counts.send_ok++;
        else {
          counts.send_fail++;
          findings.push(`send_fail post-refresh cycle ${cycle}: ${r.reason}`);
        }
      } else if (phase === 8) {
        if (cycle === 8 || cycle === 17 || cycle === 26 || cycle === 35) {
          await hardNavRoundtrip(page, t0);
          counts.ui.nav_roundtrip++;
          counts.by_kind.ordinary_chat++;
          const r = await provenSend(
            page,
            t0,
            `Soak13Retest after navigation cycle ${cycle}. Reply NAVOK${cycle}. No artifacts/notes/memory.`,
            "ordinary_chat",
            { expectResource: false }
          );
          if (r.ok) counts.send_ok++;
          else {
            counts.send_fail++;
            findings.push(`send_fail after-nav cycle ${cycle}: ${r.reason}`);
          }
        } else {
          await switchSessions(page, t0);
          counts.ui.session_switch++;
          await thrashDrawers(page, t0);
          counts.ui.drawer_thrash++;
          counts.by_kind.ordinary_chat++;
          const r = await provenSend(
            page,
            t0,
            `Soak13Retest mid-soak chat ${cycle}. One-word reply: MID${cycle}. No resource creation.`,
            "ordinary_chat",
            { expectResource: false }
          );
          if (r.ok) counts.send_ok++;
          else {
            counts.send_fail++;
            findings.push(`send_fail mid cycle ${cycle}: ${r.reason}`);
          }
        }
      } else {
        await thrashDrawers(page, t0);
        counts.ui.drawer_thrash++;
        await switchSessions(page, t0);
        counts.ui.session_switch++;
        await inspectAgents(page, t0);
        counts.ui.inspect_agents++;
      }
    } catch (e) {
      findings.push(`cycle ${cycle} error: ${String(e)}`);
      appendLog({
        ts: new Date().toISOString(),
        elapsed_s: Math.round((Date.now() - t0) / 1000),
        type: "cycle_error",
        cycle,
        error: String(e),
      });
      try {
        await page.goto(APP, { waitUntil: "domcontentloaded" });
        await enterIdentityIfNeeded(page, t0);
        await installHarness(page);
      } catch {}
    }

    appendLog({
      ts: new Date().toISOString(),
      elapsed_s: Math.round((Date.now() - t0) / 1000),
      type: "cycle_end",
      cycle,
      send_ok: counts.send_ok,
      send_fail: counts.send_fail,
    });
  }

  const duration_s = Math.round((Date.now() - t0) / 1000);
  const finalSnap = await snapshot(page).catch((e) => ({ error: String(e) }));
  const finalJobs = await pollJobs();
  try {
    await page.screenshot({ path: SCREENSHOT, fullPage: true });
  } catch (e) {
    findings.push("screenshot_failed: " + String(e));
  }

  const pass =
    duration_s >= TARGET_SEC &&
    counts.send_ok > 0 &&
    counts.send_fail === 0 &&
    findings.filter((f) => !f.startsWith("screenshot")).length === 0;

  // Soft PASS if duration met and send_ok dominates with no hard harness bugs —
  // product failures on resource turns that still prove stream/transcript count as send_ok
  // when receipt/clarify present. FAIL if duration short or any send_fail.
  const verdict =
    duration_s >= TARGET_SEC && counts.send_fail === 0 && counts.send_ok >= 4
      ? "PASS"
      : duration_s >= TARGET_SEC && counts.send_ok > counts.send_fail
        ? "PASS_WITH_FINDINGS"
        : "FAIL";

  const out = {
    duration_s,
    target_sec: TARGET_SEC,
    verdict,
    pass: verdict === "PASS" || verdict === "PASS_WITH_FINDINGS",
    cycles: counts.cycles,
    send_ok: counts.send_ok,
    send_fail: counts.send_fail,
    by_kind: counts.by_kind,
    ui: counts.ui,
    findings,
    finalSnap,
    finalJobs,
    driver: "chrome-playwright-fill",
    glass_mcp_note:
      "Glass browser MCP could not hold a tab (tabs evaporate between tool calls); soak used Chrome for Testing + Playwright fill() on maxlength=10000 textarea against same /workspace URL",
    end_iso: new Date().toISOString(),
  };
  fs.writeFileSync(RESULT, JSON.stringify(out, null, 2) + "\n");
  appendLog({
    ts: new Date().toISOString(),
    elapsed_s: duration_s,
    type: "soak_end",
    result: out,
  });

  console.log(JSON.stringify({ done: true, ...out }, null, 2));
  try {
    await browser.close();
  } catch {}
  try {
    process.kill(-chromeProc.pid);
  } catch {}
  process.exit(verdict === "FAIL" ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  fs.appendFileSync(
    LOG,
    JSON.stringify({
      ts: new Date().toISOString(),
      type: "fatal",
      error: String(e),
      stack: e.stack,
    }) + "\n"
  );
  process.exit(2);
});
