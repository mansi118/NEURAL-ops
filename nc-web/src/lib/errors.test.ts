import { describe, it, expect } from "vitest";
import { humanizeAuthError, humanizeSendError } from "./errors";

describe("humanizeAuthError", () => {
  it("maps a forbidden / bad-credentials error to plain guidance (no blame, no internals)", () => {
    expect(humanizeAuthError({ errcode: "M_FORBIDDEN", message: "Invalid password" })).toMatch(
      /didn't match/i,
    );
    expect(humanizeAuthError(new Error("403 Forbidden"))).toMatch(/didn't match/i);
  });
  it("maps deactivated, rate-limit, and network errors distinctly", () => {
    expect(humanizeAuthError({ errcode: "M_USER_DEACTIVATED" })).toMatch(/deactivated/i);
    expect(humanizeAuthError({ errcode: "M_LIMIT_EXCEEDED" })).toMatch(/too many/i);
    expect(humanizeAuthError(new Error("Failed to fetch"))).toMatch(/connection/i);
  });
  it("falls back to a safe generic message and never leaks the raw error", () => {
    const out = humanizeAuthError(new Error("boom secret internal xyz"));
    expect(out).toMatch(/sign-in failed/i);
    expect(out).not.toContain("boom secret internal xyz");
  });
});

describe("humanizeSendError", () => {
  it("distinguishes network from generic, both recoverable", () => {
    expect(humanizeSendError(new Error("network down"))).toMatch(/connection/i);
    expect(humanizeSendError(new Error("weird"))).toMatch(/try again/i);
  });
});
