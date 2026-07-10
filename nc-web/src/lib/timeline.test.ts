import { describe, it, expect } from "vitest";
import { mergeMessages, addOptimistic, reconcileOptimistic } from "./timeline";
import type { ChatMessage } from "./messages";

function msg(eventId: string, ts: number, body = "b", extra: Partial<ChatMessage> = {}): ChatMessage {
  return { eventId, sender: "@u:hs", displayName: "u", body, ts, isNeop: false, isSelf: false, ...extra };
}

describe("timeline reducer", () => {
  it("dedups by eventId (incoming wins) and sorts by ts then id", () => {
    const out = mergeMessages(
      [msg("$b", 2), msg("$a", 1)],
      [msg("$a", 1, "edited"), msg("$c", 2)],
    );
    expect(out.map((m) => m.eventId)).toEqual(["$a", "$b", "$c"]); // ts asc, tie $b/$c broken by id
    expect(out.find((m) => m.eventId === "$a")?.body).toBe("edited");
  });

  it("addOptimistic appends a pending message", () => {
    const out = addOptimistic([msg("$a", 1)], msg("~local-1", 2, "sending", { pending: true }));
    expect(out.map((m) => m.eventId)).toEqual(["$a", "~local-1"]);
    expect(out[1].pending).toBe(true);
  });

  it("reconcileOptimistic replaces the local twin with the server echo", () => {
    const withPending = addOptimistic([msg("$a", 1)], msg("~local-1", 2, "sending", { pending: true }));
    const out = reconcileOptimistic(withPending, msg("$real", 2, "sending"), "~local-1");
    expect(out.map((m) => m.eventId)).toEqual(["$a", "$real"]);
    expect(out.some((m) => m.eventId === "~local-1")).toBe(false);
    expect(out.some((m) => m.pending)).toBe(false);
  });
});
