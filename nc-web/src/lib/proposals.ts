// Decision Queue model — the product surface for the intelligence loops. Proposals arrive in a Matrix
// room as `m.neop.proposal` events (posted by the flywheel / vault / governance emit sinks); a human's
// approve/reject is sent back as `m.neop.verdict`. Pure parse/encode; unit-tested; the producers wire in
// when those harnesses deploy.

export const PROPOSAL_TYPE = "m.neop.proposal";
export const VERDICT_TYPE = "m.neop.verdict";

export type ProposalKind = "flywheel" | "vault" | "governance" | "unknown";
export type Verdict = "approve" | "reject";

export interface Proposal {
  id: string;
  kind: ProposalKind;
  title: string;
  detail: string;
  // The NEop whose output/decision this proposal concerns — a verdict on it informs THIS seat's twin
  // (fidelity signal). Producers stamp `seat` on m.neop.proposal; governance falls back to action.seat.
  seat?: string;
}

export interface ProposalEvent {
  eventId: string;
  sender: string;
  ts: number;
  content: Record<string, unknown>;
}

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

function trunc(s: string, n = 80): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/** Normalize an `m.neop.proposal` event into a renderable Proposal, or null if content isn't an object. */
export function parseProposal(ev: ProposalEvent): Proposal | null {
  const c = ev?.content;
  if (!c || typeof c !== "object") return null;
  const id = str(c.proposal_id) ?? ev.eventId;
  const kind = str(c.kind);
  // Originating seat: producers stamp a top-level `seat`; governance carries it on `action.seat`.
  const seat = str(c.seat) ?? str(obj(c.action).seat);
  if (kind === "flywheel") {
    const spec = obj(c.spec);
    const tools = Array.isArray(spec.tools) ? (spec.tools as unknown[]).map(String) : [];
    return {
      id,
      kind: "flywheel",
      title: `New NEop: ${str(spec.neop_id) ?? "?"}`,
      detail: `role ${str(spec.role) ?? "?"} · tools ${tools.join(",") || "—"}`,
      seat,
    };
  }
  if (kind === "vault") {
    const rec = obj(c.record);
    return {
      id,
      kind: "vault",
      title: `Promote memory: ${str(rec.key) ?? id}`,
      detail: `${str(rec.category) ?? "fact"}: ${trunc(str(rec.content) ?? "")}`,
      seat,
    };
  }
  if (kind === "governance") {
    const action = obj(c.action);
    return {
      id,
      kind: "governance",
      title: `Would ${str(c.would) ?? "gate"}: ${str(action.name) ?? "?"}`,
      detail: `${str(action.scope) ?? "?"} · seat ${str(action.seat) ?? "?"}`,
      seat,
    };
  }
  return { id, kind: "unknown", title: str(c.body) ?? "Proposal", detail: str(c.detail) ?? "", seat };
}

/** Encode a human verdict for the `m.neop.verdict` event the harness consumes. `seat` echoes the
 * proposal's originating NEop so the bridge can key the fidelity signal to the right twin without
 * having to remember proposal→seat. `by` is the operator identity. */
export function encodeVerdict(proposalId: string, verdict: Verdict, seat?: string, by?: string): Record<string, unknown> {
  const out: Record<string, unknown> = { proposal_id: proposalId, verdict };
  if (seat) out.seat = seat;
  if (by) out.by = by;
  return out;
}

/** Pick the Decision-Queue room from the room list (name contains "decision"). */
export function findDecisionRoom<T extends { name: string }>(rooms: T[]): T | undefined {
  return rooms.find((r) => /decision/i.test(r.name));
}
