import { useMemo, useState } from "react";
import type { MatrixService } from "../lib/matrixService";
import {
  PROPOSAL_TYPE,
  VERDICT_TYPE,
  parseProposal,
  encodeVerdict,
  type Proposal,
  type Verdict,
} from "../lib/proposals";

// Decision Queue panel (PR-D): renders m.neop.proposal events from the decision room as cards and
// sends the human verdict back as m.neop.verdict. Parse/encode live in the tested pure module; this
// is the thin view. Renders empty until the producer harnesses (flywheel/vault/governance) post.
export default function DecisionQueue({ svc, roomId }: { svc: MatrixService; roomId: string | null }) {
  const proposals = useMemo<Proposal[]>(() => {
    if (!roomId) return [];
    return svc
      .roomEventsOfType(roomId, PROPOSAL_TYPE)
      .map(parseProposal)
      .filter((p): p is Proposal => p !== null);
  }, [svc, roomId]);

  const [resolved, setResolved] = useState<Record<string, Verdict>>({});

  async function decide(p: Proposal, verdict: Verdict) {
    if (!roomId) return;
    setResolved((r) => ({ ...r, [p.id]: verdict })); // optimistic
    try {
      await svc.sendEvent(roomId, VERDICT_TYPE, encodeVerdict(p.id, verdict, p.seat, svc.currentUserId() ?? undefined));
    } catch {
      setResolved((r) => {
        const next = { ...r };
        delete next[p.id];
        return next;
      });
    }
  }

  if (!roomId) {
    return <p className="nc-empty">No Decision Queue room. Proposals appear here once a decision room exists.</p>;
  }
  if (proposals.length === 0) {
    return <p className="nc-empty">Queue is clear — no proposals awaiting review.</p>;
  }

  return (
    <ul className="nc-queue">
      {proposals.map((p) => {
        const verdict = resolved[p.id];
        return (
          <li key={p.id} className={"nc-proposal" + (verdict ? " resolved" : "")}>
            <div className="nc-proposal-main">
              <span className={"nc-kind nc-kind-" + p.kind}>{p.kind}</span>
              <div>
                <div className="nc-proposal-title">{p.title}</div>
                <div className="nc-proposal-detail">{p.detail}</div>
              </div>
            </div>
            {verdict ? (
              <span className={"nc-verdict " + verdict}>{verdict === "approve" ? "Approved" : "Rejected"}</span>
            ) : (
              <div className="nc-proposal-actions">
                <button className="approve" onClick={() => decide(p, "approve")}>
                  Approve
                </button>
                <button className="reject" onClick={() => decide(p, "reject")}>
                  Reject
                </button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
