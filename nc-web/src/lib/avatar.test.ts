import { describe, it, expect } from "vitest";
import { initials, colorFor } from "./avatar";

describe("avatar", () => {
  it("derives up-to-two initials, stripping mxid host + separators", () => {
    expect(initials("aria")).toBe("A");
    expect(initials("@neop_recon:hs")).toBe("NR"); // neop + recon
    expect(initials("Mansi Lex")).toBe("ML");
    expect(initials("@mansi:neuraledge.in")).toBe("M");
    expect(initials("")).toBe("?");
  });

  it("is a deterministic, stable color per name", () => {
    expect(colorFor("aria")).toBe(colorFor("aria"));
    expect(colorFor("aria")).not.toBe(colorFor("recon"));
    expect(colorFor("aria")).toMatch(/^hsl\(\d+ 55% 52%\)$/);
  });
});
