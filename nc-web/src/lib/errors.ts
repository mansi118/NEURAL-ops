// Human-readable error messages — Design of Everyday Things error standards: say what went wrong in
// plain language, point at the fix, never blame the user, never leak internals. Maps raw Matrix/network
// errors to guidance. Pure; unit-tested.

function detail(err: unknown): { msg: string; code: string } {
  const msg = err instanceof Error ? err.message : String(err ?? "");
  const code = (err as { errcode?: string } | null)?.errcode ?? "";
  return { msg, code };
}

/** Sign-in failures → a friendly, actionable message. */
export function humanizeAuthError(err: unknown): string {
  const { msg, code } = detail(err);
  if (code === "M_FORBIDDEN" || /invalid password|invalid username|forbidden|\b403\b/i.test(msg))
    return "That username or password didn't match. Check them and try again.";
  if (code === "M_USER_DEACTIVATED" || /deactivated/i.test(msg))
    return "That account is deactivated. Ask your admin for access.";
  if (code === "M_LIMIT_EXCEEDED" || /rate|too many/i.test(msg))
    return "Too many attempts — wait a moment, then try again.";
  if (/network|failed to fetch|fetch|timeout|econn|dns|unreachable/i.test(msg))
    return "Couldn't reach the server. Check your connection and try again.";
  return "Sign-in failed. Please try again, or contact your admin if it keeps happening.";
}

/** Message-send failures → a short, recoverable message. */
export function humanizeSendError(err: unknown): string {
  const { msg } = detail(err);
  if (/network|failed to fetch|fetch|timeout|econn|unreachable/i.test(msg))
    return "Couldn't send — check your connection and try again.";
  return "Couldn't send that message. Try again.";
}
