import { describe, it, expect } from "vitest";
import { formatClock, formatTs } from "./time";

describe("time", () => {
  it("formats a Date as a zero-padded 24h clock", () => {
    expect(formatClock(new Date(2026, 0, 1, 9, 5))).toBe("09:05");
    expect(formatClock(new Date(2026, 0, 1, 23, 59))).toBe("23:59");
    expect(formatClock(new Date(2026, 0, 1, 0, 0))).toBe("00:00");
  });

  it("formatTs round-trips through Date", () => {
    const ts = new Date(2026, 5, 10, 14, 30).getTime();
    expect(formatTs(ts)).toBe("14:30");
  });
});
