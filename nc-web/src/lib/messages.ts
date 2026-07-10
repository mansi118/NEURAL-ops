// Message model — pure parsing of Matrix timeline events into nc-web's ChatMessage. NEops are Matrix
// users under the @neop_* namespace (the bridge's puppets); nc-web renders them as assistants, so the
// model tags them. Kept pure + sdk-free so it's fully unit-tested.

export const NEOP_PREFIX = "@neop_";

export interface ChatMessage {
  eventId: string;
  sender: string;
  displayName: string;
  body: string;
  ts: number;
  isNeop: boolean;
  isSelf: boolean;
  pending?: boolean;
}

// The structural subset of a matrix-js-sdk MatrixEvent that the model reads.
export interface RawEvent {
  getId(): string | undefined;
  getSender(): string | undefined;
  getType(): string;
  getContent(): Record<string, unknown>;
  getTs(): number;
}

export function isNeopUser(userId: string | undefined | null): boolean {
  return typeof userId === "string" && userId.startsWith(NEOP_PREFIX);
}

/** localpart of an mxid → a display name (e.g. @neop_aria:hs → "aria"). */
export function displayNameFor(userId: string): string {
  const m = /^@([^:]+):/.exec(userId);
  const local = m ? m[1] : userId;
  return local.startsWith("neop_") ? local.slice("neop_".length) : local;
}

/** Parse one timeline event → a ChatMessage, or null if it isn't a renderable text message. */
export function parseEvent(ev: RawEvent, selfUserId: string | null): ChatMessage | null {
  if (ev.getType() !== "m.room.message") return null;
  const content = ev.getContent();
  const body = typeof content?.body === "string" ? content.body : undefined;
  const eventId = ev.getId();
  const sender = ev.getSender();
  if (!body || !eventId || !sender) return null;
  return {
    eventId,
    sender,
    displayName: displayNameFor(sender),
    body,
    ts: ev.getTs(),
    isNeop: isNeopUser(sender),
    isSelf: sender === selfUserId,
  };
}

/** Build a local (pending) message for optimistic echo before the server echo arrives. */
export function optimisticMessage(localId: string, sender: string, body: string, ts: number): ChatMessage {
  return {
    eventId: localId,
    sender,
    displayName: displayNameFor(sender),
    body,
    ts,
    isNeop: isNeopUser(sender),
    isSelf: true,
    pending: true,
  };
}
