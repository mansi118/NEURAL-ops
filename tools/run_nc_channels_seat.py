#!/usr/bin/env python3
"""nc-channels SEAT runner — reflect=False: forward each Matrix message to the Hermes seat wrapper (B-fwd).

SIBLING of run_nc_channels_bar1a.py (reflect=True, the Bar 1a transport ECHO) — NOT a replacement. Bar 1a
still uses the echo runner and is still an owed box proof; run the echo first to prove the transport in
isolation, THEN switch to this runner to layer the seam on (so a reflect=False failure is definitely seam,
not transport). This runner is Bar 1b/2: it forwards to pi-neop-runtime's `POST /seat/turn` and renders the
returned ReplyEnvelope back into the room.

FAIL-CLOSED at boot: refuses to start without BOTH SEAT_URL and FORWARD_TOKEN (the bridge→seat trust seam —
never a naked, unauthenticated forward), surfacing _seat_forward's per-call guards early. FORWARD_TOKEN MUST
equal the value the Hermes wrapper expects — a mismatch is a 403 at the forward→wrapper hop.

Requires (env): the AS registration vars (as bar1a) + HS_BASE_URL + SEAT_URL + FORWARD_TOKEN.
This is a LIVE NEop reply (Bar 1b/2). Run it only AFTER: Bar 1a (transport) is proven, and the Hermes seat's
box proofs are green (A2 injection-resistance, B GAP-1 ranked) and the wrapper is T9-acked. Box-side, yours.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nc_channels.service import ASRegistration, ASService


def _req(name: str) -> str:
    v = os.environ.get(name, "")
    if not v.strip():
        sys.stderr.write(f"FATAL: env {name} is required and blank — refusing to start (fail-closed)\n")
        raise SystemExit(2)
    return v


def _registration() -> ASRegistration:
    return ASRegistration(
        id=os.environ.get("AS_ID", "neos-nc-channels-neuraledge"),
        url=_req("AS_URL"),
        tenant=os.environ.get("AS_TENANT", "neuraledge"),
        sender_localpart=os.environ.get("AS_SENDER", "neos-bot"),
        user_namespace_regex=_req("AS_USER_REGEX"),   # @neop_.*:neuraledge\.in (delegated server_name, #85)
        as_token=_req("AS_TOKEN"),
        hs_token=_req("HS_TOKEN"),
        adapter_hmac_key=os.environ.get("AS_HMAC_KEY", "seat-forward-unused"),
        server_name=os.environ.get("AS_SERVER_NAME", "neuraledge.in"),
    )


def _no_inprocess(*_a, **_k):
    # reflect=False forwards to Hermes; the in-process Python handle must NEVER run (core.py raises on live).
    raise NotImplementedError("nc-channels seat runner forwards to Hermes; the in-process handle is not wired")


def main() -> None:
    reg = _registration()
    # FAIL-CLOSED at boot: both required, or refuse — mirrors _seat_forward's guards, surfaced early so a
    # misconfigured bridge fails fast rather than at the first message.
    seat_url = _req("SEAT_URL")            # the Hermes POST /seat/turn endpoint
    forward_token = _req("FORWARD_TOKEN")  # bridge→seat shared secret — MUST match the wrapper's FORWARD_TOKEN
    svc = ASService(
        reg, handle=_no_inprocess, classifier=None,
        hs_base_url=os.environ.get("HS_BASE_URL", "http://localhost:8008"),
        seat_url=seat_url, forward_token=forward_token)
    host = os.environ.get("LISTEN_HOST", "127.0.0.1")
    port = int(os.environ.get("LISTEN_PORT", "8010"))
    sys.stderr.write(
        f"nc-channels SEAT runner on {host}:{port} (reflect=False) → Hermes {seat_url}, HS {svc.hs_base_url}\n")
    svc.serve(host, port, reflect=False)


if __name__ == "__main__":
    main()
