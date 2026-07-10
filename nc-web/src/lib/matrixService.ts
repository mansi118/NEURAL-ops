// MatrixService — the typed, testable seam over matrix-js-sdk.
//
// nc-web is a Matrix client on the same rooms as Element (no new backend). This wrapper is the ONLY
// place that touches the sdk, so the app is unit-testable without a homeserver: the sdk client is
// injected as a `ClientFactory`, mocked in tests and the real `createClient` in the app. Typed against
// a minimal structural `MatrixLike` (just the methods we use) so mocks stay trivial and tsc stays honest.

import { parseEvent, type RawEvent, type ChatMessage } from "./messages";

export type { RawEvent, ChatMessage } from "./messages";

export interface LoginResponse {
  access_token: string;
  user_id: string;
}

export interface RoomSummary {
  roomId: string;
  name: string;
}

export interface RoomLike {
  roomId: string;
  name: string;
  getLiveTimeline(): { getEvents(): RawEvent[] };
}

// A matrix-js-sdk Room.timeline listener: (event, room, ...). Typed loosely; the service extracts.
export type TimelineListener = (event: RawEvent, room: { roomId: string } | undefined) => void;

// The structural subset of matrix-js-sdk's MatrixClient that nc-web uses. The real createClient
// satisfies this; tests supply a fake.
export interface MatrixLike {
  login(type: string, data: { user: string; password: string }): Promise<LoginResponse>;
  startClient(opts?: { initialSyncLimit?: number }): Promise<void>;
  stopClient(): void;
  getRooms(): RoomSummary[];
  getRoom(roomId: string): RoomLike | null;
  sendTextMessage(roomId: string, body: string): Promise<{ event_id: string }>;
  sendEvent(
    roomId: string,
    eventType: string,
    content: Record<string, unknown>,
  ): Promise<{ event_id: string }>;
  on(event: string, listener: TimelineListener): void;
  off(event: string, listener: TimelineListener): void;
}

export interface TypedEvent {
  eventId: string;
  sender: string;
  ts: number;
  content: Record<string, unknown>;
}

export interface ClientFactoryOpts {
  baseUrl: string;
  accessToken?: string;
  userId?: string;
}

export type ClientFactory = (opts: ClientFactoryOpts) => MatrixLike;

export class NotLoggedInError extends Error {
  constructor() {
    super("MatrixService: not logged in");
    this.name = "NotLoggedInError";
  }
}

export class MatrixService {
  private client: MatrixLike | null = null;
  private userId: string | null = null;

  constructor(
    private readonly baseUrl: string,
    private readonly factory: ClientFactory,
  ) {}

  /** Password login → an authenticated client. Returns the resolved user id. */
  async login(user: string, password: string): Promise<{ userId: string }> {
    const anon = this.factory({ baseUrl: this.baseUrl });
    const res = await anon.login("m.login.password", { user, password });
    this.client = this.factory({
      baseUrl: this.baseUrl,
      accessToken: res.access_token,
      userId: res.user_id,
    });
    this.userId = res.user_id;
    return { userId: res.user_id };
  }

  private require(): MatrixLike {
    if (!this.client) throw new NotLoggedInError();
    return this.client;
  }

  async start(): Promise<void> {
    await this.require().startClient({ initialSyncLimit: 20 });
  }

  stop(): void {
    this.client?.stopClient();
  }

  rooms(): RoomSummary[] {
    return this.require().getRooms().map((r) => ({ roomId: r.roomId, name: r.name }));
  }

  async send(roomId: string, body: string): Promise<string> {
    const res = await this.require().sendTextMessage(roomId, body);
    return res.event_id;
  }

  /** Current text messages in a room's live timeline, parsed + filtered to renderable ones. */
  roomMessages(roomId: string): ChatMessage[] {
    const room = this.require().getRoom(roomId);
    if (!room) return [];
    const out: ChatMessage[] = [];
    for (const ev of room.getLiveTimeline().getEvents()) {
      const msg = parseEvent(ev, this.userId);
      if (msg) out.push(msg);
    }
    return out;
  }

  /** Custom-typed events in a room's live timeline (e.g. m.neop.proposal) → raw content. */
  roomEventsOfType(roomId: string, eventType: string): TypedEvent[] {
    const room = this.require().getRoom(roomId);
    if (!room) return [];
    const out: TypedEvent[] = [];
    for (const ev of room.getLiveTimeline().getEvents()) {
      if (ev.getType() !== eventType) continue;
      const eventId = ev.getId();
      const sender = ev.getSender();
      if (!eventId || !sender) continue;
      out.push({ eventId, sender, ts: ev.getTs(), content: ev.getContent() });
    }
    return out;
  }

  /** Send a custom-typed event (e.g. m.neop.verdict) → the event id. */
  async sendEvent(roomId: string, eventType: string, content: Record<string, unknown>): Promise<string> {
    const res = await this.require().sendEvent(roomId, eventType, content);
    return res.event_id;
  }

  /** Subscribe to new timeline messages across rooms. Returns an unsubscribe fn. */
  subscribeMessages(cb: (roomId: string, msg: ChatMessage) => void): () => void {
    const client = this.require();
    const listener: TimelineListener = (event, room) => {
      const msg = parseEvent(event, this.userId);
      if (msg && room?.roomId) cb(room.roomId, msg);
    };
    client.on("Room.timeline", listener);
    return () => client.off("Room.timeline", listener);
  }

  isLoggedIn(): boolean {
    return this.client !== null;
  }

  currentUserId(): string | null {
    return this.userId;
  }
}
