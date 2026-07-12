import { describe, it, expect } from "vitest";
import {
  parseProposal,
  encodeVerdict,
  findDecisionRoom,
  type ProposalEvent,
} from "./proposals";

function pe(content: Record<string, unknown>, eventId = "$e"): ProposalEvent {
  return { eventId, sender: "@neos-bot:hs", ts: 1, content };
}

describe("proposals model", () => {
  it("parses a flywheel NEop-spec proposal", () => {
    const p = parseProposal(
      pe({
        kind: "flywheel",
        proposal_id: "recon|scrape",
        spec: { neop_id: "recon-auto", role: "reactive", tools: ["scrape", "summarize"] },
      }),
    );
    expect(p).toMatchObject({
      id: "recon|scrape",
      kind: "flywheel",
      title: "New NEop: recon-auto",
      detail: "role reactive · tools scrape,summarize",
    });
  });

  it("parses a vault promotion proposal (truncating content)", () => {
    const p = parseProposal(
      pe({ kind: "vault", record: { key: "e1", category: "fact", content: "NordMarine is an ICP" } }),
    );
    expect(p).toMatchObject({ kind: "vault", title: "Promote memory: e1" });
    expect(p?.detail).toContain("fact:");
  });

  it("parses a governance would-block proposal", () => {
    const p = parseProposal(
      pe({ kind: "governance", would: "deny", action: { scope: "tool", name: "bash", seat: "aria" } }),
    );
    expect(p).toMatchObject({ kind: "governance", title: "Would deny: bash", detail: "tool · seat aria" });
  });

  it("falls back to unknown kind and uses body/eventId", () => {
    const p = parseProposal(pe({ body: "something" }, "$fallback"));
    expect(p).toMatchObject({ id: "$fallback", kind: "unknown", title: "something" });
  });

  it("encodes a verdict with optional seat + author", () => {
    expect(encodeVerdict("p1", "approve", "aria", "@mansi:hs")).toEqual({
      proposal_id: "p1",
      verdict: "approve",
      seat: "aria",
      by: "@mansi:hs",
    });
    // seat echoes the proposal's originating NEop so the bridge can key the fidelity signal
    expect(encodeVerdict("p1", "reject", "recon")).toEqual({
      proposal_id: "p1",
      verdict: "reject",
      seat: "recon",
    });
    expect(encodeVerdict("p1", "reject")).toEqual({ proposal_id: "p1", verdict: "reject" });
  });

  it("parseProposal carries the originating seat (top-level or governance action.seat)", () => {
    expect(parseProposal(pe({ kind: "vault", seat: "aria", record: { key: "k" } }))?.seat).toBe("aria");
    expect(parseProposal(pe({ kind: "governance", action: { name: "send", seat: "recon" } }))?.seat).toBe("recon");
  });

  it("finds the decision room by name", () => {
    const rooms = [{ name: "bar1a-echo" }, { name: "Decision Queue" }];
    expect(findDecisionRoom(rooms)?.name).toBe("Decision Queue");
    expect(findDecisionRoom([{ name: "chat" }])).toBeUndefined();
  });
});
