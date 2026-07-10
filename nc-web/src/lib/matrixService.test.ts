import { describe, it, expect, vi } from "vitest";
import {
  MatrixService,
  NotLoggedInError,
  type MatrixLike,
  type ClientFactory,
  type TimelineListener,
  type RawEvent,
} from "./matrixService";

function rawMessage(id: string, sender: string, body: string, ts = 1): RawEvent {
  return {
    getId: () => id,
    getSender: () => sender,
    getType: () => "m.room.message",
    getContent: () => ({ body, msgtype: "m.text" }),
    getTs: () => ts,
  };
}

// A fake MatrixLike client + a factory that records how it was constructed, so we can assert the
// service authenticates and threads the token without any real homeserver.
function makeFake() {
  const calls: { opts: unknown }[] = [];
  const rooms = [
    { roomId: "!a:hs", name: "bar1a-echo" },
    { roomId: "!b:hs", name: "Recon" },
  ];
  const timelines: Record<string, RawEvent[]> = {
    "!a:hs": [rawMessage("$1", "@mansi:hs", "hi", 1), rawMessage("$2", "@neop_aria:hs", "hello", 2)],
  };
  const sent: { roomId: string; body: string }[] = [];
  const listeners: TimelineListener[] = [];
  const client: MatrixLike = {
    login: vi.fn(async (_type, data) => ({
      access_token: `tok-${data.user}`,
      user_id: `@${data.user}:neuraledge.in`,
    })),
    startClient: vi.fn(async () => {}),
    stopClient: vi.fn(() => {}),
    getRooms: vi.fn(() => rooms),
    getRoom: vi.fn((roomId: string) =>
      timelines[roomId]
        ? { roomId, name: roomId, getLiveTimeline: () => ({ getEvents: () => timelines[roomId] }) }
        : null,
    ),
    sendTextMessage: vi.fn(async (roomId, body) => {
      sent.push({ roomId, body });
      return { event_id: `$evt-${sent.length}` };
    }),
    on: vi.fn((_e: string, l: TimelineListener) => listeners.push(l)),
    off: vi.fn((_e: string, l: TimelineListener) => {
      const i = listeners.indexOf(l);
      if (i >= 0) listeners.splice(i, 1);
    }),
  };
  const factory: ClientFactory = (opts) => {
    calls.push({ opts });
    return client;
  };
  const emit = (roomId: string, ev: RawEvent) => listeners.forEach((l) => l(ev, { roomId }));
  return { factory, client, calls, sent, listeners, emit };
}

describe("MatrixService", () => {
  it("logs in and threads the access token into a second client", async () => {
    const { factory, calls } = makeFake();
    const svc = new MatrixService("https://matrix.neuraledge.in", factory);
    const { userId } = await svc.login("aria", "pw");
    expect(userId).toBe("@aria:neuraledge.in");
    expect(svc.isLoggedIn()).toBe(true);
    expect(svc.currentUserId()).toBe("@aria:neuraledge.in");
    // anon client (no token) then authenticated client (with token)
    expect(calls).toHaveLength(2);
    expect((calls[0].opts as { accessToken?: string }).accessToken).toBeUndefined();
    expect((calls[1].opts as { accessToken?: string }).accessToken).toBe("tok-aria");
  });

  it("lists rooms as summaries after login", async () => {
    const { factory } = makeFake();
    const svc = new MatrixService("https://hs", factory);
    await svc.login("u", "pw");
    await svc.start();
    expect(svc.rooms().map((r) => r.name)).toEqual(["bar1a-echo", "Recon"]);
  });

  it("sends a message and returns the event id", async () => {
    const { factory, sent } = makeFake();
    const svc = new MatrixService("https://hs", factory);
    await svc.login("u", "pw");
    const evt = await svc.send("!a:hs", "hello");
    expect(evt).toBe("$evt-1");
    expect(sent).toEqual([{ roomId: "!a:hs", body: "hello" }]);
  });

  it("throws NotLoggedInError before login", () => {
    const { factory } = makeFake();
    const svc = new MatrixService("https://hs", factory);
    expect(() => svc.rooms()).toThrow(NotLoggedInError);
  });

  it("reads a room's timeline as parsed ChatMessages with NEop + self tagging", async () => {
    const { factory } = makeFake();
    const svc = new MatrixService("https://hs", factory);
    await svc.login("mansi", "pw"); // self = @mansi:neuraledge.in (not the timeline's @mansi:hs)
    const msgs = svc.roomMessages("!a:hs");
    expect(msgs.map((m) => [m.body, m.isNeop])).toEqual([
      ["hi", false],
      ["hello", true],
    ]);
    expect(svc.roomMessages("!missing:hs")).toEqual([]);
  });

  it("subscribes to new timeline messages and unsubscribes cleanly", async () => {
    const { factory, emit, listeners } = makeFake();
    const svc = new MatrixService("https://hs", factory);
    await svc.login("u", "pw");
    const got: string[] = [];
    const unsub = svc.subscribeMessages((roomId, msg) => got.push(`${roomId}:${msg.body}`));
    emit("!a:hs", rawMessage("$new", "@neop_recon:hs", "scanning", 5));
    expect(got).toEqual(["!a:hs:scanning"]);
    unsub();
    expect(listeners).toHaveLength(0);
    emit("!a:hs", rawMessage("$after", "@u:hs", "ignored", 6));
    expect(got).toEqual(["!a:hs:scanning"]); // no delivery after unsubscribe
  });
});
