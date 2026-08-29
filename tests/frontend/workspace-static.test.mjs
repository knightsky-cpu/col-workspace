import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../../frontend/index.html", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../frontend/styles.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../../frontend/app.mjs", import.meta.url), "utf8");
const chatView = readFileSync(new URL("../../frontend/chat-view.mjs", import.meta.url), "utf8");
const markdownRenderer = readFileSync(
  new URL("../../frontend/markdown-renderer.mjs", import.meta.url),
  "utf8",
);

test("workspace labels artifact surfaces with human-facing names", () => {
  assert.match(html, /<span class="section-heading__label" id="work-list-title"[\s\S]*Artifacts[\s\S]*<\/span>/);
  assert.match(html, /<h2>Artifacts Viewer<\/h2>/);
  assert.match(html, /aria-label="Artifacts Viewer"/);
  assert.doesNotMatch(html, /<h2 id="work-list-title">Work<\/h2>/);
});

test("workspace does not expose a raw Google ID token field", () => {
  assert.doesNotMatch(html, /Google ID token/);
  assert.doesNotMatch(html, /name="auth_token"/);
  assert.match(html, /data-google-signin/);
});

test("workspace hides internal Google subject field from authenticated users", () => {
  assert.doesNotMatch(html, /verified workspace user/);
  assert.match(html, /data-google-account-status/);
});

test("workspace omits manual artifact creation from the left drawer", () => {
  assert.match(html, /data-work-list/);
  assert.doesNotMatch(html, /data-artifact-create-form/);
  assert.doesNotMatch(html, /Create Artifact/);
  assert.doesNotMatch(html, /name="source_text"/);
});

