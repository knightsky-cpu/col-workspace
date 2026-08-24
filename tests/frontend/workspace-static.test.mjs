import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../../frontend/index.html", import.meta.url), "utf8");

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
