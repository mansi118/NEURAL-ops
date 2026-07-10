import { describe, it, expect } from "vitest";
import { parseFidelity, latestBySeat, pct, findFidelityRoom, type FidelityEvent } from "./fidelity";

function fe(content: Record<string, unknown>, ts = 1, eventId = "$f"): FidelityEvent {
  return { eventId, ts, content };
}

describe("fidelity model", () => {
  it("parses a snapshot with the honest blended/human/machine split", () => {
    const s = parseFidelity(
      fe({
        seat: "aria",
        maturity: "growing",
        agreement_rate_30d: 0.72,
        human_only: 0.8,
        machine_only: 0.66,
        n_scored: 100,
        shadow_predictions: 140,
      }),
    );
    expect(s).toMatchObject({
      seat: "aria",
      maturity: "growing",
      blended: 0.72,
      humanOnly: 0.8,
      machineOnly: 0.66,
      scored: 100,
      predictions: 140,
    });
  });

  it("defaults unknown maturity to seed and missing rates to null", () => {
    const s = parseFidelity(fe({ seat: "recon", maturity: "bogus" }));
    expect(s?.maturity).toBe("seed");
    expect(s?.blended).toBeNull();
    expect(s?.scored).toBe(0);
  });

  it("returns null without a seat", () => {
    expect(parseFidelity(fe({ maturity: "mature" }))).toBeNull();
  });

  it("keeps the newest snapshot per seat, sorted by seat", () => {
    const snaps = [
      parseFidelity(fe({ seat: "recon", agreement_rate_30d: 0.4 }, 5))!,
      parseFidelity(fe({ seat: "aria", agreement_rate_30d: 0.5 }, 1))!,
      parseFidelity(fe({ seat: "aria", agreement_rate_30d: 0.7 }, 9))!, // newer aria wins
    ];
    const latest = latestBySeat(snaps);
    expect(latest.map((s) => [s.seat, s.blended])).toEqual([
      ["aria", 0.7],
      ["recon", 0.4],
    ]);
  });

  it("formats rates as percent or em-dash", () => {
    expect(pct(0.65)).toBe("65%");
    expect(pct(1)).toBe("100%");
    expect(pct(null)).toBe("—");
  });

  it("finds a fidelity/neops room by name", () => {
    expect(findFidelityRoom([{ name: "chat" }, { name: "neops" }])?.name).toBe("neops");
    expect(findFidelityRoom([{ name: "Fidelity" }])?.name).toBe("Fidelity");
    expect(findFidelityRoom([{ name: "chat" }])).toBeUndefined();
  });
});