test("structured action chat prose does not interpolate internal ids", () => {
  assert.doesNotMatch(app, /Record \$\{decision\.decision\} decision for memory proposal/);
  assert.doesNotMatch(app, /Record \$\{decision\.decision\} decision for note proposal/);
  assert.doesNotMatch(app, /Artifact \$\{decision\.artifact_id\}/);
  assert.match(app, /Approve\"} this memory proposal/);
  assert.match(app, /Approve\"} this workspace note/);
});

test("workspace print stylesheet prints only the artifact detail surface", () => {
  assert.match(styles, /@media print/);
  assert.match(styles, /\.work-panel/);
  assert.match(styles, /data-work-detail/);
  assert.match(styles, /display:\s*none\s*!important/);
  assert.match(styles, /display:\s*block\s*!important/);
});

test("workspace provides a bounded memory clarification choice region", () => {
  assert.match(html, /data-memory-clarification-choices/);
  assert.match(styles, /\.memory-clarification-choices/);
  assert.match(styles, /\.memory-clarification-choice/);
  assert.match(styles, /overflow-wrap:\s*anywhere/);
  assert.match(app, /buildMemoryClarificationSelectionChatRequest/);
  assert.match(app, /onSelectMemoryClarification/);
});

test("workspace provides a separate notes drawer and continuity choice region", () => {
  assert.match(html, /<span class="section-heading__label" id="notes-title"[\s\S]*Notes[\s\S]*<\/span>/);
  assert.match(html, /data-section="notes"/);
  assert.match(html, /data-notes-panel/);
  assert.match(html, /data-continuity-choices/);
  assert.match(styles, /\.notes-card/);
  assert.match(styles, /\.continuity-choices/);
  assert.match(app, /createNotesView/);
  assert.match(app, /buildContinuitySelectionChatRequest/);
});

test("workspace shell provides persistent non-emoji icon hooks for primary navigation", () => {
  for (const section of ["workspace", "work", "notes", "memory", "chats"]) {
    assert.match(
      html,
      new RegExp(`data-section-toggle="${section}"[\\s\\S]*class="title-icon[^"]*"[\\s\\S]*aria-hidden="true"`),
    );
  }

  assert.match(html, /data-new-conversation[\s\S]*class="button-icon"/);
  assert.match(html, /id="empty-conversation-title"[\s\S]*class="title-icon[^"]*"/);
  assert.doesNotMatch(html, /section-heading__chevron/);
  assert.doesNotMatch(styles, /\.section-heading__chevron/);
  assert.match(app, /setButtonLabel/);
});

test("drawer parent cards are full header disclosure controls without selected state", () => {
  assert.doesNotMatch(app, /highlightedSection/);
  assert.doesNotMatch(app, /data-drawer-highlighted/);
  assert.doesNotMatch(styles, /data-drawer-highlighted/);

  for (const section of ["workspace", "work", "notes", "memory", "chats"]) {
    assert.match(
      html,
      new RegExp(`<button[^>]+class="section-heading"[^>]+data-section-toggle="${section}"[\\s\\S]*<span class="section-heading__label"[\\s\\S]*</button>`),
    );
  }

  assert.doesNotMatch(html, /<button type="button" class="drawer-toggle" data-section-toggle/);
});

test("drawer selected child subcards use amber current styling and standard compact controls", () => {
  assert.match(styles, /\.work-list-item\[aria-current="true"\]/);
  assert.match(styles, /border-inline-start-color:\s*var\(--amber\)/);
  assert.match(styles, /background:\s*var\(--amber-soft\)/);
  assert.doesNotMatch(styles, /\.work-list-item\[aria-current="true"\]\s*\{[\s\S]*?border-inline-start-color:\s*var\(--accent\)/);

  assert.match(styles, /\.drawer-action-control/);
  assert.match(styles, /\.memory-actions button,\s*\.workspace-actions button,\s*\.notes-actions button,\s*\.artifact-actions button,\s*\.export-controls button,\s*\.feedback-form button,\s*\.notes-correction-form button/);
  assert.match(styles, /min-height:\s*1\.21rem/);
  assert.match(styles, /font-size:\s*0\.73rem/);
  assert.match(styles, /\.notes-correction-form button\s*\{[\s\S]*?justify-self:\s*start/);
  assert.doesNotMatch(styles, /\.subcard-disclosure-toggle::after/);
  assert.doesNotMatch(styles, /content:\s*">"/);
  assert.doesNotMatch(styles, /content:\s*"v"/);
  assert.doesNotMatch(styles, /\.chat-session-details-toggle/);
});

test("workspace create form keeps input and create button compact", () => {
  assert.match(styles, /\.workspace-create-form\s*\{/);
  assert.match(styles, /\.workspace-create-form label\s*\{/);
  assert.match(styles, /\.workspace-create-form input\s*\{/);
  assert.match(styles, /\.workspace-create-form button\s*\{/);
  assert.match(styles, /\.workspace-create-form button\s*\{[\s\S]*?min-height:\s*1\.75rem/);
  assert.match(styles, /\.workspace-create-form button\s*\{[\s\S]*?font-size:\s*0\.8125rem/);
  assert.match(styles, /\.workspace-create-form button\s*\{[\s\S]*?justify-self:\s*start/);
});

test("chat pending status keeps live text while exposing per-letter reduced-motion-safe animation hooks", () => {
  assert.match(
    html,
    /<p class="chat-status" data-chat-status role="status" aria-atomic="true"><\/p>/,
  );
  assert.match(app, /function setChatStatus\(message, statusState = ""\)/);
  assert.match(app, /function renderChatStatusLetters\(status, message\)/);
  assert.match(app, /status\.setAttribute\("aria-label", message\)/);
  assert.match(app, /letter\.setAttribute\("aria-hidden", "true"\)/);
  assert.match(app, /letter\.classList\.add\("chat-status__letter"\)/);
  assert.match(app, /letter\.style\.setProperty\("--chat-status-letter-index", String\(index\)\)/);
  assert.match(app, /status\.removeAttribute\("aria-label"\)/);
  assert.match(app, /status\.dataset\.chatStatusState = statusState/);
  assert.match(app, /delete status\.dataset\.chatStatusState/);
  assert.match(app, /setChatStatus\("Waiting for Agent Col", "pending"\)/);
  assert.match(app, /setChatStatus\(""\)/);
  assert.match(styles, /\.chat-status\[data-chat-status-state="pending"\]/);
  assert.doesNotMatch(styles, /\.chat-status\[data-chat-status-state="pending"\]\s*\{[\s\S]*?animation:\s*chat-status-wave/);
  assert.match(styles, /\.chat-status__letter/);
  assert.match(styles, /\.chat-status\[data-chat-status-state="pending"\] \.chat-status__letter/);
  assert.doesNotMatch(styles, /\.chat-status\[data-chat-status-state="pending"\]::after/);
  assert.match(styles, /animation:\s*chat-status-letter-wave 1\.65s ease-in-out infinite/);
  assert.match(styles, /animation-delay:\s*calc\(var\(--chat-status-letter-index\) \* 85ms\)/);
  assert.match(styles, /@keyframes chat-status-letter-wave/);
  assert.match(styles, /transform:\s*translateY\(/);
  assert.match(
    styles,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.chat-status\[data-chat-status-state="pending"\] \.chat-status__letter[\s\S]*?animation:\s*none/,
  );
});

test("chat final state renders before secondary refreshes", () => {
  const submitStart = app.indexOf("async function submitRequest(request)");
  const completion = app.indexOf("state = completePendingTurn(state, response);", submitStart);
  const immediateRender = app.indexOf("renderWorkspace();", completion);
  const effectRefresh = app.indexOf("await refreshAuthoritativeEffects(response);", completion);

  assert.notEqual(submitStart, -1);
  assert.notEqual(completion, -1);
  assert.notEqual(immediateRender, -1);
  assert.notEqual(effectRefresh, -1);
  assert.equal(immediateRender < effectRefresh, true);
  assert.match(app, /await refreshAuthoritativeEffects\(error\.partialFailure\)/);
  assert.doesNotMatch(app, /refreshAuthoritativeEffects\(state\.pendingResponseText\)/);
});

test("chat adaptation receipts have compact disclosure styling hooks", () => {
  assert.match(styles, /\.receipt-disclosure\s*\{/);
  assert.match(styles, /\.receipt-disclosure__summary\s*\{/);
  assert.match(styles, /\.receipt-list--disclosure\s*\{/);
  assert.match(styles, /\.receipt-disclosure__summary\s*\{[\s\S]*?cursor:\s*pointer/);
  assert.match(styles, /\.receipt-disclosure__summary\s*\{[\s\S]*?font-size:\s*0\.875rem/);
  assert.match(styles, /\.receipt-list--disclosure\s*\{[\s\S]*?margin-block-start:\s*0\.45rem/);
});

test("chat turn polish uses decorative icons, amber message text, and distinct accents", () => {
  assert.doesNotMatch(html, /data-emoji|emoji-menu|@/i);
  assert.doesNotMatch(app, /data-emoji|emoji-menu|@/i);
  assert.match(chatView, /turn-author-icon--user/);
  assert.match(chatView, /turn-author-icon--model/);
  assert.match(styles, /--chat-text:\s*var\(--text\)/);
  assert.match(styles, /--chat-user-accent:\s*var\(--amber\)/);
  assert.match(styles, /--chat-model-accent:\s*#c7b8ff/);
  assert.match(styles, /\.turn-user\s*\{[\s\S]*?border-inline-start:\s*3px solid var\(--chat-user-accent\)/);
  assert.match(styles, /\.turn-model\s*\{[\s\S]*?border-inline-start:\s*3px solid var\(--chat-model-accent\)/);
  assert.match(styles, /\.turn-user,\s*\.turn-model\s*\{[\s\S]*?color:\s*var\(--chat-text\)/);
  assert.match(styles, /\[data-character-count-level="safe"\]/);
  assert.match(styles, /\[data-character-count-level="warn"\]/);
  assert.match(styles, /\[data-character-count-level="danger"\]/);
});

test("chat model Markdown rendering uses local DOM construction and scoped styles", () => {
  assert.match(chatView, /renderSafeMarkdown\(messageText, message\)/);
  assert.match(markdownRenderer, /export function renderSafeMarkdown/);
  assert.match(markdownRenderer, /element\(`h/);
  assert.match(markdownRenderer, /document\.createTextNode/);
  assert.doesNotMatch(markdownRenderer, /innerHTML|insertAdjacentHTML|outerHTML/);
  assert.match(markdownRenderer, /isSafeLinkHref/);
  assert.match(markdownRenderer, /noopener noreferrer/);
  assert.match(styles, /\.turn-model \.turn-message-text\s*\{/);
  assert.match(styles, /\.markdown-heading\s*\{/);
  assert.match(styles, /\.markdown-code-block\s*\{/);
  assert.match(styles, /\.markdown-inline-code\s*\{/);
  assert.match(styles, /\.markdown-table\s*\{/);
  assert.match(styles, /\.markdown-link\s*\{/);
});
