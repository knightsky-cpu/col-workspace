import { isValidIdentifier } from "./requests.mjs";

export function authRequiresGoogleSignIn(config) {
  return (
    config?.auth_mode === "google_oidc"
    && config?.google_signin_required === true
  );
}

export function googleSessionToContext(session, projectId, authToken) {
  if (session?.authenticated !== true || !session.user_id) {
    throw new Error("Google authentication did not produce a verified user.");
  }
  const normalizedProjectId = String(projectId ?? "").trim();
  const normalizedToken = String(authToken ?? "").trim();
  if (!isValidIdentifier(normalizedProjectId)) {
    throw new Error("Project ID is invalid.");
  }
  if (!normalizedToken) {
    throw new Error("Google authentication token is missing.");
  }
  return {
    user_id: session.user_id,
    project_id: normalizedProjectId,
    auth_token: normalizedToken,
  };
}

export function googleSessionDisplayLabel() {
  return "Signed in with Google";
}

export function initializeGoogleSignIn({
  clientId,
  buttonContainer,
  googleIdentity = globalThis.google,
  onCredential,
}) {
  if (!clientId) {
    throw new Error("Google OAuth client ID is not configured.");
  }
  const accounts = googleIdentity?.accounts?.id;
  if (!accounts) {
    throw new Error("Google sign-in library is not available.");
  }
  accounts.initialize({
    client_id: clientId,
    callback(response) {
      if (!response?.credential) {
        throw new Error("Google sign-in did not return an ID token.");
      }
      onCredential(response.credential);
    },
  });
  accounts.renderButton(buttonContainer, {
    type: "standard",
    theme: "outline",
    size: "large",
    text: "signin_with",
  });
  accounts.prompt();
}

export function loadGoogleIdentityScript(documentLike = globalThis.document) {
  if (globalThis.google?.accounts?.id) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const existing = documentLike.querySelector(
      'script[src="https://accounts.google.com/gsi/client"]',
    );
    if (existing) {
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener("error", reject, { once: true });
      return;
    }
    const script = documentLike.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.addEventListener("load", resolve, { once: true });
    script.addEventListener("error", () => {
      reject(new Error("Google sign-in library failed to load."));
    }, { once: true });
    documentLike.head.append(script);
  });
}
