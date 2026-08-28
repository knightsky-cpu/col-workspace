import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../../frontend/index.html", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../frontend/styles.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../../frontend/app.mjs", import.meta.url), "utf8");

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

test("workspace exposes a bounded generic artifact creation form", () => {
  assert.match(html, /data-artifact-create-form/);
  assert.match(html, /name="artifact_family"/);
  assert.match(html, /name="format"/);
  assert.match(html, /name="filename"/);
  assert.match(html, /name="source_text"/);
});

test("artifacts drawer lists artifacts before the create form", () => {
  const listIndex = html.indexOf("data-work-list");
  const createIndex = html.indexOf("data-artifact-create-form");

  assert.notEqual(listIndex, -1);
  assert.notEqual(createIndex, -1);
  assert.equal(listIndex < createIndex, true);
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
  assert.match(styles, /\.section-heading__chevron::before/);
  assert.match(styles, /\.section-heading\[aria-expanded="true"\] \.section-heading__chevron::before/);
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

test("drawer selected child subcards use amber current styling and compact actions", () => {
  assert.match(styles, /\.work-list-item\[aria-current="true"\]/);
  assert.match(styles, /border-inline-start-color:\s*var\(--amber\)/);
  assert.match(styles, /background:\s*var\(--amber-soft\)/);
  assert.doesNotMatch(styles, /\.work-list-item\[aria-current="true"\]\s*\{[\s\S]*?border-inline-start-color:\s*var\(--accent\)/);

  assert.match(styles, /\.memory-actions button,\s*\.workspace-actions button,\s*\.notes-actions button/);
  assert.match(styles, /min-height:\s*1\.35rem/);
  assert.match(styles, /font-size:\s*0\.72rem/);
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
