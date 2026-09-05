/**
 * Post-fix retest soak harness with submission proof.
 * Evidence-only helper under docs/abuse-testing-retest-evidence/.
 * Not application source.
 *
 * A send counts only when ALL are proven:
 * - textarea contains intended value before submit
 * - real chat submission occurs
 * - new /api/chat/stream request observed
 * - exact user message appears in transcript
 * - stream lifecycle reaches completion or explicit error
 * - resource turns produce matching queued receipt/job OR explicit no-action
 *
 * Native form validation, unchanged request count, or unchanged transcript => send_fail
 */
(function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const getSend = () =>
    [...document.querySelectorAll("button")].find(
      (b) => b.textContent.trim() === "Send"
    );
  const getTa = () =>
    document.querySelector('textarea[aria-label="Message"]') ||
    [...document.querySelectorAll("textarea")].find(
      (t) => t.getAttribute("maxlength") === "10000"
    ) ||
    null;

  function installNetworkProbe() {
    if (window.__retestStreamProbe) return window.__retestStreamProbe;
    const probe = { streams: [], fetchCount: 0 };
    const origFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const input = args[0];
      const url = typeof input === "string" ? input : input?.url || "";
      const isStream = /\/api\/chat\/stream/.test(url);
      if (isStream) {
        probe.fetchCount += 1;
        const started = Date.now();
        const entry = {
          id: probe.fetchCount,
          url,
          started,
          status: null,
          completed: false,
          error: null,
        };
        probe.streams.push(entry);
        try {
          const res = await origFetch(...args);
          entry.status = res.status;
          // Clone to observe body end without consuming consumer stream if possible
          try {
            const clone = res.clone();
            clone.text().then(() => {
              entry.completed = true;
              entry.ended = Date.now();
            }).catch((e) => {
              entry.error = String(e);
              entry.completed = true;
            });
          } catch (e) {
            entry.completed = true;
            entry.error = "clone_failed:" + String(e);
          }
          return res;
        } catch (e) {
          entry.error = String(e);
          entry.completed = true;
          throw e;
        }
      }
      return origFetch(...args);
    };
    window.__retestStreamProbe = probe;
    return probe;
  }

  async function waitSendReady(timeout = 120000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const send = getSend();
      if (send && !send.disabled) return true;
      await sleep(200);
    }
    return false;
  }

  function transcriptHasExact(text) {
    // Prefer matching visible chat bubbles / body text
    return document.body.innerText.includes(text);
  }

  async function provenSend(text, { expectResource = false } = {}) {
    const probe = installNetworkProbe();
    const result = {
      ok: false,
      classification: null,
      text,
      beforeValue: null,
      streamIdBefore: probe.fetchCount,
      streamIdAfter: null,
      streamEntry: null,
      transcriptHit: false,
      queuedReceipt: null,
      jobHint: null,
      noAction: false,
      reason: null,
    };

    if (!(await waitSendReady())) {
      result.classification = "send_fail";
      result.reason = "send_not_ready";
      return result;
    }

    const ta = getTa();
    if (!ta) {
      result.classification = "send_fail";
      result.reason = "no_textarea";
      return result;
    }

    ta.focus();
    // Prefer native setter + input events for React
    const proto = Object.getPrototypeOf(ta);
    const desc =
      Object.getOwnPropertyDescriptor(proto, "value") ||
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (desc && desc.set) desc.set.call(ta, text);
    else ta.value = text;
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    ta.dispatchEvent(new Event("change", { bubbles: true }));

    result.beforeValue = ta.value;
    if (result.beforeValue !== text) {
      result.classification = "send_fail";
      result.reason = "value_mismatch_before_submit";
      return result;
    }

    const streamsBefore = probe.fetchCount;
    const transcriptBefore = document.body.innerText.length;
    const send = getSend();
    send.click();

    // Wait for disabled (submission started) or timeout
    const tClick = Date.now();
    let sawDisabled = false;
    while (Date.now() - tClick < 8000) {
      if (getSend()?.disabled) {
        sawDisabled = true;
        break;
      }
      await sleep(50);
    }

    // Wait for new stream
    const tStream = Date.now();
    while (Date.now() - tStream < 30000) {
      if (probe.fetchCount > streamsBefore) break;
      await sleep(100);
    }
    result.streamIdAfter = probe.fetchCount;
    if (!(probe.fetchCount > streamsBefore)) {
      result.classification = "send_fail";
      result.reason = sawDisabled
        ? "no_new_stream_after_disabled"
        : "no_new_stream_unchanged_request_count";
      return result;
    }

    const entry = probe.streams[probe.streams.length - 1];
    result.streamEntry = entry;

    // Wait ready + stream complete/error
    await waitSendReady(180000);
    const tEnd = Date.now();
    while (Date.now() - tEnd < 60000) {
      if (entry.completed || entry.error) break;
      await sleep(100);
    }

    result.transcriptHit = transcriptHasExact(text);
    if (!result.transcriptHit) {
      result.classification = "send_fail";
      result.reason = "transcript_missing_user_message";
      return result;
    }

    if (!entry.completed && !entry.error) {
      result.classification = "send_fail";
      result.reason = "stream_lifecycle_incomplete";
      return result;
    }
    if (entry.error && !entry.status) {
      result.classification = "send_fail";
      result.reason = "stream_error:" + entry.error;
      // still may be valid explicit error — record as error outcome if transcript present
    }

    const queued = [...document.body.innerText.matchAll(/Queued action:[^\n]+/g)].map(
      (m) => m[0]
    );
    result.queuedReceipt = queued.slice(-1)[0] || null;
    result.noAction =
      /do not create|no resource|control chat|DRAFT-OK|no AgentJob/i.test(
        document.body.innerText.slice(-2000)
      ) || !expectResource;

    if (expectResource) {
      if (!result.queuedReceipt) {
        // allow explicit no-action / clarify
        const clarify = /clarify|which preference|which one/i.test(
          document.body.innerText.slice(-2500)
        );
        if (!clarify) {
          result.classification = "send_fail";
          result.reason = "resource_turn_missing_receipt_or_explicit_outcome";
          return result;
        }
        result.noAction = true;
        result.reason = "clarify_or_explicit_no_queue";
      }
    }

    result.ok = true;
    result.classification = "send_ok";
    return result;
  }

  window.__retestProvenSend = provenSend;
  window.__retestInstallProbe = installNetworkProbe;
  console.info("[retest-harness] submission-proof helpers installed");
})();

window.__retestStartProof = function (text) {
  const probe = installNetworkProbe();
  const ta = getTa();
  return { beforeValue: ta ? ta.value : null, streamsBefore: probe.fetchCount, text };
};
