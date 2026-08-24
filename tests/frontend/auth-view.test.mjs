import test from "node:test";
import assert from "node:assert/strict";

import {
  authRequiresGoogleSignIn,
  googleSessionDisplayLabel,
  googleSessionToContext,
  googleWorkspaceDisplayLabel,
  initializeGoogleSignIn,
} from "../../frontend/auth-view.mjs";

test("authRequiresGoogleSignIn follows public backend config", () => {
  assert.equal(authRequiresGoogleSignIn({
    auth_mode: "google_oidc",
    google_signin_required: true,
  }), true);
  assert.equal(authRequiresGoogleSignIn({
    auth_mode: "local_dev",
    google_signin_required: false,
  }), false);
});

test("googleSessionToContext derives user ID from verified backend session", () => {
  const context = googleSessionToContext(
    {
      authenticated: true,
      user_id: "google--109876543210",
      workspace_project_id: "project--abcdef123456",
    },
    "agent-col",
    "google-id-token",
  );

  assert.deepEqual(context, {
    user_id: "google--109876543210",
    project_id: "project--abcdef123456",
    auth_token: "google-id-token",
  });
});

test("googleSessionToContext requires a server-owned workspace project in Google mode", () => {
  assert.throws(
    () => googleSessionToContext(
      { authenticated: true, user_id: "google--109876543210" },
      "agent-col",
      "google-id-token",
    ),
    /Google authentication did not produce a workspace project/,
  );
});

test("googleSessionToContext validates project locator and auth token", () => {
  assert.throws(
    () => googleSessionToContext(
      {
        authenticated: true,
        user_id: "google--109876543210",
        workspace_project_id: "bad/project",
      },
      "bad/project",
      "google-id-token",
    ),
    /Project ID is invalid/,
  );
  assert.throws(
    () => googleSessionToContext(
      {
        authenticated: true,
        user_id: "google--109876543210",
        workspace_project_id: "project--abcdef123456",
      },
      "agent-col",
      "",
    ),
    /Google authentication token is missing/,
  );
});

test("googleSessionDisplayLabel hides Google subject from user-facing UI", () => {
  assert.equal(
    googleSessionDisplayLabel({
      authenticated: true,
      user_id: "google--109876543210",
      email: "user@example.com",
      display_name: "WiFi Knight",
    }),
    "Signed in with Google",
  );
});

test("googleWorkspaceDisplayLabel hides Google-derived project locator", () => {
  assert.equal(googleWorkspaceDisplayLabel(), "Private Google workspace");
});

test("initializeGoogleSignIn renders Google button and passes credential", () => {
  const calls = [];
  const container = {};
  let callback = null;
  initializeGoogleSignIn({
    clientId: "client-123",
    buttonContainer: container,
    googleIdentity: {
      accounts: {
        id: {
          initialize(config) {
            calls.push(["initialize", config.client_id]);
            callback = config.callback;
          },
          renderButton(target, options) {
            calls.push(["renderButton", target, options.type]);
          },
          prompt() {
            calls.push(["prompt"]);
          },
        },
      },
    },
    onCredential(credential) {
      calls.push(["credential", credential]);
    },
  });

  callback({ credential: "google-id-token" });

  assert.deepEqual(calls, [
    ["initialize", "client-123"],
    ["renderButton", container, "standard"],
    ["prompt"],
    ["credential", "google-id-token"],
  ]);
});
