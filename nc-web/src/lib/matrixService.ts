// MatrixService — the typed, testable seam over matrix-js-sdk.
//
// nc-web is a Matrix client on the same rooms as Element (no new backend). This wrapper is the ONLY
// place that touches the sdk, so the app is unit-testable without a homeserver: the sdk client is
// injected as a `ClientFactory`, mocked in tests and the real `createClient` in the app. Typed against
// a minimal structural `MatrixLike` (just the methods we use) so mocks stay trivial and tsc stays honest.

export interface LoginResponse {
  access_token: string;
  user_id: string;
}

export interface RoomSummary {
  roomId: string;
  name: string;
}

// The structural subset of matrix-js-sdk's MatrixClient that nc-web uses. The real createClient
// satisfies this; tests supply a fake.
export interface MatrixLike {
  login(type: string, data: { user: string; password: string }): Promise<LoginResponse>;
  startClient(opts?: { initialSyncLimit?: number }): Promise<void>;
  stopClient(): void;
  getRooms(): RoomSummary[];
  sendTextMessage(roomId: string, body: string): Promise<{ event_id: string }>;
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

  isLoggedIn(): boolean {
    return this.client !== null;
  }

  currentUserId(): string | null {
    return this.userId;
  }
}
