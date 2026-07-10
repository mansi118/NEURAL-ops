import { useMemo } from "react";
import type { MatrixService } from "../lib/matrixService";
import {
  FIDELITY_TYPE,
  parseFidelity,
  latestBySeat,
  pct,
  type FidelitySnapshot,
} from "../lib/fidelity";
import { colorFor, initials } from "../lib/avatar";

// Fidelity dashboard (PR-E): per-seat maturity + agreement_rate_30d, with the honest blended vs human
// split. Reads m.neop.fidelity events from the ops room (reusing the roomEventsOfType seam), newest per
// seat. Renders empty until the live fidelity harness publishes. Parse/reduce live in the tested module.
export default function FidelityDashboard({ svc, roomId }: { svc: MatrixService; roomId: string | null }) {
  const seats = useMemo<FidelitySnapshot[]>(() => {
    if (!roomId) return [];
    const parsed = svc
      .roomEventsOfType(roomId, FIDELITY_TYPE)
      .map((ev) => parseFidelity({ eventId: ev.eventId, ts: ev.ts, content: ev.content }))
      .filter((s): s is FidelitySnapshot => s !== null);
    return latestBySeat(parsed);
  }, [svc, roomId]);

  if (!roomId) {
    return <p className="nc-empty">No ops room. Fidelity appears here once the harness publishes snapshots.</p>;
  }
  if (seats.length === 0) {
    return <p className="nc-empty">No fidelity snapshots yet.</p>;
  }

  return (
    <div className="nc-fidelity">
      {seats.map((s) => (
        <article key={s.seat} className="nc-seat-card">
          <header>
            <span className="nc-avatar" style={{ background: colorFor(s.seat) }} aria-hidden>
              {initials(s.seat)}
            </span>
            <span className="nc-seat-name">{s.seat}</span>
            <span className={"nc-maturity nc-maturity-" + s.maturity}>{s.maturity}</span>
          </header>
          <div className="nc-fidelity-rate">
            <div className="nc-bar">
              <div className="nc-bar-fill" style={{ width: s.blended === null ? "0%" : pct(s.blended) }} />
            </div>
            <span className="nc-rate-label">{pct(s.blended)} agreement (30d)</span>
          </div>
          <dl className="nc-fidelity-meta">
            <div>
              <dt>human</dt>
              <dd>{pct(s.humanOnly)}</dd>
            </div>
            <div>
              <dt>machine</dt>
              <dd>{pct(s.machineOnly)}</dd>
            </div>
            <div>
              <dt>scored</dt>
              <dd>{s.scored}</dd>
            </div>
            <div>
              <dt>predictions</dt>
              <dd>{s.predictions}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}
