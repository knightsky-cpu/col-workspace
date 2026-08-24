import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../../frontend/index.html", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../frontend/styles.css", import.meta.url), "utf8");

test("workspace labels artifact surfaces with human-facing names", () => {
  assert.match(html, /<h2 id="work-list-title">Artifacts<\/h2>/);
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

test("workspace print stylesheet prints only the artifact detail surface", () => {
  assert.match(styles, /@media print/);
  assert.match(styles, /\.work-panel/);
  assert.match(styles, /data-work-detail/);
  assert.match(styles, /display:\s*none\s*!important/);
  assert.match(styles, /display:\s*block\s*!important/);
});
