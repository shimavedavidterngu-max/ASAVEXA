/**
 * Small pure helpers for the sign-in flows that need the browser (single sign-on redirect and return).
 * Kept free of `window`/`document` so they can be tested in plain Node.
 */

/** A random value that ties a single-sign-on attempt to THIS browser tab. The server stores only its hash. */
export function makeBinding(randomBytes) {
  const bytes = randomBytes ? randomBytes(32) : globalThis.crypto.getRandomValues(new Uint8Array(32));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Reads `?code=…&state=…` (or `?error=…`) from the address the identity provider sent the person back to. */
export function parseOidcReturn(search) {
  const q = new URLSearchParams(search || "");
  if (q.get("error")) return { error: q.get("error_description") || q.get("error") };
  const code = q.get("code"), state = q.get("state");
  return code && state ? { code, state } : null;
}

/** What a sign-in response means for the screen. `done` = we have a session; `mfa` = ask for the code. */
export function interpretLogin(res) {
  if (res && res.mfa_required && res.challenge) return { kind: "mfa", challenge: res.challenge };
  if (res && res.token && res.user) return { kind: "done", token: res.token, user: res.user };
  return { kind: "error", message: "The server's sign-in reply was not understood." };
}

/** Turns "ng, GH ,, eu" into ["NG","GH","EU"]. */
export function parseRegions(text) {
  return String(text || "").split(/[,\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
}
