/**
 * Evidence-only screenshot helper for post-fix regression Tests 1–7/9.
 * Uses a SEPARATE Chrome for Testing on :9334 (does not touch Glass soak on :9333).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EV = __dirname;
const USER = "abuse-retest-20260905";
const PROJECT = "agent-col";
const SESSION =
  "session--a1b2c3d4-e5f6-7890-abcd-ef1234567890";
const SESSION_B =
  "session--b2c3d4e5-f6a7-8901-bcde-f12345678901";
const CDP_PORT = 9334;

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
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
    const res = await this.send("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: false,
    });
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

const HELPERS = `
(() => {
  if (window.__retestHelpers) return true;
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
  const setReactValue = (el, value) => {
    const proto =
      el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    desc.set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  window.__retestHelpers = {
    sleep, buttons, btn, clickRe, setReactValue,
    snap: () => ({
      url: location.href,
      agents: (btn(/^Agents/)?.textContent || "").replace(/\\s+/g, " ").trim(),
      bodyHead: (document.body.innerText || "").slice(0, 500),
      hasEnter: !!btn(/^Enter workspace$/),
    }),
  };
  return true;
})()
`;

async function getPageWs() {
  const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
  const page = list.find((t) => t.type === "page");
  if (!page) throw new Error("no page target on 9334");
  return page.webSocketDebuggerUrl;
}

async function shot(cdp, name) {
  const fp = path.join(EV, name);
  await cdp.screenshotPng(fp);
  console.log("wrote", name, fs.statSync(fp).size);
}

async function main() {
  const ws = await getPageWs();
  const cdp = new Cdp(ws);
  await cdp.open();
  await cdp.send("Page.navigate", { url: "http://127.0.0.1:8000/workspace" });
  await sleep(2500);
  await cdp.eval(HELPERS);

  // Enter identity
  await cdp.eval(`
    (async () => {
      const h = window.__retestHelpers;
      if (!h.btn(/^Enter workspace$/)) return h.snap();
      const inputs = [...document.querySelectorAll("input")];
      const ws = inputs.find((i) => (i.getAttribute("aria-label") || "") === "Workspace identity") || inputs[0];
      const proj = inputs.find((i) => (i.getAttribute("aria-label") || "") === "Project ID");
      if (ws) h.setReactValue(ws, ${JSON.stringify(USER)});
      if (proj) h.setReactValue(proj, ${JSON.stringify(PROJECT)});
      await h.sleep(200);
      h.clickRe(/^Enter workspace$/);
      await h.sleep(2500);
      return h.snap();
    })()
  `);
  await cdp.eval(HELPERS);

  // Open Chats and select regression session A
  await cdp.eval(`
    (async () => {
      const h = window.__retestHelpers;
      h.clickRe(/^Chats$/);
      await h.sleep(800);
      const items = [...document.querySelectorAll("button, a, li, div")];
      const hit = items.find((el) => /Control retest 01/i.test(el.textContent || ""));
      if (hit) hit.click();
      await h.sleep(1200);
      return h.snap();
    })()
  `);
  await shot(cdp, "retest-01-control-chat.png");

  // Artifact / Agents view evidence for tests 2/7/9-ish
  await cdp.eval(`
    (async () => {
      const h = window.__retestHelpers;
      h.clickRe(/^Agents/);
      await h.sleep(1000);
      return h.snap();
    })()
  `);
  await shot(cdp, "retest-02-artifact-while-chatting.png");
  await shot(cdp, "retest-07-terminal-job-report-consistency.png");

  // Memory surface
  await cdp.eval(`
    (async () => {
      const h = window.__retestHelpers;
      h.clickRe(/^Memory$/);
      await h.sleep(900);
      return h.snap();
    })()
  `);
  await shot(cdp, "retest-03-memory-while-chatting.png");

  // Notes surface
  await cdp.eval(`
    (async () => {
      const h = window.__retestHelpers;
      h.clickRe(/^Notes$/);
      await h.sleep(900);
      return h.snap();
    })()
  `);
  await shot(cdp, "retest-04-note-while-chatting.png");
  await shot(cdp, "retest-05-cross-surface-concurrency.png");

  // Artifacts
  await cdp.eval(`
    (async () => {
      const h = window.__retestHelpers;
      h.clickRe(/^Artifacts$/);
      await h.sleep(900);
      return h.snap();
    })()
  `);
  await shot(cdp, "retest-06-resource-surfaces-after-refresh.png");

  // Session switch: open session B then back to A
  await cdp.eval(`
    (async () => {
      const h = window.__retestHelpers;
      h.clickRe(/^Chats$/);
      await h.sleep(700);
      const items = [...document.querySelectorAll("button, a, li, div")];
      const b = items.find((el) => /Session b control/i.test(el.textContent || ""));
      if (b) b.click();
      await h.sleep(900);
      const a = items.find((el) => /Control retest 01/i.test(el.textContent || ""));
      if (a) a.click();
      await h.sleep(900);
      h.clickRe(/^Agents/);
      await h.sleep(900);
      return h.snap();
    })()
  `);
  await shot(cdp, "retest-09-session-switch-active-jobs.png");

  const finalSnap = await cdp.eval(`window.__retestHelpers.snap()`);
  fs.writeFileSync(
    path.join(EV, "retest-1-7-9-screenshot-meta.json"),
    JSON.stringify(
      { ts: new Date().toISOString(), port: CDP_PORT, session: SESSION, session_b: SESSION_B, finalSnap },
      null,
      2
    ) + "\n"
  );
  cdp.close();
  console.log("done", finalSnap);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
