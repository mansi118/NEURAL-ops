// Fidelity dashboard model — the product view of the fidelity clock. The fidelity harness publishes a
// per-seat snapshot as an `m.neop.fidelity` event (maturity + agreement_rate_30d + the honest blended/
// human/machine split from shadow.fidelity_breakdown); nc-web reads them and shows the newest per seat.
// Pure parse/reduce; unit-tested; the producer is the live fidelity harness.

export const FIDELITY_TYPE = "m.neop.fidelity";

export type Maturity = "seed" | "growing" | "mature" | "drifted";
const MATURITIES: readonly Maturity[] = ["seed", "growing", "mature", "drifted"];

export interface FidelitySnapshot {
  seat: string;
  maturity: Maturity;
  blended: number | null; // agreement_rate_30d
  humanOnly: number | null;
  machineOnly: number | null;
  scored: number;
  predictions: number;
  ts: number;
}

export interface FidelityEvent {
  eventId: string;
  ts: number;
  content: Record<string, unknown>;
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function int(v: unknown): number {
  return typeof v === "number" && Number.isFinite(v) ? Math.trunc(v) : 0;
}

/** Parse an `m.neop.fidelity` event into a snapshot, or null if there's no seat. */
export function parseFidelity(ev: FidelityEvent): FidelitySnapshot | null {
  const c = ev?.content;
  if (!c || typeof c !== "object") return null;
  const seat = typeof c.seat === "string" ? c.seat : undefined;
  if (!seat) return null;
  const m = c.maturity;
  const maturity = (MATURITIES as readonly unknown[]).includes(m) ? (m as Maturity) : "seed";
  return {
    seat,
    maturity,
    blended: num(c.agreement_rate_30d),
    humanOnly: num(c.human_only),
    machineOnly: num(c.machine_only),
    scored: int(c.n_scored),
    predictions: int(c.shadow_predictions),
    ts: ev.ts,
  };
}

/** Reduce a stream to the newest snapshot per seat, sorted by seat name (deterministic). */
export function latestBySeat(snaps: FidelitySnapshot[]): FidelitySnapshot[] {
  const bySeat = new Map<string, FidelitySnapshot>();
  for (const s of snaps) {
    const cur = bySeat.get(s.seat);
    if (!cur || s.ts >= cur.ts) bySeat.set(s.seat, s);
  }
  return [...bySeat.values()].sort((a, b) => a.seat.localeCompare(b.seat));
}

/** Format an agreement rate (0..1) as a percent, or "—" when unscored. */
export function pct(rate: number | null): string {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`;
}

export function findFidelityRoom<T extends { name: string }>(rooms: T[]): T | undefined {
  return rooms.find((r) => /fidelity|neops/i.test(r.name));
}
