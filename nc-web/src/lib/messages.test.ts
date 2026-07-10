import { describe, it, expect } from "vitest";
import {
  parseEvent,
  isNeopUser,
  displayNameFor,
  optimisticMessage,
  type RawEvent,
} from "./messages";

interface EvOpts {
  id?: string;
  sender?: string;
  type?: string;
  body?: string;
  ts?: number;
}

function ev(opts: EvOpts): RawEvent {
  return {
    getId: () => opts.id ?? "$e1",
    getSender: () => opts.sender ?? "@u:hs",
    getType: () => opts.type ?? "m.room.message",
    getContent: () => ({ body: opts.body }),
    getTs: () => opts.ts ?? 10,
  };
}

describe("messages model", () => {
  it("flags @neop_* users as NEops", () => {
    expect(isNeopUser("@neop_aria:hs")).toBe(true);
    expect(isNeopUser("@mansi:hs")).toBe(false);
    expect(isNeopUser(null)).toBe(false);
  });

  it("derives a display name, stripping the neop_ prefix", () => {
    expect(displayNameFor("@neop_recon:neuraledge.in")).toBe("recon");
    expect(displayNameFor("@mansi:hs")).toBe("mansi");
  });

  it("parses a text message with self + neop tagging", () => {
    const m = parseEvent(ev({ id: "$x", sender: "@neop_aria:hs", body: "hello", ts: 42 }), "@me:hs");
    expect(m).toMatchObject({
      eventId: "$x",
      displayName: "aria",
      body: "hello",
      ts: 42,
      isNeop: true,
      isSelf: false,
    });
    expect(parseEvent(ev({ sender: "@me:hs", body: "hi" }), "@me:hs")?.isSelf).toBe(true);
  });

  it("ignores non-message and bodiless events", () => {
    expect(parseEvent(ev({ type: "m.reaction", body: "x" }), null)).toBeNull();
    expect(parseEvent(ev({ body: undefined }), null)).toBeNull();
  });

  it("builds a pending optimistic self-message", () => {
    const m = optimisticMessage("~local-1", "@me:hs", "sending", 99);
    expect(m).toMatchObject({ eventId: "~local-1", isSelf: true, pending: true, body: "sending" });
  });
});
