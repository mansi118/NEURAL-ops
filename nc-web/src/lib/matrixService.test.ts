import { describe, it, expect, vi } from "vitest";
import { MatrixService, NotLoggedInError, type MatrixLike, type ClientFactory } from "./matrixService";

// A fake MatrixLike client + a factory that records how it was constructed, so we can assert the
// service authenticates and threads the token without any real homeserver.
function makeFake() {
  const calls: { opts: unknown }[] = [];
  const rooms = [
    { roomId: "!a:hs", name: "bar1a-echo" },
    { roomId: "!b:hs", name: "Recon" },
  ];
  const sent: { roomId: string; body: string }[] = [];
  const client: MatrixLike = {
    login: vi.fn(async (_type, data) => ({
      access_token: `tok-${data.user}`,
      user_id: `@${data.user}:neuraledge.in`,
    })),
    startClient: vi.fn(async () => {}),
    stopClient: vi.fn(() => {}),
    getRooms: vi.fn(() => rooms),
    sendTextMessage: vi.fn(async (roomId, body) => {
      sent.push({ roomId, body });
      return { event_id: `$evt-${sent.length}` };
    }),
  };
  const factory: ClientFactory = (opts) => {
    calls.push({ opts });
    return client;
  };
  return { factory, client, calls, sent };
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
});
