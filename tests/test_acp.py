"""ACP (Flow 7) tests — signed envelopes, router gates ACP-1..4, delegation round-trip,
and the Recon -> Researcher -> Proposal Writer chain. Offline, deterministic. core untouched.
Run: python3 tests/test_acp.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from acp import envelope as E                  # noqa: E402
from acp.router import Router                  # noqa: E402
from acp.chain import run_chain                # noqa: E402
from acp.capabilities import build_registry    # noqa: E402

REG = build_registry(str(R / "agents"))
RING = E.keyring(["coordinator", "recon", "researcher", "proposal-writer", "cortex", "echo"])
AG = str(R / "agents")


def _delegate(frm, to_actor, cap, payload, hop=0, parent=None, conv="c1"):
    to = {"tenant": "neuraledge", "actor": to_actor, "type": "neop"}
    fr = {"tenant": "neuraledge", "actor": frm, "type": "coordinator"}
    return E.sign(E.build(fr, to, "delegate", cap, payload, conversation_id=conv,
                          parent=parent, hop_count=hop), RING[frm][0])


def test_sign_verify():
    env = _delegate("coordinator", "recon", "lead_list", {"text": "hi"})
    assert E.verify(env, RING["coordinator"][1])
    bad = dict(env); bad["payload"] = {"text": "tampered"}
    assert not E.verify(bad, RING["coordinator"][1])
    print("PASS test_sign_verify")


def test_capability_match_and_refuse():
    rt = Router(REG, RING, agents_root=AG)
    ok = rt.route(_delegate("coordinator", "recon", "lead_list", {"text": "leads"}))
    assert ok["intent"] == "inform" and ok["payload"]["neop"] == "recon", ok
    no = rt.route(_delegate("coordinator", "x", "nonesuch", {"text": "x"}))
    assert no["intent"] == "refuse" and "ACP-4" in no["payload"]["reason"], no
    print("PASS test_capability_match_and_refuse")


def test_bad_signature_refused():
    rt = Router(REG, RING, agents_root=AG)
    env = _delegate("coordinator", "recon", "lead_list", {"text": "x"})
    env["payload"] = {"text": "tampered"}          # break the signature
    r = rt.route(env)
    assert r["intent"] == "refuse" and "ACP-1" in r["payload"]["reason"], r
    print("PASS test_bad_signature_refused")


def test_cycle_and_hop():
    rt = Router(REG, RING, agents_root=AG)
    cyc = rt.route(_delegate("coordinator", "recon", "lead_list", {"text": "x"}), visited={"recon"})
    assert cyc["intent"] == "refuse" and "ACP-2" in cyc["payload"]["reason"], cyc
    over = rt.route(_delegate("coordinator", "recon", "lead_list", {"text": "x"}, hop=6))
    assert over["intent"] == "refuse" and "ACP-3" in over["payload"]["reason"], over
    print("PASS test_cycle_and_hop")


def test_roundtrip_identity():
    rt = Router(REG, RING, agents_root=AG)
    r = rt.route(_delegate("coordinator", "recon", "lead_list", {"text": "leads"}))
    assert r["intent"] == "inform" and r["from"]["actor"] == "recon"   # B runs under its own scope
    assert r["parent_envelope_id"] is not None
    assert E.verify(r, RING["recon"][1])                              # response signed by target
    print("PASS test_roundtrip_identity")


def test_chain():
    caps = ["lead_list", "account_research", "proposal_draft"]
    rt = Router(REG, RING, agents_root=AG)
    done = run_chain(caps, "fintech APAC", rt, RING, explicit_intent=True)
    assert done["status"] == "done", done
    assert [h["to"] for h in done["hops"]] == ["recon", "researcher", "proposal-writer"], done
    assert len(done["audit"]) == 3, done                              # chain reconstructable
    ref = run_chain(caps, "x", Router(REG, RING, agents_root=AG), RING, explicit_intent=False)
    assert ref["status"] == "refused" and "COC-5" in ref["reason"], ref  # COC-5 gate
    print("PASS test_chain")


def test_cross_hop_identity_semantic():
    # THE PIN across a delegation: A (coordinator) delegates to B (cortex). B must run
    # under its OWN seat — its memory keys on cortex, NOT the coordinator. A rides as requester.
    rt = Router(REG, RING, agents_root=AG)
    r = rt.route(_delegate("coordinator", "cortex", "cortex_answer", {"text": "what embeddings"}))
    assert r["intent"] == "inform", r
    assert r["payload"]["seat"] == "cortex", r                       # B ran under its own seat
    assert r["payload"]["requester"] == "coordinator", r            # A rides as attribution only
    assert r["payload"]["memory_authors"] == ["cortex"], r          # memory keyed on B...
    assert "coordinator" not in r["payload"]["memory_authors"], r    # ...NOT on A (no cross-wire)
    # refuse is a structured, signed envelope (not an exception)
    bad = rt.route(_delegate("coordinator", "x", "nonesuch", {"text": "x"}))
    assert bad["intent"] == "refuse" and bad["acp_version"] == "1.0" and bad["envelope_id"], bad
    print("PASS test_cross_hop_identity_semantic")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL ACP TESTS PASS")
