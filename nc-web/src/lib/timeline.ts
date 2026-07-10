// Timeline reducer — pure ordering/dedup/optimistic-echo logic over ChatMessage lists. No sdk, no
// React; the components hold this in state and render it, and it is fully unit-tested.
import type { ChatMessage } from "./messages";

/** Merge incoming messages into an existing list: dedup by eventId (incoming wins), sort by ts then
 *  eventId (stable, deterministic). */
export function mergeMessages(existing: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const byId = new Map<string, ChatMessage>();
  for (const m of existing) byId.set(m.eventId, m);
  for (const m of incoming) byId.set(m.eventId, m);
  return [...byId.values()].sort((a, b) => (a.ts - b.ts) || a.eventId.localeCompare(b.eventId));
}

/** Append a pending optimistic message (kept even though its id is temporary). */
export function addOptimistic(list: ChatMessage[], pending: ChatMessage): ChatMessage[] {
  return mergeMessages(list, [pending]);
}

/** When the server echo (real eventId) arrives, drop the local pending twin and insert the real one. */
export function reconcileOptimistic(list: ChatMessage[], real: ChatMessage, localId: string): ChatMessage[] {
  return mergeMessages(list.filter((m) => m.eventId !== localId), [real]);
}
