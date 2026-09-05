/**
 * Expanded Test 13 mixed-use frontend soak runner (browser-injected).
 * Evidence-only helper; not application source.
 */
(async function soak13() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const DURATION_MS = 10.5 * 60 * 1000;
  const t0 = Date.now();
  const events = [];
  const findings = [];
  const push = (type, detail = {}) => {
    events.push({ t: Math.round((Date.now() - t0) / 1000), type, ...detail });
    if (events.length > 500) events.splice(0, events.length - 500);
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

  const buttons = () => [...document.querySelectorAll("button")];
  const btn = (re) => buttons().find((b) => re.test((b.textContent || "").trim()));
  const clickRe = (re) => {
    const b = btn(re);
    if (b && !b.disabled) {
      b.click();
      return (b.textContent || "").trim().slice(0, 60);
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

  const waitSendReady = async (timeoutMs = 120000) => {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const s = sendBtn();
      if (s && !s.disabled) return true;
      await sleep(250);
    }
    return false;
  };

  const sendChat = async (text, kind) => {
    const ta = messageBox();
    let s = sendBtn();
    if (!ta || !s) {
      push("send_fail", { kind, reason: "missing_controls" });
      return false;
    }
    if (s.disabled) {
      const ok = await waitSendReady(90000);
      if (!ok) {
        push("send_fail", { kind, reason: "send_stuck_disabled" });
        findings.push("Send stuck disabled before " + kind);
        return false;
      }
      s = sendBtn();
    }
    setReactValue(ta, text);
    await sleep(150);
    s.click();
    push("chat_sent", { kind, preview: text.slice(0, 90) });
    await sleep(800);
    const finished = await waitSendReady(150000);
    const agents = (btn(/^Agents/)?.textContent || "").replace(/\s+/g, " ").trim();
    const body = document.body.innerText;
    push("chat_done", {
      kind,
      finished,
      agents,
      sendDisabled: !!sendBtn()?.disabled,
      hasQueued: /Queued action|queued for background/i.test(body),
      hasPending: /Pending note proposal|Pending ·/i.test(body),
    });
    if (!finished) findings.push("Send did not re-enable after " + kind);
    return finished;
  };

  const thrashDrawers = async () => {
    for (const re of [/^Artifacts/, /^Notes/, /^Memory/, /^Chats/, /^Agents/]) {
      clickRe(re);
      await sleep(180);
    }
    clickRe(/^View all job reports/i);
    await sleep(250);
    clickRe(/^Close job reports/i);
    push("drawer_thrash", {
      agents: (btn(/^Agents/)?.textContent || "").replace(/\s+/g, " ").slice(0, 80),
    });
  };

  const switchSessions = async () => {
    clickRe(/^Chats/);
    await sleep(200);
    const cards = [...document.querySelectorAll("[data-session-id]")];
    if (cards.length === 0) {
      clickRe(/New conversation/);
      push("session", { action: "new_conversation", n: 0 });
      return;
    }
    const pick = cards[Math.floor(Math.random() * cards.length)];
    const sid = pick.getAttribute("data-session-id");
    pick.click();
    await sleep(700);
    const current = document
      .querySelector('[data-session-id][aria-current="true"]')
      ?.getAttribute("data-session-id");
    push("session", { action: "select", sid, current, n: cards.length });
  };

  const softRefresh = async () => {
    clickRe(/^Refresh$/);
    await sleep(1400);
    push("soft_refresh", {
      loading: /Loading/i.test(document.body.innerText),
      hasPending: /Pending/i.test(document.body.innerText),
      hasArts: /Abuse|Artifact|Password|FocusPulse|Soak13/i.test(document.body.innerText),
    });
  };

  const enterIdentityIfNeeded = async () => {
    const enter = btn(/^Enter workspace$/);
    if (!enter || !/Development context/.test(document.body.innerText)) return false;
    const inputs = [...document.querySelectorAll("input")];
    const ws =
      inputs.find((i) => (i.getAttribute("aria-label") || "") === "Workspace identity") || inputs[0];
    const proj = inputs.find((i) => (i.getAttribute("aria-label") || "") === "Project ID");
    if (ws) setReactValue(ws, "abuse-test-user-20260905");
    if (proj && !proj.value) setReactValue(proj, "agent-col");
    await sleep(120);
    enter.click();
    await sleep(2200);
    push("reenter_identity", {
      ok: !!messageBox() && !btn(/^Enter workspace$/),
    });
    return true;
  };

  const hardNavRoundtrip = async () => {
    push("nav_away", { from: location.href });
    location.href = "http://127.0.0.1:8000/";
    await sleep(2200);
    location.href = "http://127.0.0.1:8000/workspace";
    await sleep(2800);
    await enterIdentityIfNeeded();
    await sleep(1600);
    clickRe(/^Artifacts/);
    clickRe(/^Notes/);
    clickRe(/^Memory/);
    clickRe(/^Chats/);
    clickRe(/^Agents/);
    const body = document.body.innerText;
    push("nav_back", {
      url: location.href,
      hasSurfaces: /Pending|Artifacts|Chats|Agents/i.test(body),
      sendDisabled: !!sendBtn()?.disabled,
      needsIdentity: !!btn(/^Enter workspace$/),
    });
    if (btn(/^Enter workspace$/)) findings.push("identity form still present after nav back");
  };

  const inspectFailedCompleted = async () => {
    clickRe(/^Agents/);
    await sleep(200);
    clickRe(/^View all job reports/i);
    await sleep(500);
    const text = document.body.innerText;
    push("inspect_agents", {
      hasFailed: /Failed|proposal not created|invalid/i.test(text),
      hasCompleted: /Completed|Artifact Builder|Note Curator|Memory Analyst/i.test(text),
      agentsBadge: (btn(/^Agents/)?.textContent || "").replace(/\s+/g, " ").slice(0, 80),
    });
    clickRe(/^Close job reports/i);
  };

  await enterIdentityIfNeeded();
  await waitSendReady(30000);

  let cycle = 0;
  while (Date.now() - t0 < DURATION_MS) {
    cycle += 1;
    const phase = cycle % 8;
    push("cycle_start", { cycle, phase, elapsed: Math.round((Date.now() - t0) / 1000) });
    try {
      if (phase === 1) {
        await sendChat(
          "Soak13 control tick " +
            cycle +
            ". Reply with exactly one word: ACK" +
            cycle +
            ". Do not create artifacts, notes, or memory.",
          "control"
        );
      } else if (phase === 2) {
        await sendChat(
          "Please create a Memory proposal now remembering that during abuse soak Test13 cycle " +
            cycle +
            " I prefer concise status updates. Queue the Memory job immediately.",
          "memory"
        );
        await thrashDrawers();
      } else if (phase === 3) {
        await sendChat(
          'Please create a Collaborative Note proposal titled "Soak13 Note ' +
            cycle +
            '" with body: overlapping async soak cycle ' +
            cycle +
            ". Queue the Note job immediately.",
          "note"
        );
        clickRe(/^Notes/);
        await sleep(350);
        push("notes_surface", {
          pending: (document.body.innerText.match(/Pending note proposal/g) || []).length,
        });
      } else if (phase === 4) {
        await sendChat(
          'Please create an Artifact now: short markdown document titled "Soak13 Artifact ' +
            cycle +
            '" containing exactly one bullet about overlapping UI state. Queue the artifact AgentJob immediately.',
          "artifact"
        );
        clickRe(/^Artifacts/);
        clickRe(/^Agents/);
        await sleep(450);
        push("artifact_agents", {
          agents: (btn(/^Agents/)?.textContent || "").replace(/\s+/g, " ").slice(0, 80),
        });
      } else if (phase === 5) {
        await thrashDrawers();
        await inspectFailedCompleted();
        await switchSessions();
      } else if (phase === 6) {
        await softRefresh();
        await thrashDrawers();
        await sendChat(
          "Soak13 post-refresh ping " +
            cycle +
            ". Reply briefly OK" +
            cycle +
            ". No resource actions.",
          "control_after_refresh"
        );
      } else if (phase === 7) {
        if (cycle === 7 || cycle === 15 || cycle === 23) {
          await hardNavRoundtrip();
          await sendChat(
            "Soak13 after navigation cycle " +
              cycle +
              ". Reply NAVOK" +
              cycle +
              ". No artifacts/notes/memory.",
            "control_after_nav"
          );
        } else {
          await switchSessions();
          await thrashDrawers();
          await sendChat(
            "Soak13 mid-soak chat " +
              cycle +
              ". One-word reply: MID" +
              cycle +
              ". No resource creation.",
            "control"
          );
        }
      } else {
        await thrashDrawers();
        await switchSessions();
        await inspectFailedCompleted();
      }

      const s = sendBtn();
      if (s && s.disabled) {
        await sleep(2000);
        if (sendBtn()?.disabled)
          findings.push("Send disabled outside in-flight turn at t=" + Math.round((Date.now() - t0) / 1000) + "s");
      }
    } catch (e) {
      push("cycle_error", { cycle, error: String((e && e.stack) || e) });
      findings.push("cycle " + cycle + " error: " + String(e));
    }
    await sleep(700);
  }

  clickRe(/^Artifacts/);
  clickRe(/^Notes/);
  clickRe(/^Memory/);
  clickRe(/^Chats/);
  clickRe(/^Agents/);
  const finalText = document.body.innerText;
  window.__soak13Result = {
    durationSec: Math.round((Date.now() - t0) / 1000),
    cycles: cycle,
    findings: [...new Set(findings)],
    consoleErrors: (window.__soakConsole || [])
      .filter((x) => x.level === "error" || x.level === "window-error" || x.level === "unhandledrejection")
      .slice(-50),
    consoleWarnCount: (window.__soakConsole || []).filter((x) => x.level === "warn").length,
    eventSummary: events.reduce((acc, e) => {
      acc[e.type] = (acc[e.type] || 0) + 1;
      return acc;
    }, {}),
    chatEvents: events.filter((e) => e.type === "chat_sent" || e.type === "chat_done"),
    navEvents: events.filter((e) =>
      ["nav_away", "nav_back", "soft_refresh", "reenter_identity"].includes(e.type)
    ),
    sessionEvents: events.filter((e) => e.type === "session").slice(-30),
    final: {
      url: location.href,
      agents: (btn(/^Agents/)?.textContent || "").replace(/\s+/g, " ").slice(0, 100),
      sendDisabled: !!sendBtn()?.disabled,
      pendingNotes: (finalText.match(/Pending note proposal/g) || []).length,
      hasMemoryPending: /Pending ·/.test(finalText),
      hasChats: /Control chat|Soak13|Create artifact/i.test(finalText),
    },
    recentEvents: events.slice(-80),
  };
  return window.__soak13Result;
})();
